"""Discord'da "SOUND dinliyor" durumu (Rich Presence).

Bot ya da sunucu yoktur: bilgisayarda açık olan Discord uygulamasının yerel IPC kanalına (Windows'ta adlandırılmış
boru, Linux'ta Unix soketi) bağlanılıp çalan şarkı bildirilir. Discord kapalıysa sessizce bekler, açılınca bağlanır.
Ayarlar > Arka plan > Discord'da göster (settings.discord_presence, varsayılan açık).
"""
import json
import os
import queue
import socket
import struct
import sys
import threading
import time

CLIENT_ID = "1573460232078622760"  # Discord geliştirici portalındaki "SOUND" uygulaması (bot yok); görünen ad oradan gelir
REPO = "https://github.com/Sefikak/SOUND"
RETRY_SECONDS = 20
LISTENING = 2


def _thumb(track):
    if track.get("thumbnail", "").startswith("https://"):
        return track["thumbnail"]
    tid = track.get("id") or ""
    return f"https://i.ytimg.com/vi/{tid}/hqdefault.jpg" if len(tid) == 11 else "logo"


def _clip(text, limit=128):
    text = (text or "").strip()
    if len(text) < 2:
        text = (text + "  ")[:2]
    return text if len(text) <= limit else text[:limit - 1] + "…"


class _Pipe:
    def __init__(self):
        self.handle = None
        if os.name == "nt":
            for i in range(10):
                try:
                    self.handle = open(rf"\\?\pipe\discord-ipc-{i}", "r+b", buffering=0)
                    return
                except OSError:
                    continue
        else:
            base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp"
            dirs = [base] + [os.path.join(base, d) for d in ("app/com.discordapp.Discord", "snap.discord", ".flatpak/com.discordapp.Discord/xdg-run")]
            for d in dirs:
                for i in range(10):
                    path = os.path.join(d, f"discord-ipc-{i}")
                    if os.path.exists(path):
                        try:
                            self.handle = socket.socket(socket.AF_UNIX)
                            self.handle.connect(path)
                            return
                        except OSError:
                            self.handle = None
        raise ConnectionError("Discord açık değil")

    def write(self, data):
        if os.name == "nt":
            self.handle.write(data)
        else:
            self.handle.sendall(data)

    def read(self, size):
        out = b""
        while len(out) < size:
            chunk = self.handle.read(size - len(out)) if os.name == "nt" else self.handle.recv(size - len(out))
            if not chunk:
                raise ConnectionError("Discord bağlantısı kapandı")
            out += chunk
        return out

    def close(self):
        try:
            self.handle.close()
        except Exception:
            pass


class Presence:
    def __init__(self, enabled):
        self.enabled = enabled
        self.jobs = queue.Queue()
        self.latest = None
        threading.Thread(target=self._run, daemon=True, name="discord-presence").start()

    def update(self, track, playing, position=0):
        """Çalma durumu değişti. Duraklayınca ya da şarkı yokken durum silinir."""
        self.latest = (dict(track) if track else None, bool(playing), float(position or 0), time.time())
        self.jobs.put(True)

    def set_enabled(self, on):
        self.enabled = bool(on)
        self.jobs.put(True)

    def _activity(self):
        if not self.enabled or not self.latest:
            return None
        track, playing, position, at = self.latest
        if not track or not playing:
            return None
        start = int((at - position) * 1000)
        activity = {"type": LISTENING, "details": _clip(track.get("title")), "state": _clip(track.get("artist") or "SOUND"),
                    "timestamps": {"start": start},
                    "assets": {"large_image": _thumb(track), "large_text": _clip(track.get("album") or track.get("title"))},
                    "buttons": [{"label": "SOUND'u indir", "url": REPO}]}
        duration = track.get("duration")
        if isinstance(duration, (int, float)) and duration > position:
            activity["timestamps"]["end"] = start + int(duration * 1000)
        return activity

    def _send(self, pipe, op, payload):
        data = json.dumps(payload).encode("utf-8")
        pipe.write(struct.pack("<II", op, len(data)) + data)
        op, size = struct.unpack("<II", pipe.read(8))
        reply = json.loads(pipe.read(size).decode("utf-8"))
        if op == 2:
            raise ConnectionError(reply.get("message") or "Discord bağlantıyı kapattı")
        return reply

    def _run(self):
        pipe = None
        sent = object()
        while True:
            try:
                self.jobs.get(timeout=RETRY_SECONDS)
            except queue.Empty:
                pass
            while not self.jobs.empty():  # yalnızca en son durum önemli
                self.jobs.get_nowait()
            activity = self._activity()
            if pipe is None and activity is None:
                sent = object()
                continue
            try:
                if pipe is None:
                    pipe = _Pipe()
                    self._send(pipe, 0, {"v": 1, "client_id": CLIENT_ID})
                    sent = object()
                if activity == sent:
                    continue
                self._send(pipe, 1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": activity},
                                     "nonce": str(time.time())})
                sent = activity
            except Exception:
                if pipe:
                    pipe.close()
                pipe = None
