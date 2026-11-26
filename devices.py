"""Cihazlar arası çalma: aynı hesapla açık cihazlar birbirini görür, çalma birinden diğerine aktarılır ve uzaktan yönetilir.

Taşıyıcı Supabase Realtime'ın geçici yayın kanalıdır; veritabanına yazılmaz. Kanalın adı hesaba özel, tahmin edilemeyen
bir anahtardan gelir (cloud.devices_key). Anahtar yalnızca o hesabın oturumuyla okunabilir.

Mesaj türleri
    np        çalan cihaz -> herkes: şarkı, konum, sıra
    hello     yeni açılan cihaz -> herkes: "çalan varsa durumunu gönder"
    cmd       kumanda -> çalan cihaz: çal/duraklat, geç, sar, ses, başka cihaza aktar
    transfer  çalan cihaz -> hedef: sıra ve konumla birlikte çalmayı devral
"""
import json
import re
import socket
import threading
import time
import urllib.parse

from cloud import load_config
from listen import MAX_FRAME, _clean_tracks, _number, _text, clean_command, clean_state

BEAT_SECONDS = 25
DEVICE_ID = re.compile(r"[0-9a-f]{6,32}")
REPEAT = ("off", "all", "one")


def _device_id(value):
    return isinstance(value, str) and DEVICE_ID.fullmatch(value) is not None


def clean_np(data):
    out = clean_state(data)
    if not out or not out.get("track"):
        return None
    out["shuffle"] = isinstance(data, dict) and data.get("shuffle") is True
    out["repeat"] = data.get("repeat") if data.get("repeat") in REPEAT else "off"
    out["volume"] = _number(data.get("volume"), 0, 1, 0.7)
    return out


def clean_device_command(data):
    if isinstance(data, dict) and data.get("cmd") == "handoff":
        return {"cmd": "handoff", "to": data["to"]} if _device_id(data.get("to")) else None
    if isinstance(data, dict) and data.get("cmd") == "volume":
        return {"cmd": "volume", "v": _number(data.get("v"), 0, 1, 0.7)}
    return clean_command(data)


def clean_transfer(data):
    if not isinstance(data, dict):
        return None
    queue = _clean_tracks(data.get("queue"))
    if not queue:
        return None
    return {"queue": queue, "pos": int(_number(data.get("pos"), 0, len(queue) - 1)), "at": _number(data.get("at"), 0, 86400),
            "shuffle": data.get("shuffle") is True, "repeat": data.get("repeat") if data.get("repeat") in REPEAT else "off"}


class Devices:
    """Arayüzün kullandığı kapı. Olaylar on_event ile bildirilir (webapp: push("devices", olay))."""

    def __init__(self, cloud, on_event):
        self.cloud = cloud
        self.on_event = on_event
        self.name = _text(socket.gethostname(), 40) or "Bilgisayar"
        self.kind = "pc"
        self.peers = {}        # cihaz -> {phx_ref: bilgi}
        self.connected = False
        self.ws = None
        self.ref = 0
        self.send_lock = threading.Lock()
        self.thread = None

    def describe(self, name, kind):
        self.name = _text(name, 40) or self.name
        self.kind = kind

    @property
    def me(self):
        return self.cloud.state.get("device")

    def start(self):
        if self.thread is None and self.cloud.configured:
            self.thread = threading.Thread(target=self._run, daemon=True, name="devices")
            self.thread.start()

    # ---------- durum ----------

    def status(self):
        people = []
        for device, metas in list(self.peers.items()):
            if metas:
                meta = list(metas.values())[-1]
                people.append({"id": device, "name": _text(meta.get("name"), 40) or "Cihaz", "kind": meta.get("kind") if meta.get("kind") in ("phone", "watch") else "pc"})
        people.sort(key=lambda d: (d["id"] != self.me, d["name"].casefold()))
        return {"signed_in": bool(self.cloud.status().get("signed_in")), "connected": self.connected, "me": self.me, "name": self.name, "kind": self.kind, "devices": people}

    def _emit(self, event):
        try:
            self.on_event(event)
        except Exception:
            pass

    def _changed(self):
        self._emit({"type": "status", "status": self.status()})

    # ---------- gönderme ----------

    def _raw(self, topic, event, payload):
        with self.send_lock:
            self.ref += 1
            self.ws.send(json.dumps({"topic": topic, "event": event, "payload": payload, "ref": str(self.ref)}, ensure_ascii=False))

    def send(self, kind, data, to=None):
        if not self.connected or not self.ws or kind not in ("np", "hello", "cmd", "transfer"):
            return False
        body = {"f": self.me, "k": kind, "d": data}
        if to:
            body["to"] = to
        try:
            self._raw(self.topic, "broadcast", {"type": "broadcast", "event": "m", "payload": body})
            return True
        except Exception:
            return False

    # ---------- bağlantı ----------

    def _run(self):
        delay = 2
        while True:
            if not self.cloud.status().get("signed_in"):
                time.sleep(3)
                continue
            account = (self.cloud.user or {}).get("id")
            started = time.time()
            try:
                self._session(self.cloud.devices_key(), account)
                delay = 2
            except Exception:
                delay = 2 if time.time() - started > 60 else min(delay * 2, 30)
            finally:
                self.connected = False
                self.peers = {}
                if self.ws:
                    try:
                        self.ws.close()
                    except Exception:
                        pass
                    self.ws = None
                self._changed()
            time.sleep(delay)

    def _session(self, key, account):
        import websocket
        url, apikey = load_config()
        query = urllib.parse.urlencode({"apikey": apikey, "vsn": "1.0.0"})
        self.ws = websocket.create_connection(url.replace("https://", "wss://", 1) + "/realtime/v1/websocket?" + query, timeout=15)
        self.topic = "realtime:devices-" + key
        self._raw(self.topic, "phx_join", {"config": {"broadcast": {"self": False, "ack": False},
                                                      "presence": {"key": self.me, "enabled": True}, "private": False}})
        self.ws.settimeout(1)
        beat = time.time()
        while (self.cloud.user or {}).get("id") == account and self.cloud.status().get("signed_in"):
            if time.time() - beat >= BEAT_SECONDS:
                self._raw("phoenix", "heartbeat", {})
                beat = time.time()
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
                self._raw(self.topic, "presence", {"type": "presence", "event": "track", "payload": {"name": self.name, "kind": self.kind}})
                self.connected = True
                self.send("hello", {})
                self._changed()
            elif event == "presence_diff":
                self._presence(payload.get("joins") or {}, payload.get("leaves") or {})
                self._changed()
            elif event == "broadcast" and payload.get("event") == "m":
                self._message(payload.get("payload") or {})

    def _presence(self, joins, leaves):
        for device, info in joins.items():
            for meta in (info or {}).get("metas") or []:
                self.peers.setdefault(device, {})[meta.get("phx_ref")] = meta
        for device, info in leaves.items():
            metas = self.peers.get(device)
            if metas is None:
                continue
            for meta in (info or {}).get("metas") or []:
                metas.pop(meta.get("phx_ref"), None)
            if not metas:
                self.peers.pop(device, None)

    def _message(self, body):
        sender, kind, data = body.get("f"), body.get("k"), body.get("d")
        if not _device_id(sender) or sender == self.me or body.get("to") not in (None, self.me):
            return
        clean = {"np": clean_np, "cmd": clean_device_command, "transfer": clean_transfer, "hello": lambda value: {}}.get(kind)
        data = clean(data) if clean else None
        if data is not None:
            self._emit({"type": "msg", "kind": kind, "from": sender, "data": data})
