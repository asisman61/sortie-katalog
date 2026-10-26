"""Sortie katalog reklam görseli üretici.

Şablonlar burada; tasarım değişikliği bu dosyada yapılır ve RENDER_VERSION artırılır.

Üç tasarım yönü (editorial, diptych, campaign) x iki format (square 1080x1080, story 1080x1920).
"""
import os, re, glob
os.environ.setdefault('OPENCV_LOG_LEVEL', 'ERROR')
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = lambda *p: os.path.join(ROOT, 'assets', *p)

RENDER_VERSION = 3  # şablon değişince artır: tüm görseller yeniden üretilir

INK = (26, 24, 22)
CREAM = (244, 239, 232)
SAND = (226, 216, 202)
MUTED = (120, 112, 104)
WHITE = (255, 255, 255)
WINE = (122, 32, 44)

BOTTOMS = {'Pantolon', 'Etek', 'Tayt', 'Şort', 'Eşofman Altı'}

# ---------- metin yardımcıları ----------

def tr_upper(s):
    return s.replace('i', 'İ').replace('ı', 'I').upper()

def clean_title(p):
    t = p['title']
    t = re.sub(r'^\s*\d+\s*-\s*', '', t)          # "431 - " gibi iç kodlar
    t = re.sub(r'\s*-\s*(?=\S+$)', ' ', t)          # "Gömlek - Bej" -> "Gömlek Bej"
    col = p.get('color') or ''
    if col and t.lower().endswith(col.lower()):
        t = t[: -len(col)].strip()
    return re.sub(r'\s+', ' ', t).strip()

def money(v):
    s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    if s.endswith(',00'):
        s = s[:-3]
    return s + ' TL'

def font(kind, size, wght=400, opsz=None):
    path = {'serif': 'BodoniModa[opsz,wght].ttf', 'serif_i': 'BodoniModa-Italic[opsz,wght].ttf',
            'sans': 'Jost[wght].ttf'}[kind]
    f = ImageFont.truetype(A('fonts', path), size)
    want = {b'Weight': wght, b'Optical size': opsz or min(96, max(6, size / 2))}
    try:
        f.set_variation_by_axes([want.get(ax['name'], ax['default']) for ax in f.get_variation_axes()])
    except Exception:
        pass
    return f

def text_w(f, s, track=0):
    if not s:
        return 0
    return sum(f.getlength(c) for c in s) + track * (len(s) - 1) if track else f.getlength(s)

def draw_text(d, xy, s, f, fill, track=0, anchor='l'):
    """anchor: l / m / r yatay hizalama; y üst-baseline için 'ls' kullanılır."""
    x, y = xy
    w = text_w(f, s, track)
    if anchor == 'm':
        x -= w / 2
    elif anchor == 'r':
        x -= w
    if not track:
        d.text((x, y), s, font=f, fill=fill, anchor='ls')
        return w
    for c in s:
        d.text((x, y), c, font=f, fill=fill, anchor='ls')
        x += f.getlength(c) + track
    return w

def wrap(f, s, maxw, track=0, max_lines=2):
    words, lines, cur = s.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if text_w(f, t, track) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while text_w(f, lines[-1] + '…', track) > maxw and ' ' in lines[-1]:
            lines[-1] = lines[-1].rsplit(' ', 1)[0]
        lines[-1] += '…'
    return lines

def fit_lines(kind, s, maxw, start, minsize, max_lines=2, wght=400, track=0):
    size = start
    while size > minsize:
        f = font(kind, size, wght)
        ls = wrap(f, s, maxw, track, max_lines=99)
        if len(ls) <= max_lines:
            return f, ls
        size -= 2
    f = font(kind, minsize, wght)
    return f, wrap(f, s, maxw, track, max_lines)

def strike(d, x0, x1, y, fill, w=2):
    d.line([(x0, y), (x1, y)], fill=fill, width=w)

# ---------- görsel yardımcıları ----------

def product_images(p, cache):
    files = []
    for i in range(len(p['images'])):
        m = glob.glob(os.path.join(cache, f"{p['group_id']}_{i}.*"))
        if m and not is_chart(m[0]):
            files.append(m[0])
    return files

