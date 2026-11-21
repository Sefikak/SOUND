"""Ortak dinleme: aynı oda kodunu giren cihazlar aynı şarkıyı aynı anda dinler.

Taşıyıcı Supabase Realtime'ın geçici yayın kanalıdır (Broadcast + Presence): veritabanına hiçbir şey yazılmaz, hesap
gerekmez, kanalın adı oda kodudur. Odaya ilk giren yöneticidir (host); o çıkarsa sıradaki üye kendiliğinden devralır.
Şarkıyı her cihaz kendisi çalar, kanaldan yalnızca durum ve komutlar geçer.

Mesaj türleri
    state  yönetici -> herkes: çalan şarkı, konum, sıra
    hello  üye -> yönetici: "tam durumu gönder"
    cmd    üye -> yönetici: çal/duraklat, geç, sar, şarkı ekle
    ping/pong  saat farkı ölçümü (yalnızca bu modülün içinde kalır)

Odadaki herkesten gelen veri güvenilmez sayılır: şarkı adresleri kimlikten yeniden kurulur, metinler kısaltılır.
"""
import json
import re
import secrets
import threading
import time
import urllib.parse
import uuid
from collections import deque

from cloud import load_config

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # karışan harfler yok (O/0, I/1/L)
CODE_LENGTH = 6
CODE = re.compile(f"^[{ALPHABET}]{{{CODE_LENGTH}}}$")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
ART_HOSTS = (".googleusercontent.com", ".ggpht.com", ".ytimg.com")
COMMANDS = {"toggle", "play", "pause", "next", "previous", "seek", "jump", "playlist", "add", "remove", "clear", "shuffle", "repeat"}
MAX_QUEUE = 100
MAX_FRAME = 256 * 1024
BEAT_SECONDS = 25
PING_SECONDS = 15
FIND_SECONDS = 3      # bu sürede kimse görünmezse oda yok demektir
CMD_LIMIT = 30        # bir üyeden 10 saniyede en fazla bu kadar komut
CONNECT_TRIES = 3


def new_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(text):
    return re.sub(r"[\s-]", "", str(text or "")).upper()


def clean_name(text):
    name = re.sub(r"[\x00-\x1f\x7f]", "", str(text or "")).strip()[:24]
    return name or "Misafir"


def _video_id(value):
    return isinstance(value, str) and VIDEO_ID.fullmatch(value) is not None


def _text(value, limit):
    return re.sub(r"[\x00-\x1f\x7f]", " ", value)[:limit] if isinstance(value, str) else ""


