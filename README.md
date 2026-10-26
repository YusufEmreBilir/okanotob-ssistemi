# Okan Durak

**Güncel sürüm: Python masaüstü uygulaması.** Hatlar yatay ve kaydırmasız görünür. Normal açmak için **`baslat.vbs`**, tam ekran kiosk için **`kiosk.vbs`** dosyasına çift tıklayın. Python 3.10+ ve Tcl/Tk yeterlidir; harici paket veya Node.js gerekmez.

**[Python kurulumu, kiosk modu ve başlangıç dosyaları → KULLANIM.md](KULLANIM.md)**

Python testleri: `python -m unittest -v`. Kaynaklar: `app.py`, `iett_client.py`.

---

Aşağıdaki bilgiler önceki web sürümüne aittir. Python uygulaması web sunucusunu kullanmaz.

İstanbul Okan Üniversitesi **Tuzla kampüsü** için mobil uyumlu, koyu temalı İETT ekranı. Node.js 22 veya üzeri yeterlidir; bağımlılık kurulumu gerekmez.

```sh
node server.mjs
```

Uygulamayı **http://localhost:3000** adresinde açın. Alternatif: `npm start`. Portu `PORT` ortam değişkeniyle değiştirebilirsiniz. Sunucu yalnızca yerel bilgisayarda dinler.

## Özellikler

- 209482 ve 209481 duraklarından geçen belediye hatlarını İETT servisinden otomatik keşfeder.
- Tek ekranda tüm hatlar, sıradaki tahmini varış veya planlı kampüs kalkışı, iptal duyurusu durumu.
- Bir hatta dokununca iki yöndeki tüm hafta içi / cumartesi / pazar kalkış tarifeleri.
- Hat / güzergâh araması, bir saat içinde yaklaşan sefer filtresi ve cihazda saklanan favoriler.
- 30 saniyede bir yenileme, manuel yenileme, bağlantı ve kısmi veri hataları.
- İstanbul saat dilimi, klavye erişimi, Escape ile kapanan detay penceresi.

## Canlı veri ve anlamı

Sunucu `https://iett.istanbul` adresindeki web uygulamasının kullandığı HTTP servislerine istek yapar; tarayıcı aynı kaynaktaki `/api/board` üzerinden normalize edilmiş JSON alır. API anahtarı gerekmez. Durak/duyuru verisi 30 saniye, hat listesi ve tarife 5 dakika bellekte önbelleklenir. Bu uçlar İETT tarafından değiştirilebilir; entegrasyon `lib/iett.mjs` dosyasındadır.

| Servis | Kullanım |
| --- | --- |
| `GET /tr/RouteStationAgent/GetRouteByStation?dcode=…&langid=1` | Duraktan geçen hatlar |
| `GET /tr/RouteStation/GetStationInfo?dcode=…&langid=1` | Tahmini durak varışları |
| `POST /tr/RouteStation/GetScheduledDepartureTimes` | Form: `hCode`, `lngid`; iki yön ve üç gün türünün tarifesi |
| `GET /tr/RouteStation/GetLineStatus?rcode=…` | Güncel hat duyuruları |

**Durak tahmini ile ilk durak kalkışı farklıdır.** Durak tahmini yoksa yalnızca ilk durağı Okan Üniversitesi olan tarifelerden bir sonraki kampüs kalkışı gösterilir. Ara duraktan geçen bir hattın terminal saatini kampüs varışı gibi göstermez. Veri yoksa saat yerine “—” görünür. Detayda her zaman ilk duraktan kalkış tarifeleri gösterilir. Resmî tatil istisnaları otomatik belirlenmez.

**İptal durumu hat duyurularına dayanır.** Servis tek tek seferlerin kesin iptal durumunu sağlamaz. İptal içeren duyuru varsa uyarı gösterilir; boş duyuru listesi “İptal duyurusu yok”, başarısız istek “Durum bilinmiyor” olarak görünür. Tarife rengi ve özel güzergâh işaretleri iptal olarak yorumlanmaz. Duyuru kapsamını hat detayından okuyabilirsiniz.

Kayıtlı sahte sefer verisi kullanılmaz. Bağlantı kesilirse son alınan veri yalnızca mevcut sayfa oturumunda uyarıyla tutulur; iki dakikadan eski canlı tahmin kullanılmaz.

## Doğrulama

```sh
node --test
```

Testler HTML / entity ayrıştırmasını, üç gün sütununun korunmasını, belirsiz varış işaretini, kampüs kalkışı seçimini ve İstanbul gece yarısı / hafta sonu geçişlerini kontrol eder.

Resmî kaynak: [İETT kampüs durağı](https://iett.istanbul/StationDetail?dkod=209482). İETT veya Okan Üniversitesi'nin resmî uygulaması değildir.