_chart_cache = {}
def is_chart(path):
    """Ölçü/beden tablosu gibi grafik görselleri ele; bunlar reklamda hiç kullanılmaz.

    Tabloların satır ayraçları görselin neredeyse tamamı boyunca uzanan düz yatay
    çizgilerdir; stüdyo fotoğraflarında en fazla duvar/zemin çizgisi (1-4 adet) olur.
    Enine görseller ve 4+ çizgili kare görseller (beden tablosu şablonu) da elenir.
    """
    if path in _chart_cache:
        return _chart_cache[path]
    import cv2
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    H0, W0 = g.shape
    sc = 600 / W0
    g = cv2.resize(g, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
    W = g.shape[1]
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    e = (np.abs(gy) > 25).astype(np.uint8) * 255
    hl = cv2.morphologyEx(e, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(W * 0.70), 1)))
    rows = np.flatnonzero(np.diff(np.r_[0, (hl > 0).any(1).astype(np.uint8)]) == 1)
    lines = sum(1 for k, r in enumerate(rows) if k == 0 or r - rows[k - 1] > 6)
    r = W0 / H0 > 1.15 or lines >= 5 or (W0 / H0 >= 0.95 and lines >= 4)
    _chart_cache[path] = r
    return r

_face_cache = {}
def face(path):
    """En büyük yüzün (cx, cy, genişlik) oranları; yoksa None."""
    if path in _face_cache:
        return _face_cache[path]
    import cv2
    cv2.setLogLevel(0) if hasattr(cv2, 'setLogLevel') else None
    im = cv2.imread(path)
    sc = 640 / im.shape[1]
    im = cv2.resize(im, None, fx=sc, fy=sc)
    h, w = im.shape[:2]
    det = cv2.FaceDetectorYN.create(A('yunet.onnx'), '', (w, h), 0.75)
    _, fs = det.detect(im)
    r = None
    if fs is not None and len(fs):
        f = max(fs, key=lambda x: x[2])
        r = ((f[0] + f[2] / 2) / w, (f[1] + f[3] / 2) / h, f[2] / w)
    _face_cache[path] = r
    return r

def pick_hero(imgs, wide=False):
    """Yüzü görünen ilk kare; wide=True ise boyu en çok gösteren (yüzü en küçük) kare."""
    cand = [(i, face(f)) for i, f in enumerate(imgs[:5])]
    cand = [(i, fc) for i, fc in cand if fc]
    if not cand:
        return imgs[0]
    if wide:
        return imgs[min(cand, key=lambda c: c[1][2])[0]]
    return imgs[cand[0][0]]

def subject_box(im):
    """Düz stüdyo fonundan ayrışan bölgenin kutusu (0-1 oranları)."""
    s = im.convert('RGB').copy(); s.thumbnail((240, 300))
    a = np.asarray(s).astype(int)
    h, w, _ = a.shape
    bg = np.median(np.concatenate([a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)]), 0)
    diff = np.abs(a - bg).sum(2) > 60
    cols = np.where(diff.mean(0) > 0.04)[0]
    rows = np.where(diff.mean(1) > 0.04)[0]
    if len(cols) == 0 or len(rows) == 0:
        return 0, 0, 1, 1
    return cols[0] / w, rows[0] / h, (cols[-1] + 1) / w, (rows[-1] + 1) / h

def cover(im, W, H, focus_x=0.5, focus_y=0.5):
    iw, ih = im.size
    s = max(W / iw, H / ih)
    nw, nh = round(iw * s), round(ih * s)
    im = im.resize((nw, nh), Image.LANCZOS)
    x = int(min(max(focus_x * nw - W / 2, 0), nw - W))
    y = int(min(max(focus_y * nh - H / 2, 0), nh - H))
    return im.crop((x, y, x + W, y + H))

def smart_cover(path, W, H, ptype):
    im = Image.open(path).convert('RGB')
    fc = face(path)
    fx = fc[0] if fc else 0.5
    iw, ih = im.size
    s = max(W / iw, H / ih)
    slack = ih * s - H                      # dikeyde kırpılacak toplam piksel
    if slack <= 1:
        return cover(im, W, H, fx, 0.5)
    # dikey hizalama: üst giyim -> üstten, alt giyim -> alttan, diğerleri ortaya yakın
    bias = 0.88 if ptype in BOTTOMS else (0.42 if ptype in {'Elbise', 'Set', 'Eşofman Takım', 'Alt Üst Takım'} else 0.12)
    off = bias * slack
    if fc and ptype not in BOTTOMS:
        # yüzün üstünde nefes payı bırak, yüzü asla kesme
        face_top = (fc[1] - fc[2] * 0.9) * ih * s
        off = min(off, max(0, face_top - H * 0.06))
    fy = (off + H / 2) / (ih * s)
    return cover(im, W, H, fx, fy)

