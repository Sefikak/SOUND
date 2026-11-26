"""Saatte telefonsuz çalma: masaüstü/telefon SOUND'un ortak modülleriyle (searcher, downloader, recommender) şarkıyı
bulur, sesini indirir ve sıradaki şarkıları önerir. Çalma Kotlin'de (LocalPlayer); burası yalnızca veri.

Bütün işlevler engelleyicidir, Kotlin'in arka plan iş parçacığından çağrılır. Sonuçlar JSON metni olarak döner.
"""
import json
import os
import shutil
import sys
import threading
import time
import traceback

_ready = threading.Event()
OFFLINE_DIR = None


def start(data_dir):
    """Veri klasörünü ayarla, yt-dlp güncelleyicisini etkinleştir ve modülleri arka planda ısıt."""
    global OFFLINE_DIR
    import library
    library.DATA_DIR = data_dir
    library.MUSIC_DIR = os.path.join(data_dir, "music")
    library.CACHE_DIR = os.path.join(data_dir, "cache")
    library.THUMB_DIR = os.path.join(data_dir, "thumbs")
    library.VIDEO_DIR = os.path.join(data_dir, "videos")
    library.DB_FILE = os.path.join(data_dir, "library.db")
    library.LIBRARY_FILE = os.path.join(data_dir, "library.json")
    OFFLINE_DIR = os.path.join(data_dir, "offline")
    for folder in (data_dir, library.CACHE_DIR, OFFLINE_DIR):
        os.makedirs(folder, exist_ok=True)
    import updater
    updater.activate(data_dir)  # indirilmiş yeni yt-dlp, ilk içe aktarmadan önce öne geçsin

    def warm():
        try:
            updater.warm()
            import downloader  # noqa: F401  (yt_dlp ve mutagen yüklensin: ilk şarkı beklemesin)
            import recommender  # noqa: F401
        except Exception:
            traceback.print_exc(file=sys.stderr)
        finally:
            _ready.set()
    threading.Thread(target=warm, daemon=True, name="warm").start()

    def later():
        try:
            updater.verify()
            if updater.due():
                updater.update()  # günde bir: YouTube değişince saat yeni APK beklemeden çalmaya devam etsin
        except Exception:
            traceback.print_exc(file=sys.stderr)
    timer = threading.Timer(90, later)
    timer.daemon = True
    timer.start()


def _track(data_json):
    track = json.loads(data_json)
    track.setdefault("url", f"https://www.youtube.com/watch?v={track['id']}")
    track.setdefault("title", "")
    track.setdefault("artist", "")
    return track


def _error(error):
    import downloader
    text = str(error)
    if downloader.is_network_error(error):
        return {"error": "İnternet yok", "network": True}
    if downloader.is_age_error(error):
        return {"error": "Yaş doğrulaması isteyen şarkı"}
    if downloader.is_unavailable_error(error):
        return {"error": "Şarkı YouTube'da yok"}
    return {"error": text[:200]}


def offline_path(track_id):
    return os.path.join(OFFLINE_DIR, os.path.basename(track_id) + ".webm")


def fetch(data_json, keep=False):
    """Şarkının sesini dosyaya indir, yolunu döndür. keep: saate indir (silinmez), değilse dinleme önbelleği."""
    _ready.wait(60)
    import downloader
    track = _track(data_json)
    saved = offline_path(track["id"])
    try:
        if os.path.exists(saved) and os.path.getsize(saved) > 0:
            return json.dumps({"path": saved})
        if not downloader.cache_valid(track["id"]):
            info = downloader.resolve_stream(track)
            wait = (info.get("available_at") or 0) - time.time()
            if wait > 0:
                time.sleep(min(wait, 8))  # YouTube adresi birkaç saniye sonra açılıyor
            downloader.cache_stream(track["id"], info["audio"], info["audio_headers"])
        path = downloader.cache_path(track["id"])
        if keep:
            temp = saved + ".part"
            shutil.copyfile(path, temp)
            os.replace(temp, saved)
            path = saved
        return json.dumps({"path": path})
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        return json.dumps(_error(error), ensure_ascii=False)


