import base64
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.request

import yt_dlp
from mutagen import File as MutagenFile
from mutagen.flac import Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TIT2, TPE1, TXXX
from mutagen.oggopus import OggOpus

from library import CACHE_DIR, DATA_DIR, MUSIC_DIR, THUMB_DIR, VIDEO_DIR
from searcher import thumbnail_url

TAG_KEY = "SOUND_TRACK"

# ---------- YouTube hesabı (yaş doğrulamalı videolar için) ----------
# Kullanıcının YouTube'a giriş yaptığı tarayıcının çerezleri ya da dışa aktarılmış cookies.txt.
# Çerezler yalnızca bu bilgisayarda kalır ve yalnızca YouTube'a gönderilir.

COOKIE_FILE = os.path.join(DATA_DIR, "cookies.txt")
BROWSERS = [("firefox", "Firefox"), ("chrome", "Chrome"), ("edge", "Edge"), ("brave", "Brave"), ("opera", "Opera")]
_auth = {"mode": None, "browser": None, "file": None}


def set_auth(settings):
    _auth.update({"mode": None, "browser": None, "file": None})
    _auth.update(settings or {})


UNAVAILABLE_PHRASES = ("video unavailable", "this video is not available", "not available in your country",
                       "blocked it", "has been removed", "private video", "copyright claim", "members-only",
                       "account associated with this video has been terminated")


def is_unavailable_error(error):
    """YouTube videoyu hiç vermiyor mu? ("Requested format is not available" gibi hatalar sayılmaz.)"""
    text = str(error).lower()
    return any(phrase in text for phrase in UNAVAILABLE_PHRASES)


def is_age_error(error):
    text = str(error).lower()
    return "confirm your age" in text or "age-restricted" in text or "inappropriate for some users" in text


def auth_options():
    if _auth["mode"] == "file" and _auth["file"] and os.path.exists(_auth["file"]):
        return {"cookiefile": _auth["file"]}
    if _auth["mode"] == "browser" and _auth["browser"]:
        return {"cookiesfrombrowser": (_auth["browser"],)}
    return {}


def _count_youtube_login(jar):
    names = {c.name for c in jar if "youtube.com" in c.domain}
    return len(names), bool(names & {"SID", "__Secure-3PSID", "LOGIN_INFO", "SAPISID"})


def check_browser_login(browser):
    """Tarayıcının çerezlerini okuyabiliyor muyuz ve YouTube'a giriş yapılmış mı? (başarı, mesaj)"""
    from yt_dlp.cookies import extract_cookies_from_browser
    try:
        jar = extract_cookies_from_browser(browser)
    except Exception as error:
        text = str(error)
        if "Could not copy" in text:
            return False, ("Tarayıcı açıkken çerez dosyası kilitli. Tarayıcıyı tamamen kapat (sağ alttaki simge "
                           "tepsisinde de çalışmasın) ve tekrar dene — ya da cookies.txt yolunu kullan.")
        if "decrypt" in text.lower() or "app-bound" in text.lower() or "v20" in text:
            return False, "Bu tarayıcı çerezlerini yeni yöntemle şifreliyor, okunamıyor. cookies.txt yolunu kullan."
        return False, f"Çerezler okunamadı ({text.splitlines()[0][:90]})"
    count, logged_in = _count_youtube_login(jar)
    if not logged_in:
        return False, "Bu tarayıcıda YouTube'a giriş yapılmamış görünüyor."
    # Bir kez kopyala: sonraki indirmelerde tarayıcının kapalı olması gerekmesin
    from http.cookiejar import MozillaCookieJar
    saved = MozillaCookieJar(COOKIE_FILE)
    for cookie in jar:
        if cookie.domain.endswith(("youtube.com", "google.com")):
            saved.set_cookie(cookie)
    saved.save(ignore_discard=True, ignore_expires=True)
    return True, "YouTube oturumu bulundu ve kaydedildi."