def paste_logo(canvas, name, width, xy, anchor='m'):
    lg = Image.open(A(f'{name}.png'))
    h = round(lg.size[1] * width / lg.size[0])
    lg = lg.resize((width, h), Image.LANCZOS)
    x, y = xy
    if anchor == 'm':
        x -= width // 2
    elif anchor == 'r':
        x -= width
    canvas.alpha_composite(lg, (int(x), int(y)))
    return h

def logo_variant(canvas, box, light='logo_white', dark='logo_ink'):
    """Logo bölgesi açıksa koyu, koyuysa beyaz logo seç."""
    reg = canvas.convert('L').crop(tuple(int(v) for v in box))
    return dark if np.asarray(reg).mean() > 150 else light

def gradient(W, H, top_alpha, bottom_alpha, color=(0, 0, 0)):
    g = np.linspace(top_alpha, bottom_alpha, H)[:, None].repeat(W, 1)
    g = np.clip(g, 0, 255) ** 1.0
    im = Image.new('RGBA', (W, H), color + (0,))
    im.putalpha(Image.fromarray(g.astype('uint8')))
    return im

# ---------- iş kuralları ----------

def draw_deal(d, xy, deal, size, fill, anchor='l'):
    """'%52' -> ince sans '%' + Bodoni rakamlar."""
    num = deal.lstrip('%')
    fn = font('serif', size, 500, 12)
    fpct = font('sans', int(size * 0.62), 300)
    gap = size * 0.04
    w = fpct.getlength('%') + gap + fn.getlength(num)
    x, y = xy
    if anchor == 'm':
        x -= w / 2
    d.text((x, y), '%', font=fpct, fill=fill, anchor='ls')
    d.text((x + fpct.getlength('%') + gap, y), num, font=fn, fill=fill, anchor='ls')
    return w

# Kampanya metinleri; site kampanyası değişince yalnızca burası değişir.
CAMPAIGNS = {
    'new': {'label': 'YENİ SEZON', 'kicker': 'Yeni Sezonda', 'sub': 'İNDİRİM'},
    'end': {'label': 'SEZON SONU', 'kicker': 'SEZON SONU', 'sub': 'İNDİRİM'},
}
# Sezon sonu şemsiye cümlesindeki "...'e varan" oranı. Boru hattı bunu feed'deki
# gerçek en yüksek sezon sonu indiriminden hesaplar; elle yazılan oran kullanılmaz.
UMBRELLA_MAX = None

