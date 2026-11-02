<p align="center"><img src="assets/logo.png" width="420" alt="SOUND"></p>

<p align="center">YouTube ve YouTube Music üzerinden çalışan, Spotify tarzı masaüstü müzik uygulaması.</p>

## İndir ve kur

### [⬇ SOUNDsetup.exe'yi indir](https://github.com/Sefikak/SOUND/raw/main/SOUNDsetup.exe)

1. İndirdiğin **SOUNDsetup.exe**'yi çalıştır.
2. Windows "Windows bilgisayarınızı korudu" derse **Ek bilgi → Yine de çalıştır**'a bas (kurulum dosyası imzasız olduğu için çıkar).
3. Sihirbazda klasörü seç, **Kur**'a bas. Gerekirse Python ve Git kendiliğinden kurulur; uygulama ve paketleri indirilir (~300 MB, birkaç dakika).

Kurulumdan sonra SOUND **güncellemeleri kendiliğinden alır**; kurulum dosyasını yeniden indirmen gerekmez.
Kaldırmak için: **Ayarlar → Uygulamalar → SOUND → Kaldır** (kitaplığını saklamayı seçebilirsin).

**Gereksinimler:** Windows 10/11 (64 bit), internet bağlantısı.

## Mobil sürüm (Android)

### [⬇ SOUND-android-0.1.0.apk'yı indir](https://github.com/Sefikak/SOUND/raw/android-0.1.0/SOUND-android-0.1.0.apk)

**Erken deneme sürümü:** Şimdiye kadar yalnızca emülatörde denendi, telefonda sorun çıkabilir.

1. APK'yı telefona indirip aç. Telefon sorarsa bilinmeyen kaynaktan kurma iznini ver.
2. Android 8.0 veya üstü gerekir (64 bit).

Henüz yok: video indirme, YouTube Music ve Spotify'dan içe aktarma, yaş doğrulamalı şarkılar. Güncellemeler otomatik gelmez; yeni sürüm için APK'yı yeniden indirip üzerine kur.

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
