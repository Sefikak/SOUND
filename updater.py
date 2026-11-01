"""yt-dlp'yi haftada bir arka planda günceller.

YouTube sık sık değişiyor; yt-dlp güncel tutulmazsa arama ve indirme bir gün aniden bozulur.
Yeni sürüm, çalışan uygulamaya değil bir sonraki açılışa yansır.
"""
import json
import os
import subprocess
import sys
import time

from library import DATA_DIR

STATE_FILE = os.path.join(DATA_DIR, "update.json")
PACKAGES = ["yt-dlp", "yt-dlp-ejs"]
EVERY = 7 * 24 * 3600
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _installed_version():
    result = subprocess.run([sys.executable, "-c", "import importlib.metadata as m; print(m.version('yt-dlp'))"],
                            capture_output=True, text=True, creationflags=NO_WINDOW, timeout=60)
    return result.stdout.strip() or None


def due():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return time.time() - json.load(f).get("checked", 0) > EVERY
    except (OSError, ValueError):
        return True


def update():
    """Güncellemeyi çalıştırır. (eski_sürüm, yeni_sürüm) döner; değişmediyse ikisi aynıdır."""
    before = _installed_version()
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "-q", "--disable-pip-version-check", *PACKAGES],
                   capture_output=True, creationflags=NO_WINDOW, timeout=600)
    after = _installed_version()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"checked": time.time(), "version": after}, f)
    return before, after
