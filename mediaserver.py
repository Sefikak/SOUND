"""Arayüze dosya sunan küçük yerel HTTP sunucusu (yalnızca 127.0.0.1).

/            arayüz dosyaları (web/ klasörü)
/music/...   indirilen şarkılar (Opus, eskiler MP3) · /cache/... dinleme önbelleği  · /videos/... indirilen videolar  (ileri sarma için Range destekli)
/thumb/ID    kapak resmi: önce data/thumbs, yoksa YouTube'dan alınıp oraya kaydedilir (çevrimdışı da görünsün)
/stream/ID/audio|video   YouTube akışı: YouTube bazı adresleri yalnızca yt-dlp'nin kullandığı tarayıcı
             başlıklarıyla verir; oynatıcı bu başlıkları gönderemediği için akış buradan aktarılır
"""
import mimetypes
import os
import re
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from library import CACHE_DIR, MUSIC_DIR, THUMB_DIR, VIDEO_DIR

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
TYPES = {".mp3": "audio/mpeg", ".opus": "audio/ogg", ".webm": "audio/webm", ".mp4": "video/mp4", ".js": "text/javascript", ".css": "text/css",
         ".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon",
         ".svg": "image/svg+xml", ".woff2": "font/woff2"}
VIDEO_ID = re.compile(r"^[\w-]{11}$")
STREAM_PATH = re.compile(r"^/stream/([\w-]{11})/(audio|video)$")
FIRST_CHUNK = 256 * 1024       # akışın ilk parçası: küçük, çalma hemen başlasın
NEXT_CHUNK = 2 * 1024 * 1024   # sonraki parçalar
_streams = {}  # şarkı kimliği -> {"audio": (adres, başlıklar, açılış zamanı), "video": (...)}


def register_stream(video_id, kind, url, headers, available_at=0):
    _streams.setdefault(video_id, {})[kind] = (url, dict(headers or {}), available_at)


def stream_source(video_id, kind):
    return _streams.get(video_id, {}).get(kind)
_thumb_locks = {}
_thumb_guard = threading.Lock()


def _inside(folder, name):
    path = os.path.realpath(os.path.join(folder, name))
    return path if path.startswith(os.path.realpath(folder) + os.sep) and os.path.isfile(path) else None


ART_HOSTS = (".googleusercontent.com", ".ggpht.com", "i.ytimg.com")


def _thumbnail(video_id, source=None):
    """Kapağı diskte yoksa indir (YouTube Music'in kare kapağı varsa o); aynı kapak için aynı anda tek istek."""
    path = os.path.join(THUMB_DIR, video_id + ".jpg")
    host = urllib.parse.urlparse(source or "").hostname or ""
    if not (source and source.startswith("https://") and host.endswith(ART_HOSTS)):
        source = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
    if os.path.exists(path):
        return path
    with _thumb_guard:
        lock = _thumb_locks.setdefault(video_id, threading.Lock())
    with lock:
        if os.path.exists(path):
            return path
        request = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read()
        temp = path + f".{threading.get_ident()}.tmp"
        with open(temp, "wb") as f:
            f.write(data)
        os.replace(temp, path)
    return path


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        try:
            if path.startswith("/music/"):
                self._file(_inside(MUSIC_DIR, path[7:]), cache=False)
            elif path.startswith("/cache/"):
                self._file(_inside(CACHE_DIR, path[7:]), cache=False)
            elif path.startswith("/videos/"):
                self._file(_inside(VIDEO_DIR, path[8:]), cache=False)
            elif STREAM_PATH.match(path):
                self._proxy(*STREAM_PATH.match(path).groups())
            elif path.startswith("/thumb/"):
                video_id = path[7:]
                source = urllib.parse.parse_qs(parsed.query).get("src", [None])[0]
                self._file(_thumbnail(video_id, source) if VIDEO_ID.match(video_id) else None, cache=True)
            else:
                self._file(_inside(WEB_DIR, path.lstrip("/") or "index.html"), cache=False)
        except (ConnectionError, TimeoutError):
            pass
        except Exception:
            self._error(404)

    def _error(self, code):
        try:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except OSError:
            pass

    def _proxy(self, video_id, kind):
        """YouTube akışını aktar. Oynatıcı "baştan sona hepsini" ister (bytes=0-); YouTube böyle uçsuz
        istekleri çok yavaş verir. Bu yüzden isteği küçük parçalara bölüp sırayla alıyoruz: ilk parça
        küçük (hemen başlasın), sonrakiler büyük."""
        source = _streams.get(video_id, {}).get(kind)
        if not source:
            self._error(404)
            return
        url, headers, available_at = source
        wait = available_at - time.time()
        if wait > 0:
            time.sleep(min(wait + 0.2, 15))  # YouTube adresi henüz açmadı
        headers = {k: v for k, v in headers.items() if k.lower() not in ("range", "accept-encoding")}
        match = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range") or "")
        start = int(match.group(1)) if match else 0
        wanted_end = int(match.group(2)) if match and match.group(2) else None

        def fetch(first, last):
            request = urllib.request.Request(url, headers={**headers, "Range": f"bytes={first}-{last}"})
            return urllib.request.urlopen(request, timeout=20)

        chunk = FIRST_CHUNK
        try:
            upstream = fetch(start, start + chunk - 1 if wanted_end is None else min(wanted_end, start + chunk - 1))
        except urllib.error.HTTPError as error:
            self._error(error.code)  # 403: adres eskimiş; arayüz yenisini ister
            return
        total = re.search(r"/(\d+)", upstream.headers.get("Content-Range") or "")
        total = int(total.group(1)) if total else start + int(upstream.headers.get("Content-Length") or 0)
        end = total - 1 if wanted_end is None else min(wanted_end, total - 1)
        self.send_response(206 if match else 200)
        self.send_header("Content-Type", upstream.headers.get("Content-Type") or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if match:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        position = start
        while True:
            with upstream:
                while True:
                    data = upstream.read(64 * 1024)
                    if not data:
                        break
                    self.wfile.write(data)
                    position += len(data)
            if position > end:
                return
            chunk = NEXT_CHUNK
            upstream = fetch(position, min(end, position + chunk - 1))

    def _file(self, path, cache):
        if not path:
            self._error(404)
            return
        size = os.path.getsize(path)
        start, end = 0, size - 1
        ranged = self.headers.get("Range")
        match = re.match(r"bytes=(\d*)-(\d*)", ranged or "")
        if match and (match.group(1) or match.group(2)):
            if match.group(1):
                start = int(match.group(1))
                end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
            else:
                start = max(0, size - int(match.group(2)))
            if start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        kind = TYPES.get(os.path.splitext(path)[1].lower()) or mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_header("Content-Type", kind)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "max-age=604800" if cache else "no-cache")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # oynatıcı ileri sarınca bağlantıyı keser; bu olağan, kayda gerek yok


def start():
    """Sunucuyu boş bir portta arka planda başlatır, adresini döner."""
    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"
