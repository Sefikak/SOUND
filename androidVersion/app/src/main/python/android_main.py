"""Android giriş noktası: masaüstünün Backend ve Api sınıfları olduğu gibi kullanılır, yalnızca pencere değişir."""
import json
import os
import sys
import threading
import time
import traceback
import types

_api = None
_backend = None


class Window:
    """pywebview penceresinin Backend'in kullandığı kısmı; işi Kotlin tarafına iletir."""

    def __init__(self, native):
        self.bridge = native

    def evaluate_js(self, code):
        self.bridge.evaluateJs(code)

    def set_title(self, title):
        pass

    def create_file_dialog(self, *args, **kwargs):
        return None


def _use_data_dir(data_dir):
    """Kullanıcı verisi uygulama güncellense de silinmeyen klasörde dursun (diğer modüller yollarını library'den alır)."""
    import library
    library.DATA_DIR = data_dir
    library.MUSIC_DIR = os.path.join(data_dir, "music")
    library.CACHE_DIR = os.path.join(data_dir, "cache")
    library.THUMB_DIR = os.path.join(data_dir, "thumbs")
    library.VIDEO_DIR = os.path.join(data_dir, "videos")
    library.DB_FILE = os.path.join(data_dir, "library.db")
    library.LIBRARY_FILE = os.path.join(data_dir, "library.json")
    for folder in (data_dir, library.MUSIC_DIR, library.CACHE_DIR, library.THUMB_DIR, library.VIDEO_DIR):
        os.makedirs(folder, exist_ok=True)


def _patch_downloads():
    """Masaüstü indirilen sesi ffmpeg ile .opus dosyasına aktarır; Android'de ffmpeg yok. YouTube'un sesi zaten
    Opus/WebM olduğu için dönüştürmeden olduğu gibi saklanır. Birleştirme gerektiren video indirme henüz yok."""
    import shutil
    import downloader
    from library import MUSIC_DIR

    def fetch_for_library(track, progress=None, cancelled=None):
        stem = f"{downloader.safe_name(track['title'])} [{track['id']}]"
        found = next((n for n in os.listdir(MUSIC_DIR) if n.startswith(stem + ".") and not n.endswith(".part")), None)
        if not found:
            cached = downloader.cache_path(track["id"])
            if os.path.exists(cached):
                found = stem + ".webm"
                shutil.copyfile(cached, os.path.join(MUSIC_DIR, found))
            else:
                options = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
                           "format": "bestaudio[acodec=opus]/bestaudio",
                           "outtmpl": os.path.join(MUSIC_DIR.replace("%", "%%"), stem + ".%(ext)s")}
                options.update(downloader._hooks(progress, cancelled))
                downloader._run_ytdl(track, options)
                found = next((n for n in os.listdir(MUSIC_DIR) if n.startswith(stem + ".") and not n.endswith(".part")), None)
                if not found:
                    raise RuntimeError("Ses dosyası oluşturulamadı")
        if progress:
            progress(1.0)
        try:
            downloader.fetch_thumbnail(track)
        except Exception:
            pass
        return found

    def fetch_video(track, progress=None, cancelled=None):
        raise RuntimeError("Video indirme mobil sürümde henüz yok")

    downloader.fetch_for_library = fetch_for_library
    downloader.fetch_video = fetch_video


class _Signal:
    """pywebview olayı gibi: window.events.closed += işlev"""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self):
        for handler in self.handlers:
            handler()


class _Events:
    def __init__(self):
        self.closed = _Signal()


class _BrowserLogin:
    """Masaüstünde giriş ayrı pencerede açılır; telefonda tarayıcıda. Spotify sonunda 127.0.0.1'deki
    uygulamaya döner. Kullanıcı vazgeçerse bekleyiş bir süre sonra kendiliğinden biter."""
    TIMEOUT = 15 * 60

    def __init__(self):
        self.events = _Events()
        self.timer = threading.Timer(self.TIMEOUT, self.events.closed.fire)
        self.timer.daemon = True
        self.timer.start()

    def destroy(self):
        self.timer.cancel()


def _patch_login(native, backend):
    import webapp
    import webview

    def create_window(title, url, **kwargs):
        if "accounts.spotify.com" not in url:
            raise RuntimeError("Bu özellik mobil sürümde henüz yok")
        native.openUrl(url)
        return _BrowserLogin()
    webview.create_window = create_window
    webapp.webbrowser = types.SimpleNamespace(open=native.openUrl)

    original = backend.login_import

    def login_import(service, client_id=None):
        # tarayıcıda yarım kalan giriş yenisini engellemesin: öncekini bitir, kapısının boşalmasını bekle
        previous = backend.login_window
        if previous:
            previous.events.closed.fire()
            for _ in range(20):
                if not backend.login_window:
                    break
                time.sleep(0.1)
        return original(service, client_id)
    backend.login_import = login_import


def _patch_update(native, data_dir):
    """Masaüstünde uygulama kapanıp yeniden açılır; burada yalnızca yükleme ekranı açılır, kullanıcı vazgeçebilir."""
    import selfupdate
    selfupdate.init(native, os.path.join(os.path.dirname(data_dir), "update"))

    def install():
        _backend.save_session()
        selfupdate.restart()
    _backend.restart_app = install

    def check_app_update():
        selfupdate.allow_metered = True  # kullanıcı kendisi istedi: mobil veride de iner
        try:
            return _backend.run_self_update()
        finally:
            selfupdate.allow_metered = False
    _api.check_app_update = check_app_update


def start(data_dir, native):
    """Arka ucu başlatır, arayüzün adresini döner. native: MainActivity.Native (Kotlin)."""
    global _api, _backend
    _use_data_dir(data_dir)
    import webui
    import mediaserver
    mediaserver.WEB_DIR = os.path.dirname(webui.__file__)
    import webapp
    _patch_downloads()
    _backend = webapp.Backend()
    _backend.window = Window(native)
    _api = webapp.Api(_backend)
    _patch_login(native, _backend)
    _patch_update(native, data_dir)

    original = _backend.player_state

    def player_state(state):
        original(state)
        native.playerState(json.dumps(state, ensure_ascii=False))
    _backend.player_state = player_state
    return mediaserver.start() + "/index.html"


def call(method, args_json):
    """Arayüzden gelen window.pywebview.api.<method>(...) çağrısı. Sonuç JSON: {"ok": ...} ya da {"error": ...}"""
    if method.startswith("_") or not hasattr(_api, method):
        return json.dumps({"error": f"Bilinmeyen işlev: {method}"})
    try:
        return json.dumps({"ok": getattr(_api, method)(*json.loads(args_json))}, ensure_ascii=False)
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        return json.dumps({"error": str(error)}, ensure_ascii=False)


def command(action):
    """Bildirim ya da kulaklık düğmesi: toggle, next, previous"""
    if _backend:
        _backend.push("command", action)