def check_cookie_file(path):
    from http.cookiejar import MozillaCookieJar
    jar = MozillaCookieJar()
    try:
        jar.load(path, ignore_discard=True, ignore_expires=True)
    except Exception as error:
        return False, f"Dosya okunamadı: {str(error)[:90]}"
    count, logged_in = _count_youtube_login(jar)
    if not logged_in:
        return False, "Dosyada YouTube oturum çerezi yok. Giriş yapmışken dışa aktar."
    return True, "YouTube oturumu bulundu."

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = shutil.which("ffmpeg")

# YouTube, hesaplı isteklerde (yaş doğrulaması) JavaScript ile çözülmesi gereken bir bilmece gönderiyor.
# Bunu yt-dlp, Deno çalışma ortamı + yt-dlp-ejs betikleriyle çözer; Deno PATH'te olmayabilir, yolunu veriyoruz.
try:
    import deno
    DENO = deno.find_deno_bin()
except Exception:
    DENO = shutil.which("deno")
JS_OPTIONS = {"js_runtimes": {"deno": {"path": DENO}}} if DENO and os.path.exists(DENO) else {}


def safe_name(text):
    text = re.sub(r'[<>:"/\\|?*%\x00-\x1f]', "", text).strip(" .")
    return text[:80] or "parca"


def _download_with_auth_fallback(url, options):
    """Önce oturumsuz dener: eskimiş çerezler normal videoları da bozabiliyor.
    Oturum (çerezler) yalnızca YouTube yaş doğrulaması isterse kullanılır."""
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except Exception as error:
        if not (is_age_error(error) and auth_options()):
            raise
        try:
            with yt_dlp.YoutubeDL({**options, **auth_options()}) as ydl:
                ydl.download([url])
        except Exception as auth_error:
            if "needs to be reloaded" in str(auth_error):
                raise RuntimeError("YouTube oturumu geçersiz (çerezler yenilenmiş). Çerezleri gizli pencereden "
                                   "yeniden dışa aktar — Sign in to confirm your age") from auth_error
            raise


def _alternative_url(track):
    """Engelli/silinmiş bir videonun yerine aynı şarkının başka bir yüklemesi.
    Süresi orijinale yakın olmalı ki yanlış şarkı inmesin."""
    query = f'{track.get("artist") or ""} {track["title"]}'.strip()
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
        entries = ydl.extract_info(f"ytsearch6:{query}", download=False).get("entries") or []
    wanted = track.get("duration") or 0
    for entry in entries:
        if not entry or entry.get("id") == track["id"] or len(entry.get("id") or "") != 11:
            continue
        duration = entry.get("duration") or 0
        if wanted and (not duration or abs(duration - wanted) > max(20, wanted * 0.1)):
            continue
        return f"https://www.youtube.com/watch?v={entry['id']}"
    return None


# YouTube'un "visionos" istemcisi adresleri ~1,5 sn'de veriyor ve hemen açıyor. Varsayılan istemciler
# ~4 sn sürüyor, üstüne YouTube adresleri 3-4 sn bekletiyor ("available_at"). Hızlı yol yaş kısıtlı
# videolarda çalışmaz; o zaman varsayılan yola (gerekirse çerezlerle) düşülür.
FAST_CLIENT = {"extractor_args": {"youtube": {"player_client": ["visionos"], "skip": ["hls", "translated_subs"]}}}
_fast = threading.local()  # iş parçacığı başına bir yt-dlp örneği: oynatıcı betikleri tekrar tekrar inmesin


def _fast_extract(url, options):
    key = repr(sorted(options.items()))
    ydl = getattr(_fast, "ydl", None)
    if ydl is None or _fast.key != key:
        ydl = _fast.ydl = yt_dlp.YoutubeDL({**options, **FAST_CLIENT})
        _fast.key = key
    return ydl.extract_info(url, download=False)


def _run_ytdl(track, options):
    """İndir; video engelliyse (bölge/telif) aynı şarkının başka bir yüklemesini dene.
    Yedek kullanıldıysa track["alt_source"] o adres olur (arayüz kullanıcıya söyler)."""
    try:
        with yt_dlp.YoutubeDL({**options, **FAST_CLIENT}) as ydl:  # önce hızlı yol
            ydl.download([track["url"]])
        return
    except yt_dlp.utils.DownloadCancelled:
        raise
    except Exception:
        pass
    try:
        _download_with_auth_fallback(track["url"], options)
    except Exception as error:
        if not is_unavailable_error(error) or is_age_error(error):
            raise
        alternative = _alternative_url(track)
        if not alternative:
            raise
        _download_with_auth_fallback(alternative, options)
        track["alt_source"] = alternative


