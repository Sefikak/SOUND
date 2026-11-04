# SOUND Android

Masaüstü SOUND'un Android sürümü. Ayrı bir uygulama değil, aynı kod:

- **Arayüz:** `SOUND/web/` WebView içinde çalışır. Üstüne yalnızca telefon uyarlaması biner (`app/src/main/web/`).
- **Arka uç:** `library`, `searcher`, `downloader`, `recommender`, `lyricsfinder`, `importer`, `mediaserver`, `webapp` modülleri Chaquopy ile telefonda çalışır.
- **Android'e özgü kısım:** `MainActivity` (pencere ve köprü), `PlaybackService` (bildirim, arka planda çalma), `app/src/main/python/` (Windows'a bağlı modüllerin yerine geçenler).

Ortak dosyalar her derlemede `../../SOUND` klasöründen (aynı deponun `main` dalı) alınır, burada kopyası tutulmaz. Başka bir yerdeyse: `-PsoundDir=<yol>`.

## Derleme

```
build.bat            APK üretir
build.bat install    bağlı cihaza / emülatöre kurar
build.bat release    yayın APK'sı (keystore/ klasöründeki anahtarla imzalanır)
emulator.bat         emülatörü açar, kurar ve uygulamayı başlatır
```

Java ve Android SDK `%LOCALAPPDATA%` altında aranır. Derleme çıktısı `%LOCALAPPDATA%\SOUNDbuild` içindedir (OneDrive'a girmesin diye).

## Yayınlama ve kendini güncelleme

Uygulama açılışta ve 30 dakikada bir `update/android.json` dosyasına (bu daldaki) bakar. Yeni sürüm varsa APK'yı Wi-Fi'da kendisi indirir, SHA-256 ile doğrular ve "Yükle" onayı ister. Mobil veride yalnızca Ayarlar'daki "Şimdi denetle" ile iner. Android, onaysız kurulum ve farklı anahtarla imzalı güncelleme kabul etmez.

Yeni sürüm çıkarmak:

1. `app/build.gradle.kts` içinde `versionCode` ve `versionName` değerlerini artır.
2. `build.bat release`
3. `python publish.py "yenilik 1" "yenilik 2"`: APK'yı `android-<sürüm>` etiketine koyar, `update/android.json` dosyasını yazar.
4. O dosyayı commit edip `mobile` dalına gönder. Telefonlar yeni sürümü bu adımdan sonra görür.

APK dallara değil etikete konur; masaüstü kullanıcılarının `git fetch`'i etiketleri indirmez. `keystore/` depoya girmez: anahtar kaybolursa mevcut kurulumlar artık güncellenemez, yedekle.

## Mobilde henüz olmayanlar

- Video indirme (görüntü ve sesi birleştirmek için ffmpeg gerekir). Video izleme çalışır.
- Spotify dosyasıyla aktarma. Spotify hesabıyla ve liste bağlantısıyla aktarma var; Spotify girişi telefonun tarayıcısında, Google girişi uygulamanın içinde açılır.
- Sürükle-bırak: yerine ⋯ menüsü kullanılır.

## yt-dlp güncellemesi

`updater.py` günde bir PyPI'a bakar, yeni sürümü SHA-256 ile doğrulayıp veri klasörüne açar; sürüm bir sonraki açılışta APK'dakinin önüne geçer. Yüklenemeyen, uygulamayı düşüren ya da gerçek bir videoyu çözemeyen sürüm bir daha kullanılmaz, son sağlam sürüme dönülür. Python 3.11'i bırakan sürümler indirilmez.

## Python sürümü

32 bit Android (`armeabi-v7a`) desteklendiği için Python 3.11 kullanılır; Chaquopy 3.12 ve sonrasında 32 bit desteklemiyor. Derleyen makinede de 3.11 gerekir: `%LOCALAPPDATA%\SOUNDtools\py311` ya da `-PbuildPython=<yol>`.
