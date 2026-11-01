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

## Özellikler

- Şarkı, albüm ve sanatçı arama (YouTube Music), sanatçı sayfaları, radyo ve otomatik devam
- Kitaplık: favoriler, albümler, klasörler; çevrimdışı dinleme için indirme (Opus)
- Video modu, şarkı sözleri (LRCLIB), boşluksuz geçiş ve crossfade
- YouTube Music ve Spotify'dan içe aktarma
- Medya tuşları / Bluetooth kulaklık desteği, görev çubuğu düğmeleri
- Kişiselleştirme: vurgu rengi, tema, yerleşim, arayüz boyutu

## Geliştirme

```
pip install -r requirements.txt
python main.py
```

Kurulum dosyasını derlemek için `installer\build.bat` (Inno Setup 6.7+ gerekir).
