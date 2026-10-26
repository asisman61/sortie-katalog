"""Sortie katalog otomasyonu: feed -> tasarımlı görseller -> Meta ek feed'i.

Her çalıştırmada yalnızca değişen ürünler yeniden üretilir. Çıktı klasörü (site/)
GitHub Pages'te yayınlanır; Meta ek feed'i site/feed/supplemental.csv dosyasıdır.

Kullanım:
  FEED_URL=... BASE_URL=https://kullanici.github.io/depo python src/pipeline.py
  python src/pipeline.py --feed-file feed.xml --limit 20      # yerel deneme
"""
import os
os.environ.setdefault('OPENCV_LOG_LEVEL', 'ERROR')

import argparse, csv, hashlib, io, json, shutil, sys, time, urllib.parse, urllib.request
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feed, render
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {'User-Agent': 'Mozilla/5.0 (SortieKatalog/1.0)'}
SRC_MAX = 1800  # kaynak fotoğraflar önbellekte bu boyuta küçültülür


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def fetch(url, timeout=60, tries=3):
    q = urllib.parse.quote(url, safe=':/%?=&')
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(q, headers=UA), timeout=timeout).read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def src_path(cache, url):
    return os.path.join(cache, 'src', hashlib.sha1(url.encode()).hexdigest()[:20] + '.jpg')


def download_src(job):
    url, path = job
    if os.path.exists(path):
        return True
    try:
        im = Image.open(io.BytesIO(fetch(url))).convert('RGB')
        im.thumbnail((SRC_MAX, SRC_MAX), Image.LANCZOS)
        tmp = path + '.part'
        im.save(tmp, 'JPEG', quality=92)
        os.replace(tmp, path)
        return True
    except Exception as e:
        log('  görsel indirilemedi:', url, '-', e)
        return False


