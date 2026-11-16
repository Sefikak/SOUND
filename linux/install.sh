#!/usr/bin/env bash
# SOUND Linux kurulumu. Kullanım:  bash install.sh
# İnternetten tek komutla:  curl -fsSL https://raw.githubusercontent.com/Sefikak/SOUND/main/linux/install.sh | bash
#
# Ne yapar: eksik sistem paketlerini kurar (sudo sorar), SOUND'u GitHub'dan ~/.local/share/sound'a indirir
# (bilgisayardaki gibi kendini günceller), Python ortamını kurar, uygulama menüsüne SOUND'u ekler.
set -euo pipefail

REPO="https://github.com/Sefikak/SOUND.git"
DEST="${SOUND_HOME:-$HOME/.local/share/sound}"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"
BIN="$HOME/.local/bin"

say()  { printf '\n\033[1;35m==>\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31mHata:\033[0m %s\n' "$*" >&2; exit 1; }
has()  { command -v "$1" >/dev/null 2>&1; }
ask()  { # ask "soru" varsayılan(e/h) → 0 evet, 1 hayır; terminal yoksa varsayılan
    local answer default="$2"
    if [ -r /dev/tty ]; then read -r -p "$1 [$( [ "$default" = e ] && echo E/h || echo e/H )] " answer </dev/tty || answer=""; fi
    answer="${answer:-$default}"
    [[ "$answer" =~ ^[eEyY] ]]
}

[ "$(uname -s)" = Linux ] || fail "Bu betik Linux içindir."
case "$(uname -m)" in
    x86_64|amd64) ;;
    *) say "Uyarı: $(uname -m) işlemcide denenmedi; pencere için gereken Qt WebEngine paketi bulunamayabilir." ;;
esac

say "Sistem paketleri denetleniyor"
# git, python3 + venv; Qt6 WebEngine penceresi için xcb, nss, alsa, xkbfile, egl; çöp kutusu için gio
need_sys=0
has git || need_sys=1
has python3 || need_sys=1
python3 -c 'import venv, ensurepip' >/dev/null 2>&1 || need_sys=1
for lib in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-keysyms.so.1 libxcb-shape.so.0 libnss3.so libasound.so.2 libxkbfile.so.1; do
    ldconfig -p 2>/dev/null | grep -qF "$lib" || need_sys=1
done
if [ "$need_sys" = 1 ]; then
    if has apt-get; then
        sudo apt-get update
        # Ubuntu 24.04+ / Debian 13'te ALSA paketinin adı libasound2t64
        asound=libasound2; apt-cache show libasound2t64 >/dev/null 2>&1 && asound=libasound2t64
        sudo apt-get install -y git python3 python3-venv python3-pip libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
            libxcb-shape0 libxcb-randr0 libxcb-render-util0 libxcb-image0 libxcb-xkb1 libnss3 libxkbcommon-x11-0 \
            "$asound" libxkbfile1 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libgbm1 libegl1 libgl1 libglib2.0-bin
    elif has dnf; then
        sudo dnf install -y git python3 xcb-util-cursor xcb-util-wm xcb-util-keysyms xcb-util-image xcb-util-renderutil \
            nss alsa-lib libxkbfile libxkbcommon-x11 mesa-libEGL mesa-libgbm glib2
    elif has pacman; then
        sudo pacman -S --needed --noconfirm git python xcb-util-cursor xcb-util-wm xcb-util-keysyms xcb-util-image \
            xcb-util-renderutil nss alsa-lib libxkbfile libxkbcommon-x11 libglvnd mesa glib2
    elif has zypper; then
        sudo zypper install -y git python3 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-image0 \
            libxcb-render-util0 mozilla-nss libasound2 libxkbfile1 libxkbcommon-x11-0 Mesa-libEGL1 libgbm1 glib2-tools
    else
        fail "Paket yöneticin tanınmadı. git, python3 (venv ile) ve libxcb-cursor kurup tekrar çalıştır."
    fi
fi
python3 - <<'PY' || fail "Python 3.10 ya da daha yenisi gerekli."
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY

say "SOUND indiriliyor: $DEST"
if [ -d "$DEST/.git" ]; then
    git -C "$DEST" pull --ff-only || say "Güncelleme atlandı (yerelde değişiklik var); var olan kod kullanılıyor."
else
    mkdir -p "$(dirname "$DEST")"
    git clone "$REPO" "$DEST"
fi
chmod +x "$DEST/run.sh"

say "Python ortamı kuruluyor (ilk seferde birkaç dakika sürer, ~300 MB)"
[ -x "$DEST/.venv/bin/python" ] || python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/python" -m pip install --upgrade --quiet pip
"$DEST/.venv/bin/python" -m pip install --quiet -r "$DEST/requirements.txt"

say "Uygulama menüsüne ekleniyor"
mkdir -p "$APPS" "$ICONS" "$BIN"
cp "$DEST/assets/icon.png" "$ICONS/sound.png"
ln -sf "$DEST/run.sh" "$BIN/sound"
desktop_entry() {
    cat <<DESKTOP
[Desktop Entry]
Type=Application
Name=SOUND
GenericName=Müzik çalar
Comment=YouTube ve YouTube Music'ten müzik
Exec=$DEST/run.sh
Icon=sound
Terminal=false
Categories=AudioVideo;Audio;Player;
DESKTOP
}
desktop_entry >"$APPS/sound.desktop"
has update-desktop-database && update-desktop-database "$APPS" >/dev/null 2>&1 || true
has gtk-update-icon-cache && gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true

if ask "Bilgisayar açılınca SOUND da açılsın mı?" h; then
    mkdir -p "$HOME/.config/autostart"
    desktop_entry >"$HOME/.config/autostart/sound.desktop"
    say "Açılışta başlatma eklendi (kaldırmak için: rm ~/.config/autostart/sound.desktop)"
fi

say "Kurulum tamam!"
echo "  • Uygulama menüsünden SOUND'u aç ya da terminalde: sound"
echo "  • SOUND kendini GitHub'dan günceller (Ayarlar > Güncelleme)."
echo "  • Kitaplığını getirmek için: Ayarlar > Hesap > SOUND hesabı ile giriş yap."
echo "  • Kaldırmak için: bash $DEST/linux/uninstall.sh"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "  • Not: 'sound' komutu için $BIN PATH'e eklenmeli (çoğu dağıtımda yeniden girişte olur).";; esac
