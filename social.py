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
METHODS = {"overview", "save_profile", "search", "profile", "add_friend", "accept", "remove_friend", "messages", "send", "mark_read",
           "create_group", "group", "group_messages", "group_send", "group_add", "group_remove", "group_leave", "group_admin",
           "group_rename", "group_read"}
ROOM_CODE = re.compile(r"[A-Z0-9]{6}")  # listen.CODE ile aynı biçim
MESSAGE_FIELDS = "id,sender,recipient,body,kind,created_at,read_at"
GROUP_MESSAGE_FIELDS = "id,group_id,sender,body,kind,created_at"


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
    if "PGRST202" in text or "PGRST205" in text or ("group" in text and "does not exist" in text):
        return "Gruplar sunucuda henüz kurulmamış (supabase/groups.sql çalıştırılmalı)."
    return text


def _body(body, kind):
    """Mesaj gövdesi; ortak dinleme davetinde (jam) gövde oda kodudur."""
    if kind not in ("text", "jam"):
        raise CloudError("Geçersiz mesaj türü.")
    body = _text(body, 2000)
    if kind == "jam" and not ROOM_CODE.fullmatch(body):
        raise CloudError("Geçersiz oda kodu.")
    if not body:
        raise CloudError("Boş mesaj gönderilemez.")
    return body