def product_key(p, umbrella):
    """Görseli etkileyen her şeyin parmak izi; değişmezse görsel yeniden üretilmez."""
    b = render.badges(p)
    parts = [render.RENDER_VERSION, render.style_for(p), p['title'], p['color'], p['type'],
             p['price'], p['sale'], p['discount'], p['new_season'], p['in_stock'], p['sizes'],
             p['images'], umbrella if b.get('camp') == 'end' else None]
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def render_one(args):
    p, files, out_dir, quality, umbrella = args
    render.UMBRELLA_MAX = umbrella
    style = render.style_for(p)
    try:
        for fmt, suffix in (('square', ''), ('story', '_story')):
            im = render.render(p, style, fmt, files)
            if im is None:
                return p['group_id'], 'görsel yok'
            tmp = os.path.join(out_dir, f"{p['group_id']}{suffix}.jpg.part")
            im.save(tmp, 'JPEG', quality=quality, optimize=True, progressive=True)
            os.replace(tmp, tmp[:-5])
        return p['group_id'], None
    except Exception as e:
        return p['group_id'], f'{type(e).__name__}: {e}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--feed-url', default=os.environ.get('FEED_URL'))
    ap.add_argument('--feed-file')
    ap.add_argument('--base-url', default=os.environ.get('BASE_URL', '').rstrip('/'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'site'))
    ap.add_argument('--cache', default=os.path.join(ROOT, 'cache'))
    ap.add_argument('--limit', type=int, default=0, help='deneme için ilk N ürün grubu')
    ap.add_argument('--workers', type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, 'config.json'), encoding='utf-8'))
    t0 = time.time()

    os.makedirs(os.path.join(a.cache, 'src'), exist_ok=True)
    img_dir = os.path.join(a.out, 'img'); os.makedirs(img_dir, exist_ok=True)
    os.makedirs(os.path.join(a.out, 'feed'), exist_ok=True)

    # 1) feed
    feed_path = a.feed_file or os.path.join(a.cache, 'feed.xml')
    if not a.feed_file:
        if not a.feed_url:
            sys.exit('FEED_URL tanımlı değil (GitHub > Settings > Secrets > FEED_URL).')
        data = fetch(a.feed_url, timeout=180)
        if len(data) < 1000 or b'<entry' not in data:
            sys.exit('Feed boş ya da bozuk geldi; önceki görseller korunuyor.')
        open(feed_path, 'wb').write(data)
    products = feed.load(feed_path)
    live = [p for p in products if p['in_stock'] and p['images']]
    if a.limit:
        live = live[:a.limit]
    umbrella = max((p['discount'] for p in products if p['in_stock'] and not p['new_season']), default=0) or None
    render.UMBRELLA_MAX = umbrella
    log(f'feed: {len(products)} grup, stokta {len(live)}; sezon sonu en yüksek indirim: %{umbrella}')

    # 2) hangi ürünler değişti
    man_path = os.path.join(a.out, 'manifest.json')
    try:
        manifest = json.load(open(man_path))
    except Exception:
        manifest = {}
    n_src = cfg.get('source_images_per_product', 5)
    todo = []
    for p in live:
        k = product_key(p, umbrella)
        have = os.path.exists(os.path.join(img_dir, p['group_id'] + '.jpg'))
        if manifest.get(p['group_id'], {}).get('key') != k or not have:
            todo.append((p, k))
    log(f'yeniden üretilecek: {len(todo)} grup')

    # 3) kaynak fotoğraflar (önbellekli)
    jobs = {(u, src_path(a.cache, u)) for p, _ in todo for u in p['images'][:n_src]}
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(download_src, sorted(jobs)))

    # 4) üretim
    errors = {}
    no_photo = []
    args = []
    for p, k in todo:
        files = [src_path(a.cache, u) for u in p['images'][:n_src] if os.path.exists(src_path(a.cache, u))]
        args.append((p, files, img_dir, cfg.get('jpeg_quality', 88), umbrella))
    keys = dict((p['group_id'], k) for p, k in todo)
    done = 0
    with ProcessPoolExecutor(a.workers) as ex:
        for gid, err in ex.map(render_one, args, chunksize=4):
            done += 1
            if err == 'görsel yok':
                # kullanılabilir fotoğrafı yok (ör. yalnızca ölçü tablosu): eski görseli
                # de kaldır ki ek feed'e girmesin; Meta ana feed'deki görseli kullanır
                no_photo.append(gid)
                manifest.pop(gid, None)
                for suf in ('', '_story'):
                    f = os.path.join(img_dir, gid + suf + '.jpg')
                    if os.path.exists(f):
                        os.remove(f)
            elif err:
                errors[gid] = err
            else:
                manifest[gid] = {'key': keys[gid], 'at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
            if done % 50 == 0:
                log(f'  {done}/{len(args)}')
    for gid, err in errors.items():
        log('  HATA', gid, err)
    if no_photo:
        log('  kullanılabilir fotoğrafı olmayan ürünler (atlandı):', ', '.join(no_photo))

    # 5) feed'den düşen ürünlerin görsellerini temizle
    live_ids = {p['group_id'] for p in live}
    if not a.limit:
        for gid in list(manifest):
            if gid not in live_ids:
                manifest.pop(gid)
                for suf in ('', '_story'):
                    f = os.path.join(img_dir, gid + suf + '.jpg')
                    if os.path.exists(f):
                        os.remove(f)

    # 6) Meta ek feed'i: varyant id -> tasarımlı görsel
    rollout = set(cfg.get('rollout', ['end']))
    base = a.base_url or '.'
    rows, story_rows, per_camp = [], [], {}
    for p in live:
        gid = p['group_id']
        if gid not in manifest:
            continue
        camp = render.badges(p).get('camp') or 'none'
        per_camp[camp] = per_camp.get(camp, 0) + 1
        if camp not in rollout:
            continue
        v = manifest[gid]['key'][:8]  # adres değişsin ki Meta yeni görseli çeksin
        for vid in p['ids']:
            rows.append({'id': vid, 'image_link': f'{base}/img/{gid}.jpg?v={v}'})
            story_rows.append({'id': vid, 'story_image': f'{base}/img/{gid}_story.jpg?v={v}'})
    for name, data, cols in (('supplemental.csv', rows, ['id', 'image_link']),
                             ('story.csv', story_rows, ['id', 'story_image'])):
        tmp = os.path.join(a.out, 'feed', name + '.part')
        with open(tmp, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(data)
        os.replace(tmp, tmp[:-5])

    json.dump(manifest, open(man_path, 'w'), indent=0)
    status = {
        'son_calisma': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'stokta_grup': len(live), 'yeniden_uretilen': len(todo) - len(errors) - len(no_photo), 'hata': len(errors),
        'fotografsiz_urunler': no_photo,
        'kampanya_dagilimi': per_camp, 'ek_feed_kampanyalari': sorted(rollout),
        'ek_feed_satir': len(rows), 'sezon_sonu_en_yuksek_indirim': umbrella,
        'sure_sn': round(time.time() - t0),
    }
    json.dump(status, open(os.path.join(a.out, 'status.json'), 'w'), ensure_ascii=False, indent=1)
    write_index(a.out, live, manifest, status)
    log('bitti', json.dumps(status, ensure_ascii=False))
    # çok fazla hata varsa iş başarısız sayılsın ki GitHub e-posta atsın
    if todo and len(errors) > max(5, 0.1 * len(todo)):
        sys.exit(f'{len(errors)} üründe hata: yayın yine de önceki görsellerle sürüyor.')


def write_index(out, live, manifest, status):
    """Pages kök sayfası: son çalışmanın özeti ve görsellere hızlı bakış."""
    items = []
    for p in live:
        if p['group_id'] in manifest:
            items.append(f'<a href="img/{p["group_id"]}.jpg"><img loading="lazy" src="img/{p["group_id"]}.jpg" alt=""></a>')
    s = status
    html = f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sortie Katalog Görselleri</title><meta name="robots" content="noindex">
<style>body{{font:15px/1.5 system-ui,sans-serif;margin:24px;background:#f6f3ee;color:#1a1816}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}}img{{width:100%;display:block}}
code{{background:#ede7de;padding:2px 6px}}</style>
<h1>Sortie katalog görselleri</h1>
<p>Son çalışma: {s["son_calisma"]} (UTC) · stokta {s["stokta_grup"]} grup · bu çalışmada {s["yeniden_uretilen"]} yeni/güncel · hata {s["hata"]}<br>
Ek feed: <code>feed/supplemental.csv</code> ({s["ek_feed_satir"]} satır, kampanyalar: {", ".join(s["ek_feed_kampanyalari"])})</p>
<div class="g">{"".join(items)}</div>'''
    open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write(html)


if __name__ == '__main__':
    main()
