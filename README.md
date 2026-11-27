<p align="center"><img src="assets/logo.png" width="420" alt="SOUND"></p>

<p align="center">YouTube ve YouTube Music üzerinden çalışan, Spotify tarzı masaüstü müzik uygulaması.</p>

<p align="center"><b><a href="CHANGELOG.md">📋 Güncellemelerde neler var?</a></b></p>

## İndir ve kur

### [⬇ SOUNDsetup.exe'yi indir](https://github.com/Sefikak/SOUND/raw/main/SOUNDsetup.exe)

1. İndirdiğin **SOUNDsetup.exe**'yi çalıştır.
2. Windows "Windows bilgisayarınızı korudu" derse **Ek bilgi → Yine de çalıştır**'a bas (kurulum dosyası imzasız olduğu için çıkar).
3. Sihirbazda klasörü seç, **Kur**'a bas. Gerekirse Python ve Git kendiliğinden kurulur; uygulama ve paketleri indirilir (~300 MB, birkaç dakika).

Kurulumdan sonra SOUND **güncellemeleri kendiliğinden alır**; kurulum dosyasını yeniden indirmen gerekmez.
Kaldırmak için: **Ayarlar → Uygulamalar → SOUND → Kaldır** (kitaplığını saklamayı seçebilirsin).

**Gereksinimler:** Windows 10/11 (64 bit), internet bağlantısı.

## Linux

### [⬇ SOUND-linux.zip'i indir](https://github.com/Sefikak/SOUND/raw/main/SOUND-linux.zip)

Zip'i aç, içindeki **SOUND-linux** klasöründe terminali açıp `bash install.sh` yaz. Ya da hiçbir şey indirmeden tek komutla kur:

```bash
curl -fsSL https://raw.githubusercontent.com/Sefikak/SOUND/main/linux/install.sh | bash
```

Kurulum eksik sistem paketlerini kurar (şifre sorar), SOUND'u `~/.local/share/sound`'a indirir ve uygulama menüsüne ekler. Terminalden `sound` komutuyla da açılır. Windows'taki gibi kendini günceller.
Kaldırmak için: `bash ~/.local/share/sound/linux/uninstall.sh`

**Gereksinimler:** 64 bit Linux (Ubuntu/Debian/Mint, Fedora, Arch, openSUSE), Python 3.10+, masaüstü ortamı.

## Mobil sürüm (Android)

### [⬇ SOUND-android-0.1.14.apk'yı indir](https://github.com/Sefikak/SOUND/raw/android-0.1.14/SOUND-android-0.1.14.apk)

**Erken deneme sürümü:** Sorun çıkabilir. 32 ve 64 bit telefonlarda kurulabilir.

1. APK'yı telefona indirip aç. Telefon sorarsa bilinmeyen kaynaktan kurma iznini ver.
2. Android 8.0 veya üstü gerekir.

0.1.3'ten itibaren uygulama kendini günceller: yeni sürümü Wi-Fi'da indirir, yüklemek için onayını ister. Kaynak kodu [`mobile` dalında](https://github.com/Sefikak/SOUND/tree/mobile).

Henüz yok: video indirme, YouTube Music'ten ve Spotify dosyasından içe aktarma, yaş doğrulamalı şarkılar.

## Galaxy Watch / Wear OS

### [⬇ SOUND-watch-1.1.apk'yı indir](https://github.com/Sefikak/SOUND/raw/wear-1.1/SOUND-watch-1.1.apk)

- **Telefonsuz çalar:** saat Wi-Fi'dan şarkı arar ve çalar, ardından benzer şarkılarla devam eder. Listeleri **saate indirip** internetsiz de dinleyebilirsin (Kitaplık'ta listenin yanındaki ⬇).
- **Telefonu kumanda eder:** çalan şarkı ve kapak, çal/duraklat, önceki/sonraki, beğen / beğenmedim, döner çerçeveyle ses, kaydırınca açılan kart.
- **Bilgisayardaki SOUND'u kumanda eder:** şarkıyı değiştir, sesi aç/kıs, çalmayı saate ya da başka cihaza aktar. Bilgisayar da saatte çalanı görüp kumanda edebilir. Bunun için telefonda SOUND hesabına giriş yapılmış olmalı.
- **Kendini günceller:** yeni sürüm çıkınca saat indirir, Kitaplık'ta "Güncelleme hazır" görünür (ilk seferde saat bir kez yükleme izni ister).

Telefonun listelerini ve hesabını alması için telefonda **SOUND 0.1.14 veya üstü** olmalı. Bluetooth kulaklık bağlı değilse saatin hoparlöründen çalar.

#### Saatten bilgisayarı kumanda etmek

1. **Bir kerelik hazırlık:** telefonda ve bilgisayarda aynı **SOUND hesabıyla** giriş yap, bilgisayarda SOUND açık olsun. Telefon yakındayken saatte SOUND'u bir kez aç; saat bağlantı bilgisini telefondan alır. Sonrasında telefon gerekmez, saatin internete (Wi-Fi) bağlı olması yeter.
2. Saatte SOUND'u aç, **üstteki küçük düğmeye** (⌚ SAAT / 📱 TELEFON yazan) dokun.
3. **"Nerede çalsın?"** listesinde, **SOUND hesabındaki cihazlar** altında bilgisayarını seç.
4. Üstte bilgisayarının adı (💻) görünür, ekran bilgisayarda çalanı gösterir:
   - **▶ / ❚❚** çal / duraklat, **⏮ ⏭** önceki / sonraki
   - **Döner çerçeve** bilgisayarın sesini açar / kısar
   - **♥ / 👎** beğen / beğenmedim
   - **Kitaplık (♫)** listeden ya da aramadan seçtiğin şarkı bilgisayarda çalar
