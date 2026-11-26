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

### [⬇ SOUND-android-0.1.13.apk'yı indir](https://github.com/Sefikak/SOUND/raw/android-0.1.13/SOUND-android-0.1.13.apk)

**Erken deneme sürümü:** Sorun çıkabilir. 32 ve 64 bit telefonlarda kurulabilir.

1. APK'yı telefona indirip aç. Telefon sorarsa bilinmeyen kaynaktan kurma iznini ver.
2. Android 8.0 veya üstü gerekir.

0.1.3'ten itibaren uygulama kendini günceller: yeni sürümü Wi-Fi'da indirir, yüklemek için onayını ister. Kaynak kodu [`mobile` dalında](https://github.com/Sefikak/SOUND/tree/mobile).

Henüz yok: video indirme, YouTube Music'ten ve Spotify dosyasından içe aktarma, yaş doğrulamalı şarkılar.

## Galaxy Watch / Wear OS

### [⬇ SOUND-watch-1.0.apk'yı indir](https://github.com/Sefikak/SOUND/raw/wear-1.0/SOUND-watch-1.0.apk)

Saatten telefondaki SOUND'u kumanda edersin: çalan şarkı ve kapak, çal/duraklat, önceki/sonraki, beğen, döner çerçeveyle ses, kitaplıktan (favoriler, mixler, albümler, son çalınanlar) şarkı başlatma ve kaydırınca açılan kart. Telefonda **SOUND 0.1.13 veya üstü** kurulu olmalı; saat telefon olmadan müzik çalmaz.

Saate kurmak (Play Store'da olmadığı için elle):
1. Saatte **Ayarlar › Telefon hakkında › Yazılım bilgisi**'nde *Yazılım sürümü*ne 5 kez dokun (Geliştirici seçenekleri açılır).
2. **Ayarlar › Geliştirici seçenekleri**'nde *ADB hata ayıklama* ve *Kablosuz hata ayıklama*yı aç.
3. Telefona **Bugjaeger** ya da **Wear Installer 2** gibi bir uygulama kur, saatte *Cihazı eşleme kodu ile eşle*'deki kod ve adresle eşleştir, APK'yı seçip saate yükle.
   Bilgisayardan: `adb pair <adres:port> <kod>` → `adb connect <adres:port>` → `adb install SOUND-watch-1.0.apk`

## Özellikler

- Şarkı, albüm ve sanatçı arama (YouTube Music), sanatçı sayfaları, radyo ve otomatik devam
- Kitaplık: favoriler, albümler, klasörler; çevrimdışı dinleme için indirme (Opus)
- Video modu, şarkı sözleri (LRCLIB), boşluksuz geçiş ve crossfade
- YouTube Music ve Spotify'dan içe aktarma
- Medya tuşları / Bluetooth kulaklık desteği, görev çubuğu düğmeleri
- 10 bantlı ekolayzır ve ses dengeleme (şarkılar arası ses farkını giderir)
- Dinleme istatistikleri: süre, en çok dinlenen şarkı ve sanatçılar, günlere ve saatlere göre dağılım
- Kişiselleştirme: vurgu rengi, tema, yerleşim, arayüz boyutu

## Geliştirme

```
pip install -r requirements.txt
python main.py
```

Kurulum dosyasını derlemek için `installer\build.bat` (Inno Setup 6.7+ gerekir).
