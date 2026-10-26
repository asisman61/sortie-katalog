# Sortie katalog görselleri

Sitenin ürün feed'inden her gece tasarımlı reklam görselleri üretir ve Meta kataloğu için bir **ek feed** yayınlar.

- **Yeni Sezon** ürünleri → Diptik tasarım (ön + arka/detay, "Yeni Sezon" rozeti, %20)
- **Sezon Sonu** ürünleri → Kampanya tasarımı (büyük indirim oranı, "…'e varan indirimler")
- Kare (1080×1080) ve story (1080×1920) görseller birlikte üretilir.
- Yalnızca değişen ürünler yeniden üretilir: yeni ürün, fiyat/indirim değişikliği, kampanya geçişi, beden tükenmesi.

## Kurulum

### 1. Feed adresini gizli değişken olarak ekleyin
Depoda **Settings → Secrets and variables → Actions → New repository secret**
- Name: `FEED_URL`
- Secret: Ticimax XML adresinin tamamı (`https://www.sortiecollection.com/XMLExport/...`)

### 2. GitHub Pages'i açın
**Settings → Pages → Build and deployment → Source: GitHub Actions**

### 3. İlk çalıştırma
**Actions → Katalog görselleri → Run workflow**. İlk çalışma tüm kataloğu üretir (yaklaşık 10–20 dakika). Bittiğinde Pages adresinizde (`https://KULLANICI.github.io/DEPO/`) görsellerin önizlemesi görünür.

### 4. Meta'ya bağlayın
Commerce Manager → kataloğunuz → **Katalog → Veri kaynakları → Ek veri kaynağı ekle (Supplementary feed)**
- Yükleme yöntemi: **Planlanmış feed (URL)**
- URL: `https://KULLANICI.github.io/DEPO/feed/supplemental.csv`
- Sıklık: **Günlük, 05:00**
- Bağlanacak ana feed: mevcut Ticimax XML feed'iniz

Ek feed yalnızca `id` ve `image_link` içerir; ürünün diğer bilgileri ana feed'den gelmeye devam eder.

## Günlük kullanım

| Ne yapmak istiyorsunuz | Nerede |
|---|---|
| Yeni Sezon ürünlerini de teste almak | `config.json` → `"rollout": ["end", "new"]` |
| Tüm kataloğu yeni görsellere geçirmek | `config.json` → `"rollout": ["end", "new", "none"]` |
| Eski görsellere dönmek | Commerce Manager'da ek veri kaynağını silin veya `"rollout": []` |
| Son çalışmanın özeti | `https://KULLANICI.github.io/DEPO/status.json` |
| Bir kampanyanın tasarımını değiştirmek | `config.json` → `"styles"` (diptych, campaign, editorial) |
| Story görsellerinin listesi | `https://KULLANICI.github.io/DEPO/feed/story.csv` |

Tasarım şablonları `src/render.py` içindedir. Şablon değişince dosyadaki `RENDER_VERSION` bir artırılır; ertesi gece tüm görseller yeniden üretilir.

## Notlar

- Görsellerdeki indirim oranı her zaman ürünün kendi gerçek oranıdır. "…'e varan" ifadesindeki oran, feed'deki stokta olan sezon sonu ürünlerinin en yüksek indiriminden hesaplanır; elle girilmez.
- Üstü çizili fiyat feed'deki `price` alanından gelir. İndirim reklamlarında önceki fiyatın son 10 günün en düşük fiyatı olması gerekir; bunu Ticimax tarafında kontrol edin.
- Ölçü/beden tablosu görselleri otomatik tanınır ve reklam görsellerinde kullanılmaz. Hiç fotoğrafı olmayan (yalnızca tablo görseli olan) ürünler ek feed'e girmez; listeleri `status.json` içindeki `fotografsiz_urunler` alanındadır.
- Feed boş veya bozuk gelirse çalışma durur ve önceki gecenin görselleri yayında kalır. Hata olduğunda GitHub hesabınıza e-posta gelir.
- GitHub, uzun süre değişmeyen depolarda zamanlanmış işleri durdurur; iş ayın ilk günü depoya küçük bir işaret yazarak bunu önler.
