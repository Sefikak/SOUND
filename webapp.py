"""SOUND: pencere (pywebview + Windows'un Edge WebView2 motoru) ve arayüze açılan Python tarafı.

Arayüz web/ klasöründe (HTML/CSS/JS). Ses ve video arayüzün içindeki oynatıcıyla çalınır: indirilmiş
şarkılar diskten, diğerleri YouTube'dan doğrudan akış olarak. Python tarafı arama, indirme, kitaplık,
öneriler, YouTube hesabı ve Windows entegrasyonunu (görev çubuğu butonları, medya tuşları) yürütür.
"""
import ctypes
try:
    import ctypes.wintypes  # yalnızca Windows'ta kullanılıyor; bazı Linux/Android Python'larında yüklenemiyor
except (ImportError, ValueError):
    pass
import json
import os
import queue
import shutil
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

# Sonraki şarkıya kendiliğinden geçerken tarayıcının "önce kullanıcı tıklasın" kuralı engel olmasın
# Tarayıcı motorunun kendi medya oturumunu kapat: yoksa Windows iki oturum görür, kulaklık / klavye medya
# tuşları SOUND yerine motorun oturumuna gidip kaybolur (mediakeys.py tek yetkili oturum olsun)
# arka plan kısıtlamaları kapalı: pencere küçültülünce ya da tepsiye inince zamanlayıcılar (geçiş, sıradakini hazırlama) yavaşlamasın
BROWSER_FLAGS = ("--autoplay-policy=no-user-gesture-required --disable-features=HardwareMediaKeyHandling,MediaSessionService "
                 "--disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows")
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", BROWSER_FLAGS)  # Windows (Edge WebView2)
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", BROWSER_FLAGS)  # Linux (Qt WebEngine; medya tuşları mpris.py'de)
IS_WINDOWS = os.name == "nt"

import webview

import cloud
import listen
import devices
import social
import downloader
import lyricsfinder
import mediakeys
import mediaserver
import selfupdate
import updater
if IS_WINDOWS:
    import wintaskbar
else:
    wintaskbar = None  # görev çubuğu düğmeleri yalnızca Windows'ta
from library import DATA_DIR, Library
import importer
from recommender import build_home, mix_for
from searcher import (_norm, artist_page, artist_radio, clean_channel, find_artist, playlist_tracks, release_songs,
                      remove_duplicates, search_albums,
                      search_artists, search_playlists, search_songs, search_tracks)

APP_ID = "SOUND.MusicPlayer"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE_DIR, "assets")
ICON = os.path.join(ASSETS, "icon.ico")
ICON_PNG = os.path.join(ASSETS, "icon.png")  # Linux pencere / uygulama menüsü ikonu
DEFAULT_ACCENT = "#8b5cf6"
SESSION_FILE = os.path.join(DATA_DIR, "session.json")
HOME_REFRESH_AFTER = 3 * 3600
STREAM_MARGIN = 120  # akış adresinin bitmesine bu kadar saniye kala yenisini al
STREAM_WAIT = 30     # internet kesilince adres araması asılı kalabilir: en fazla bu kadar saniye beklenir
THUMBBAR_ICONS = ("tb_prev", "tb_play", "tb_pause", "tb_next", "tb_shuffle", "tb_shuffle_on",
                  "tb_repeat", "tb_repeat_on", "tb_repeat_one")


def shorten(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def friendly_error(error):
    text = str(error)
    if any(key in text for key in ("getaddrinfo", "urlopen", "timed out", "Failed to resolve", "NameResolution")):
        return "İnternet bağlantısı yok gibi görünüyor."
    if "oturumu geçersiz" in text:
        return "YouTube oturumu geçersiz — çerezleri gizli pencereden yeniden dışa aktar."
    if "Sign in to confirm your age" in text:
        return "YouTube bu video için yaş doğrulaması istiyor."
    if "age-restricted" in text:
        return "Video yaş kısıtlamalı; YouTube hesabının yaşı doğrulanmamış olabilir."
    if downloader.is_unavailable_error(error):
        return "Bu video YouTube'da artık yok ya da bu bölgede engelli."
    return shorten(text.replace("ERROR: ", ""), 110)


def recycle(paths):
    """Dosyaları kalıcı silmek yerine Geri Dönüşüm Kutusu'na (Linux'ta çöp kutusuna) taşı (geri alınabilsin)."""
    if not paths:
        return True
    if not IS_WINDOWS:
        import subprocess
        try:
            return subprocess.run(["gio", "trash", "--", *paths], capture_output=True, timeout=60).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False  # gio yoksa dosyalar yerinde kalır (kalıcı silmektense)
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    operation = SHFILEOPSTRUCTW(wFunc=FO_DELETE, pFrom="\0".join(paths) + "\0\0",
                                fFlags=FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI)
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation)) == 0


IS_WSL = not IS_WINDOWS and bool(os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"))


def _windows_open(target, url=False):
    """WSL'de: Windows tarafının varsayılan uygulamasıyla açar (Linux'ta tarayıcı/dosya yöneticisi yok).
    Bağlantılar rundll32 url.dll ile: explorer.exe ?/& içeren uzun adresi tanımayıp Belgeler'i açıyor."""
    import subprocess
    command = ["rundll32.exe", "url.dll,FileProtocolHandler", target] if url else ["explorer.exe", target]
    try:
        # Windows programı Linux klasöründe başlarsa UNC yolu uyarısı verir; /mnt/c'den başlat
        subprocess.Popen(command, start_new_session=True, cwd="/mnt/c" if os.path.isdir("/mnt/c") else None,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


# GoodbyeDPI (Türkiye'de yaygın DPI aşma aracı) bazı ayarlarda YouTube'un ses sunucusuna (googlevideo.com)
# giden bağlantıyı da bozuyor; bu bir sürücü düzeyinde olduğu için uygulamadan aşılamıyor. Şarkı çalınamazsa
# arayüz buna bakıp kullanıcıya GoodbyeDPI'yi yalnızca engelli sitelere uygulamayı anlatıyor.
DPI_BLACKLIST = ["discord.com", "discord.gg", "discordapp.com", "discordapp.net", "discord.media",
                 "wattpad.com", "imgur.com", "pastebin.com", "roblox.com"]
_dpi_cache = [0.0, None]


def _hidden_run(command, timeout=10):
    import subprocess
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, errors="replace",
                          creationflags=0x08000000)  # CREATE_NO_WINDOW


def goodbyedpi_info():
    """{"running", "service", "folder", "args"} — GoodbyeDPI çalışıyor mu, hangi klasörde, hangi ayarla."""
    if not IS_WINDOWS:
        return {"running": False}
    if time.time() - _dpi_cache[0] < 10 and _dpi_cache[1]:
        return _dpi_cache[1]
    info = {"running": False, "service": False, "folder": None, "args": ""}
    try:
        out = _hidden_run(["tasklist", "/FI", "IMAGENAME eq goodbyedpi.exe", "/NH", "/FO", "CSV"]).stdout
        info["running"] = "goodbyedpi.exe" in out.lower()
        if info["running"]:
            # hizmet olarak kurulduysa yolu ve ayarları hizmet kaydında (yönetici gerekmez)
            config = _hidden_run(["sc", "qc", "GoodbyeDPI"]).stdout
            line = next((l for l in config.splitlines() if "BINARY_PATH_NAME" in l), "")
            if line:
                command = line.split(":", 1)[1].strip()
                exe_end = command.lower().find("goodbyedpi.exe") + len("goodbyedpi.exe")
                exe = command[:exe_end].strip('" ')
                info.update(service=True, exe=exe, args=command[exe_end:].strip('" '),
                            folder=os.path.dirname(os.path.dirname(exe)))  # ...\GoodbyeDPI\x86_64\goodbyedpi.exe
    except Exception:
        pass
    _dpi_cache[:] = [time.time(), info]
    return info


def goodbyedpi_fixed_args(args):
    """Mevcut ayardan bağlantıyı bozan kipleri (-1..-9, --set-ttl N, --auto-ttl [a-b-c], --min-ttl N) ve eski
    --blacklist'i atar; DNS yönlendirmesi gibi geri kalanı aynen bırakır. Başına -9 + blacklist eklenecek."""
    tokens = (args or "").split()
    kept, i = [], 0
    while i < len(tokens):
        token = tokens[i]
        has_value = i + 1 < len(tokens) and not tokens[i + 1].startswith("-")
        if token in ("--set-ttl", "--min-ttl", "--blacklist", "--auto-ttl"):
            i += 2 if has_value else 1
            continue
        if not (len(token) == 2 and token[0] == "-" and token[1].isdigit()):
            kept.append(token)
        i += 1
    return " ".join(kept)


def goodbyedpi_write_blacklist(folder):
    """GoodbyeDPI klasörüne blacklist.txt yazar (varsa dokunmaz)."""
    path = os.path.join(folder, "blacklist.txt")
    if os.path.exists(path):
        return {"path": path, "existed": True}
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(DPI_BLACKLIST) + "\n")
    return {"path": path, "existed": False}


