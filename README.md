# Okan Ulaşım

Okan Üniversitesi **Tuzla kampüsü** duraklarından geçen İETT hatlarını tek ekranda gösteren, mobil uyumlu web uygulaması.

## Çalıştırma

Python 3.11+ gerekir. Harici Python paketi, Node.js, API anahtarı veya veritabanı gerekmez.

```sh
cd /workspace/okanotob-ssistemi
python server.py
```

Varsayılan port `3000`; `PORT` ve `HOST` ile değiştirilebilir. Python sürecinin `api.ibb.gov.tr` adresine HTTPS erişimi olmalıdır. Python, ortamın standart HTTPS proxy ayarlarını kullanır; TLS doğrulaması açıktır. Arayüz ve API aynı sunucudan servis edilir.

## Özellikler

- Hat kartları: sıradaki **ilk durak kalkışı**, gün/yön filtreleri ve iptal/hat duyuruları.
- Karttan açılan erişilebilir detay penceresi: gün ve yön bazında saatler, ilgili duyurular.
- İstanbul saatiyle hesaplama, dakikada otomatik yenileme, manuel yenileme, hat/güzergâh arama.
- Sunucu tarafında saatler için 5 dakika, duyurular için 60 saniye önbellek. Kesintide eski veriler açıkça işaretlenir; veri yokluğu “iptal yok” sayılmaz.

## Veri kapsamı ve sınırlar

Kaynak: [İBB açık veri kataloğu](https://data.ibb.gov.tr/api/3/action/package_search?q=iett).

- Saatler: `https://api.ibb.gov.tr/iett/UlasimAnaVeri/PlanlananSeferSaati.asmx`, `GetPlanlananSeferSaati_json`.
- Duyurular: `https://api.ibb.gov.tr/iett/UlasimDinamikVeri/Duyurular.asmx`, `GetDuyurular_json`.
- Durak doğrulama: `https://api.ibb.gov.tr/iett/ibb/ibb.asmx`, `DurakDetay_GYY_wYonAdi`.

`data/lines.json` içindeki beş hat (130H, 132D, 133GP, 133P, KM28), 26 Ekim 2026 tarihinde İBB GTFS verisindeki `209481` ve `209482` duraklarından türetildi. KM28, GTFS dosyasında bulunmadığından canlı durak servisiyle ayrıca doğrulandı. GTFS `stop_times → trips → routes` bağlantısıyla bulunan **güzergâh kodları** kullanılır; bir hattın kampüse uğramayan normal seferleri listeye dahil edilmez. KM28 için durak servisiyle doğrulanan D/G ana güzergâhları kullanılır. Katalog otomatik değişmez; hat güzergâhları değişince yeniden doğrulanmalıdır.

**Önemli:** API kaynakları arasında güzergâh ve hat adı tutarsızlıkları gözlendi. Bazı özel seferler yalnız belirli günlerde çalışır. Hiç sefer görünmemesi hattın tamamen çalışmadığı anlamına gelmez.

Saatler kampüs durağına varış tahmini değildir. Kaynak API'nin `D/G` yön kodları, `I` (hafta içi), `C` (cumartesi), `P` (pazar) gün tipleri gösterilir. Resmî tatil tarifesi otomatik tespit edilmez; kullanıcı gün tipini seçebilir.

İptal duyurularında tam tarih ve makineyle güvenilir eşleşen yön bilgisi bulunmayabilir. Bu nedenle hat bazında duyuru gösterilir; saat eşleşmesi **olası iptal uyarısıdır**, kesin iptal etiketi değildir. Duyuru metni saklanır, seferler otomatik silinmez. “İptal duyurusu yok”, yalnızca son API yanıtında ilgili duyurunun bulunmadığını ifade eder.

## Doğrulama

```sh
python -m unittest discover -s tests -v
node --check public/app.js  # Node varsa isteğe bağlı sözdizimi kontrolü
curl --fail http://127.0.0.1:3000/health
curl --fail http://127.0.0.1:3000/api/dashboard
```

`/health` süreç kontrolüdür. İşlevsel kontrol için `/api/dashboard` içindeki her hattın `scheduleState.error` ve `noticesState.error` alanlarını, saat listesini ve arayüzü kontrol edin. Testler ağ hatası/önbellek davranışını ve kampüse uğramayan güzergâhların elenmesini kapsar.
