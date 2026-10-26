"""Sortie feed okuyucu: XML'i renk/model grubu bazında ürünlere çevirir."""
import xml.etree.ElementTree as ET, re, html
NS = {'a': 'http://www.w3.org/2005/Atom', 'g': 'http://base.google.com/ns/1.0'}
SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '2XL', '3XL', 'STD']

def _g(e, t):
    x = e.find('g:' + t, NS)
    return x.text.strip() if x is not None and x.text else ''

def _money(s):
    return float(s.split()[0]) if s else None

def load(path):
    root = ET.parse(path).getroot()
    groups = {}
    for e in root.findall('a:entry', NS):
        gid = _g(e, 'item_group_id') or _g(e, 'id')
        groups.setdefault(gid, []).append(e)
    products = []
    for gid, rows in groups.items():
        f = rows[0]
        price, sale = _money(_g(f, 'price')), _money(_g(f, 'sale_price'))
        sizes = [(_g(r, 'size'), _g(r, 'availability') == 'in stock') for r in rows]
        sizes.sort(key=lambda s: SIZE_ORDER.index(s[0]) if s[0] in SIZE_ORDER else 99)
        imgs = [_g(f, 'image_link')] + [x.text.strip() for x in f.findall('g:additional_image_link', NS) if x.text]
        seen, uniq = set(), []
        for u in imgs:
            if u and u not in seen:
                seen.add(u); uniq.append(u)
        products.append(dict(
            group_id=gid, ids=[_g(r, 'id') for r in rows],
            title=_g(f, 'title'), type=_g(f, 'product_type'), color=_g(f, 'color'),
            link=_g(f, 'link'), price=price, sale=sale,
            discount=round((1 - sale / price) * 100) if sale and price and sale < price else 0,
            new_season=_g(f, 'custom_label_3') == 'Yeni Sezon',
            sizes=sizes, in_stock=[s for s, ok in sizes if ok],
            images=uniq,
        ))
    return products
