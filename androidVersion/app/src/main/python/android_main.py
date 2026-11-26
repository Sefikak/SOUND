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
_login = None


class Window:
    """pywebview penceresinin Backend'in kullandığı kısmı; işi Kotlin tarafına iletir."""

    def __init__(self, native):
        self.bridge = native

    def evaluate_js(self, code):
        self.bridge.evaluateJs(code)

    def set_title(self, title):
        pass

    def create_file_dialog(self, dialog_type=None, directory="", allow_multiple=False, save_filename="", file_types=()):
        """Android'in dosya seçicisi; seçilenler uygulamanın önbelleğine kopyalanmış yollar olarak döner."""
        paths = json.loads(str(self.bridge.pickFiles(bool(allow_multiple))))
        return paths or None


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
    Opus/WebM olduğu için dönüştürmeden olduğu gibi saklanır."""
    import shutil
    import downloader
    from library import MUSIC_DIR

    def fetch_for_library(track, progress=None, cancelled=None):
        stem = f"{downloader.safe_name(track['title'])} [{track['id']}]"
        found = next((n for n in os.listdir(MUSIC_DIR) if n.startswith(stem + ".") and not n.endswith(".part")), None)
        if not found:
            cached = downloader.cache_path(track["id"])
            if downloader.cache_valid(track["id"]):
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
        """ffmpeg olmadığından birleştirme yok: görüntü sessiz dosya olarak iner, ses normal indirmeyle ayrı gelir.
        Tam ekran görüntüyü zaten sesiz oynatıp sesle eşleştiriyor, sonuç çevrimdışı da aynı. En çok 720p: yer kaplamasın."""
        from library import VIDEO_DIR
        stem = f"{downloader.safe_name(track['title'])} [{track['id']}]"
        target = os.path.join(VIDEO_DIR, stem + ".mp4")
        if not os.path.exists(target):
            options = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
                       "format": "bestvideo[ext=mp4][vcodec^=avc1][height<=720]/bestvideo[ext=mp4][height<=720]/best[ext=mp4]",
                       "outtmpl": os.path.join(VIDEO_DIR.replace("%", "%%"), stem + ".%(ext)s")}
            options.update(downloader._hooks(progress, cancelled))
            downloader._run_ytdl(track, options)
            if not os.path.exists(target):
                raise RuntimeError("Video dosyası oluşturulamadı")
        if progress:
            progress(1.0)
        if _backend and not _backend.lib.is_downloaded(track["id"]):
            _backend.download(track, "audio")  # çevrimdışı izlerken ses de olsun
        return stem + ".mp4"

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


class _InAppLogin:
    """Google girişi uygulamanın içinde açılır: oturum çerezleri tarayıcıdan okunamaz, kendi görünümümüzden okunur.
    pywebview penceresinin Backend'in kullandığı kısmı."""

    def __init__(self, native, url):
        self.native = native
        self.events = _Events()
        native.openLogin(url)

    def get_current_url(self):
        return self.native.loginUrl()

    def get_cookies(self):
        from http.cookies import CookieError, SimpleCookie
        jar = SimpleCookie()
        for part in (self.native.loginCookies() or "").split(";"):
            name, _, value = part.strip().partition("=")
            try:
                jar[name] = value
            except CookieError:
                continue
            jar[name]["domain"] = ".youtube.com"
            jar[name]["path"] = "/"
            jar[name]["secure"] = True
        return [jar]

    def destroy(self):
        self.native.closeLogin()


