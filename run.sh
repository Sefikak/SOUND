#!/bin/sh
# SOUND'u Linux'ta başlatır. linux/install.sh bunu uygulama menüsüne ve ~/.local/bin/sound'a bağlar.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "SOUND kurulu değil: önce linux/install.sh dosyasını çalıştır." >&2
    exit 1
fi
exec ./.venv/bin/python main.py "$@"