def goodbyedpi_fix():
    """Hizmeti -9 + blacklist ile yeniden yapılandırır (Windows yönetici izni sorar). DNS ayarları korunur."""
    info = goodbyedpi_info()
    if not info.get("service") or not info.get("exe"):
        return {"error": "GoodbyeDPI hizmet olarak kurulu değil; adımları elle uygula"}
    blacklist = goodbyedpi_write_blacklist(info["folder"])["path"]
    # sc config binPath= "\"...\goodbyedpi.exe\" -9 --blacklist \"...\blacklist.txt\" --dns-addr ..."
    inner = f'\\"{info["exe"]}\\" -9 --blacklist \\"{blacklist}\\" {goodbyedpi_fixed_args(info["args"])}'.rstrip()
    command = f'"{inner}"'
    script = os.path.join(DATA_DIR, "goodbyedpi_fix.cmd")
    with open(script, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("@echo off\nchcp 65001 >nul\nsc stop GoodbyeDPI >nul\nping -n 3 127.0.0.1 >nul\n"
                f"sc config GoodbyeDPI binPath= {command}\nsc start GoodbyeDPI >nul\n")
    try:
        run = _hidden_run(["powershell", "-NoProfile", "-Command",
                           "Start-Process cmd -ArgumentList '/c \"\"{}\"\"' -Verb RunAs -Wait -WindowStyle Hidden"
                           .format(script.replace("'", "''"))], timeout=180)  # izin penceresini bekler
    except Exception:
        return {"error": "Yönetici izni alınamadı"}
    _dpi_cache[0] = 0
    if run.returncode != 0:
        return {"error": "Yönetici izni verilmedi"}
    time.sleep(1.5)
    after = goodbyedpi_info()
    if "--blacklist" not in after.get("args", ""):
        return {"error": "Ayar değiştirilemedi; adımları elle uygula"}
    return {"ok": True, "running": after["running"]}


def open_path(path):
    """Dosyayı/klasörü sistemin varsayılan uygulamasıyla açar."""
    if IS_WINDOWS:
        os.startfile(path)
        return
    import subprocess
    if IS_WSL:
        try:
            windows_path = subprocess.run(["wslpath", "-w", path], capture_output=True, text=True,
                                          timeout=10).stdout.strip()
            if windows_path and _windows_open(windows_path):
                return
        except (OSError, subprocess.SubprocessError):
            pass
    subprocess.Popen(["xdg-open", path], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_browser(url):
    """Bağlantıyı varsayılan tarayıcıda açar; açılamadıysa False."""
    if IS_WSL and _windows_open(url, url=True):
        return True
    try:
        # Android'de webbrowser yerine native.openUrl konuyor ve None döndürüyor: yalnızca açık False başarısızlık
        return webbrowser.open(url) is not False
    except Exception:
        return False


def login_page(ok, title, detail, ui=None, focus=False, back=None):
    """Tarayıcıdaki giriş dönüş sayfası (web/login_done.html): uygulamanın alev paletiyle yanan alev,
    logo, sonuç yazısı. "SOUND'a dön" düğmesi: focus=True ise masaüstünde POST /focus pencereyi öne alır,
    back verilirse (telefonda "soundapp://back") o bağlantı açılır ve Android uygulamayı öne getirir."""
    import base64
    ui = ui if isinstance(ui, dict) else {}
    cfg = {"ok": bool(ok), "title": title, "detail": detail, "focus": bool(focus), "back": back or None,
           "flame": ui.get("flame") or "fire", "accent": ui.get("accent") or DEFAULT_ACCENT, "calm": bool(ui.get("calm"))}
    try:
        with open(os.path.join(mediaserver.WEB_DIR, "login_done.html"), encoding="utf-8") as f:
            page = f.read()
        with open(os.path.join(mediaserver.WEB_DIR, "login_logo.png"), "rb") as f:
            logo = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return (f"<meta charset='utf-8'><h2 style='font-family:sans-serif'>{title}</h2>").encode("utf-8")
    # JSON'u <script> içine koyarken "</" kapanış etiketini bozmasın
    data = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    return page.replace("__CFG__", data).replace("__LOGO__", logo).encode("utf-8")


def plain_track(track):
    return {key: track.get(key) for key in ("id", "title", "artist", "duration", "thumbnail", "url")}


class Backend:
    def __init__(self):
        self.lib = Library()
        threading.Thread(target=self.lib.tidy_covers, daemon=True).start()  # kullanılmayan kapak resimleri
        downloader.set_auth(self.lib.data.get("youtube_auth"))
        self.window = None
        self.app_return_url = None  # telefonda android_main "soundapp://back" koyar (giriş sayfasındaki düğme)
        self.hwnd = None
        self.closing = False
        self.quitting = False  # tepsiden Çıkış / yeniden başlatma: kapatma tepsiye indirmesin
        self.tray = None       # tray.Tray; kurulamadıysa None (pencereyi kapatmak uygulamayı kapatır)
        self.tray_menu = None  # TrayMenu (Windows): tepsideki temalı sağ tık menüsü
        self.tray_now = {}     # menü için çalan şarkı
        self.started = False
        self.events = queue.Queue()
        self.win = ThreadPoolExecutor(1)        # Windows görev çubuğu / medya kartı işleri tek iş parçacığında
        self.stream_pool = ThreadPoolExecutor(2)    # tıklanan şarkı: önden hazırlıkları beklemesin
        self.prefetch_pool = ThreadPoolExecutor(2)  # önden hazırlık (arama sonuçları, sıradaki, üzerinde durulan)
        self.cache_pool = ThreadPoolExecutor(1)     # dinlenen şarkıları önbelleğe indirme
        self.download_pool = ThreadPoolExecutor(3)
        self.streams = {}          # şarkı kimliği -> akış bilgisi (arayüze verilen yerel adreslerle)
        self.stream_count = 0
        self.stream_jobs = {}      # şarkı kimliği -> Future
        self.stream_lock = threading.Lock()
        self.download_progress = {}  # anahtar ("kimlik" ya da "kimlik:video") -> 0..1, None: sırada
        self.download_jobs = {}
        self.download_failed = {}
        self.download_lock = threading.Lock()
        self.playlists = {}
        self.artists = {}
        self.importing = False
        self.login_window = None
        self.radios = {}
        self.track_info = {}
        self.home_loading = False
        self.home_error = None
        self.thumbbar = None
        self.media = None
        self.app_update = None  # indirilmiş, yeniden başlatma bekleyen güncelleme
        self._self_update_lock = threading.Lock()
        self.media_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="media")
        self.shown_title = None
        self.session = self._load_session()
        self.geometry = _sane_geometry(self.session.get("window"))
        self.lib.subscribe(lambda: self.push("library", self.snapshot()))
        self.cloud = cloud.Cloud(self.lib, lambda status: self.push("cloud", status))
        self.cloud_login = None  # Google girişinin dönüşünü bekleyen yerel sunucu
        self.listen = listen.Listen(lambda event: self.push("listen", event))
        self.devices = devices.Devices(self.cloud, lambda event: self.push("devices", event))
        self.social = social.Social(self.cloud, self.lib, lambda event: self.push("social", event))
        self.presence = None
        if IS_WINDOWS or sys.platform.startswith("linux"):  # telefonda Discord IPC yok
            try:
                import discordrpc
                self.presence = discordrpc.Presence(self.lib.settings.get("discord_presence", True) is not False)
            except Exception:
                self.presence = None
        threading.Thread(target=self._event_loop, daemon=True).start()

    # ---------- arayüze bildirim ----------

    def push(self, kind, data=None):
        self.events.put({"type": kind, "data": data})

    def toast(self, message, error=False):
        self.push("toast", {"message": message, "error": error})

    def _event_loop(self):
        while True:
            event = self.events.get()
            if self.window is None or self.closing:
                continue
            try:
                self.window.evaluate_js(f"window.SOUND && SOUND.receive({json.dumps(event, ensure_ascii=False)})")
            except Exception:
                pass

    def snapshot(self):
        data = self.lib.data
        return {
            "tracks": data["tracks"],
            "favorites": data["favorites"],
            "albums": data["albums"],
            "folders": data["folders"],
            "album_covers": data["album_covers"],
            "added": data["added"],  # listeye eklenme zamanları ("Son eklenen" sıralaması)
            "recent": [t["id"] for t in self.lib.recent_tracks(30)],
            "history": [e["id"] for e in data["history"]],
            "top_artists": [[artist, track["id"]] for artist, track in self.lib.top_artists(12)],
            "recent_searches": data["recent_searches"],
            "undo": self.lib.undo_label,
            "undo_seq": self.lib.undo_seq,
        }

    def downloads_state(self):
        with self.download_lock:
            return {
                "progress": dict(self.download_progress),
                "active": [{"key": k, "track": j["track"], "kind": j["kind"]} for k, j in self.download_jobs.items()],
                "failed": [{"key": k, **f} for k, f in self.download_failed.items()],
            }

    # ---------- oturum ----------

    def _load_session(self):
        try:
            with open(SESSION_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_session(self, state=None):
        if state is not None:
            self.session.update(state)
        self.session["window"] = self.geometry
        try:
            temp = SESSION_FILE + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(self.session, f, ensure_ascii=False)
            os.replace(temp, SESSION_FILE)
        except (OSError, TypeError, ValueError):
            pass

    # ---------- pencere ----------

    def on_shown(self):
        if not IS_WINDOWS:
            self.media_thread.submit(self._setup_media)  # Linux: MPRIS medya kontrolleri
            return
        hwnd = None
        try:
            hwnd = int(self.window.native.Handle.ToInt64())
        except Exception:
            pass
        if not hwnd:
            return
        self.hwnd = hwnd
        self.ensure_on_screen()
        self.set_app_icon((self.lib.settings.get("ui") or {}).get("accent"))
        self.win.submit(self._setup_windows_controls)

    def set_app_icon(self, accent=None):
        """Pencere / görev çubuğu ikonu: Kişiselleştir'de vurgu rengi seçildiyse o renge boyanmış ikon."""
        if not self.hwnd:
            return False
        path = ICON
        if isinstance(accent, str) and len(accent) == 7 and accent.startswith("#") and accent.lower() != DEFAULT_ACCENT:
            try:
                int(accent[1:], 16)
                from widgets import tinted_icon_file
                path = tinted_icon_file(accent, os.path.join(DATA_DIR, "icons")) or ICON
            except (ValueError, OSError, ImportError):
                path = ICON
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p)
        user32.DestroyIcon.argtypes = (ctypes.c_void_p,)
        old = getattr(self, "_icon_handles", [])
        self._icon_handles = []
        # ICON_SMALL / ICON_BIG, ekran ölçeğine uygun boyutlarda
        for which, metric in ((0, 49), (1, 11)):  # SM_CXSMICON, SM_CXICON
            size = user32.GetSystemMetrics(metric) or (16 if which == 0 else 32)
            handle = user32.LoadImageW(None, path, 1, size, size, 0x10)
            if handle:
                user32.SendMessageW(self.hwnd, 0x0080, which, handle)  # WM_SETICON
                self._icon_handles.append(handle)
        for handle in old:
            user32.DestroyIcon(handle)
        command = f'wscript.exe "{os.path.join(BASE_DIR, "run.vbs")}"'
        # Görev çubuğu ikonu kimliğe (AppUserModelID) göre önbelleğe alınır ve aynı kimlik için bir daha okunmaz;
        # bu yüzden her renk kendi kimliğini kullanır (varsayılan morda asıl kimlik)
        app_id = APP_ID if path == ICON else f"{APP_ID}.{os.path.splitext(os.path.basename(path))[0]}"
        try:
            wintaskbar.set_window_identity(self.hwnd, app_id, path, "SOUND", command)
            self._icon_path = path
        except OSError:
            pass
        return True

    def _setup_windows_controls(self):
        ctypes.windll.ole32.CoInitialize(None)
        icons = {name: os.path.join(ASSETS, name + ".ico") for name in THUMBBAR_ICONS}
        if not all(os.path.exists(path) for path in icons.values()):
            from widgets import ensure_thumbbar_icons
            icons = ensure_thumbbar_icons()
        try:
            self.thumbbar = wintaskbar.ThumbBar(self.hwnd, icons, self._thumbbar_click, self.win.submit)
            time.sleep(0.6)
            self.thumbbar.add()
        except OSError:
            self.thumbbar = None
        # Medya kontrolleri kendi iş parçacığında (MTA): bu iş parçacığı CoInitialize ile STA ve mesaj döngüsü yok;
        # STA'da kurulunca kulaklık / klavye medya tuşlarının olayları hiç ulaşmıyordu
        self.media_thread.submit(self._setup_media)

    def _setup_media(self):
        if IS_WINDOWS:
            self.media = mediakeys.create(lambda job: job(), lambda action: self.push("command", action))
        else:
            import mpris
            self.media = mpris.create(lambda action: self.push("command", action), self.focus_window)

    def _thumbbar_click(self, button_id):
        bar = wintaskbar.ThumbBar
        action = {bar.PREV: "previous", bar.NEXT: "next", bar.SHUFFLE: "shuffle", bar.REPEAT: "repeat"}.get(button_id, "toggle")
        self.push("command", action)

    def player_state(self, state):
        """Arayüzdeki çalma durumu değişti: görev çubuğu, medya kartı ve pencere başlığı."""
        track = state.get("track")
        playing, loading = bool(state.get("playing")), bool(state.get("loading"))
        shuffle, repeat = bool(state.get("shuffle")), state.get("repeat") or "off"

        def apply():
            if self.thumbbar:
                self.thumbbar.set_state(playing or loading, shuffle, repeat)

        def apply_media():
            if self.media:
                try:
                    self.media.update(track, playing, loading)
                except Exception:
                    pass
        self.win.submit(apply)
        self.media_thread.submit(apply_media)
        if self.presence:
            self.presence.update(track, playing and not loading, state.get("position") or 0)
        self.tray_now = {"track": track, "playing": playing or loading}
        if self.tray:
            artist = f" — {track['artist']}" if track and track.get("artist") else ""
            self.tray.set_state(f"{track['title']}{artist}" if track else "SOUND", playing or loading)
        title = f"{track['title']} · SOUND" if track else "SOUND"
        if title != self.shown_title and self.window:
            self.shown_title = title
            try:
                self.window.set_title(title)
            except Exception:
                pass

    def _minimized(self):
        # küçültülmüş pencere Windows'ta -32000'e taşınır ve 160x28 olur; bunu kaydedersek sonraki açılışta
        # pencere ekranın dışında açılır ("uygulama açık ama pencere yok")
        return bool(IS_WINDOWS and self.hwnd and ctypes.windll.user32.IsIconic(self.hwnd))

    def on_moved(self, x, y):
        if not self.geometry.get("maximized") and not self._minimized() and x > -10000 and y > -10000:
            self.geometry.update(x=x, y=y)

    def on_resized(self, width, height):
        if not self.geometry.get("maximized") and not self._minimized() and width >= 400 and height >= 300:
            self.geometry.update(width=width, height=height)

    def ensure_on_screen(self):
        """Pencere hiçbir ekranda görünmüyorsa (ikinci ekran çıkarıldı, bozuk konum kaydı) ana ekranın ortasına al."""
        if not IS_WINDOWS or not self.hwnd:
            return
        user32 = ctypes.windll.user32
        if user32.IsIconic(self.hwnd):
            return  # küçültülmüşse geri açılınca eski (görünür) yerine döner
        rect = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return
        # başlık çubuğu bir ekrana değiyor mu (yoksa pencere tutulup çekilemez)
        title = ctypes.wintypes.RECT(rect.left + 40, rect.top, rect.right - 40, rect.top + 30)
        if user32.MonitorFromRect(ctypes.byref(title), 0):  # MONITOR_DEFAULTTONULL
            return
        area = ctypes.wintypes.RECT()
        user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)  # SPI_GETWORKAREA: ana ekran, görev çubuğu hariç
        width = min(rect.right - rect.left, area.right - area.left)
        height = min(rect.bottom - rect.top, area.bottom - area.top)
        if width < 400 or height < 300:
            width, height = min(1320, area.right - area.left), min(840, area.bottom - area.top)
        x = area.left + (area.right - area.left - width) // 2
        y = area.top + (area.bottom - area.top - height) // 2
        user32.SetWindowPos(self.hwnd, 0, x, y, width, height, 0x0004 | 0x0010)  # NOZORDER | NOACTIVATE

    def on_closing(self):
        if not self.geometry.get("maximized") and not self._minimized():
            try:
                w = self.window
                if w.x > -10000 and w.y > -10000 and w.width >= 400 and w.height >= 300:
                    self.geometry.update(x=w.x, y=w.y, width=w.width, height=w.height)
            except Exception:
                pass
        self.save_session()
        if self.tray and not self.quitting and self.lib.settings.get("tray", True):
            # kapatma tepsiye indirir: pencere gizlenir, çalma sürer. Gizleme kapanış olayı bittikten sonra
            # (olay arayüz iş parçacığını bekletiyor; içinden hide() çağırmak kilitlenir)
            threading.Timer(0.05, self._hide_to_tray).start()
            return False
        self.closing = True
        if self.tray:
            self.tray.stop()

    def _hide_to_tray(self):
        try:
            self.window.hide()
        except Exception:
            return
        if not self.lib.settings.get("tray_hint_shown"):
            self.lib.update_settings({"tray_hint_shown": True})
            self.tray.notify("SOUND arka planda çalmaya devam ediyor. Tamamen kapatmak için simgeye sağ tıklayıp "
                             "Çıkış'ı seç; bunu Ayarlar'dan kapatabilirsin.")

    def show_window(self):
        """Tepsiden ya da ikinci kez açılınca: gizli pencereyi geri getirip öne al. Uygulama kapanıyorsa
        (Çıkış, güncelleme sonrası yeniden başlatma) False: yeni açılan kopya kendisi açılsın."""
        if self.quitting or self.closing:
            return False

        def show():
            try:
                self.window.show()
            except Exception:
                pass
            self.focus_window()
            self.ensure_on_screen()
        threading.Thread(target=show, daemon=True).start()
        return True

    def notify(self, title, body, target=""):
        """Sistem bildirimi (yeni mesaj, arkadaşlık isteği, ortak dinleme daveti). Tıklanınca pencere öne gelir ve
        arayüz hedefi açar (target: "chat:<id>", "group:<id>", "social", "jam:<kod>"). Telefonda android_main değiştirir."""
        if not self.tray:
            return False

        def clicked():
            self.show_window()
            self.push("open_target", target)
        self.tray.notify(str(body)[:250], str(title)[:60] or "SOUND", clicked)
        return True

    def quit_app(self):
        self.quitting = True
        self.save_session()
        if self.tray:
            self.tray.stop()
        if self.tray_menu:
            self.tray_menu.destroy()
        try:
            self.window.destroy()
        finally:
            threading.Timer(3, lambda: os._exit(0)).start()  # pencere kapanmazsa da çık

    # ---------- açılış işleri ----------

    def start_background_jobs(self):
        threading.Thread(target=self._sync_music_folder, daemon=True).start()
        threading.Thread(target=self._trim_cache, daemon=True).start()
        threading.Timer(20, self._check_updates).start()
        threading.Thread(target=self._self_update_loop, daemon=True).start()
        self.cloud.start()
        self.cloud.sync_now()
        self.devices.start()
        self.social.start()
        self.ensure_home()

    def _trim_cache(self):
        downloader.trim_cache(int(self.lib.settings["cache_mb"]) * 1024 * 1024)

    def _sync_music_folder(self):
        self._delete_pending()
        self._purge_mp3_once()
        try:
            missing = downloader.scan_music_folder(self.lib.files_by_name())
        except Exception:
            return
        if missing:
            added = self.lib.restore_downloads(missing)
            if added:
                self.toast(f"{added} indirilen şarkı dosyalarından geri yüklendi")

    def _check_updates(self):
        if not updater.due():
            return
        try:
            before, after = updater.update()
        except Exception:
            return
        if after and before != after:
            self.toast(f"yt-dlp güncellendi ({before} → {after}), bir sonraki açılışta etkin")

    # ---------- uygulamanın kendi güncellemesi (GitHub) ----------

    SELF_UPDATE_EVERY = 30 * 60

    def _self_update_loop(self):
        time.sleep(12)  # açılışı yavaşlatmasın
        while not self.closing:
            if self.lib.settings.get("auto_update", True):
                self.run_self_update()
            for _ in range(self.SELF_UPDATE_EVERY):
                if self.closing:
                    return
                time.sleep(1)

    def run_self_update(self):
        with self._self_update_lock:
            if self.app_update and self.app_update.get("status") == "updated":
                return self.app_update  # zaten indirildi, yeniden başlatma bekleniyor
            result = selfupdate.check_and_update()
            if result.get("status") == "updated":
                self.app_update = result
                self.push("app_update", result)
            return result

    def restart_app(self):
        self.quitting = True
        self.save_session()
        selfupdate.restart()
        try:
            self.window.destroy()
        finally:
            threading.Timer(1.5, lambda: os._exit(0)).start()

    # ---------- ana sayfa ----------

    def home_state(self):
        cache = self.lib.home_cache or {}
        return {"sections": cache.get("sections") or [], "loading": self.home_loading, "error": self.home_error}

    def ensure_home(self, force=False):
        cache = self.lib.home_cache
        stale = (not cache or time.time() - cache["at"] > HOME_REFRESH_AFTER
                 or (cache["cold"] and self.lib.data["history"]))
        if (force or stale) and not self.home_loading:
            self.home_loading = True
            self.home_error = None
            threading.Thread(target=self._build_home, daemon=True).start()
        return self.home_state()

    def _build_home(self):
        recent = self.lib.recent_tracks(3)
        artists = self.lib.top_artists(2)
        known = self.lib.history_ids() | set(self.lib.data["favorites"])
        try:
            sections, cold = build_home(recent, artists, known)
        except Exception as error:
            sections, cold = None, False
            self.home_error = friendly_error(error)
        self.home_loading = False
        if sections:
            self.lib.set_home_cache(sections, cold)
        self.push("home", self.home_state())

    # ---------- akış (indirmeden çalma) ----------

    def stream(self, track, force=False, video=False):
        """Çalmak için ses (ve panel için görüntü) adresi. Şarkı önbellekteyse ses diskten gelir:
        anında başlar, internet gerekmez; görüntü istenirse yine YouTube'dan alınır."""
        track_id = track["id"]
        cached = downloader.cache_valid(track_id)
        if cached and not video and not force:
            return {"audio": f"/cache/{track_id}.webm", "video": None, "expire": 0, "alt": None, "cached": True}
        data = self._stream_remote(track, force)
        if cached and not data.get("error"):
            data = {**data, "audio": f"/cache/{track_id}.webm", "cached": True}
        return data

    def _stream_remote(self, track, force=False):
        track_id = track["id"]
        if not force:
            cached = self.streams.get(track_id)
            if cached and (not cached["expire"] or cached["expire"] - time.time() > STREAM_MARGIN):
                return cached
        future = self._stream_job(track, force)
        try:
            return future.result(timeout=STREAM_WAIT)
        except FutureTimeout:
            with self.stream_lock:  # asılı kalan iş sonraki denemeyi de bekletmesin
                if self.stream_jobs.get(track_id) is future:
                    self.stream_jobs.pop(track_id, None)
            return {"error": "İnternet bağlantısı yok", "offline": True}
        except Exception as error:
            return {"error": friendly_error(error), "age": downloader.is_age_error(error),
                    "unavailable": downloader.is_unavailable_error(error), "offline": downloader.is_network_error(error)}

    def _stream_job(self, track, force=False, prefetch=False):
        track_id = track["id"]
        with self.stream_lock:
            future = self.stream_jobs.get(track_id)
            if future is not None and not prefetch and getattr(future, "prefetch", False) and future.cancel():
                future = None  # henüz başlamamış bir ön hazırlıktı: sırada bekletme, hemen başlat
            if future is None or (force and future.done()):
                pool = self.prefetch_pool if prefetch else self.stream_pool
                future = pool.submit(self._resolve, plain_track(track))
                future.prefetch = prefetch
                self.stream_jobs[track_id] = future
            return future

    def _resolve(self, track):
        track_id = track["id"]
        try:
            info = downloader.resolve_stream(track)
            self.stream_count += 1  # yeni adres: oynatıcının önbelleği eskisini kullanmasın
            mediaserver.register_stream(track_id, "audio", info["audio"], info["audio_headers"], info["available_at"])
            data = {"audio": f"/stream/{track_id}/audio?n={self.stream_count}", "video": None,
                    "expire": info["expire"], "alt": info["alt"]}
            if info["video"]:
                mediaserver.register_stream(track_id, "video", info["video"], info["video_headers"], info["available_at"])
                data["video"] = f"/stream/{track_id}/video?n={self.stream_count}"
            self.streams[track_id] = data
            return data
        finally:
            with self.stream_lock:
                self.stream_jobs.pop(track_id, None)

    def prefetch(self, tracks, video=False):
        for track in tracks[:4]:
            cached = self.streams.get(track["id"])
            if (self.lib.is_downloaded(track["id"]) and not video) or (cached and cached["expire"] - time.time() > 1800):
                continue
            waiting = sum(1 for f in list(self.stream_jobs.values()) if getattr(f, "prefetch", False) and not f.running())
            if waiting >= 3:  # ağı boğmasın; en yenisi en olası tıklanacak olandır ama sıra uzamasın
                return
            self._stream_job(track, prefetch=True)

    def played(self, track):
        self.lib.add_history(plain_track(track))
        self.push("library", self.snapshot())
        self.cache_pool.submit(self._cache_track, track["id"])

    def _cache_track(self, track_id):
        """Dinlenen şarkının sesini arka planda önbelleğe indir: tekrar dinlemek anında ve internetsiz olur."""
        if self.lib.is_downloaded(track_id) or downloader.cache_valid(track_id):
            return
        source = mediaserver.stream_source(track_id, "audio")
        if not source:
            return
        url, headers, available_at = source
        wait = available_at - time.time()
        if wait > 0:
            time.sleep(wait + 0.2)
        try:
            downloader.cache_stream(track_id, url, headers, lambda: self.closing)
        except Exception:
            return
        self._trim_cache()

    def fetch_track_info(self, track):
        track_id = track["id"]
        if track_id in self.track_info:
            return self.track_info[track_id]
        data = {}
        try:
            import yt_dlp
            options = {"quiet": True, "no_warnings": True, "skip_download": True, **downloader.JS_OPTIONS}
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(track["url"], download=False, process=False)
            description = "\n".join(line for line in (info.get("description") or "").splitlines()
                                    if line.strip() and "http" not in line)
            data = {
                "artist": info.get("artist") or info.get("creator"),
                "album": info.get("album"),
                "year": info.get("release_year") or (info.get("upload_date") or "")[:4] or None,
                "views": info.get("view_count"),
                "followers": info.get("channel_follower_count"),
                "channel": clean_channel(info.get("channel") or info.get("uploader")) or None,
                "channel_url": info.get("channel_url") or info.get("uploader_url"),
                "description": shorten(description, 320) if description else "",
            }
            self.track_info[track_id] = data
        except Exception:
            pass
        return data

    # ---------- arama ve YouTube listeleri ----------

    def search(self, query):
        query = (query or "").strip()
        if not query:
            return {"tracks": [], "albums": [], "artists": []}
        self.lib.add_recent_search(query)
        # Dördü aynı anda: YouTube Music şarkıları, albümleri ve sanatçıları, YouTube videoları
        with ThreadPoolExecutor(4) as pool:
            songs_job = pool.submit(search_songs, query)
            albums_job = pool.submit(search_albums, query, 12)
            artists_job = pool.submit(search_artists, query, 6)
            videos_job = pool.submit(search_tracks, query)
        songs = self._result(songs_job)
        videos = self._result(videos_job)
        albums = self._result(albums_job) or []
        if len(albums) < 3:
            albums += self._safe(search_playlists, query, 12 - len(albums)) or []
        if songs is None and videos is None:
            return {"tracks": [], "videos": [], "albums": [], "artists": [], "error": friendly_error(videos_job.exception())}
        songs, videos = songs or [], videos or []
        if not songs:  # YouTube Music'e ulaşılamadıysa eskisi gibi YouTube sonuçları şarkı olarak
            songs, videos = videos, []
        videos = remove_duplicates(videos, songs)
        self.prefetch(songs[:3])  # büyük ihtimalle bunlardan birine tıklanacak
        self.push("library", self.snapshot())
        return {"tracks": songs, "videos": videos, "albums": albums, "artists": self._result(artists_job) or []}

    @staticmethod
    def _result(job):
        try:
            return job.result()
        except Exception:
            return None

    @staticmethod
    def _safe(func, *args):
        try:
            return func(*args)
        except Exception:
            return None

    def artist(self, ref):
        """Sanatçı sayfası; ref = {"id": YouTube Music kimliği} ya da yalnızca {"name": ...}."""
        artist_id = ref.get("id")
        try:
            if not artist_id:
                found = find_artist(ref.get("name") or "")
                if not found:
                    return {"error": "Bu sanatçı YouTube Music'te bulunamadı."}
                artist_id = found["id"]
            if artist_id not in self.artists:
                self.artists[artist_id] = artist_page(artist_id)
        except Exception as error:
            return {"error": friendly_error(error)}
        page = self.artists[artist_id]
        self.prefetch(page["songs"][:1])
        return page

    def artist_radio(self, radio_id):
        try:
            return {"tracks": artist_radio(radio_id)}
        except Exception as error:
            return {"error": friendly_error(error)}

    def artist_mix(self, refs, count=30, popular=False):
        """Sanatçı Mix: seçilen sanatçıların popüler şarkılarından ve son albümlerinden rastgele şarkılarla
        yeni bir albüm. Şarkılar sanatçılar arasında eşit bölünür, sonra karıştırılır. refs: [{"id"|"name"}]
        popular=True: yalnızca popüler şarkılar (sanatçı başına en çok 25), albüm/single şarkıları katılmaz."""
        import math
        import random
        refs = [r for r in refs or [] if isinstance(r, dict) and (r.get("id") or r.get("name"))][:12]
        if not refs:
            return {"error": "En az bir sanatçı seç."}
        count = max(5, min(100, int(count or 30)))

        def pool_for(ref):
            page = self.artist(ref)
            if page.get("error"):
                return ref.get("name") or "?", None, []
            songs = list(page["songs"])
            for release in [] if popular else (page.get("albums") or [])[:3] + (page.get("singles") or [])[:2]:
                try:
                    songs += release_songs(release["id"], 40)
                except Exception:
                    pass  # bir albüm gelmezse diğerleri yeter
            seen, unique = set(), []
            for track in songs:  # aynı şarkının albüm ve single kopyaları tek sayılsın
                key = _norm(track.get("title"))
                if track.get("id") and key and key not in seen:
                    seen.add(key)
                    unique.append(track)
            return page["name"], page["id"], unique

        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(pool_for, refs))
        found = [(name, songs) for name, _, songs in results if songs]
        missing = [name for name, _, songs in results if not songs]
        if not found:
            return {"error": "Seçilen sanatçıların şarkıları alınamadı; internet bağlantını kontrol et."}
        per = math.ceil(count / len(found))
        picked, rest = [], []
        for _, songs in found:
            pool = songs[:]
            random.shuffle(pool)
            picked += pool[:per]
            rest += pool[per:]
        random.shuffle(picked)
        random.shuffle(rest)
        mix = (picked + rest)[:count]  # bir sanatçının şarkısı azsa diğerlerinden tamamlanır
        random.shuffle(mix)
        names = [name for name, _ in found]
        title = "Sanatçı Mix: " + ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
        self.lib.checkpoint("Sanatçı Mix")
        album_id = self.lib.create_album(title, tracks=[plain_track(t) for t in mix])
        return {"id": album_id, "name": title, "count": len(mix), "missing": missing}

    def radio(self, track):
        """Kuyruk bitince çalmaya devam etmek için benzer şarkılar."""
        if track["id"] not in self.radios:
            try:
                self.radios[track["id"]] = mix_for(track["id"], 25)
            except Exception:
                return []
        return self.radios[track["id"]]

    def playlist(self, playlist_id):
        if playlist_id in self.playlists:
            return {"tracks": self.playlists[playlist_id]}
        try:
            tracks = playlist_tracks(playlist_id)
        except Exception as error:
            return {"error": friendly_error(error)}
        self.playlists[playlist_id] = tracks
        return {"tracks": tracks}

    def save_playlist(self, playlist, download=False):
        result = self.playlist(playlist["id"])
        tracks = result.get("tracks")
        if not tracks:
            return {"error": f"Albüm kaydedilemedi: {result.get('error') or 'şarkı yok'}"}
        album_id = self.lib.album_by_source(playlist["id"])
        if album_id:
            self.lib.add_tracks_to_album(album_id, tracks)
            message = "Bu albüm zaten kitaplığında"
        else:
            album_id = self.lib.create_album(shorten(playlist["title"], 60), source=playlist["id"], tracks=tracks)
            message = f"“{shorten(playlist['title'], 30)}” kitaplığına kaydedildi"
        if download:
            missing = [t for t in tracks if not self.lib.is_downloaded(t["id"])]
            self.download_all(missing, quiet=True)
            message += f" · {len(missing)} şarkı indiriliyor" if missing else " · hepsi zaten indirilmiş"
        return {"message": message, "album": album_id}

    def add_playlist_to_album(self, playlist, album_id):
        result = self.playlist(playlist["id"])
        tracks = result.get("tracks")
        if not tracks:
            return {"error": f"Albüm eklenemedi: {result.get('error') or 'şarkı yok'}"}
        added = self.lib.add_tracks_to_album(album_id, tracks)
        name = shorten(self.lib.album(album_id)["name"], 30)
        return {"message": f"{added} şarkı “{name}” albümüne eklendi" if added else "Bu şarkılar zaten albümde"}

    # ---------- indirme ----------

    def download(self, track, kind="audio"):
        track_id = track["id"]
        key = track_id if kind == "audio" else f"{track_id}:video"
        if kind == "audio" and self.lib.is_downloaded(track_id):
            return "Bu şarkı zaten indirildi"
        if kind == "video" and self.lib.video_path(track_id):
            return "Bu video zaten indirildi"
        track = plain_track(track)
        cancel = threading.Event()
        with self.download_lock:
            if key in self.download_jobs:
                return None
            self.download_progress[key] = None
            self.download_jobs[key] = {"track": track, "kind": kind, "cancel": cancel}
            self.download_failed.pop(key, None)
        self.push("downloads", self.downloads_state())
        last = {"step": -1}

        def progress(fraction):
            step = int(fraction * 50)  # %2'lik adımlarla bildir
            if step != last["step"]:
                last["step"] = step
                self.download_progress[key] = fraction
                self.push("progress", {"key": key, "value": fraction})

        def job():
            if cancel.is_set():
                self._download_finished(key, None, None)
                return
            progress(0.0)
            try:
                fetch = downloader.fetch_video if kind == "video" else downloader.fetch_for_library
                filename = fetch(track, progress, cancel.is_set)
            except Exception as error:
                self._download_finished(key, None, None if cancel.is_set() else error)
                return
            self._download_finished(key, filename, None)

        self.download_pool.submit(job)
        return None

    def _download_finished(self, key, filename, error):
        with self.download_lock:
            job = self.download_jobs.pop(key, None)
            self.download_progress.pop(key, None)
        if not job:
            return
        track = job["track"]
        if filename:
            note = " (orijinali engelli, başka bir yüklemesi indirildi)" if track.pop("alt_source", None) else ""
            if job["kind"] == "video":
                self.lib.set_video(track, filename)
                self.toast(f"Video indirildi: {shorten(track['title'], 40)}{note}")
            else:
                self.lib.set_downloaded(track, filename)
                self.toast(f"İndirildi: {shorten(track['title'], 40)}{note}")
        elif error is None:
            self.toast("İndirme iptal edildi")
        else:
            message = friendly_error(error)
            with self.download_lock:
                self.download_failed[key] = {"track": track, "kind": job["kind"], "error": message}
            self.toast(f"İndirilemedi: {message}", error=True)
            if downloader.is_age_error(error):
                self.push("age", {"key": key, "title": track["title"]})
        self.push("downloads", self.downloads_state())

    def download_all(self, tracks, quiet=False):
        missing = [t for t in tracks if not self.lib.is_downloaded(t["id"]) and t["id"] not in self.download_jobs]
        for track in missing:
            self.download(track)
        if missing and not quiet:
            return f"{len(missing)} şarkı indiriliyor…"
        return None

    def cancel_download(self, key):
        job = self.download_jobs.get(key)
        if job:
            job["cancel"].set()

    def retry_download(self, key):
        failed = self.download_failed.pop(key, None)
        if failed:
            self.download(failed["track"], failed["kind"])

    def dismiss_failed(self, key):
        self.download_failed.pop(key, None)
        self.push("downloads", self.downloads_state())

    # ---------- ayarlar ----------

    def settings_state(self):
        return {"settings": self.lib.settings, "cache_bytes": downloader.cache_size(), "autostart": _autostart_state()}

    def clear_cache(self):
        downloader.trim_cache(0)
        return self.settings_state()

    def _delete_pending(self):
        pending = self.lib.data.get("pending_delete") or []
        left = []
        for path in pending:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                left.append(path)
        if pending:
            self.lib._set("pending_delete", left)

    def _purge_mp3_once(self):
        """Kullanıcı isteği (2026-10-28): eski MP3 indirmeleri bir kez Geri Dönüşüm Kutusu'na taşınır.
        Şarkıların listesi kaybolmasın diye "Eski indirilenler" albümünde kalır; istersen yeniden indirirsin."""
        if self.lib.data.get("mp3_purged"):
            return
        from library import MUSIC_DIR
        tracks = [t for t in self.lib.downloaded_tracks() if (t.get("file") or "").lower().endswith(".mp3")]
        loose = [n for n in os.listdir(MUSIC_DIR) if n.lower().endswith(".mp3")]
        if tracks:
            self.lib.create_album("Eski indirilenler", tracks=[plain_track(t) for t in tracks])
        moved = recycle([os.path.join(MUSIC_DIR, n) for n in loose])
        self.lib.forget_files([t["id"] for t in tracks])
        self.lib._set("mp3_purged", True)
        if loose:
            self.toast(f"{len(loose)} MP3 Geri Dönüşüm Kutusu'na taşındı · liste “Eski indirilenler” albümünde"
                       if moved else "MP3'ler silinemedi")

    def lyrics(self, track):
        """Şarkı sözleri (LRCLIB, ücretsiz). Bulunanlar ve bulunamayanlar veritabanında saklanır."""
        cached = self.lib.lyrics(track["id"])
        if cached is not None:
            return cached
        try:
            data = lyricsfinder.find(track)
        except Exception:
            return {"error": True}  # bağlantı sorunu: kaydetme, sonra tekrar denensin
        self.lib.set_lyrics(track["id"], data)
        return data

    # ---------- içe aktarma ----------

    def start_import(self, source, links="", files=None, token=None):
        if self.importing:
            return {"error": "Bir aktarma zaten sürüyor."}
        if source == "spotify" and not importer.spotify_links(links) and not files and not token:
            return {"error": "Bir Spotify liste bağlantısı yapıştır ya da dosya seç."}
        self.importing = True
        threading.Thread(target=self._import_job, args=(source, links, files or [], token), daemon=True).start()
        return {"ok": True}

    def _import_job(self, source, links, files, token=None):
        def progress(text, done=None, total=None):
            self.push("import", {"text": text, "done": done, "total": total})

        name = "YouTube Music" if source == "ytmusic" else "Spotify"
        progress(f"{name} kitaplığın okunuyor…")
        try:
            missing = failed = 0
            if source == "ytmusic":
                liked, playlists = importer.youtube_music(progress)
            else:
                cache = dict(self.lib.data.get("spotify_matches") or {})
                raw_liked, raw_lists = [], []
                if token:
                    raw_liked, raw_lists, failed = importer.spotify_account(token, progress)
                for kind, item_id in importer.spotify_links(links):
                    progress("Spotify: liste okunuyor…")
                    title, items = importer.spotify_page(kind, item_id)
                    raw_lists.append((f"spotify:{item_id}", title, items))
                if files:
                    file_liked, file_lists = importer.spotify_files(files)
                    raw_liked += file_liked
                    raw_lists += [(f"spotify:{n}", n, items) for n, items in file_lists]
                liked = importer.match(raw_liked, cache, progress, "Beğenilenler") if raw_liked else []
                playlists = [(src, title, importer.match(items, cache, progress, title)) for src, title, items in raw_lists]
                self.lib._set("spotify_matches", cache)
                missing = len(raw_liked) - len(liked) + sum(len(i) for _, _, i in raw_lists) - sum(len(t) for _, _, t in playlists)
            progress(f"{name}: kitaplığa ekleniyor…")
            self.lib.checkpoint(f"{name} içe aktarma")
            st = self.lib.import_collection(liked, playlists)
            parts = []
            if st["liked"] or st["liked_skipped"]:
                parts.append(f"{st['liked']} beğenilen şarkı favorilere eklendi")
            if st["albums_new"] or st["albums_merged"]:
                where = " + ".join(x for x in (st["albums_new"] and f"{st['albums_new']} yeni albüm",
                                              st["albums_merged"] and f"{st['albums_merged']} mevcut albüm") if x)
                parts.append(f"{st['tracks']} şarkı {where}e aktarıldı")
            skipped = st["skipped"] + st["liked_skipped"]
            if not st["liked"] and not st["tracks"]:
                self.lib.drop_checkpoint()  # hiçbir şey değişmedi: geri alınacak bir adım bırakma
                message = (f"{name}: her şey zaten kitaplığında, yeni bir şey eklenmedi ({skipped} şarkı atlandı)."
                           if skipped else f"{name}: aktarılacak bir şey bulunamadı.")
            else:
                message = f"{name}: " + ", ".join(p for p in parts if not p.startswith("0 ")) + "."
                if skipped:
                    message += f" Zaten olan {skipped} şarkı atlandı."
            if missing:
                message += f" {missing} şarkı YouTube Music'te bulunamadı."
            if failed:
                message += f" Spotify'ın kendi hazırladığı {failed} liste (Discover Weekly gibi) uygulamalara kapalı olduğu için alınamadı."
            self.push("import", {"finished": True, "message": message})
        except importer.ImportError_ as error:
            self.push("import", {"finished": True, "error": True, "message": str(error),
                                 "auth": source == "ytmusic" and "bağla" in str(error)})
        except Exception as error:
            self.push("import", {"finished": True, "error": True, "message": f"{name} aktarılamadı: {friendly_error(error)}"})
        finally:
            self.importing = False
            self.push("library", self.snapshot())

    # ---------- hesapla giriş (içe aktarma için) ----------

    YTM_LOGIN = "https://accounts.google.com/ServiceLogin?service=youtube&hl=tr&continue=https%3A%2F%2Fmusic.youtube.com%2F"

    def login_import(self, service, client_id=None, start_import=True):
        """start_import=False: yalnızca hesap bağlanır (yaş doğrulaması için), bitince "account" olayı gelir."""
        if self.importing:
            return {"error": "Bir aktarma zaten sürüyor."}
        if self.login_window:
            return {"error": "Giriş penceresi zaten açık."}
        if service == "spotify":
            client_id = (client_id or self.lib.settings.get("spotify_client_id") or "").strip()
            if not client_id:
                return {"error": "Spotify Client ID gerekli.", "setup": True}
            verifier, challenge, state = importer.spotify_pkce()
            try:
                server = self._spotify_callback_server(state)
            except OSError:
                return {"error": f"{importer.SPOTIFY_PORT} numaralı kapı kullanımda; uygulamayı yeniden başlatıp tekrar dene."}
            url, title = importer.spotify_auth_url(client_id, challenge, state), "Spotify'a giriş yap"
        else:
            url, title, server = self.YTM_LOGIN, "YouTube Music'e giriş yap", None
        window = webview.create_window(title, url, width=520, height=780, min_size=(420, 560))
        self.login_window = window
        closed = threading.Event()
        window.events.closed += closed.set
        if service == "spotify":
            threading.Thread(target=self._spotify_login_watch, args=(window, closed, server, client_id, verifier),
                             daemon=True).start()
        else:
            threading.Thread(target=self._ytm_login_watch, args=(window, closed, start_import), daemon=True).start()
        return {"ok": True}

    def _close_login(self, window):
        self.login_window = None
        try:
            window.destroy()
        except Exception:
            pass

    @staticmethod
    def _window_cookies(window):
        from http.cookiejar import Cookie
        out = []
        expires = int(time.time()) + 180 * 86400
        for jar in window.get_cookies() or []:
            for name, m in jar.items():
                domain = m["domain"] or ".youtube.com"
                out.append(Cookie(0, name, m.value, None, False, domain, True, domain.startswith("."), m["path"] or "/",
                                  True, bool(m["secure"]), expires, False, None, None, {}))
        return out

    def _ytm_login_watch(self, window, closed, start_import=True):
        """Kullanıcı music.youtube.com'a girişli olarak ulaşınca çerezleri kaydet ve aktarmayı başlat."""
        from http.cookiejar import MozillaCookieJar
        deadline = time.time() + 1200
        while not closed.is_set() and time.time() < deadline:
            time.sleep(1)
            try:
                url = window.get_current_url() or ""
                if not url.startswith("https://music.youtube.com"):
                    continue
                cookies = self._window_cookies(window)
            except Exception:
                continue
            if not any(c.name in ("SAPISID", "__Secure-3PAPISID") for c in cookies):
                continue  # henüz giriş yapılmamış
            jar = MozillaCookieJar(downloader.COOKIE_FILE)
            for cookie in cookies:
                jar.set_cookie(cookie)
            jar.save(ignore_discard=True, ignore_expires=True)
            # Aynı oturum yaş doğrulamalı şarkılar için de kullanılır
            self.save_auth({"mode": "file", "file": downloader.COOKIE_FILE, "login": True})
            self._close_login(window)
            self.toast("YouTube Music hesabına giriş yapıldı")
            if start_import:
                self.start_import("ytmusic")
            else:
                self.push("account", True)
            return
        self._close_login(window)
        if not closed.is_set():
            self.push("import", {"finished": True, "error": True, "message": "Giriş süresi doldu, tekrar dene."})

    def _spotify_callback_server(self, state):
        """Spotify girişten sonra tarayıcıyı 127.0.0.1'e yönlendirir; kodu buradan alırız."""
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import parse_qs, urlparse
        result = {}
        done = threading.Event()
        backend_ui = lambda: self.lib.settings.get("ui")
        backend_back = self.app_return_url

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = parse_qs(urlparse(self.path).query)
                ok = query.get("state", [None])[0] == state and "code" in query
                if urlparse(self.path).path == "/callback" and query.get("state", [None])[0] == state:
                    result.update({k: v[0] for k, v in query.items()})
                    done.set()
                ui, back = backend_ui(), backend_back
                body = (login_page(True, "Giriş tamam", "SOUND şarkılarını aktarmaya başladı. Uygulamaya dönebilirsin.", ui, back=back)
                        if ok else login_page(False, "Giriş yapılamadı", "Spotify girişi tamamlanmadı. SOUND'dan tekrar dene.", ui, back=back))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", importer.SPOTIFY_PORT), Handler)
        server.result, server.done = result, done
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def _spotify_login_watch(self, window, closed, server, client_id, verifier):
        try:
            while not closed.is_set() and not server.done.is_set():
                server.done.wait(0.5)
        finally:
            server.shutdown()
            server.server_close()
        self._close_login(window)
        result = server.result
        if "code" not in result:
            if result.get("error"):
                self.push("import", {"finished": True, "error": True,
                                     "message": "Spotify girişi iptal edildi." if result["error"] == "access_denied"
                                     else f"Spotify girişi başarısız: {result['error']}"})
            return
        try:
            token = importer.spotify_token(client_id, result["code"], verifier)
        except importer.ImportError_ as error:
            self.push("import", {"finished": True, "error": True, "message": str(error)})
            return
        self.lib.update_settings({"spotify_client_id": client_id})
        self.start_import("spotify", token=token)

    # ---------- SOUND hesabı (cloud.py) ----------

    def cloud_call(self, job, *args):
        try:
            return job(*args) or {"ok": True}
        except cloud.CloudError as error:
            return {"error": str(error)}

    def cloud_google(self):
        """Google ile giriş sistem tarayıcısında olur (Google gömülü pencereleri reddedebiliyor);
        dönüş 127.0.0.1'deki küçük sunucuya gelir."""
        if not self.cloud.configured:
            return {"error": "SOUND hesabı henüz yapılandırılmadı."}
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import parse_qs, urlparse
        old, self.cloud_login = self.cloud_login, None  # düğmeye art arda basılırsa iki çağrı aynı sunucuyu kapatmasın
        if old:
            old.shutdown()
            old.server_close()
        try:
            url, verifier = self.cloud.google_url()
        except cloud.CloudError as error:
            return {"error": str(error)}
        backend = self

        can_focus = self.window is not None and (IS_WINDOWS or sys.platform.startswith("linux"))
        back = self.app_return_url  # telefonda: uygulamayı öne getiren bağlantı

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != "/auth/callback" or getattr(self.server, "answered", False):
                    self.send_response(404)
                    self.end_headers()
                    return
                self.server.answered = True  # kod bir kez kullanılır; sayfa yenilenirse yeniden denenmez
                query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                if "code" in query:
                    result = backend.cloud_call(backend.cloud.finish_google, query["code"], verifier)
                else:
                    result = {"error": query.get("error_description") or "Giriş iptal edildi."}
                ok = "error" not in result
                ui = backend.lib.settings.get("ui")
                body = (login_page(True, "Giriş tamam", "SOUND hesabına bağlandın, kitaplığın eşitleniyor.", ui, can_focus, back)
                        if ok else login_page(False, "Giriş yapılamadı", result["error"], ui, back=back))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                backend.push("cloud_login", result)
                # "SOUND'a dön" düğmesi için sunucu bir süre daha açık kalır
                threading.Timer(120, backend._close_cloud_login, args=(self.server,)).start()

            def do_POST(self):
                if urlparse(self.path).path == "/focus" and can_focus:
                    backend.focus_window()
                    self.send_response(204)
                else:
                    self.send_response(404)
                self.end_headers()

            def log_message(self, *args):
                pass

        try:
            server = HTTPServer(("127.0.0.1", cloud.CALLBACK_PORT), Handler)
        except OSError:
            return {"error": f"{cloud.CALLBACK_PORT} numaralı kapı kullanımda; uygulamayı yeniden başlatıp tekrar dene."}
        self.cloud_login = server
        threading.Thread(target=server.serve_forever, daemon=True).start()
        threading.Timer(600, self._close_cloud_login, args=(server,)).start()
        if not open_browser(url):
            self._close_cloud_login(server)
            return {"error": "Tarayıcı açılamadı. Sistemde varsayılan bir tarayıcı ayarlı olmalı."}
        return {"ok": True}

    def focus_window(self):
        """Uygulama penceresini öne getirir (küçültülmüşse geri açar). Windows, arka plandaki bir sürecin
        pencere öne almasını engeller; kısa bir Alt basışı bu kilidi açar."""
        if not IS_WINDOWS:
            try:
                self.window.restore()
                self.window.show()
            except Exception:
                pass
            return
        try:
            hwnd = int(self.window.native.Handle.ToInt64())
        except Exception:
            return
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU basılı
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 2, 0)  # bırak
        user32.BringWindowToTop(hwnd)

    def _close_cloud_login(self, server):
        if self.cloud_login is server:
            self.cloud_login = None
            server.shutdown()
            server.server_close()

    # ---------- YouTube hesabı ----------

    def auth_status(self):
        auth = self.lib.data.get("youtube_auth") or {}
        names = dict(downloader.BROWSERS)
        if auth.get("mode") == "browser":
            return f"Şu an: {names.get(auth.get('browser'), auth.get('browser'))} tarayıcısındaki YouTube oturumu kullanılıyor."
        if auth.get("mode") == "file" and auth.get("login"):
            return "Şu an: uygulama içinden giriş yaptığın Google hesabı kullanılıyor."
        if auth.get("mode") == "file" and auth.get("browser"):
            return f"Şu an: {names.get(auth['browser'], auth['browser'])} tarayıcısından kaydedilen YouTube oturumu kullanılıyor."
        if auth.get("mode") == "file":
            return "Şu an: seçtiğin cookies.txt dosyası kullanılıyor."
        return "Şu an: bağlı değil."

    def save_auth(self, settings):
        self.lib.set_youtube_auth(settings)
        downloader.set_auth(settings)
        self.streams.clear()

    def auth_browser(self, key):
        ok, message = downloader.check_browser_login(key)
        if ok:
            # Çerezler cookies.txt'ye kopyalandı; tarayıcı sonra açık olsa da çalışır
            self.save_auth({"mode": "file", "file": downloader.COOKIE_FILE, "browser": key})
        return {"ok": ok, "message": message}

    def auth_file(self):
        paths = self.window.create_file_dialog(webview.FileDialog.OPEN,
                                               file_types=("Çerez dosyası (*.txt)", "Tüm dosyalar (*.*)"))
        if not paths:
            return None
        path = paths[0]
        ok, message = downloader.check_cookie_file(path)
        if ok:
            target = os.path.join(DATA_DIR, "cookies.txt")
            if os.path.abspath(path) != os.path.abspath(target):
                shutil.copyfile(path, target)
            self.save_auth({"mode": "file", "file": target})
        return {"ok": ok, "message": message}


