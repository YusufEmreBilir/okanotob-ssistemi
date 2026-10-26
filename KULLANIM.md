# Okan Durak — Python masaüstü uygulaması

İstanbul Okan Üniversitesi **Tuzla kampüsü** için minimal, koyu temalı İETT ekranı. Hatlar tek yatay sırada, pencere boyutuna uyarlanarak görünür; ana ekranda kaydırma yoktur. Bir karta dokununca aynı pencerede tüm sefer tarifeleri açılır.

## Çalıştırma

**Python 3.10+ ve Tcl/Tk** gereklidir. Windows Python kurulumundaki `tcl/tk and IDLE` ve `Add Python to PATH` seçeneklerini etkinleştirin. Harici Python paketi, Node.js veya tarayıcı gerekmez.

| Dosya | İşlev |
| --- | --- |
| **`baslat.vbs`** | Normal pencere olarak, konsol göstermeden açar. Çift tıklayın. |
| **`kiosk.vbs`** | Tam ekran ve en üstte kiosk olarak açar. Hata ile kapanırsa 5 saniye sonra yeniden başlatır. |
| `calistir.cmd normal` | Komut satırından normal başlatma. |
| `calistir.cmd kiosk` | Komut satırından kiosk başlatma. |
| `Baslangica-Ekle.ps1` | Kiosk kısayolunu mevcut kullanıcının Başlangıç klasörüne ekler. |
| `Baslangictan-Kaldir.ps1` | Yalnızca Okan Durak başlangıç kısayolunu kaldırır. |

Komut satırı alternatifi:

```powershell
python app.py
python app.py --kiosk
```

Başlatıcı önce klasördeki `.venv\Scripts\python.exe`, sonra `py -3`, son olarak PATH içindeki `python` komutunu kullanır. Python/Tk bulunamazsa açıklayıcı bir pencere açılır. Günlükler `%LOCALAPPDATA%\OkanDurak` klasöründedir.

## Hedef bilgisayarda başlangıca ekleme

1. **Tüm proje klasörünü** hedef bilgisayarda sabit bir konuma kopyalayın. Başlangıca ekledikten sonra taşımayın.
2. Python'u yukarıdaki seçeneklerle kurun. `baslat.vbs` ve sonra `kiosk.vbs` ile kontrol edin.
3. İsterseniz `Baslangica-Ekle.ps1` dosyasını o bilgisayarda PowerShell ile çalıştırın. Alternatif: `Win+R → shell:startup` klasörüne **kiosk.vbs dosyasının kısayolunu** koyun. Dosyanın kendisini taşımayın.
4. Uygulama kullanıcının **Windows oturumu açıldığında** başlar; yalnızca bilgisayarın açılması yeterli değildir. Otomatik Windows oturum açma bu proje tarafından ayarlanmaz.

Bu geliştirme bilgisayarında başlangıca ekleme veya Windows kiosk politikası uygulanmamıştır.

## Kiosk davranışı ve bakım çıkışı