def _number(value, low, high, default=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return default
    return max(low, min(high, value))


def clean_track(track):
    """Başka bir cihazdan gelen şarkı: adres kimlikten kurulur, başka adres kabul edilmez."""
    if not isinstance(track, dict) or not _video_id(track.get("id")):
        return None
    video_id = track["id"]
    out = {"id": video_id, "title": _text(track.get("title"), 200) or "Bilinmeyen şarkı", "artist": _text(track.get("artist"), 120),
           "duration": _number(track.get("duration"), 0, 86400), "url": f"https://www.youtube.com/watch?v={video_id}"}
    art = track.get("thumbnail")
    if isinstance(art, str) and len(art) < 600 and art.startswith("https://"):
        host = urllib.parse.urlparse(art).hostname or ""
        if host.endswith(ART_HOSTS):
            out["thumbnail"] = art
    return out


def _clean_tracks(items):
    if not isinstance(items, list):
        return []
    return [t for t in (clean_track(x) for x in items[:MAX_QUEUE]) if t]


def clean_state(data):
    if not isinstance(data, dict):
        return None
    out = {"seq": int(_number(data.get("seq"), 0, 2 ** 53)), "playing": data.get("playing") is True,
           "at": _number(data.get("at"), 0, 86400), "ts": _number(data.get("ts"), 0, 2 ** 53),
           "qv": int(_number(data.get("qv"), 0, 2 ** 53)), "control": data.get("control") is not False,
           "track": clean_track(data.get("track"))}
    if "queue" in data:
        out["queue"] = _clean_tracks(data.get("queue"))
        out["pos"] = int(_number(data.get("pos"), 0, MAX_QUEUE))
    return out


def clean_command(data):
    if not isinstance(data, dict) or data.get("cmd") not in COMMANDS:
        return None
    cmd = data["cmd"]
    out = {"cmd": cmd}
    if cmd == "seek":
        out["at"] = _number(data.get("at"), 0, 86400)
    elif cmd in ("jump", "remove"):
        if not _video_id(data.get("id")):
            return None
        out["id"] = data["id"]
    elif cmd == "playlist":
        out["tracks"] = _clean_tracks(data.get("tracks"))
        if not out["tracks"]:
            return None
        out["index"] = int(_number(data.get("index"), 0, len(out["tracks"]) - 1))
    elif cmd == "add":
        out["track"] = clean_track(data.get("track"))
        if not out["track"]:
            return None
        out["next"] = data.get("next") is True
    return out


class _RoomMissing(Exception):
    pass


class _Session(threading.Thread):
    """Bir odadaki bağlantı. Kopunca kendiliğinden yeniden bağlanır, odadan çıkılana kadar sürer."""

    def __init__(self, owner, code, name, create):
        super().__init__(daemon=True, name="listen-room")
        self.owner = owner
        self.code = code
        self.name = name
        self.topic = "realtime:listen-" + code
        self.me = uuid.uuid4().hex[:12]
        self.joined = 1 if create else None
        self.must_find = not create
        self.members = {}      # üye -> {phx_ref: bilgi}
        self.connected = False
        self.offset = 0.0      # yöneticinin saati - bu cihazın saati (ms)
        self.best_rtt = None
        self.ping_host = None
        self.stopped = threading.Event()
        self.ws = None
        self.send_lock = threading.Lock()
        self.ref = 0
        self.commands = {}

    # ---------- üyeler ----------

    def member_list(self):
        people = []
        for member, metas in self.members.items():
            if metas:
                meta = list(metas.values())[-1]
                people.append({"id": member, "name": clean_name(meta.get("name")), "joined": _number(meta.get("joined"), 0, 2 ** 53)})
        return sorted(people, key=lambda p: (p["joined"], p["id"]))

    def host(self):
        people = self.member_list()
        return people[0]["id"] if people else None

    def status(self):
        return {"active": True, "code": self.code, "me": self.me, "host": self.host(), "members": self.member_list(),
                "connected": self.connected, "offset": self.offset}

    def _changed(self):
        self.owner.emit({"type": "status", "status": self.status()})

    # ---------- gönderme ----------

    def _raw(self, event, payload, topic=None):
        with self.send_lock:
            self.ref += 1
            self.ws.send(json.dumps({"topic": topic or self.topic, "event": event, "payload": payload, "ref": str(self.ref)}, ensure_ascii=False))

    def publish(self, kind, data, to=None):
        if not self.connected or not self.ws:
            return False
        body = {"f": self.me, "k": kind, "d": data}
        if to:
            body["to"] = to
        try:
            self._raw("broadcast", {"type": "broadcast", "event": "m", "payload": body})
            return True
        except Exception:
            return False

    # ---------- bağlantı ----------

    def run(self):
        delay = 1
        failures = 0
        ever = False
        while not self.stopped.is_set():
            try:
                self._connect()
                return
            except _RoomMissing:
                self.owner.closed(self, "Bu kodla açık bir oda bulunamadı.")
                return
            except Exception:
                failures += 1
                ever = ever or self.connected
            finally:
                self.connected = False
                self.members = {}
                if self.ws:
                    try:
                        self.ws.close()
                    except Exception:
                        pass
                    self.ws = None
            if self.stopped.is_set():
                return
            if not ever and failures >= CONNECT_TRIES:
                self.owner.closed(self, "Ortak dinleme sunucusuna bağlanılamadı; internet bağlantını kontrol et.")
                return
            self._changed()
            self.stopped.wait(delay)
            delay = min(delay * 2, 15)

    def _connect(self):
        import websocket
        url, key = load_config()
        query = urllib.parse.urlencode({"apikey": key, "vsn": "1.0.0"})
        self.ws = websocket.create_connection(url.replace("https://", "wss://", 1) + "/realtime/v1/websocket?" + query, timeout=15)
        self._raw("phx_join", {"config": {"broadcast": {"self": False, "ack": False},
                                          "presence": {"key": self.me, "enabled": True}, "private": False}})
        self.ws.settimeout(1)
        beat = time.time()
        next_ping = 0
        pings = 0
        find_until = None
        while not self.stopped.is_set():
            now = time.time()
            if now - beat >= BEAT_SECONDS:
                self._raw("heartbeat", {}, "phoenix")
                beat = now
            if find_until and now > find_until and self.must_find:
                raise _RoomMissing()
            host = self.host()
            if host != self.ping_host:
                self.ping_host, self.best_rtt, pings = host, None, 0
                next_ping = 0
            if host and host != self.me and now >= next_ping:
                self.publish("ping", {"t0": now * 1000}, host)
                pings += 1
                next_ping = now + (1 if pings < 4 else PING_SECONDS)
            try:
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                raise ConnectionError("bağlantı kapandı")
            if len(raw) > MAX_FRAME:
                continue
            message = json.loads(raw)
            event, payload = message.get("event"), message.get("payload") or {}
            if event == "phx_reply" and payload.get("status") == "error":
                raise ConnectionError(str(payload.get("response"))[:200])
            if event in ("phx_close", "phx_error"):
                raise ConnectionError(event)
            if event == "presence_state":
                self._presence(payload, {})
                if self.joined is None:
                    self.joined = max((p["joined"] for p in self.member_list()), default=0) + 1
                self._raw("presence", {"type": "presence", "event": "track", "payload": {"name": self.name, "joined": self.joined}})
                self.connected = True
                if self.must_find:
                    find_until = time.time() + FIND_SECONDS
                self._found()
                self._changed()
            elif event == "presence_diff":
                self._presence(payload.get("joins") or {}, payload.get("leaves") or {})
                self._found()
                self._changed()
            elif event == "broadcast" and payload.get("event") == "m":
                self._message(payload.get("payload") or {})

    def _found(self):
        if any(member != self.me for member in self.members):
            self.must_find = False

    def _presence(self, joins, leaves):
        for member, info in joins.items():
            for meta in (info or {}).get("metas") or []:
                self.members.setdefault(member, {})[meta.get("phx_ref")] = meta
        for member, info in leaves.items():
            metas = self.members.get(member)
            if metas is None:
                continue
            for meta in (info or {}).get("metas") or []:
                metas.pop(meta.get("phx_ref"), None)
            if not metas:
                self.members.pop(member, None)

    def _message(self, body):
        sender, kind, data = body.get("f"), body.get("k"), body.get("d")
        if not isinstance(sender, str) or sender == self.me or (body.get("to") not in (None, self.me)):
            return
        host = self.host()
        if kind == "ping":
            if host == self.me and isinstance(data, dict):
                self.publish("pong", {"t0": _number(data.get("t0"), 0, 2 ** 53), "t1": time.time() * 1000}, sender)
        elif kind == "pong":
            if sender == host and isinstance(data, dict):
                self._clock(data)
        elif kind == "state":
            state = clean_state(data) if sender == host else None
            if state:
                self.owner.emit({"type": "msg", "kind": "state", "from": sender, "data": state})
        elif kind == "hello":
            if host == self.me:
                self.owner.emit({"type": "msg", "kind": "hello", "from": sender, "data": {}})
        elif kind == "cmd":
            command = clean_command(data) if host == self.me and self._allowed(sender) else None
            if command:
                self.owner.emit({"type": "msg", "kind": "cmd", "from": sender, "name": self._name_of(sender), "data": command})

    def _name_of(self, member):
        return next((p["name"] for p in self.member_list() if p["id"] == member), "Misafir")

    def _allowed(self, sender):
        now = time.time()
        times = self.commands.setdefault(sender, deque())
        while times and now - times[0] > 10:
            times.popleft()
        if len(times) >= CMD_LIMIT:
            return False
        times.append(now)
        return True

    def _clock(self, data):
        now = time.time() * 1000
        t0, t1 = _number(data.get("t0"), 0, 2 ** 53), _number(data.get("t1"), 0, 2 ** 53)
        rtt = now - t0
        if rtt < 0 or (self.best_rtt is not None and rtt > self.best_rtt):
            return
        self.best_rtt = rtt
        offset = t1 - (t0 + now) / 2
        moved = abs(offset - self.offset) > 15
        self.offset = offset
        if moved:
            self._changed()

    def stop(self):
        self.stopped.set()
        if self.ws:
            try:
                self._raw("phx_leave", {})
            except Exception:
                pass


class Listen:
    """Arayüzün kullandığı kapı. Olaylar on_event ile bildirilir (webapp: push("listen", olay))."""

    def __init__(self, on_event):
        self.on_event = on_event
        self.session = None
        self.lock = threading.Lock()

    def emit(self, event):
        try:
            self.on_event(event)
        except Exception:
            pass

    def status(self):
        session = self.session
        return session.status() if session else {"active": False}

    def _open(self, code, name, create):
        url, key = load_config()
        if not url or not key:
            return {"error": "Ortak dinleme sunucusu ayarlanmamış."}
        try:
            import websocket  # noqa: F401
        except ImportError:
            return {"error": "Ortak dinleme bu kurulumda kullanılamıyor."}
        with self.lock:
            old, self.session = self.session, _Session(self, code, clean_name(name), create)
            if old:
                old.stop()
            self.session.start()
            return self.session.status()

    def create(self, name):
        return self._open(new_code(), name, True)

    def join(self, code, name):
        code = normalize_code(code)
        if not CODE.match(code):
            return {"error": f"Oda kodu {CODE_LENGTH} karakter olmalı."}
        return self._open(code, name, False)

    def leave(self):
        with self.lock:
            session, self.session = self.session, None
        if session:
            session.stop()
        return {"active": False}

    def closed(self, session, error):
        with self.lock:
            if self.session is not session:
                return
            self.session = None
        self.emit({"type": "closed", "error": error})

    def send(self, kind, data):
        session = self.session
        if not session or kind not in ("state", "hello", "cmd"):
            return False
        if kind == "state" and session.host() != session.me:
            return False
        return session.publish(kind, data)
