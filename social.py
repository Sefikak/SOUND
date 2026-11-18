"""Profil, arkadaşlık ve mesajlaşma. Veriler Supabase'de durur (supabase/social.sql), yetkileri satır güvenliği belirler.

Yeni mesaj ve arkadaşlık değişiklikleri Realtime ile anında gelir; bağlantı yoksa arayüz sayfa açılışlarında yeniden okur.
"""
import json
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone

from cloud import CloudError

USERNAME = re.compile(r"[a-z0-9_]{3,20}")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
PROFILE_FIELDS = "id,username,display_name,bio,showcase"
PAGE_SIZE = 50
BEAT_SECONDS = 25
METHODS = {"overview", "save_profile", "search", "profile", "add_friend", "accept", "remove_friend", "messages", "send", "mark_read"}


def _text(value, limit):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value).strip()[:limit] if isinstance(value, str) else ""


def _peer(value):
    if not isinstance(value, str) or not UUID.fullmatch(value):
        raise CloudError("Geçersiz kullanıcı.")
    return value


def _friendly(error):
    text = str(error)
    if "profiles_username_key" in text:
        return "Bu kullanıcı adı alınmış."
    if "profiles_username_format" in text:
        return "Kullanıcı adı 3-20 karakter olmalı; küçük harf, rakam ve _ kullanılabilir."
    if "friendships_pair" in text or "friendships_pkey" in text:
        return "Bu kişiyle zaten bir arkadaşlık isteğin var."
    if "row-level security" in text:
        return "Bu işlem için arkadaş olmanız gerekiyor."
    return text