class TrayMenu:
    """Tepsi simgesine sağ tıklayınca açılan temalı menü (Windows; web/traymenu.html). Pencere açılışta gizli kurulur,
    her açılışta çalan şarkı ve kullanıcının renkleriyle (settings.ui) yeniden çizilir; dışarı tıklanınca gizlenir.
    Linux'ta ve kurulamazsa pystray'in sistem menüsü kullanılır."""
    TITLE = "SOUND menü"
    WIDTH, HEIGHT = 280, 284  # mantıksal piksel (traymenu.html içeriğine göre)

    def __init__(self, backend, base):
        self.backend = backend
        self.base = base
        self.hwnd = None
        self.visible = False
        self.window = webview.create_window(self.TITLE, url=base + "/traymenu.html", js_api=TrayMenuApi(self),
                                            width=self.WIDTH, height=self.HEIGHT, x=0, y=0,  # x/y: WinForms ilk gösterişte
                                            hidden=True, frameless=True,                      # pencereyi kendi yerine koymasın
                                            easy_drag=False, on_top=True, resizable=False, focus=True,
                                            background_color="#121212")
        self.window.events.loaded += self._loaded

    def _loaded(self):
        user32 = ctypes.windll.user32
        try:  # pywebview'un formu (WinForms); başlıkla aramak aynı adlı iç pencereleri ya da başka SOUND'u bulabiliyor
            self.hwnd = int(self.window.native.Handle.ToInt64())
        except Exception:
            self.hwnd = self._own_window()
        if not self.hwnd:
            return
        style = user32.GetWindowLongW(self.hwnd, -20)  # GWL_EXSTYLE: görev çubuğunda / Alt+Tab'da görünmesin
        user32.SetWindowLongW(self.hwnd, -20, (style | 0x80) & ~0x40000)  # +WS_EX_TOOLWINDOW, -WS_EX_APPWINDOW
        try:  # Windows 11 yuvarlak köşe
            ctypes.windll.dwmapi.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
        except Exception:
            pass

    def _own_window(self):
        """Bu sürecin menü penceresi. Başlıkla FindWindow kullanılmaz: aynı anda başka bir SOUND (test kopyası,
        kapanmakta olan eski kopya) açıksa onun penceresini bulup taşıyordu."""
        user32 = ctypes.windll.user32
        me, found = os.getpid(), []
        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def check(hwnd, _):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
            if pid.value == me:
                title = ctypes.create_unicode_buffer(64)
                user32.GetWindowTextW(ctypes.c_void_p(hwnd), title, 64)
                if title.value == self.TITLE:
                    found.append(hwnd)
                    return False
            return True
        user32.EnumWindows(enum_proc(check), 0)
        return found[0] if found else None

    def state(self):
        b = self.backend
        now = b.tray_now or {}
        track = now.get("track")
        info = None
        if track:
            info = {"title": track.get("title") or "", "artist": track.get("artist") or "",
                    "art": f"{self.base}/thumb/{track['id']}" if track.get("id") else ""}
        return {"track": info, "playing": bool(now.get("playing")), "ui": b.lib.settings.get("ui") or {},
                "volume": b.lib.volume}

    def show(self):
        """Sağ tık (tepsi iş parçacığı). Pencere henüz hazır değilse False: sistem menüsü açılır."""
        if not self.hwnd or self.backend.quitting:
            return False
        threading.Thread(target=self._show, daemon=True).start()
        return True

    @staticmethod
    def _set_pos(hwnd, x, y, w, h, flags):
        """SetWindowPos türleri belirtilerek: belirtilmezse 64 bit Windows'ta HWND_TOPMOST (-1) bozuk tutamaca dönüşüyor
        ve çağrı sessizce başarısız oluyordu (menü hep pywebview'un ilk konumunda açılıyordu)."""
        from ctypes import wintypes
        fn = ctypes.WinDLL("user32").SetWindowPos
        fn.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        fn.restype = wintypes.BOOL
        return fn(hwnd, wintypes.HWND(-1), x, y, w, h, flags)  # HWND_TOPMOST

    def _show(self):
        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(user32.MonitorFromPoint(pt, 2), ctypes.byref(info))
        scale = (user32.GetDpiForWindow(self.hwnd) or 96) / 96
        w, h = round(self.WIDTH * scale), round(self.HEIGHT * scale)
        work = info.rcWork
        gap = round(8 * scale)
        icon = self.backend.tray.icon_rect() if self.backend.tray else None
        if icon and icon[0] <= pt.x <= icon[2] + 2 and icon[1] - 2 <= pt.y <= icon[3] + 2:
            # simgenin (görev çubuğunda ya da taşma kutusunda) hemen üstünde, ortalanmış
            x = (icon[0] + icon[2]) // 2 - w // 2
            y = icon[1] - h - gap if icon[1] - h - gap >= work.top else icon[3] + gap
        else:  # simgenin yeri alınamadı (taşma kutusunda E_FAIL dönebiliyor): imlecin üstünde, ortalı; açılır kutuyu
            lift = round(28 * scale)  # (taşma kutusu / görev çubuğu simgesi) örtmeyecek kadar yukarıda
            x = pt.x - w // 2
            y = pt.y - h - lift if pt.y - h - lift >= work.top else pt.y + lift
        x = max(work.left, min(x, work.right - w))  # ekrandan taşmasın
        y = max(work.top, min(y, work.bottom - h))
        try:
            self.window.evaluate_js(f"render({json.dumps(self.state())})")
        except Exception:
            pass
        self._set_pos(self.hwnd, x, y, w, h, 0x0010)  # SWP_NOACTIVATE: gösterilmeden önce yerine
        self.window.show()
        self._set_pos(self.hwnd, x, y, w, h, 0x0040)  # SWP_SHOWWINDOW: show() sonrasında da aynı yerde kalsın
        user32.SetForegroundWindow(self.hwnd)
        self.visible = True
        # dışarı tıklanınca (başka pencere öne geçince) kapan; WebView odağı almasa da çalışır
        time.sleep(0.25)
        while self.visible and user32.GetForegroundWindow() == self.hwnd:
            time.sleep(0.1)
        self.hide()

    def hide(self):
        if self.visible:
            self.visible = False
            try:
                self.window.hide()
            except Exception:
                pass

    def destroy(self):
        try:
            self.window.destroy()
        except Exception:
            pass


