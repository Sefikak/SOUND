"""Bilgisayar açılınca SOUND'u başlatma (Ayarlar > Arka plan).

Windows: HKCU\\...\\Run altında "SOUND" değeri; kurulum sihirbazının Başlangıç klasörüne koyduğu kısayol da
tanınır, kapatınca o da silinir. Linux: ~/.config/autostart/sound.desktop (linux/install.sh ile aynı biçim).
Açılışta başlatılınca pencere küçültülmüş açılır (--startup).
"""
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "SOUND"
STARTUP_FLAG = "--startup"


def _startup_shortcut():
    return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", NAME + ".lnk")


def _desktop_file():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "autostart", "sound.desktop")


def _command():
    if os.name == "nt":
        wscript = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")
        return f'"{wscript}" "{os.path.join(APP_DIR, "run.vbs")}" {STARTUP_FLAG}'
    return f'"{os.path.join(APP_DIR, "run.sh")}" {STARTUP_FLAG}'


def supported():
    return os.name == "nt" or sys.platform.startswith("linux")


def enabled():
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, NAME)
                return True
        except OSError:
            return os.path.exists(_startup_shortcut())
    return os.path.exists(_desktop_file())


def set_enabled(on):
    """Açar ya da kapatır; sonucu (gerçek durum) döndürür."""
    if os.name == "nt":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if on:
                winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, NAME)
                except OSError:
                    pass
        if not on and os.path.exists(_startup_shortcut()):
            os.remove(_startup_shortcut())
    elif sys.platform.startswith("linux"):
        path = _desktop_file()
        if on:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nType=Application\nName=SOUND\nComment=Müzik\n"
                        f"Exec={_command()}\nIcon=sound\nTerminal=false\nCategories=AudioVideo;Audio;Player;\n"
                        "X-GNOME-Autostart-enabled=true\n")
        elif os.path.exists(path):
            os.remove(path)
    return enabled()


def launched_at_startup():
    return STARTUP_FLAG in sys.argv[1:]