_age_restricted = set()  # yaş doğrulaması istediği görülen adresler: bir dahaki sefere doğrudan oturumla dene


def _extract_with_auth_fallback(url, options):
    """_download_with_auth_fallback'in indirmeyen hali: yalnızca bilgileri ve akış adreslerini alır.
    Önce hızlı istemci; olmazsa varsayılan istemciler, yaş doğrulamasında çerezlerle."""
    if url not in _age_restricted:
        try:
            return _fast_extract(url, options)
        except Exception as error:
            if is_unavailable_error(error) and not is_age_error(error):
                raise  # video hiç yok: varsayılan yolu denemek boşuna
    if url in _age_restricted and auth_options():
        options = {**options, **auth_options()}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as error:
        if not (is_age_error(error) and auth_options()) or "cookiefile" in options or "cookiesfrombrowser" in options:
            raise
        _age_restricted.add(url)
        try:
            with yt_dlp.YoutubeDL({**options, **auth_options()}) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as auth_error:
            if "needs to be reloaded" in str(auth_error):
                raise RuntimeError("YouTube oturumu geçersiz (çerezler yenilenmiş). Çerezleri gizli pencereden "
                                   "yeniden dışa aktar — Sign in to confirm your age") from auth_error
            raise


def _pick_video(formats):
    """Panelde gösterilecek sessiz görüntü akışı (format sözlüğü): panel küçük, en fazla 480p yeter
    (daha çabuk açılır); mümkünse MP4 (H.264)."""
    videos = [f for f in formats if f.get("url") and f.get("vcodec") not in (None, "none")
              and f.get("acodec") in (None, "none") and (f.get("height") or 0) <= 480
              and f.get("protocol", "https").startswith("http")]
    if not videos:
        return None
    return max(videos, key=lambda f: (f.get("height") or 0, (f.get("vcodec") or "").startswith("avc1"), f.get("tbr") or 0))


def resolve_stream(track):
    """Şarkıyı indirmeden çalmak için YouTube'un doğrudan ses (ve görüntü) adresleri ve istenen HTTP başlıkları.

    Adresler birkaç saat geçerlidir ("expire"). Video engelliyse aynı şarkının başka bir yüklemesi kullanılır."""
    options = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
               "format": "bestaudio[ext=webm]/bestaudio/best", **JS_OPTIONS}
    alternative = None
    try:
        info = _extract_with_auth_fallback(track["url"], options)
    except Exception as error:
        if not is_unavailable_error(error) or is_age_error(error):
            raise
        alternative = _alternative_url(track)
        if not alternative:
            raise
        info = _extract_with_auth_fallback(alternative, options)
    audio = info.get("url")
    if not audio:
        raise RuntimeError("Ses akışı bulunamadı")
    match = re.search(r"[?&/]expire[=/](\d+)", audio)
    video = _pick_video(info.get("formats") or [])
    # YouTube bazı adresleri birkaç saniye sonra açıyor ("available_at"); öncesinde istek 403 alır
    audio_format = next((f for f in info.get("formats") or [] if f.get("format_id") == info.get("format_id")), info)
    return {
        "audio": audio,
        "audio_headers": info.get("http_headers") or {},
        "video": video and video["url"],
        "video_headers": video and (video.get("http_headers") or {}),
        "expire": int(match.group(1)) if match else 0,
        "available_at": max(audio_format.get("available_at") or 0, (video or {}).get("available_at") or 0),
        "alt": alternative,
    }


def _base_options(folder, stem):
    if not FFMPEG:
        raise RuntimeError("ffmpeg bulunamadı (pip install imageio-ffmpeg)")
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "outtmpl": os.path.join(folder.replace("%", "%%"), stem + ".%(ext)s"),
        "ffmpeg_location": FFMPEG,
        **JS_OPTIONS,
    }