class TrayMenuApi:
    """traymenu.html'in çağırdıkları (pywebview js_api). Menü nesnesi alt çizgili: pywebview onu JS'e açmaz."""

    def __init__(self, menu):
        self._menu = menu

    def command(self, action):
        if action in ("toggle", "next", "previous"):
            self._menu.backend.push("command", action)
        if action != "toggle":
            self._menu.hide()

    def volume(self, value):
        """Menüdeki ses kaydırıcısı (0-1, uygulamadaki kaydırıcı konumu). Uygulama sesi ayarlar ve kaydeder."""
        try:
            value = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return
        self._menu.backend.push("volume", round(value, 3))

    def open(self):
        self._menu.hide()
        self._menu.backend.show_window()

    def quit(self):
        self._menu.hide()
        self._menu.backend.quit_app()

    def hide(self):
        self._menu.hide()


class Api:
    """Arayüzün (JavaScript) çağırabildiği fonksiyonlar: window.pywebview.api.<ad>(...)"""

    def __init__(self, backend):
        self._b = backend

    # açılış
    def init(self):
        b = self._b
        if not b.started:
            b.started = True
            b.start_background_jobs()
        return {"lib": b.snapshot(), "session": b.session, "downloads": b.downloads_state(),
                "home": b.home_state(), "volume": b.lib.volume, "browsers": downloader.BROWSERS,
                "settings": b.lib.settings}

    def snapshot(self):
        return self._b.snapshot()

    def home(self, force=False):
        return self._b.ensure_home(force)

    def search(self, query):
        return self._b.search(query)

    def artist(self, ref):
        return self._b.artist(ref)

    def artist_radio(self, radio_id):
        return self._b.artist_radio(radio_id)

    def artist_search(self, query):
        try:
            return {"artists": search_artists(query, 8)}
        except Exception as error:
            return {"error": friendly_error(error)}

    def artist_mix(self, refs, count=30, popular=False):
        return self._b.artist_mix(refs, count, popular is True)

    def radio(self, track):
        return self._b.radio(track)

    def playlist(self, playlist_id):
        return self._b.playlist(playlist_id)

    def stream(self, track, force=False, video=False):
        return self._b.stream(track, force, video)

    def prefetch(self, tracks, video=False):
        self._b.prefetch(tracks, video)

    def played(self, track):
        self._b.played(track)

    def listen(self, session, track, seconds):
        self._b.lib.log_listen(session, plain_track(track), seconds)

    def stats(self, period="30"):
        return self._b.lib.stats(period)

    def loudness(self, track_id):
        return self._b.lib.loudness(track_id)

    def set_loudness(self, track_id, lufs, seconds):
        self._b.lib.set_loudness(track_id, lufs, seconds)

    def track_info(self, track):
        return self._b.fetch_track_info(track)

    def player_state(self, state):
        self._b.player_state(state)

    def save_session(self, state):
        self._b.save_session(state)

    def settings(self):
        return self._b.settings_state()

    def update_settings(self, changes):
        self._b.lib.update_settings(changes)
        if "cache_mb" in changes:
            threading.Thread(target=self._b._trim_cache, daemon=True).start()
        if "discord_presence" in changes and self._b.presence:
            self._b.presence.set_enabled(changes["discord_presence"] is not False)
        return self._b.settings_state()

    def clear_cache(self):
        return self._b.clear_cache()

    def set_app_icon(self, accent):
        return self._b.set_app_icon(accent)

    def set_autostart(self, on):
        """Ayarlar > Arka plan > Bilgisayar açılınca başlat."""
        try:
            import autostart
            autostart.set_enabled(bool(on))
        except Exception as error:
            return {**self._b.settings_state(), "error": f"Ayarlanamadı: {error}"}
        return self._b.settings_state()

    def app_version(self):
        return {"version": selfupdate.current_version(), "git": selfupdate.available(),
                "pending": self._b.app_update}

    def check_app_update(self):
        return self._b.run_self_update()

    def restart_app(self):
        threading.Thread(target=self._b.restart_app, daemon=True).start()
        return True

    def set_zoom(self, factor):
        """Kişiselleştir > Arayüz boyutu: WebView2'nin kendi yakınlaştırması (Ctrl+artı gibi)."""
        try:
            factor = min(1.5, max(0.5, float(factor)))
            form = self._b.window.native
            view = form.browser.webview
            from System import Action
            form.Invoke(Action(lambda: setattr(view, "ZoomFactor", factor)))
            return True
        except Exception:
            return False

    def lyrics(self, track):
        return self._b.lyrics(track)

    def remove_recent_search(self, query):
        self._b.lib.remove_recent_search(query)
        return self._b.lib.recent_searches

    def clear_recent_searches(self):
        self._b.lib.clear_recent_searches()
        return []

    def set_volume(self, value):
        self._b.lib.volume = round(float(value), 3)

    # kitaplık
    def toggle_favorite(self, track):
        self._b.lib.checkpoint("Favori değişikliği")
        return self._b.lib.toggle_favorite(plain_track(track))

    def reorder_favorites(self, track_id, target_id, after):
        self._b.lib.checkpoint("Favori sıralaması")
        self._b.lib.reorder_favorites(track_id, target_id, after)

    def create_album(self, name, folder_id=None, tracks=None):
        self._b.lib.checkpoint("Albüm oluşturma")
        return self._b.lib.create_album(name, folder_id, tracks=[plain_track(t) for t in tracks or []])

    def rename_album(self, album_id, name):
        self._b.lib.checkpoint("Albüm adı değişikliği")
        self._b.lib.rename_album(album_id, name)

    def delete_album(self, album_id):
        self._b.lib.checkpoint("Albüm silme")
        self._b.lib.delete_album(album_id)

    def move_album(self, album_id, folder_id):
        self._b.lib.checkpoint("Albüm taşıma")
        self._b.lib.move_album(album_id, folder_id)

    def reorder_side(self, item_id, target_id, after):
        self._b.lib.checkpoint("Kitaplık sıralaması")
        if not self._b.lib.reorder_side(item_id, target_id, after):
            self._b.lib.drop_checkpoint()

    def add_to_album(self, album_id, track):
        self._b.lib.checkpoint("Albüme ekleme")
        return self._b.lib.add_to_album(album_id, plain_track(track))

    def remove_from_album(self, album_id, track_id):
        self._b.lib.checkpoint("Albümden çıkarma")
        self._b.lib.remove_from_album(album_id, track_id)

    def reorder_album(self, album_id, track_id, target_id, after):
        self._b.lib.checkpoint("Albüm sıralaması")
        self._b.lib.reorder_album(album_id, track_id, target_id, after)

    def create_folder(self, name):
        self._b.lib.checkpoint("Klasör oluşturma")
        return self._b.lib.create_folder(name)

    def rename_folder(self, folder_id, name):
        self._b.lib.checkpoint("Klasör adı değişikliği")
        self._b.lib.rename_folder(folder_id, name)

    def delete_folder(self, folder_id):
        self._b.lib.checkpoint("Klasör silme")
        self._b.lib.delete_folder(folder_id)

    def save_playlist(self, playlist, download=False):
        self._b.lib.checkpoint("Listeyi kaydetme")
        return self._b.save_playlist(playlist, download)

    def add_playlist_to_album(self, playlist, album_id):
        self._b.lib.checkpoint("Listeyi albüme ekleme")
        return self._b.add_playlist_to_album(playlist, album_id)

    def undo(self):
        return self._b.lib.undo()

    # içe aktarma
    def start_import(self, source, links="", files=None):
        return self._b.start_import(source, links, files)

    def login_import(self, service, client_id=None, start_import=True):
        return self._b.login_import(service, client_id, start_import)

    def set_album_cover(self, album_id, cover):
        try:
            return {"cover": self._b.lib.set_album_cover(album_id, cover)}
        except ValueError as error:
            return {"error": str(error)}
        except OSError:
            return {"error": "Resim kaydedilemedi."}

    def pick_image(self):
        """Kapak için resim seç (masaüstünde dosya penceresi, telefonda Android seçicisi). Arayüz küçültüp
        set_album_cover'a gönderir; burada yalnızca okunur."""
        import base64
        paths = self._b.window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Resimler (*.jpg;*.jpeg;*.png;*.webp;*.gif;*.bmp)", "Tüm dosyalar (*.*)"))
        if not paths:
            return None
        path = paths[0] if isinstance(paths, (list, tuple)) else paths
        try:
            if os.path.getsize(path) > 25_000_000:
                return {"error": "Resim çok büyük (en fazla 25 MB)."}
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            return {"error": "Resim açılamadı."}
        kinds = [(b"\xff\xd8\xff", "jpeg"), (b"\x89PNG", "png"), (b"GIF8", "gif"), (b"BM", "bmp")]
        mime = next((m for sig, m in kinds if raw.startswith(sig)), "webp" if raw[8:12] == b"WEBP" else None)
        if not mime:
            return {"error": "Bu dosya bir resim değil."}
        return {"data": f"data:image/{mime};base64," + base64.b64encode(raw).decode()}

    def pick_import_files(self):
        paths = self._b.window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=True,
            file_types=("Spotify verisi (*.zip;*.json;*.csv)", "Tüm dosyalar (*.*)"))
        return list(paths or [])

    # indirme
    def download(self, track, kind="audio"):
        return self._b.download(track, kind)

    def download_all(self, tracks):
        return self._b.download_all(tracks)

    def cancel_download(self, key):
        self._b.cancel_download(key)

    def retry_download(self, key):
        self._b.retry_download(key)

    def dismiss_failed(self, key):
        self._b.dismiss_failed(key)

    def remove_download(self, track_id):
        self._b.lib.remove_download(track_id)

    def remove_video(self, track_id):
        self._b.lib.remove_video(track_id)

    def open_video(self, track_id):
        path = self._b.lib.video_path(track_id)
        if path:
            open_path(path)

    def open_url(self, url):
        if url.startswith("https://"):
            open_browser(url)

    def dpi_info(self):
        info = goodbyedpi_info()
        return {**info, "blacklist": DPI_BLACKLIST}

    def dpi_blacklist(self):
        info = goodbyedpi_info()
        if not info.get("folder") or not os.path.isdir(info["folder"]):
            return {"error": "GoodbyeDPI klasörü bulunamadı"}
        try:
            result = goodbyedpi_write_blacklist(info["folder"])
        except OSError as error:
            return {"error": f"blacklist.txt yazılamadı: {error}"}
        open_path(info["folder"])
        return result

    def dpi_fix(self):
        return goodbyedpi_fix()

    def dpi_open_folder(self):
        info = goodbyedpi_info()
        if info.get("folder") and os.path.isdir(info["folder"]):
            open_path(info["folder"])

    def open_music_folder(self):
        open_path(os.path.join(DATA_DIR, "music"))

    # YouTube hesabı
    def auth_status(self):
        return self._b.auth_status()

    def auth_browser(self, key):
        return self._b.auth_browser(key)

    def auth_file(self):
        return self._b.auth_file()

    def auth_clear(self):
        self._b.save_auth(None)
        return self._b.auth_status()

    # SOUND hesabı
    def listen_status(self):
        return self._b.listen.status()

    def listen_create(self, name):
        return self._b.listen.create(name)

    def listen_join(self, code, name):
        return self._b.listen.join(code, name)

    def listen_leave(self):
        return self._b.listen.leave()

    def listen_send(self, kind, data):
        return self._b.listen.send(kind, data)

    def notify(self, title, body, target=""):
        return self._b.notify(title, body, target)

    def drop_cache(self, track_id):
        """Önbellekteki dosya çalınamadı: silinir, şarkı yeniden YouTube'dan alınır."""
        downloader.drop_cache(track_id)

    def social(self, method, args=None):
        return self._b.social.call(method, args or [])

    def devices_status(self):
        return self._b.devices.status()

    def devices_send(self, kind, data, to=None):
        return self._b.devices.send(kind, data, to)

    def cloud_status(self):
        return self._b.cloud.status()

    def cloud_sign_up(self, email, password):
        return self._b.cloud_call(self._b.cloud.sign_up, email, password)

    def cloud_sign_in(self, email, password):
        return self._b.cloud_call(self._b.cloud.sign_in, email, password)

    def cloud_reset_password(self, email):
        return self._b.cloud_call(self._b.cloud.reset_password, email)

    def cloud_google(self):
        return self._b.cloud_google()

    def cloud_sync(self):
        self._b.cloud.sync_now(manual=True)
        return self._b.cloud.status()

    def cloud_set_auto(self, on):
        self._b.cloud.set_auto(on)
        return self._b.cloud.status()

    def cloud_sign_out(self):
        return self._b.cloud_call(self._b.cloud.sign_out)

    def cloud_delete_account(self):
        return self._b.cloud_call(self._b.cloud.delete_account)


