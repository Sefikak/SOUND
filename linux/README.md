# SOUND — Linux

SOUND'un Linux sürümü. Windows ve Android'deki SOUND ile **aynı uygulama**: aynı arayüz, aynı özellikler
(arama, sanatçı sayfaları, Sanatçı Mix, indirme, sözler, ekolayzır, istatistikler, SOUND hesabıyla eşitleme...).
Kod aynı GitHub deposundan gelir; Windows'taki gibi kendini günceller.

## Kurulum

Bu klasörü Linux bilgisayara kopyala ve terminalde:

```bash
bash install.sh
```

ya da hiçbir şey kopyalamadan, internetten tek komutla:

```bash
curl -fsSL https://raw.githubusercontent.com/Sefikak/SOUND/main/linux/install.sh | bash
```

Kurulum:

1. Eksik sistem paketlerini kurar (şifren sorulur): git, Python 3, pencere için gereken birkaç kütüphane.
   Ubuntu / Debian / Mint, Fedora, Arch / Manjaro ve openSUSE tanınır.
2. SOUND'u `~/.local/share/sound` klasörüne indirir.
3. Python paketlerini kurar (ilk seferde birkaç dakika, yaklaşık 300 MB).
4. Uygulama menüsüne **SOUND**'u ekler; terminalden `sound` komutuyla da açılır.
5. İstersen bilgisayar açılınca SOUND'un da açılmasını ayarlar.

Kitaplığını (favoriler, albümler) getirmek için: **Ayarlar → Hesap → SOUND hesabı** ile giriş yap; telefon ve
Windows'taki kitaplığınla otomatik eşitlenir.

## Kaldırma

```bash
bash ~/.local/share/sound/linux/uninstall.sh
```

Kitaplığını (indirilen şarkılar dahil) saklamak isteyip istemediğini sorar.

## Gereksinimler

- 64 bit Linux (x86_64), Python 3.10 ya da daha yeni
- Masaüstü ortamı (GNOME, KDE, XFCE, Cinnamon...; X11 ya da Wayland)

## Windows'tan farkları

| | Linux |
|---|---|
| Pencere | Qt WebEngine (Windows'taki Edge WebView2 ile aynı Chromium motoru) |
| Medya tuşları, kilit ekranı / bildirim medya kartı | MPRIS: GNOME, KDE ve diğerlerinin medya kontrolleri |
| Görev çubuğu küçük resim düğmeleri (⏮ ⏯ ⏭) | Yok (Windows'a özel) |
| Uygulama ikonunun vurgu rengine boyanması | Yok (Windows'a özel) |
| Kişiselleştir → Arayüz boyutu | Yeniden başlatınca uygulanır (Windows'ta anında) |
| Silinen indirmeler | Çöp kutusuna gider |

## Dosyalar

- `install.sh` — kurulum (depodaki `linux/install.sh` ile aynı)
- `uninstall.sh` — kaldırma
- Uygulamanın kendisi GitHub'dan iner: <https://github.com/Sefikak/SOUND>