def _ffmpeg(*args):
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: konsol penceresi açılmasın
    result = subprocess.run([FFMPEG, "-v", "error", "-y", *args], capture_output=True, creationflags=flags)
    if result.returncode != 0:
        raise RuntimeError("Ses dönüştürülemedi: " + result.stderr.decode(errors="replace")[-200:])


def _hooks(progress, cancelled, parts=1):
    """yt-dlp ilerleme bildirimleri -> progress(0..1); cancelled() True dönerse indirmeyi keser.
    Video indirmede görüntü ve ses ayrı dosyalar olarak iner (parts=2); ilerleme ikisinin ortalaması."""
    files = {}

    def on_download(d):
        if cancelled and cancelled():
            raise yt_dlp.utils.DownloadCancelled("İndirme iptal edildi")
        if progress and d.get("status") in ("downloading", "finished"):
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = 1.0 if d["status"] == "finished" else (d.get("downloaded_bytes", 0) / total if total else 0)
            files[d.get("filename")] = min(done, 1.0)
            progress(0.9 * sum(files.values()) / max(parts, len(files)))

    def on_post(d):
        if progress and d.get("status") == "started":
            progress(0.94)  # ffmpeg dönüştürüyor

    return {"progress_hooks": [on_download], "postprocessor_hooks": [on_post]}