INSTANCE_FILE = os.path.join(DATA_DIR, "instance.json")
_instance_lock = None  # Windows mutex tutamacı: süreç yaşadıkça açık kalır


def _sane_geometry(saved):
    """Kayıtlı pencere konumu/boyutu; küçültülmüş pencereden kalan (-32000, 160x28) değerler atılır."""
    geometry = dict(saved or {})
    if (geometry.get("x") or 0) < -10000 or (geometry.get("y") or 0) < -10000:
        geometry.pop("x", None)
        geometry.pop("y", None)
    if (geometry.get("width") or 0) < 400 or (geometry.get("height") or 0) < 300:
        geometry.pop("width", None)
        geometry.pop("height", None)
    return geometry


def _acquire_single_instance():
    """Yalnızca bir SOUND çalışsın. Başka biri çalışıyorsa onun penceresi öne getirilir ve False döner.
    Windows'ta adlandırılmış mutex (aynı anda iki kez tıklansa da tek kopya); kapanmakta olan bir kopya varsa
    (güncelleme sonrası yeniden başlatma) onun çıkması beklenir."""
    global _instance_lock
    if not IS_WINDOWS:
        return not _show_running_instance()
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    handle = kernel32.CreateMutexW(None, False, "Local\\SOUND.MusicPlayer.Instance")
    if not handle:
        return not _show_running_instance()
    deadline = time.time() + 20
    while time.time() < deadline:
        if kernel32.WaitForSingleObject(handle, 0) in (0, 0x80):  # sahiplenildi / önceki kopya düşmüş
            _instance_lock = handle
            return True
        if _show_running_instance():
            return False
        if kernel32.WaitForSingleObject(handle, 500) in (0, 0x80):
            _instance_lock = handle
            return True
    return False  # öteki kopya ne yanıt veriyor ne kapanıyor: ikinci pencere açma