def forget(track_id):
    """Saate indirilen şarkıyı sil."""
    try:
        os.remove(offline_path(track_id))
    except OSError:
        pass


def offline_ids():
    try:
        return json.dumps([n[:-5] for n in os.listdir(OFFLINE_DIR) if n.endswith(".webm")])
    except OSError:
        return "[]"


def offline_size():
    try:
        return sum(os.path.getsize(os.path.join(OFFLINE_DIR, n)) for n in os.listdir(OFFLINE_DIR))
    except OSError:
        return 0


def radio(seed_json, context_json="[]", exclude_json="[]"):
    """Sıradakiler: seçilen şarkıya benzeyen şarkılar (telefon/masaüstüyle aynı akıllı sıra)."""
    _ready.wait(60)
    try:
        import recommender
        import searcher
        seed = _track(seed_json)
        try:
            tracks = recommender.smart_queue(seed, context=json.loads(context_json), exclude=json.loads(exclude_json), limit=20)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            tracks = searcher.radio(seed["id"], 20)
        return json.dumps({"tracks": [_slim(t) for t in tracks]}, ensure_ascii=False)
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        return json.dumps(_error(error), ensure_ascii=False)


def search(query):
    _ready.wait(60)
    try:
        import searcher
        songs = searcher.search_songs(query, 15)
        if not songs:
            songs = searcher.search_tracks(query, 15)
        return json.dumps({"tracks": [_slim(t) for t in songs]}, ensure_ascii=False)
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        return json.dumps(_error(error), ensure_ascii=False)


def _slim(track):
    return {"id": track["id"], "title": track.get("title") or "", "artist": track.get("artist") or "",
            "duration": int(track.get("duration") or 0)}


def trim(max_mb=400):
    """Dinleme önbelleği saatin depolamasını doldurmasın (indirilenler ayrı klasörde, dokunulmaz)."""
    try:
        import downloader
        downloader.trim_cache(int(max_mb) * 1024 * 1024)
    except Exception:
        traceback.print_exc(file=sys.stderr)


# ---------- hesabın diğer cihazları (devices.py): saatten PC'yi kumanda et, PC saati görsün ----------

class _Account:
    """devices.Devices'ın istediği kadarı: telefonun verdiği kanal anahtarı. Saatte hesap oturumu tutulmaz."""
    configured = True

    def __init__(self, key, device):
        self.key = key
        self.state = {"device": device}
        self.user = {"id": "watch"}

    def status(self):
        return {"signed_in": bool(self.key)}

    def devices_key(self):
        return self.key


_devices = None


def devices_start(key, device, name):
    """Kanalı aç (anahtar değiştiyse yeniden). Olaylar Kotlin'e Remote.event(json) ile gider."""
    global _devices
    try:
        import devices
        from java import jclass
        remote = jclass("com.sound.wear.Remote")
        if _devices is not None:
            if _devices.cloud.key == key:
                return
            _devices.cloud.key = ""  # eski oturum kapanır (_run döngüsü hesabı yok görür)
            _devices.cloud.user = {"id": "old"}
        account = _Account(key, device)

        class _Logged(devices.Devices):
            def _session(self, *args):
                try:
                    return super()._session(*args)
                except Exception:
                    traceback.print_exc(file=sys.stderr)  # bağlantı neden koptu: logcat (python.stderr)
                    raise
        _devices = _Logged(account, lambda event: remote.event(json.dumps(event, ensure_ascii=False)))
        _devices.describe(name, "watch")
        _devices.start()
    except Exception:
        traceback.print_exc(file=sys.stderr)


def devices_send(kind, data_json, to=""):
    if _devices is None:
        return False
    return bool(_devices.send(kind, json.loads(data_json), to or None))


def devices_status():
    return json.dumps(_devices.status() if _devices else {"connected": False, "devices": []}, ensure_ascii=False)