def login_closed():
    """Kullanıcı giriş ekranını kapattı (Kotlin çağırır)."""
    if _login:
        _login.events.closed.fire()


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
        global _login
        if "accounts.spotify.com" in url:
            native.openUrl(url)
            return _BrowserLogin()
        _login = _InAppLogin(native, url)
        return _login
    webview.create_window = create_window
    webapp.webbrowser = types.SimpleNamespace(open=native.openUrl)

    original = backend.login_import

    def login_import(service, client_id=None, start_import=True):
        # tarayıcıda yarım kalan giriş yenisini engellemesin: öncekini bitir, kapısının boşalmasını bekle
        previous = backend.login_window
        if previous:
            previous.events.closed.fire()
            for _ in range(20):
                if not backend.login_window:
                    break
                time.sleep(0.1)
        return original(service, client_id, start_import)
    backend.login_import = login_import

    forget = _api.auth_clear

    def auth_clear():
        """Hesaptan çıkınca oturum telefonda kalmasın: dosya ve giriş ekranının çerezleri silinir."""
        import downloader
        status = forget()
        native.clearLogin()
        if os.path.exists(downloader.COOKIE_FILE):
            os.remove(downloader.COOKIE_FILE)
        return status
    _api.auth_clear = auth_clear


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
    import updater
    updater.activate(data_dir)  # yt_dlp'yi ilk içe aktaran webapp'tan önce: indirilmiş sürüm öne geçsin (hemen döner)
    import webapp
    _patch_downloads()
    _backend = webapp.Backend()
    _backend.window = Window(native)
    from android.os import Build
    _backend.devices.describe(f"{Build.MANUFACTURER.capitalize()} {Build.MODEL}", "phone")
    _backend.app_return_url = "soundapp://back"  # tarayıcıdaki giriş sayfasının "SOUND'a dön" düğmesi (AndroidManifest)
    _api = webapp.Api(_backend)
    _patch_login(native, _backend)
    _patch_update(native, data_dir)

    original = _backend.player_state

    def player_state(state):
        global _last_state
        original(state)
        _last_state = state
        native.playerState(json.dumps(_with_watch_fields(state), ensure_ascii=False))
    _backend.player_state = player_state
    _backend.lib.subscribe(_library_changed)  # saat: beğeni değişince kalp, kitaplık değişince listeler
    # sistem bildirimi: masaüstündeki tepsi baloncuğu yerine Android bildirimi (MainActivity.Native.notify)
    _backend.notify = lambda title, body, target="": native.notify(str(title)[:60], str(body)[:250], str(target)[:80]) or True
    _patch_audio(native, _backend)
    global _watch_likes_file
    _watch_likes_file = os.path.join(os.path.dirname(data_dir), "watch_likes.jsonl")
    threading.Timer(5, _drain_watch_likes).start()
    # yt_dlp arayüz açılırken arka planda yüklenir; ilk arama/çalma onu beklemesin diye hemen başlıyor
    threading.Thread(target=updater.warm, daemon=True, name="ytdlp-warm").start()
    threading.Timer(30, updater.verify).start()
    return mediaserver.start() + "/index.html"


def _patch_audio(native, backend):
    """Ses çıkışları ve kulaklık ayarları Kotlin'de (AudioOutputs, Prefs): uygulama kapalıyken de bilinmeli."""
    _api.audio_outputs = lambda: json.loads(str(native.audioOutputs()))
    _api.audio_output_select = lambda device_id="": json.loads(str(native.selectOutput(str(device_id or ""))))
    _api.audio_output_more = lambda: bool(native.bluetoothSettings())

    def sync():
        settings = backend.lib.settings
        native.headsetPrefs(settings.get("headset_play", True) is not False, settings.get("headset_pause", True) is not False)

    original = _api.update_settings

    def update_settings(changes):
        result = original(changes)
        if "headset_play" in changes or "headset_pause" in changes:
            sync()
        return result
    _api.update_settings = update_settings
    sync()


# ---------- Galaxy Watch (WatchLink.kt / WatchService) ----------

_last_state = None
_lists_timer = None


def _with_watch_fields(state):
    """Çalma durumuna saatin istediği alanlar: beğenildi mi, ses düzeyi, vurgu rengi."""
    out = dict(state or {})
    track = out.get("track") or {}
    try:
        out["liked"] = bool(track.get("id")) and _backend.lib.is_favorite(track["id"])
        out["volume"] = _backend.lib.volume
        out["accent"] = (_backend.lib.settings.get("ui") or {}).get("accent") or "#8b5cf6"
    except Exception:
        pass
    return out


def _library_changed():
    global _lists_timer
    if _last_state and _last_state.get("track"):
        _native().playerState(json.dumps(_with_watch_fields(_last_state), ensure_ascii=False))
    if _lists_timer:
        _lists_timer.cancel()
    _lists_timer = threading.Timer(3, watch_lists_now)
    _lists_timer.daemon = True
    _lists_timer.start()


def _native():
    return _backend.window.bridge


def watch_lists():
    """Saatteki Kitaplık ekranı: favoriler, mixler, albümler."""
    lib = _backend.lib
    mixes = []
    cache = lib.data.get("mixes") or {}
    for mix in list(cache.get("daily") or []) + [m for m in (cache.get("weekly"), cache.get("radar")) if m]:
        mixes.append({"key": mix["key"], "title": mix["title"], "sub": mix.get("subtitle", ""), "count": len(mix.get("tracks") or [])})
    albums = sorted(lib.data["albums"].items(), key=lambda kv: kv[1].get("created") or 0, reverse=True)
    return {
        "favorites": len(lib.data["favorites"]),
        "mixes": mixes,
        "albums": [{"id": album_id, "title": album["name"], "count": len(album["tracks"])} for album_id, album in albums[:40]],
        "recent": [{"id": t["id"], "title": t["title"], "artist": t["artist"]} for t in lib.recent_tracks(12)],
        "devices": _devices_key(),
        "at": time.time(),
    }