_DATIVE_ONES = {1: "'e", 2: "'ye", 3: "'e", 4: "'e", 5: "'e", 6: "'ya", 7: "'ye", 8: "'e", 9: "'a"}
_DATIVE_TENS = {1: "'a", 2: "'ye", 3: "'a", 4: "'a", 5: "'ye", 6: "'a", 7: "'e", 8: "'e", 9: "'a"}
def pct_dative(n):
    """%62 -> %62'ye, %70 -> %70'e (Türkçe yönelme eki)."""
    n = int(n)
    suf = _DATIVE_ONES[n % 10] if n % 10 else _DATIVE_TENS.get(n // 10 % 10, "'e")
    if n == 100:
        suf = "'e"
    return f'%{n}{suf}'

def badges(p):
    """Görselde gösterilecek mesajlar. Her oran ürünün kendi gerçek indirimidir."""
    out = {}
    rate = p['discount']
    if p['new_season']:
        out['camp'] = 'new'
    elif rate > 0:
        out['camp'] = 'end'
    if 'camp' in out:
        out['label'] = CAMPAIGNS[out['camp']]['label']
    if rate > 0:
        out['deal'] = f'%{rate}'
    if p['in_stock'] and len(p['sizes']) >= 3 and len(p['in_stock']) <= 2:
        out['last'] = 'SON BEDENLER  ·  ' + ' · '.join(p['in_stock'])
    return out

def price_parts(p):
    if p['sale'] and p['sale'] < p['price']:
        return money(p['sale']), money(p['price'])
    return money(p['price']), None

def sizes_line(p):
    return '  '.join(p['in_stock'])

# ---------- A: EDİTORYAL ----------
# Story güvenli alanı: üst ~250 px ve alt ~380 px Instagram arayüzü altında kalır.

def editorial(p, imgs, fmt):
    story = fmt == 'story'
    W, H = (1080, 1920) if story else (1080, 1080)
    c = smart_cover(pick_hero(imgs), W, H, p['type']).convert('RGBA')
    b = badges(p)
    m = 36
    top = 290 if story else 76
    lx = m + 40
    lv = logo_variant(c, (lx, top - 10, lx + 240, top + 60))
    gh = 900 if story else 520
    c.alpha_composite(gradient(W, gh, 0, 180), (0, H - gh))
    if lv == 'logo_white':
        c.alpha_composite(gradient(W, 420 if story else 240, 110, 0), (0, 0))
    d = ImageDraw.Draw(c)
    d.rectangle([m, m, W - m, H - m], outline=(255, 255, 255, 210), width=2)
    paste_logo(c, lv, 240, (lx, top), anchor='l')
    tag = b.get('label')
    if tag:
        f = font('sans', 22, 500)
        tw = text_w(f, tag, 4)
        bx, by = W - m - 40 - tw - 36, top - 4
        d.rectangle([bx, by, bx + tw + 36, by + 46], fill=(255, 255, 255, 235) if lv == 'logo_white' else INK + (255,))
        draw_text(d, (bx + 18, by + 31), tag, f, INK if lv == 'logo_white' else WHITE, 4)
    base = 1470 if story else H - m - 60
    now, old = price_parts(p)
    fp = font('sans', 40, 500)
    fo = font('sans', 28, 400)
    draw_text(d, (m + 44, base), now, fp, WHITE)
    x = m + 44 + text_w(fp, now) + 22
    if old:
        w = draw_text(d, (x, base), old, fo, (255, 255, 255, 200))
        strike(d, x, x + w, base - 10, (255, 255, 255, 220), 2)
        x += w + 22
    if 'deal' in b:
        f = font('sans', 26, 600)
        w = text_w(f, b['deal'])
        d.rectangle([x, base - 34, x + w + 24, base + 8], fill=WHITE)
        draw_text(d, (x + 12, base - 3), b['deal'], f, WINE)
    ft, lines = fit_lines('serif', clean_title(p), W - 2 * m - 88, 66 if story else 58, 40, 2)
    lh = ft.size * 1.12
    y = base - 64 - lh * (len(lines) - 1)
    for i, ln in enumerate(lines):
        draw_text(d, (m + 44, y + i * lh), ln, ft, WHITE)
    info = b.get('last') or ('BEDENLER  ·  ' + ' · '.join(p['in_stock']))
    draw_text(d, (m + 44, y - ft.size - 18), info, font('sans', 22, 500), (255, 255, 255, 230), 4)
    return c.convert('RGB')

# ---------- B: DİPTİK ----------

def _others(imgs, hero):
    rest = [f for f in imgs if f != hero]
    return (rest + [hero, hero])[:2]

def diptych(p, imgs, fmt):
    story = fmt == 'story'
    W, H = (1080, 1920) if story else (1080, 1080)
    c = Image.new('RGBA', (W, H), CREAM + (255,))
    d = ImageDraw.Draw(c)
    b = badges(p)
    hero = pick_hero(imgs)
    second, third = _others(imgs, hero)
    if not story:
        pad, gap = 40, 14
        pw = (W - 2 * pad - gap) // 2
        ph, y0 = 760, 108
        c.paste(smart_cover(hero, pw, ph, p['type']), (pad, y0))
        c.paste(smart_cover(second, pw, ph, p['type']), (pad + pw + gap, y0))
        paste_logo(c, 'logo_ink', 230, (W / 2, 40))
        ty = y0 + ph + 34
        maxw = W - 2 * pad - 300
    else:
        # üst krem bant + logo, büyük ana kare, metin (güvenli alan), altta kenara taşan ikili şerit
        pad, gap = 48, 14
        y0, mh = 340, 840
        mw = W - 2 * pad
        c.paste(smart_cover(hero, mw, mh, p['type']), (pad, y0))
        paste_logo(c, 'logo_ink', 280, (W / 2, 250))
        ty = y0 + mh + 26
        maxw = W - 2 * pad - 320
        sy = 1430
        sw = (mw - gap) // 2
        c.paste(smart_cover(second, sw, H - sy, p['type']), (pad, sy))
        c.paste(smart_cover(third, sw, H - sy, p['type']), (pad + sw + gap, sy))
    tx = pad
    tag = b.get('last') or b.get('label')
    if tag:
        f = font('sans', 20, 500)
        tw = text_w(f, tag, 4)
        bx, by = pad + 18, y0 + 18
        d.rectangle([bx, by, bx + tw + 32, by + 42], fill=CREAM + (255,))
        draw_text(d, (bx + 16, by + 29), tag, f, INK, 4)
    if 'deal' in b:
        R = 58
        cx, cy = W - pad - 18 - R, y0 + 18 + R
        d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(WINE if b.get('camp') == 'end' else INK) + (255,))
        draw_deal(d, (cx, cy + 14), b['deal'], 42, WHITE, anchor='m')
    ft, lines = fit_lines('serif', clean_title(p), maxw, 50 if story else 44, 30, 2)
    lh = ft.size * 1.15
    for i, ln in enumerate(lines):
        draw_text(d, (tx, ty + ft.size + i * lh), ln, ft, INK)
    info = (tr_upper(p['color']) + '   ·   ' if p['color'] else '') + 'BEDEN  ' + ' · '.join(p['in_stock'])
    draw_text(d, (tx, ty + ft.size + (len(lines) - 1) * lh + 42), info, font('sans', 20, 500), MUTED, 3)
    now, old = price_parts(p)
    rx, by = W - pad, ty + 44
    draw_text(d, (rx, by), now, font('sans', 40, 500), INK, anchor='r')
    if old:
        w = draw_text(d, (rx, by + 40), old, font('sans', 26, 400), MUTED, anchor='r')
        strike(d, rx - w, rx, by + 30, MUTED, 2)
    return c.convert('RGB')