- Çerçevesiz tam ekran açılır ve en üstte tutulur.
- Pencere kapatma isteği ve `Alt+F4` engellenir. `Esc` yalnızca tarife detayından ana ekrana döner.
- Çalıştığı sürece Windows ekranının uykuya geçmesini engeller; kapanışta bu istek kaldırılır. Güç planı değiştirilmez.
- **`Ctrl+Shift+Q`** bakım çıkışını açar. Onaylayınca uygulama kapanır ve başlatıcı yeniden açmaz. Bu bir parola koruması değildir.
- Ana ekranda `F5` veriyi yeniler; karta dokunmak iki yönün hafta içi/cumartesi/pazar tarifesini açar.
- Tarife, geri bildirim ve kayıtlar dâhil bir menüde 30 saniye fare/klavye etkinliği olmazsa uygulama ana ekrana döner. Geri bildirimden sonra **Ana sayfaya dön** düğmesi de kullanılabilir.
- Ana ekranın sağ altındaki **Ayarlar** düğmesi yönetici girişini açar. Şifre `YEB`'dir. Yönetici panelinde geri bildirimler sayfalanarak incelenebilir; **Mesaj** düğmesi tam notu açar, **Sil** düğmesi kaydı onaydan sonra CSV dosyasından da kaldırır. Bu parola kaynak kodunda sabit ve yerel kiosk içindir; güçlü bir Windows hesap/parola güvenlik sınırı değildir.
- Ana ekrandaki belirgin **Geri bildirim** düğmesinden önce hat, sonra zamanında/geç/gelmedi yanıtı seçilir; isteğe bağlı not uygulamanın kendi dokunmatik klavyesiyle yazılır. Hat seçilince yazı ekranında klavye açılır; **Bitti** ile yanıt seçeneklerine dönülür. **Ayarlar** ekranında `YEB` şifre klavyesi de uygulamanın içindedir ve yönetici girişi açılınca otomatik görünür. Yanıta göre teşekkür veya özür mesajı gösterilir. **Kayıtlar** sayfasında son yanıtlar görünür; tüm kayıtlar `%LOCALAPPDATA%\OkanDurak\geri_bildirim.csv` dosyasında tutulur.
- Her hat kartındaki zamanında gelme oranı, o hatta gelen geçerli yanıtların içindeki “zamanında geldi” yanıtlarının yüzdesidir. Bildirim sayısı yüzdeyle birlikte gösterilir; az kayıt olduğunda sonuç küçük örneklem olarak değerlendirilmelidir. Bu istatistikler yalnızca bu bilgisayardaki yerel CSV kayıtlarını kapsar ve başka cihazlarla paylaşılmaz. Yeşil süre canlı İETT tahminini, turuncu süre tarifeden hesaplanan tahmini belirtir.

**Bu mod Windows'u bütünüyle kilitlemez.** `Ctrl+Alt+Del`, Windows tuşu, görev yöneticisi, uygulama değiştirme ve diğer sistem yollarını kapatan bir güvenlik sınırı değildir. Hedef bilgisayarın yalnız bu programı kullanması için ayrı bir standart kiosk hesabı ve Windows sürümüne uygun uygulama kısıtlama politikaları gerekir. Masaüstü Python uygulamaları için [Microsoft Shell Launcher](https://learn.microsoft.com/windows/configuration/shell-launcher/) ve ek uygulama kısıtlamaları değerlendirilebilir; Shell Launcher tek başına diğer uygulamalara erişimi engellemez. Desteklenen Windows sürümleri için [Microsoft kiosk karşılaştırmasına](https://learn.microsoft.com/windows/configuration/shell-launcher/browser-support) bakın. Başlatıcılar kayıt defteri, Explorer kabuğu, oturum açma veya güvenlik politikalarını değiştirmez.

## Canlı durak tahminleri

`iett_client.py`, İETT'nin kendi web uygulamasının kullandığı HTTP servislerine doğrudan bağlanır. API anahtarı gerektirmez.

| Servis | Kullanım |
| --- | --- |
| `GET https://iett.istanbul/tr/RouteStationAgent/GetRouteByStation?dcode=…&langid=1` | Duraktan geçen güncel hat listesi |
| `GET https://iett.istanbul/tr/RouteStation/GetStationInfo?dcode=…&langid=1` | **İETT tahmini varış saati ve dakika verisi** |
| `POST https://iett.istanbul/tr/RouteStation/GetScheduledDepartureTimes` | Form: `hCode`, `lngid`; iki yön ve üç gün türü için tarife |
| `GET https://iett.istanbul/tr/RouteStation/GetLineStatus?rcode=…` | Güncel hat duyuruları |

**209482 ve 209481** duraklarının ikisi de her 30 saniyede, varış yanıtı önbelleklenmeden sorgulanır. `iett.istanbul` ve `www.iett.istanbul` birlikte kontrol edilir; ana sunucuda eksik olan yön/hat diğerinden tamamlanır. Aynı araç yönünün iki ayrı tahmini birleştirilmez. Alternatif olarak araştırılan otobusnezaman.com ve iettapi.pcislocked.net servisleri erişimi HTTP 403 ile reddettiği için bunlar uygulamaya eklenmemiştir. Hat listesi ve tarifeler 5 dakika önbelleklenir. Ağ istekleri arayüzden ayrı iş parçacıklarında çalışır.