class Social:
    """Arayüzün kullandığı kapı. Olaylar on_event ile bildirilir (webapp: push("social", olay))."""

    def __init__(self, cloud, library, on_event):
        self.cloud = cloud
        self.lib = library
        self.on_event = on_event
        self.thread = None

    @property
    def uid(self):
        return (self.cloud.user or {}).get("id")

    def _signed_in(self):
        return bool(self.cloud.status().get("signed_in") and self.uid)

    def _rest(self, method, path, body=None, prefer=None):
        return self.cloud._authed(method, "/rest/v1/" + path, body, {"Prefer": prefer} if prefer else None)

    def call(self, method, args):
        """Arayüzden gelen çağrı: hata metin olarak döner, uygulamayı düşürmez."""
        if method not in METHODS or not isinstance(args, list):
            return {"error": "Bilinmeyen işlem."}
        if not self._signed_in() and method != "overview":
            return {"error": "Önce SOUND hesabına giriş yap."}
        try:
            return getattr(self, method)(*args)
        except CloudError as error:
            return {"error": _friendly(error)}
        except TypeError:
            return {"error": "Geçersiz istek."}

    # ---------- profil ----------

    def _showcase(self):
        lib = self.lib
        return {"top_artists": [artist for artist, _ in lib.top_artists(6)],
                "albums": [{"name": album["name"][:60], "count": len(album["tracks"])} for _, album in lib.all_albums()[:12]],
                "favorites": len(lib.data["favorites"])}

    def _me(self):
        rows = self._rest("GET", f"profiles?select={PROFILE_FIELDS}&id=eq.{self.uid}") or []
        return rows[0] if rows else None

    def save_profile(self, username, display_name="", bio=""):
        username = _text(username, 30).lower()
        if not USERNAME.fullmatch(username):
            return {"error": "Kullanıcı adı 3-20 karakter olmalı; küçük harf, rakam ve _ kullanılabilir."}
        fields = {"username": username, "display_name": _text(display_name, 40), "bio": _text(bio, 300), "showcase": self._showcase()}
        if self._me():
            rows = self._rest("PATCH", f"profiles?id=eq.{self.uid}", fields, "return=representation")
        else:
            rows = self._rest("POST", "profiles", {"id": self.uid, **fields}, "return=representation")
        return rows[0] if rows else {"error": "Profil kaydedilemedi."}

    def _people(self, ids):
        ids = sorted(set(ids))
        if not ids:
            return {}
        rows = self._rest("GET", f"profiles?select={PROFILE_FIELDS}&id=in.({','.join(ids)})") or []
        return {row["id"]: row for row in rows}

    def _links(self):
        return self._rest("GET", "friendships?select=requester,addressee,status,created_at") or []

    def overview(self):
        if not self._signed_in():
            return {"signed_in": False}
        me = self._me()
        if not me:
            return {"signed_in": True, "me": None, "friends": [], "incoming": [], "outgoing": []}
        links = self._links()
        people = self._people(link[side] for link in links for side in ("requester", "addressee") if link[side] != self.uid)
        unread = {}
        for row in self._rest("GET", f"messages?select=sender&recipient=eq.{self.uid}&read_at=is.null&limit=500") or []:
            unread[row["sender"]] = unread.get(row["sender"], 0) + 1
        out = {"signed_in": True, "me": me, "friends": [], "incoming": [], "outgoing": []}
        for link in links:
            mine = link["requester"] == self.uid
            person = people.get(link["addressee"] if mine else link["requester"])
            if not person:
                continue
            if link["status"] == "accepted":
                out["friends"].append({**person, "unread": unread.get(person["id"], 0)})
            else:
                out["outgoing" if mine else "incoming"].append(person)
        out["friends"].sort(key=lambda p: (-p["unread"], (p["display_name"] or p["username"]).casefold()))
        return out

    def search(self, query):
        query = re.sub(r"[^\w ]", "", _text(query, 30)).strip()
        if len(query) < 2:
            return []
        pattern = urllib.parse.quote(f'"*{query}*"')
        rows = self._rest("GET", f"profiles?select={PROFILE_FIELDS}&or=(username.ilike.{pattern},display_name.ilike.{pattern})&limit=20") or []
        return [row for row in rows if row["id"] != self.uid]

    def profile(self, peer):
        rows = self._rest("GET", f"profiles?select={PROFILE_FIELDS}&id=eq.{_peer(peer)}") or []
        if not rows:
            return {"error": "Bu kullanıcı bulunamadı."}
        relation = "self" if peer == self.uid else "none"
        for link in self._links():
            if peer in (link["requester"], link["addressee"]):
                relation = "friend" if link["status"] == "accepted" else "outgoing" if link["requester"] == self.uid else "incoming"
        return {**rows[0], "relation": relation}

    # ---------- arkadaşlık ----------

    def add_friend(self, peer):
        _peer(peer)
        for link in self._links():
            if link["requester"] == peer and link["status"] == "pending":
                return self.accept(peer)  # o da bize istek atmış: beklemeden arkadaş olunur
        self._rest("POST", "friendships", {"requester": self.uid, "addressee": peer}, "return=minimal")
        return {"ok": True}

    def accept(self, peer):
        self._rest("PATCH", f"friendships?requester=eq.{_peer(peer)}&addressee=eq.{self.uid}", {"status": "accepted"}, "return=minimal")
        return {"ok": True}

    def remove_friend(self, peer):
        me = self.uid
        _peer(peer)
        self._rest("DELETE", f"friendships?or=(and(requester.eq.{me},addressee.eq.{peer}),and(requester.eq.{peer},addressee.eq.{me}))", None, "return=minimal")
        return {"ok": True}

    # ---------- mesajlar ----------

    def messages(self, peer, before=None):
        me = self.uid
        _peer(peer)
        path = f"messages?select=id,sender,recipient,body,created_at,read_at&or=(and(sender.eq.{me},recipient.eq.{peer}),and(sender.eq.{peer},recipient.eq.{me}))&order=id.desc&limit={PAGE_SIZE}"
        if isinstance(before, int) and not isinstance(before, bool):
            path += f"&id=lt.{before}"
        return list(reversed(self._rest("GET", path) or []))

    def send(self, peer, body):
        body = _text(body, 2000)
        if not body:
            return {"error": "Boş mesaj gönderilemez."}
        rows = self._rest("POST", "messages", {"recipient": _peer(peer), "body": body}, "return=representation")
        return rows[0] if rows else {"error": "Mesaj gönderilemedi."}

    def mark_read(self, peer):
        now = datetime.now(timezone.utc).isoformat()
        self._rest("PATCH", f"messages?sender=eq.{_peer(peer)}&recipient=eq.{self.uid}&read_at=is.null", {"read_at": now}, "return=minimal")
        return {"ok": True}

    # ---------- anlık bildirimler ----------

    def start(self):
        if self.thread is None and self.cloud.configured:
            self.thread = threading.Thread(target=self._run, daemon=True, name="social")
            self.thread.start()

    def _emit(self, event):
        try:
            self.on_event(event)
        except Exception:
            pass

    def _run(self):
        delay = 3
        while True:
            if not self._signed_in():
                time.sleep(3)
                continue
            try:
                self._session(self.uid)
                delay = 3
            except Exception:
                delay = min(delay * 2, 120)
            time.sleep(delay)

    def _session(self, uid):
        import websocket
        cloud = self.cloud
        query = urllib.parse.urlencode({"apikey": cloud.key, "vsn": "1.0.0"})
        ws = websocket.create_connection(cloud.url.replace("https://", "wss://", 1) + "/realtime/v1/websocket?" + query, timeout=15)
        topic = "realtime:social-" + cloud.state["device"]
        ref = 0

        def send(event, payload, to=topic):
            nonlocal ref
            ref += 1
            ws.send(json.dumps({"topic": to, "event": event, "payload": payload, "ref": str(ref)}))

        token = cloud._token()
        changes = [{"event": "*", "schema": "public", "table": "messages", "filter": "recipient=eq." + uid},
                   {"event": "*", "schema": "public", "table": "messages", "filter": "sender=eq." + uid},
                   {"event": "*", "schema": "public", "table": "social_pings", "filter": "user_id=eq." + uid}]
        try:
            send("phx_join", {"config": {"broadcast": {"self": False}, "presence": {"key": ""}, "postgres_changes": changes}, "access_token": token})
            ws.settimeout(5)
            beat = time.time()
            while self._signed_in() and self.uid == uid:
                if time.time() - beat >= BEAT_SECONDS:
                    send("heartbeat", {}, "phoenix")
                    beat = time.time()
                    fresh = cloud._token()
                    if fresh != token:
                        token = fresh
                        send("access_token", {"access_token": token})
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    raise ConnectionError("bağlantı kapandı")
                message = json.loads(raw)
                event, payload = message.get("event"), message.get("payload") or {}
                if event == "system" and payload.get("extension") == "postgres_changes" and payload.get("status") == "ok":
                    self._emit({"type": "ready"})
                elif event == "postgres_changes":
                    data = payload.get("data") or {}
                    if data.get("table") == "social_pings":
                        self._emit({"type": "friends"})
                    elif data.get("type") == "INSERT":
                        self._emit({"type": "message", "message": data.get("record") or {}})
                    elif data.get("type") == "UPDATE":
                        self._emit({"type": "read", "message": data.get("record") or {}})
                elif event in ("phx_close", "phx_error"):
                    raise ConnectionError(event)
        finally:
            try:
                ws.close()
            except Exception:
                pass