# ---------- C: KAMPANYA ----------

GREY = (170, 162, 152)

def _headline(d, p, b, x, y, big, maxw=10**6):
    """Kampanya başlığı (Yeni Sezonda %20 / SEZON SONU %52); yeni y döner."""
    camp = b.get('camp')
    if camp and 'deal' in b:
        cfg = CAMPAIGNS[camp]
        if camp == 'new':
            draw_text(d, (x, y + 48), cfg['kicker'], font('serif_i', int(big * 0.36), 400, 96), WHITE)
        else:
            draw_text(d, (x, y + 30), cfg['kicker'], font('sans', 22, 500), SAND, 8)
        yb = y + 48 + int(big * 0.95)
        draw_deal(d, (x - 4, yb), b['deal'], big, WHITE)
        sub = cfg['sub']
        if camp == 'end' and UMBRELLA_MAX:
            sub = tr_upper(f"{pct_dative(UMBRELLA_MAX)} varan indirimler")
        fs = font('sans', 22, 500)
        tr = 8 if text_w(fs, sub, 8) <= maxw else 3
        draw_text(d, (x, yb + 48), sub, fs, SAND, tr)
        return yb + 92
    f = font('serif_i', int(big * 0.52), 400, 96)
    head = 'Yeni Sezon' if p['new_season'] else 'Sortie Seçkisi'
    draw_text(d, (x, y + int(big * 0.46)), head, f, WHITE)
    fs = font('sans', 22, 500)
    sub = tr_upper(p['type']) + ' KOLEKSİYONU' if p['new_season'] else 'ÖZEL SEÇİM'
    if text_w(fs, sub, 6) > maxw:
        sub = 'YENİ KOLEKSİYON'
    draw_text(d, (x, y + int(big * 0.46) + 48), sub, fs, SAND, 6)
    return y + int(big * 0.46) + 100

def _sizes(d, p, b, x, y):
    f = font('sans', 20, 500)
    if 'last' in b:
        draw_text(d, (x, y), b['last'], f, (230, 160, 120), 4)
    else:
        draw_text(d, (x, y), 'BEDEN  ' + ' · '.join(p['in_stock']), f, SAND, 4)