Ana ekranda **Tahmini varış**, saat ve **kaç dakika kaldığı** ayrı etiketlerle gösterilir. Planlı kalkışın canlı tahmin olmadığı belirtilir. Hattın uyarı metni, tıklamaya gerek kalmadan sütunların altındaki alanda görünür. Detay ekranının sefer saatleri kutucuk içindedir.

- Canlı tahmin geldiyse kartın ana saati doğrudan o veridir; dakika sayacı veri yaşıyla azalır. Yön ve durak kodu da görünür.
- `B` işaretli tahminler **sinyal belirsiz** olarak etiketlenir; canlı doğrulanmış araç sayılmaz.
- İki dakikadan eski varışlar kullanılmaz. Bağlantı kesilirse son veri, bağlantı uyarısıyla tutulur.
- Araştırma sırasında 132D, 133GP ve KM28 için gerçek İETT durak tahminleri doğrulandı; her hat için her an canlı tahmin bulunacağı garanti edilmez.
- Canlı tahmin bulunmayan hatlarda **Okan'a uğrayan normal ve özel (depar) güzergâhların tarifeleri** kullanılır. `GetFastStation?routeid=…&langid=1` servisindeki özel güzergâhların durak listeleri ve tarifeleri eşleştirilir; `GetStationForRoute` ile normal güzergâh da kontrol edilir. Kampüse uğramayan seferler hesaba katılmaz. Başka terminalin kalkış saati doğrudan kampüs varışı olarak sunulmaz.
- Ara durak geçişi için kaba model: **kalkış saati + yayımlanan tek yön sefer süresi × kampüsün durak sırası / toplam durak aralığı**. Örneğin toplam 40 dakika ve 4 aralıklı güzergâhta kampüs ikinci aralıktaysa kalkışa 20 dakika eklenir. Durak aralıklarının aynı sürede geçildiği varsayılır; güzergâh varyantının ana hattan farklı sürebileceği, trafik ve beklemeler bu modelde ölçülmez. Bu nedenle gerçek zamanlı doğruluk iddiası yoktur.
- Model saatleri **~** ve **Hesaplanan varış** ile, model payı **±en az 5 dakika veya yol süresinin %30'u** olacak şekilde gösterilir. Bu pay sezgisel bir göstergedir; ölçülmüş istatistiksel güven aralığı veya garanti değildir. Kaynak veri eksikse saat uydurulmaz. Gece yarısı geçişi ve sonraki hafta içi seferler de hesaplanır; sonraki gün açıkça belirtilir.
- Kampüs ilk duraksa yol süresi eklenmez ve **Planlı kampüs kalkışı** yazılır. Canlı İETT tahmini gelirse modelin önüne geçer. 130H'nin Okan'a uğrayan özel seferleri ve 133P'nin Okan çıkışlı/varışlı deparları bu şekilde kapsanır.
- İptal bilgisi **hat duyurularına** dayanır. Kesin sefer bazlı iptal kaydı sunulmaz. Tarife rengi veya özel güzergâh işaretleri iptal olarak yorumlanmaz.
- Tarifeler **ilk duraktan kalkış** saatleridir. İstanbul saati UTC+3 kullanılır. Resmî tatil istisnaları otomatik belirlenmez.

İETT'nin web uçları değişebilir; bir hata olduğunda veri uydurulmaz ve yeniden bağlantı denenir. Bağımsız bir uygulamadır; İETT veya üniversitenin resmî uygulaması değildir.

## Testler

```powershell
python -m unittest -v
python app.py --smoke-test
```

Otomatik testler hat/HTML ayrıştırma, yön bilgisi, boş gün sütunları, canlı tahmin önceliği, sayaç azalması, eski veri, `B` işareti, kampüs kalkışının seçimi, hafta sonu tarifeleri, alternatif kaynak birleştirme, eksik dakika/saat biçimleri ve durak uyarılarını kontrol eder. Smoke test normal pencereyi kısa süre açıp kapatır.

Önceki Node.js web sürümü `public/`, `lib/`, `server.mjs` altında durur; Python uygulaması bunlara ihtiyaç duymaz.