def _show_running_instance():
    """SOUND zaten açıksa (belki tepside) onun penceresini öne getirir ve True döner; ikinci kopya açılmaz."""
    import urllib.request
    try:
        with open(INSTANCE_FILE, encoding="utf-8") as f:
            port = int(json.load(f)["port"])
        request = urllib.request.Request(f"http://127.0.0.1:{port}/show", data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status == 204
    except Exception:
        return False


def _autostart_state():
    """None: bu platformda yok (telefon)."""
    try:
        import autostart
        return autostart.enabled() if autostart.supported() else None
    except Exception:
        return None


def _launched_at_startup():
    try:
        import autostart
        return autostart.launched_at_startup()
    except Exception:
        return False


def _patch_qt_permissions():
    """Linux (Qt): pywebview'in izin işleyicisi PyQt6'da setFeaturePermission'a düz sayı veriyor → TypeError;
    PyQt6 yuvadaki yakalanmamış hatada süreci abort ediyor. Pano yazma (oda kodunu kopyala) bu izni
    istediği için uygulama çöküyordu. İşleyici doğru enum'larla ve hata yutarak değiştirilir."""
    try:
        from webview.platforms import qt as wq
        from qtpy.QtWebEngineCore import QWebEnginePage
    except Exception:
        return
    F, P = QWebEnginePage.Feature, QWebEnginePage.PermissionPolicy
    allowed = {getattr(F, n) for n in ("MediaAudioCapture", "MediaVideoCapture", "MediaAudioVideoCapture",
                                       "ClipboardReadWrite", "ClipboardSanitizedWrite") if hasattr(F, n)}

    def on_permission(self, url, feature):
        try:
            policy = P.PermissionGrantedByUser if feature in allowed else P.PermissionDeniedByUser
            self.setFeaturePermission(url, feature, policy)
        except Exception as e:  # buradan hata çıkarsa PyQt6 tüm uygulamayı kapatır
            print("izin isteği yanıtlanamadı:", feature, e, file=sys.stderr)

    wq.BrowserView.WebPage.onFeaturePermissionRequested = on_permission


def run():
    if not _acquire_single_instance():
        return
    backend = Backend()
    base = mediaserver.start()
    mediaserver.on_show = backend.show_window
    try:
        with open(INSTANCE_FILE, "w", encoding="utf-8") as f:
            json.dump({"port": int(base.rsplit(":", 1)[1]), "pid": os.getpid()}, f)
    except (OSError, ValueError):
        pass
    geometry = backend.geometry
    window = webview.create_window(
        "SOUND", url=base + "/index.html", js_api=Api(backend),
        width=geometry.get("width") or 1320, height=geometry.get("height") or 840,
        x=geometry.get("x"), y=geometry.get("y"), min_size=(980, 640),
        maximized=bool(geometry.get("maximized")), minimized=_launched_at_startup(), background_color="#000000")
    backend.window = window
    window.events.shown += backend.on_shown
    window.events.closing += backend.on_closing
    window.events.moved += backend.on_moved
    window.events.resized += backend.on_resized
    window.events.maximized += lambda: backend.geometry.update(maximized=True)
    window.events.restored += lambda: backend.geometry.update(maximized=False)
    import tray
    backend.tray = tray.Tray(ICON if IS_WINDOWS else ICON_PNG, backend.show_window,
                             lambda action: backend.push("command", action), backend.quit_app)
    if not backend.tray.start():
        backend.tray = None
    elif IS_WINDOWS:
        try:
            backend.tray_menu = TrayMenu(backend, base)
            backend.tray.on_menu = backend.tray_menu.show
        except Exception:
            backend.tray_menu = None  # sistem menüsü kalır
    options = {}
    if not IS_WINDOWS:
        # Linux: Qt WebEngine (Edge WebView2 ile aynı Chromium motoru). Arayüz boyutu canlı değişemiyor
        # (set_zoom yalnızca Windows'ta); kayıtlı boyut açılışta Qt ölçeğiyle uygulanır.
        zoom = ((backend.lib.settings.get("ui") or {}).get("zoom") or 100) / 100
        if abs(zoom - 1) > 0.01:
            os.environ.setdefault("QT_SCALE_FACTOR", f"{zoom:.2f}")
        try:  # görev çubuğu / Wayland pencereyi sound.desktop ile (ikon, ad) eşleştirsin (install.sh)
            from qtpy.QtGui import QGuiApplication
            QGuiApplication.setDesktopFileName("sound")
            QGuiApplication.setApplicationName("SOUND")
        except Exception:
            pass
        _patch_qt_permissions()
        options = {"gui": "qt", "icon": ICON_PNG}
    webview.start(private_mode=False, storage_path=os.path.join(DATA_DIR, "webview"), **options)
    backend.save_session()