def _download_mp3(track, folder, stem, progress=None, cancelled=None):
    final_path = os.path.join(folder, stem + ".mp3")
    if os.path.exists(final_path):
        return final_path
    options = _base_options(folder, stem)
    options["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    options["postprocessor_args"] = {"extractaudio": ["-compression_level", "9"]}  # en hızlı kodlama (~2 kat)
    options.update(_hooks(progress, cancelled))
    _run_ytdl(track, options)
    if not os.path.exists(final_path):
        raise RuntimeError("Ses dosyası oluşturulamadı")
    return final_path


def cache_path(track_id):
    """Dinleme önbelleği: dinlenen şarkının YouTube'daki orijinal sesi (Opus, WebM içinde)."""
    return os.path.join(CACHE_DIR, track_id + ".webm")


def _wav_path(track_id):
    return os.path.join(CACHE_DIR, track_id + ".wav")


def cache_stream(track_id, url, headers, cancelled=None):
    """Akış adresinden sesi parça parça önbelleğe indirir (uçsuz istekleri YouTube yavaş verir)."""
    target = cache_path(track_id)
    if os.path.exists(target):
        return target
    temp = target + ".part"
    headers = {k: v for k, v in (headers or {}).items() if k.lower() != "range"}
    position, total = 0, None
    try:
        with open(temp, "wb") as f:
            while total is None or position < total:
                if cancelled and cancelled():
                    raise yt_dlp.utils.DownloadCancelled("İptal")
                request = urllib.request.Request(url, headers={**headers, "Range": f"bytes={position}-{position + 2 * 1024 * 1024 - 1}"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    if total is None:
                        match = re.search(r"/(\d+)", response.headers.get("Content-Range") or "")
                        total = int(match.group(1)) if match else int(response.headers.get("Content-Length") or 0)
                    data = response.read()
                if not data:
                    break
                f.write(data)
                position += len(data)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.remove(temp)
    return target


def fetch_for_stream(track):
    """(Eski Tk sürümü için) dinlemek üzere WAV'a açılmış önbellek dosyası."""
    final_path = _wav_path(track["id"])
    if os.path.exists(final_path):
        return final_path
    stem = track["id"] + ".raw"
    _run_ytdl(track, _base_options(CACHE_DIR, stem))
    raw = next((os.path.join(CACHE_DIR, name) for name in os.listdir(CACHE_DIR) if name.startswith(stem + ".")), None)
    if not raw:
        raise RuntimeError("Ses dosyası oluşturulamadı")
    temp = final_path + ".part.wav"
    try:
        _ffmpeg("-i", raw, "-vn", "-c:a", "pcm_s16le", temp)
        os.replace(temp, final_path)
    finally:
        for path in (raw, temp):
            if os.path.exists(path):
                os.remove(path)
    return final_path


def fetch_video(track, progress=None, cancelled=None):
    """Videoyu (en fazla 1080p, MP4) data/videos içine indirir, dosya adını döner."""
    stem = f'{safe_name(track["title"])} [{track["id"]}]'
    target = os.path.join(VIDEO_DIR, stem + ".mp4")
    if not os.path.exists(target):
        options = _base_options(VIDEO_DIR, stem)
        options["format"] = ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                             "bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best")
        options["merge_output_format"] = "mp4"
        options.update(_hooks(progress, cancelled, parts=2))
        _run_ytdl(track, options)
        if not os.path.exists(target):
            raise RuntimeError("Video dosyası oluşturulamadı")
    if progress:
        progress(1.0)
    return stem + ".mp4"


def _to_opus(source, target):
    """YouTube'un sesi zaten Opus: yeniden kodlamadan .opus dosyasına aktar (anında, kayıpsız).
    Opus değilse (nadiren AAC) Opus'a kodla."""
    temp = target + ".part.opus"
    try:
        try:
            _ffmpeg("-i", source, "-vn", "-map_metadata", "-1", "-c:a", "copy", temp)
        except RuntimeError:
            _ffmpeg("-i", source, "-vn", "-map_metadata", "-1", "-c:a", "libopus", "-b:a", "160k", temp)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def fetch_for_library(track, progress=None, cancelled=None):
    """Kalıcı olarak data/music içine indirir (YouTube'un orijinal sesi, Opus), dosya adını döner.

    MP3'e çevirmiyoruz: çevirmek kalite kaybettirir, zaman alır ve dosyayı büyütür. Şarkı az önce
    dinlendiyse önbellekteki ses kullanılır, hiç indirilmez."""
    stem = f'{safe_name(track["title"])} [{track["id"]}]'
    target = os.path.join(MUSIC_DIR, stem + ".opus")
    if not os.path.exists(target):
        cached = cache_path(track["id"])
        if os.path.exists(cached):
            if progress:
                progress(0.5)
            _to_opus(cached, target)
        else:
            raw_stem = stem + ".raw"
            options = _base_options(MUSIC_DIR, raw_stem)
            options["format"] = "bestaudio[acodec=opus]/bestaudio"
            options.update(_hooks(progress, cancelled))
            _run_ytdl(track, options)
            raw = next((os.path.join(MUSIC_DIR, name) for name in os.listdir(MUSIC_DIR)
                        if name.startswith(raw_stem + ".") and not name.endswith(".part")), None)
            if not raw:
                raise RuntimeError("Ses dosyası oluşturulamadı")
            if progress:
                progress(0.95)
            try:
                _to_opus(raw, target)
            finally:
                os.remove(raw)
    if progress:
        progress(1.0)

    try:
        fetch_thumbnail(track)
    except Exception:
        pass
    try:
        write_tags(target, track)
    except Exception:
        pass
    return stem + ".opus"


# ---------- dosya etiketleri ----------
# Şarkının bilgileri ve kapağı dosyanın içine de yazılır. Böylece YouTube'dan silinse,
# kitaplık kaybolsa bile dosya kendi başına yeterli olur ve kitaplık geri kurulabilir.
# MP3: ID3 etiketleri · Opus: Vorbis yorumları (kapak METADATA_BLOCK_PICTURE olarak)

def _meta(track):
    return {key: track.get(key) for key in ("id", "title", "artist", "duration", "thumbnail", "url")}


def write_tags(path, track):
    cover = os.path.join(THUMB_DIR, track["id"] + ".jpg")
    if path.lower().endswith(".opus"):
        audio = OggOpus(path)
        audio["title"] = track["title"]
        audio["artist"] = track["artist"]
        audio[TAG_KEY.lower()] = json.dumps(_meta(track), ensure_ascii=False)
        if os.path.exists(cover):
            picture = Picture()
            picture.type, picture.mime, picture.desc = 3, "image/jpeg", "Cover"
            with open(cover, "rb") as f:
                picture.data = f.read()
            audio["metadata_block_picture"] = base64.b64encode(picture.write()).decode()
        audio.save()
        return
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.setall("TIT2", [TIT2(encoding=3, text=track["title"])])
    tags.setall("TPE1", [TPE1(encoding=3, text=track["artist"])])
    tags.setall(f"TXXX:{TAG_KEY}", [TXXX(encoding=3, desc=TAG_KEY, text=json.dumps(_meta(track), ensure_ascii=False))])
    if os.path.exists(cover):
        with open(cover, "rb") as f:
            tags.setall("APIC", [APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=f.read())])
    tags.save(path)


def has_tags(path):
    try:
        if path.lower().endswith(".opus"):
            return TAG_KEY.lower() in OggOpus(path)
        return bool(ID3(path).getall(f"TXXX:{TAG_KEY}"))
    except Exception:
        return False


def read_tags(path):
    """Dosyadan şarkı bilgisini çıkar; etiket yoksa dosya adındaki [video-id]'den tahmin et."""
    meta, picture = None, None
    try:
        if path.lower().endswith(".opus"):
            audio = OggOpus(path)
            if TAG_KEY.lower() in audio:
                meta = json.loads(audio[TAG_KEY.lower()][0])
                if "metadata_block_picture" in audio:
                    picture = Picture(base64.b64decode(audio["metadata_block_picture"][0])).data
        else:
            tags = ID3(path)
            frames = tags.getall(f"TXXX:{TAG_KEY}")
            if frames:
                meta = json.loads(frames[0].text[0])
                pictures = tags.getall("APIC")
                picture = pictures[0].data if pictures else None
    except Exception:
        meta = None
    if meta and picture:
        cover = os.path.join(THUMB_DIR, meta["id"] + ".jpg")
        if not os.path.exists(cover):
            with open(cover, "wb") as f:
                f.write(picture)

    if meta is None:
        match = re.match(r"^(.*) \[([\w-]{11})\]\.(mp3|opus)$", os.path.basename(path))
        if not match:
            return None
        video_id = match.group(2)
        try:
            duration = int(MutagenFile(path).info.length)
        except Exception:
            duration = 0
        meta = {"id": video_id, "title": match.group(1), "artist": "Bilinmeyen sanatçı", "duration": duration,
                "thumbnail": thumbnail_url(video_id), "url": f"https://www.youtube.com/watch?v={video_id}"}
    return meta


def scan_music_folder(known_by_file):
    """Etiketi eksik indirilenlere etiket yazar; kitaplıkta olmayan dosyaları [(dosya, bilgi)] döner."""
    missing = []
    for name in os.listdir(MUSIC_DIR):
        if not name.lower().endswith(".opus"):  # eski MP3'ler artık kullanılmıyor
            continue
        path = os.path.join(MUSIC_DIR, name)
        track = known_by_file.get(name)
        if track:
            if not has_tags(path):
                try:
                    fetch_thumbnail(track)
                except Exception:
                    pass
                try:
                    write_tags(path, track)
                except Exception:
                    pass
        else:
            meta = read_tags(path)
            if meta:
                missing.append((name, meta))
    return missing


def fetch_thumbnail(track):
    path = os.path.join(THUMB_DIR, track["id"] + ".jpg")
    if os.path.exists(path):
        return path

    request = urllib.request.Request(track["thumbnail"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read()

    temp = path + ".tmp"
    with open(temp, "wb") as f:
        f.write(data)
    os.replace(temp, path)
    return path


def trim_cache(max_bytes=1500 * 1024 * 1024):
    """Dinleme önbelleğini sınırda tut: en uzun süredir dinlenmeyenleri sil. Eski WAV dosyaları hep silinir."""
    files = []
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        if not name.endswith(".webm"):
            if not name.endswith(".part"):
                try:
                    os.remove(path)
                except OSError:
                    pass
            continue
        files.append((os.path.getmtime(path), os.path.getsize(path), path))
    files.sort(reverse=True)
    total = 0
    for _, size, path in files:
        total += size
        if total > max_bytes:
            try:
                os.remove(path)
            except OSError:
                pass


def cache_size():
    return sum(os.path.getsize(os.path.join(CACHE_DIR, n)) for n in os.listdir(CACHE_DIR) if n.endswith(".webm"))
