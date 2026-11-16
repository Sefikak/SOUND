#!/usr/bin/env bash
# SOUND'u Linux'tan kaldırır. Kitaplığını (favoriler, albümler, indirilen şarkılar) saklamak istersen sorar.
set -euo pipefail
DEST="${SOUND_HOME:-$HOME/.local/share/sound}"
ask() {
    local answer default="$2"
    if [ -r /dev/tty ]; then read -r -p "$1 [$( [ "$default" = e ] && echo E/h || echo e/H )] " answer </dev/tty || answer=""; fi
    answer="${answer:-$default}"
    [[ "$answer" =~ ^[eEyY] ]]
}

pkill -f "$DEST/main.py" 2>/dev/null || true
rm -f "$HOME/.local/share/applications/sound.desktop" "$HOME/.config/autostart/sound.desktop" \
      "$HOME/.local/share/icons/hicolor/256x256/apps/sound.png"
[ -L "$HOME/.local/bin/sound" ] && rm -f "$HOME/.local/bin/sound"

if [ -d "$DEST" ]; then
    if [ -d "$DEST/data" ] && ask "Kitaplığın (favoriler, albümler, indirilen şarkılar) saklansın mı?" e; then
        backup="$HOME/SOUND-kitaplik"
        rm -rf "$backup"
        mv "$DEST/data" "$backup"
        echo "Kitaplığın şuraya taşındı: $backup (tekrar kurunca $DEST/data olarak geri koyabilirsin)"
    fi
    rm -rf "$DEST"
fi
echo "SOUND kaldırıldı."