def _members(value):
    if not isinstance(value, list) or len(value) > 49:
        raise CloudError("Geçersiz üye listesi.")
    return [_peer(v) for v in value]


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
        try:
            out["groups"] = self._rest("POST", "rpc/my_groups", {}) or []
            self._groups = out["groups"]
        except CloudError as error:
            if _friendly(error).startswith("Gruplar sunucuda"):
                out["groups"] = None  # groups.sql henüz çalıştırılmadı
            else:
                # ağ kopması vb.: grup bölümü kaybolmasın, son bilinen liste kalsın
                out["groups"] = getattr(self, "_groups", [])
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
        path = f"messages?select={MESSAGE_FIELDS}&or=(and(sender.eq.{me},recipient.eq.{peer}),and(sender.eq.{peer},recipient.eq.{me}))&order=id.desc&limit={PAGE_SIZE}"
        if isinstance(before, int) and not isinstance(before, bool):
            path += f"&id=lt.{before}"
        return list(reversed(self._rest("GET", path) or []))

    def send(self, peer, body, kind="text"):
        record = {"recipient": _peer(peer), "body": _body(body, kind)}
        if kind != "text":
            record["kind"] = kind
        try:
            rows = self._rest("POST", "messages", record, "return=representation")
        except CloudError as error:
            if kind != "text" and "kind" in str(error):
                return {"error": "Davet için sunucu güncellenmeli (supabase/groups.sql çalıştırılmalı)."}
            raise
        return rows[0] if rows else {"error": "Mesaj gönderilemedi."}

    def mark_read(self, peer):
        now = datetime.now(timezone.utc).isoformat()
        self._rest("PATCH", f"messages?sender=eq.{_peer(peer)}&recipient=eq.{self.uid}&read_at=is.null", {"read_at": now}, "return=minimal")
        return {"ok": True}

    # ---------- gruplar ----------

    def create_group(self, name, members):
        name = _text(name, 40)
        if not name:
            return {"error": "Grup adını yaz."}
        group_id = self._rest("POST", "rpc/create_group", {"p_name": name, "p_members": _members(members)})
        return {"id": group_id}

    def group(self, group_id):
        group_id = _peer(group_id)
        rows = self._rest("GET", f"groups?select=id,name,created_by,created_at&id=eq.{group_id}") or []
        if not rows:
            return {"error": "Bu grubu göremiyorsun; çıkarılmış olabilirsin."}
        members = self._rest("GET", f"group_members?select=user_id,role,joined_at&group_id=eq.{group_id}&order=joined_at") or []
        people = self._people(m["user_id"] for m in members)
        out = []
        for m in members:
            person = people.get(m["user_id"]) or {"id": m["user_id"], "username": "silinmis", "display_name": "Silinmiş hesap"}
            out.append({**person, "role": m["role"]})
        me = next((m for m in out if m["id"] == self.uid), None)
        friends = {link["requester"] if link["addressee"] == self.uid else link["addressee"]
                   for link in self._links() if link["status"] == "accepted"}
        return {**rows[0], "members": out, "admin": bool(me and me["role"] == "admin"), "friends": sorted(friends)}

    def group_messages(self, group_id, before=None):
        path = f"group_messages?select={GROUP_MESSAGE_FIELDS}&group_id=eq.{_peer(group_id)}&order=id.desc&limit={PAGE_SIZE}"
        if isinstance(before, int) and not isinstance(before, bool):
            path += f"&id=lt.{before}"
        return list(reversed(self._rest("GET", path) or []))

    def group_send(self, group_id, body, kind="text"):
        record = {"group_id": _peer(group_id), "body": _body(body, kind), "kind": kind}
        rows = self._rest("POST", "group_messages", record, "return=representation")
        return rows[0] if rows else {"error": "Mesaj gönderilemedi."}

    def group_add(self, group_id, members):
        self._rest("POST", "rpc/add_group_members", {"g": _peer(group_id), "p_members": _members(members)})
        return {"ok": True}

    def group_remove(self, group_id, peer):
        self._rest("POST", "rpc/remove_group_member", {"g": _peer(group_id), "u": _peer(peer)})
        return {"ok": True}

    def group_leave(self, group_id):
        self._rest("POST", "rpc/leave_group", {"g": _peer(group_id)})
        return {"ok": True}

    def group_admin(self, group_id, peer, on):
        self._rest("POST", "rpc/set_group_admin", {"g": _peer(group_id), "u": _peer(peer), "on_off": on is True})
        return {"ok": True}

    def group_rename(self, group_id, name):
        self._rest("POST", "rpc/rename_group", {"g": _peer(group_id), "p_name": _text(name, 40)})
        return {"ok": True}

    def group_read(self, group_id):
        self._rest("POST", "rpc/mark_group_read", {"g": _peer(group_id)})
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
            started = time.time()
            try:
                self._session(self.uid)
                delay = 3
            except Exception:
                # bir süre çalışmış bağlantı koptuysa hemen yeniden bağlan; art arda kopuşta en çok 30 sn bekle
                # (yeniden bağlanınca "ready" gelir, arayüz kaçırdıklarını tazeler)
                delay = 3 if time.time() - started > 60 else min(delay * 2, 30)
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
        # gruplar ayrı kanalda: groups.sql çalıştırılmamışsa yalnızca bu kanal reddedilir, DM'ler etkilenmez.
        # Süzgeç yok: satır güvenliği herkese yalnızca üyesi olduğu grupların mesajlarını iletir.
        group_topic = "realtime:groups-" + cloud.state["device"]
        group_changes = [{"event": "INSERT", "schema": "public", "table": "group_messages"}]
        try:
            send("phx_join", {"config": {"broadcast": {"self": False}, "presence": {"key": ""}, "postgres_changes": changes}, "access_token": token})
            send("phx_join", {"config": {"broadcast": {"self": False}, "presence": {"key": ""}, "postgres_changes": group_changes},
                              "access_token": token}, group_topic)
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
                        send("access_token", {"access_token": token}, group_topic)
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    raise ConnectionError("bağlantı kapandı")
                message = json.loads(raw)
                event, payload = message.get("event"), message.get("payload") or {}
                if message.get("topic") == group_topic:
                    if event == "postgres_changes":
                        data = payload.get("data") or {}
                        if data.get("type") == "INSERT":
                            self._emit({"type": "gmessage", "message": data.get("record") or {}})
                    continue
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