def campaign(p, imgs, fmt):
    story = fmt == 'story'
    W, H = (1080, 1920) if story else (1080, 1080)
    c = Image.new('RGBA', (W, H), INK + (255,))
    b = badges(p)
    hero = pick_hero(imgs)
    now, old = price_parts(p)
    pad = 52
    if not story:
        pw = 600
        c.paste(smart_cover(hero, pw, H, p['type']), (0, 0))
        d = ImageDraw.Draw(c)
        x = pw + pad
        innerw = W - pw - 2 * pad
        paste_logo(c, 'icon_white', 46, (x, 56), anchor='l')
        y = _headline(d, p, b, x, 190, 150, innerw)
        d.line([(x, y), (x + 80, y)], fill=SAND, width=2)
        y += 50
        ft, lines = fit_lines('serif', clean_title(p), innerw, 40, 28, 3)
        lh = ft.size * 1.18
        for i, ln in enumerate(lines):
            draw_text(d, (x, y + ft.size + i * lh), ln, ft, WHITE)
        y += ft.size + (len(lines) - 1) * lh + 70
        w = draw_text(d, (x, y + 20), now, font('sans', 44, 500), WHITE)
        if old:
            ox = x + w + 18
            w2 = draw_text(d, (ox, y + 20), old, font('sans', 26, 400), GREY)
            strike(d, ox, ox + w2, y + 10, GREY, 2)
        _sizes(d, p, b, x, y + 80)
        cy = H - 70
        paste_logo(c, 'wordmark_white', 170, (x, cy - 4), anchor='l')
        draw_text(d, (W - pad, cy + 22), 'İNCELE', font('sans', 20, 500), WHITE, 5, anchor='r')
        return c.convert('RGB')
    ph = 940
    c.paste(smart_cover(hero, W, ph, p['type']), (0, 0))
    lv = logo_variant(c, (pad, 250, pad + 260, 320))
    if lv == 'logo_white':
        c.alpha_composite(gradient(W, 360, 100, 0), (0, 0))
    paste_logo(c, lv, 240, (pad, 262), anchor='l')
    d = ImageDraw.Draw(c)
    x = pad
    y = _headline(d, p, b, x, ph + 36, 140, W - 2 * pad - 300)
    rx = W - pad
    draw_text(d, (rx, ph + 110), now, font('sans', 50, 500), WHITE, anchor='r')
    if old:
        w2 = draw_text(d, (rx, ph + 158), old, font('sans', 28, 400), GREY, anchor='r')
        strike(d, rx - w2, rx, ph + 148, GREY, 2)
    d.line([(x, y), (x + 80, y)], fill=SAND, width=2)
    y += 36
    ft, lines = fit_lines('serif', clean_title(p), W - 2 * pad, 50, 34, 2)
    lh = ft.size * 1.16
    for i, ln in enumerate(lines):
        draw_text(d, (x, y + ft.size + i * lh), ln, ft, WHITE)
    y += ft.size + (len(lines) - 1) * lh + 46
    _sizes(d, p, b, x, y)
    # CTA düğmesi: metnin altında, alt arayüz alanının (≈1540+) üstünde
    by = y + 28
    assert by + 64 <= 1545, f"story CTA güvenli alan dışında: {by}"
    f = font('sans', 22, 600)
    label = 'ŞİMDİ İNCELE'
    tw = text_w(f, label, 6)
    d.rectangle([x, by, x + tw + 64, by + 64], outline=WHITE, width=2)
    draw_text(d, (x + 32, by + 40), label, f, WHITE, 6)
    # alt bölge: arayüz altında kalacak sakin marka imzası
    d.line([(pad, 1640), (W - pad, 1640)], fill=(60, 56, 52), width=1)
    paste_logo(c, 'icon_white', 54, (W / 2, 1690))
    return c.convert('RGB')

STYLES = {'editorial': editorial, 'diptych': diptych, 'campaign': campaign}

def render(p, style, fmt, files):
    """files: ürünün yerel görsel yolları, feed sırasıyla."""
    imgs = [f for f in files if not is_chart(f)]
    if not imgs:
        return None
    return STYLES[style](p, imgs, fmt)

# Kampanyaya göre tasarım yönü
STYLE_FOR = {'new': 'diptych', 'end': 'campaign', None: 'diptych'}

def style_for(p):
    return STYLE_FOR[badges(p).get('camp')]