def _devices_key():
    """Saat de hesabın cihazlarından biri olsun (PC'yi kumanda etsin, PC onu görsün): cihaz kanalının anahtarı.
    Yalnızca bu uygulamanın saatteki eşine (aynı imza) Data Layer üzerinden gider."""
    try:
        cloud = _backend.cloud
        if cloud.status().get("signed_in"):
            return cloud.state.get("devices_key") or ""
    except Exception:
        pass
    return ""


def _slim(track):
    return {"id": track["id"], "title": track.get("title") or "", "artist": track.get("artist") or "",
            "duration": int(track.get("duration") or 0)}


def watch_library():
    """Saatin telefonsuz çalabilmesi için listelerin şarkıları (saat bunu saklar; telefon uzaktayken buradan çalar)."""
    lib = _backend.lib
    cache = lib.data.get("mixes") or {}
    mixes = [{"key": m["key"], "title": m["title"], "sub": m.get("subtitle", ""), "tracks": [_slim(t) for t in m.get("tracks") or []]}
             for m in list(cache.get("daily") or []) + [m for m in (cache.get("weekly"), cache.get("radar")) if m]]
    albums = sorted(lib.data["albums"].items(), key=lambda kv: kv[1].get("created") or 0, reverse=True)
    return {
        "favorites": [_slim(t) for t in lib.favorite_tracks()[:1000]],
        "albums": [{"id": album_id, "title": album["name"], "tracks": [_slim(t) for t in lib.album_tracks(album_id)]}
                   for album_id, album in albums[:60]],
        "mixes": mixes,
        "recent": [_slim(t) for t in lib.recent_tracks(30)],
        "at": time.time(),
    }


def watch_lists_now():
    if _backend:
        try:
            _drain_watch_likes()
            _native().watchLists(json.dumps(watch_lists(), ensure_ascii=False), json.dumps(watch_library(), ensure_ascii=False))
        except Exception:
            traceback.print_exc(file=sys.stderr)


_watch_likes_file = None


def watch_like(data_json):
    """Saatte (telefonsuz çalarken) beğenilen / beğeni kaldırılan şarkı: {"track": {...}, "on": true}.
    "dislike": true ise "Beğenmedim" listesine eklenir / çıkarılır."""
    if not _backend:
        return
    try:
        data = json.loads(data_json)
        track = dict(data["track"])
        track.setdefault("url", f"https://www.youtube.com/watch?v={track['id']}")
        if data.get("dislike"):
            _backend.lib.dislike(track, bool(data.get("on")))
        elif bool(data.get("on")) != _backend.lib.is_favorite(track["id"]):
            _backend.lib.toggle_favorite(track)
    except Exception:
        traceback.print_exc(file=sys.stderr)


def _drain_watch_likes():
    """SOUND kapalıyken saatten gelen beğeniler WatchService tarafından dosyada bekletilir."""
    if not _watch_likes_file or not os.path.exists(_watch_likes_file):
        return
    try:
        with open(_watch_likes_file, encoding="utf-8") as file:
            lines = file.read().splitlines()
        os.remove(_watch_likes_file)
    except OSError:
        return
    for line in lines:
        if line.strip():
            watch_like(line)


def watch_play(data_json):
    """Saatteki Kitaplık ekranından bir şey seçildi: arayüz çalar (app.js "watch_play")."""
    if _backend:
        try:
            _backend.push("watch_play", json.loads(data_json))
        except ValueError:
            pass


def audio_changed(state_json):
    """Kulaklık bağlandı / çıktı (AudioOutputs.watch): arayüz güncellensin."""
    if _backend:
        _backend.push("audioout", json.loads(state_json))


def call(method, args_json):
    """Arayüzden gelen window.pywebview.api.<method>(...) çağrısı. Sonuç JSON: {"ok": ...} ya da {"error": ...}"""
    if method.startswith("_") or not hasattr(_api, method):
        return json.dumps({"error": f"Bilinmeyen işlev: {method}"})
    try:
        return json.dumps({"ok": getattr(_api, method)(*json.loads(args_json))}, ensure_ascii=False)
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        return json.dumps({"error": str(error)}, ensure_ascii=False)


def open_target(target):
    """Bildirime dokunuldu: arayüz ilgili sohbeti / daveti açar."""
    if _backend:
        _backend.push("open_target", target)


def command(action):
    """Bildirim ya da kulaklık düğmesi: toggle, next, previous"""
    if _backend:
        _backend.push("command", action)