5. **Çalmayı taşımak:** aynı listeden **Bu saat**'i seçersen bilgisayarda çalan şarkı kaldığı yerden saate geçer; saatte çalarken bilgisayarı seçersen şarkı bilgisayara geçer. Bilgisayar da saatte çalanı görür ve kumanda edebilir.

Bilgisayar listede görünmüyorsa: telefondaki SOUND'un 0.1.14 veya üstü ve hesabın açık olduğunu, bilgisayardaki SOUND'un güncel ve açık olduğunu kontrol et, sonra telefon yakındayken saatte SOUND'u kapatıp yeniden aç.

Saate kurmak (Play Store'da olmadığı için elle):
1. Saatte **Ayarlar › Telefon hakkında › Yazılım bilgisi**'nde *Yazılım sürümü*ne 5 kez dokun (Geliştirici seçenekleri açılır).
2. **Ayarlar › Geliştirici seçenekleri**'nde *ADB hata ayıklama* ve *Kablosuz hata ayıklama*yı aç.
3. Telefona **Bugjaeger** ya da **Wear Installer 2** gibi bir uygulama kur, saatte *Cihazı eşleme kodu ile eşle*'deki kod ve adresle eşleştir, APK'yı seçip saate yükle.
   Bilgisayardan: `adb pair <adres:port> <kod>` → `adb connect <adres:port>` → `adb install SOUND-watch-1.1.apk`

## Özellikler

- Şarkı, albüm ve sanatçı arama (YouTube Music), sanatçı sayfaları, radyo ve otomatik devam
- Kitaplık: favoriler, albümler, klasörler; çevrimdışı dinleme için indirme (Opus)
- Video modu, şarkı sözleri (LRCLIB), boşluksuz geçiş ve crossfade
- YouTube Music ve Spotify'dan içe aktarma
- Medya tuşları / Bluetooth kulaklık desteği, görev çubuğu düğmeleri
- 10 bantlı ekolayzır ve ses dengeleme (şarkılar arası ses farkını giderir)
- Dinleme istatistikleri: süre, en çok dinlenen şarkı ve sanatçılar, günlere ve saatlere göre dağılım
- Kişiselleştirme: vurgu rengi, tema, yerleşim, arayüz boyutu

## Şarkılarını YouTube Music ve Spotify'dan aktar

Aktarma ekranı: **Ayarlar → Kitaplık ve depolama → İçe aktar**. Beğendiğin şarkılar **favorilere**, listelerin ve albümlerin **albüm** olarak eklenir. Kitaplığında zaten olan şarkılar atlanır, yani aktarmayı istediğin kadar tekrarlayabilirsin. İlerleme altta görünür; aktarırken uygulamayı kullanmaya devam edebilirsin.

### YouTube Music

1. **YouTube Music** satırındaki **Giriş yap ve aktar**'a bas.
2. Açılan pencerede Google hesabınla giriş yap.
3. Giriş bitince aktarma kendiliğinden başlar: beğendiğin şarkılar, kayıtlı albümlerin ve listelerin gelir.

### Spotify (Premium gerekmez)

**Spotify bağlantı ya da dosya** satırındaki **Aktar**'a bas. İki yol var, ikisini birlikte de kullanabilirsin:

**a) Liste bağlantısı (hızlı):**
1. Spotify'da listeyi aç, **⋯ → Paylaş → Bağlantıyı kopyala**.
2. Bağlantıyı kutuya yapıştır. Birden çok listeyi alt alta yapıştırabilirsin.
3. **Aktar**'a bas.

Bu yolla liste başına **en fazla 100 şarkı** gelir ve **Beğenilen Şarkılar** alınamaz. Hepsi için aşağıdaki dosya yolunu kullan.

**b) Hesap verisi dosyası (beğenilenler dahil her şey):**
1. [spotify.com → Hesap → Gizlilik](https://www.spotify.com/account/privacy/) sayfasında **Hesap verileri**'ni iste.
2. Spotify birkaç gün içinde e-postayla bir indirme bağlantısı gönderir. **my_spotify_data.zip** dosyasını indir (açmana gerek yok).
3. SOUND'da **Dosya seç** ile bu zip'i seç ve **Aktar**'a bas.

[Exportify](https://exportify.app)'dan indirdiğin **CSV** dosyaları da aynı şekilde seçilebilir; beklemeden tek tek liste almak için iyi bir yol.

Spotify şarkıları YouTube Music'te aranıp eşleştirilir. Çok nadir de olsa bir şarkı bulunamayabilir ya da farklı bir sürümü gelebilir.

### Spotify hesabıyla giriş (yalnızca Premium)

Spotify, hesaba bağlanan uygulamalardan bir **Client ID** istiyor ve bunu artık yalnızca Premium hesaplara veriyor. Premium'un varsa:

1. **Spotify hesabı (Premium)** satırındaki **Giriş yap ve aktar**'a bas; ilk seferde kurulum penceresi açılır.
2. [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)'a gir, **Create app**'e bas. Ad/açıklamaya istediğini yaz (ör. SOUND).
3. **Redirect URI** olarak `http://127.0.0.1:43117/callback` ekle, **Web API**'yi işaretle, kaydet.
4. Uygulamanın sayfasındaki **Client ID**'yi SOUND'daki kutuya yapıştır, **Giriş yap ve aktar**'a bas.
5. Tarayıcıda izin ver; beğendiğin şarkılar ve listelerin doğrudan aktarılır. Bu kurulum bir kez yapılır.

Premium değilsen "Web API" kutusu seçilemez; o durumda yukarıdaki bağlantı ya da dosya yolunu kullan.

## Geliştirme

```
pip install -r requirements.txt
python main.py
```

Kurulum dosyasını derlemek için `installer\build.bat` (Inno Setup 6.7+ gerekir).
