"""SOUND hesabı: Supabase ile giriş ve kitaplık eşitleme (favoriler, albümler, klasörler).

Yalnızca standart kütüphane kullanılır (urllib), Android'de (Chaquopy) de aynen çalışır.
Sunucu şeması: supabase/schema.sql. Bağlantı bilgisi: cloud_config.json ({"url": ..., "key": ...});
anahtar Supabase'in herkese açık "anon" anahtarıdır, satırları RLS kuralları korur.

Eşitleme modeli: her kitaplık öğesi sunucuda bir satır (anahtar → JSON değer). Değişen öğeler gönderilir,
silinenler deleted=true olarak kalır. Çakışmada sunucuya en son yazılan kazanır; zamanı sunucu koyar.
"""
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta

from library import BASE_DIR, DATA_DIR

CONFIG_FILE = os.path.join(BASE_DIR, "cloud_config.json")
STATE_FILE = os.path.join(DATA_DIR, "cloud.json")
CALLBACK_PORT = 43118
CALLBACK_URL = f"http://127.0.0.1:{CALLBACK_PORT}/auth/callback"
POLL_SECONDS = 30
PUSH_DELAY = 1.5
TRACK_META = ("id", "title", "artist", "duration", "thumbnail", "url")


class CloudError(Exception):
    pass


def load_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            config = json.load(f)
        if config.get("url") and config.get("key"):
            return config["url"].rstrip("/"), config["key"]
    except (OSError, ValueError):
        pass
    return None, None


def _log_error(method, path, error):
    """Ağ hatasının ayrıntısı (kullanıcıya kısa metin gösteriliyor; neden burada kalsın)."""
    try:
        with open(os.path.join(DATA_DIR, "cloud_errors.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {method} {path.split('?')[0]}: {type(error).__name__}: {error}\n")
    except OSError:
        pass


def _digest(value):
    return hashlib.sha1(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _meta(track):
    return {k: track.get(k) for k in TRACK_META}


def _message(body, status):
    """Supabase hata yanıtından kullanıcıya gösterilecek Türkçe metin."""
    try:
        data = json.loads(body)
    except ValueError:
        data = {}
    code = str(data.get("error_code") or data.get("code") or data.get("error") or "")
    text = str(data.get("msg") or data.get("message") or data.get("error_description") or data.get("error") or "")
    known = {
        "invalid_credentials": "E-posta ya da şifre yanlış.",
        "invalid_grant": "E-posta ya da şifre yanlış.",
        "email_not_confirmed": "E-posta adresin henüz onaylanmamış; gelen kutundaki bağlantıya tıkla.",
        "user_already_exists": "Bu e-postayla zaten bir hesap var; giriş yap.",
        "weak_password": "Şifre çok zayıf; en az 6 karakter kullan.",
        "over_email_send_rate_limit": "Çok fazla e-posta gönderildi; biraz bekleyip tekrar dene.",
        "over_request_rate_limit": "Çok fazla deneme; biraz bekleyip tekrar dene.",
        "validation_failed": "E-posta adresi geçerli görünmüyor.",
        "email_address_invalid": "E-posta adresi geçerli görünmüyor.",
        "signup_disabled": "Yeni hesap açma şu an kapalı.",
    }
    if code in known:
        return known[code]
    if "Invalid login credentials" in text:
        return known["invalid_credentials"]
    if "already registered" in text:
        return known["user_already_exists"]
    if "Password should be" in text:
        return known["weak_password"]
    return text or f"Sunucu hatası ({status})"


class Cloud:
    """Hesap oturumu ve eşitleme. Arayüze durum değişiklikleri on_status(status) ile bildirilir."""

    def __init__(self, library, on_status=None):
        self.lib = library
        self.url, self.key = load_config()
        self.on_status = on_status or (lambda status: None)
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._push_timer = None
        self._applying = False
        self._thread = None
        self.syncing = False
        self.error = None
        self.last_sync = None
        self.state = self._load_state()
        self.state.setdefault("device", uuid.uuid4().hex[:12])
        library.subscribe(self._library_changed)

    # ---------- durum ----------

    @property
    def configured(self):
        return bool(self.url and self.key)

    @property
    def user(self):
        return self.state.get("user")

    def status(self):
        user = self.user
        return {
            "configured": self.configured,
            "signed_in": bool(user and self.state.get("refresh_token")),
            "email": (user or {}).get("email"),
            "provider": (user or {}).get("provider"),
            "syncing": self.syncing,
            "error": self.error,
            "last_sync": self.last_sync,
        }

    def _load_state(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_state(self):
        with self._lock:
            temp = STATE_FILE + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False)
            os.replace(temp, STATE_FILE)

    def _notify(self):
        try:
            self.on_status(self.status())
        except Exception:
            pass

    # ---------- HTTP ----------

    def _request(self, method, path, body=None, token=None, headers=None, timeout=20):
        if not self.configured:
            raise CloudError("SOUND hesabı henüz yapılandırılmadı.")
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("apikey", self.key)
        # Yeni "sb_publishable_" anahtarları JWT değil, Authorization'da reddedilir: yalnızca oturum belirteci gider
        if token:
            req.add_header("Authorization", "Bearer " + token)
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            if error.code == 401 and token:
                raise _Unauthorized(_message(raw, error.code))
            raise CloudError(_message(raw, error.code))
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            _log_error(method, path, error)
            raise CloudError("Sunucuya ulaşılamadı; internet bağlantını kontrol et.")
        return json.loads(raw) if raw.strip() else None

    def _token(self):
        """Geçerli erişim anahtarı; süresi bitmek üzereyse yenilenir."""
        with self._lock:
            if not self.state.get("refresh_token"):
                raise CloudError("Giriş yapılmamış.")
            if self.state.get("access_token") and self.state.get("expires_at", 0) > time.time() + 60:
                return self.state["access_token"]
            try:
                session = self._request("POST", "/auth/v1/token?grant_type=refresh_token",
                                        {"refresh_token": self.state["refresh_token"]})
            except CloudError as error:
                if "refresh" in str(error).lower() or "Invalid" in str(error):
                    self._forget_session()
                    raise CloudError("Oturumun süresi doldu; tekrar giriş yap.")
                raise
            self._store_session(session)
            return self.state["access_token"]

    def _authed(self, method, path, body=None, headers=None):
        try:
            return self._request(method, path, body, self._token(), headers)
        except _Unauthorized:
            with self._lock:
                self.state["expires_at"] = 0
            return self._request(method, path, body, self._token(), headers)

    # ---------- giriş ----------

    def _store_session(self, session):
        user = session.get("user") or {}
        with self._lock:
            previous = (self.state.get("user") or {}).get("id")
            if previous and previous != user.get("id"):
                self._reset_sync()  # başka bir hesaba geçildi: eşitleme baştan
            self.state.update({
                "access_token": session["access_token"],
                "refresh_token": session["refresh_token"],
                "expires_at": time.time() + int(session.get("expires_in") or 3600),
                "user": {"id": user.get("id"), "email": user.get("email"),
                         "provider": (user.get("app_metadata") or {}).get("provider")},
            })
            self._save_state()

    def _reset_sync(self):
        for key in ("known", "cursor", "merged"):
            self.state.pop(key, None)

    def _forget_session(self):
        with self._lock:
            for key in ("access_token", "refresh_token", "expires_at", "user"):
                self.state.pop(key, None)
            self._reset_sync()
            self._save_state()

    def sign_up(self, email, password):
        """Yeni hesap. E-posta onayı açıksa oturum hemen gelmez: {"confirm": True} döner."""
        data = self._request("POST", "/auth/v1/signup", {"email": email.strip(), "password": password})
        if data and data.get("access_token"):
            self._signed_in(data)
            return {"ok": True}
        if data and not (data.get("identities") or (data.get("user") or {}).get("identities") or [True]):
            raise CloudError("Bu e-postayla zaten bir hesap var; giriş yap.")
        return {"confirm": True}

    def sign_in(self, email, password):
        data = self._request("POST", "/auth/v1/token?grant_type=password", {"email": email.strip(), "password": password})
        self._signed_in(data)
        return {"ok": True}

    def reset_password(self, email):
        self._request("POST", "/auth/v1/recover", {"email": email.strip()})
        return {"ok": True}

    def google_url(self):
        """Google girişi (PKCE): tarayıcıda açılacak adres ve kodu almak için gereken doğrulayıcı."""
        settings = self._request("GET", "/auth/v1/settings", timeout=10) or {}
        if not (settings.get("external") or {}).get("google"):
            raise CloudError("Google ile giriş henüz açılmadı; şimdilik e-postayla giriş yap.")
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = urllib.parse.urlencode({"provider": "google", "redirect_to": CALLBACK_URL,
                                        "code_challenge": challenge, "code_challenge_method": "s256"})
        return f"{self.url}/auth/v1/authorize?{query}", verifier

    def finish_google(self, code, verifier):
        data = self._request("POST", "/auth/v1/token?grant_type=pkce", {"auth_code": code, "code_verifier": verifier})
        self._signed_in(data)
        return {"ok": True}

    def _signed_in(self, session):
        self._store_session(session)
        self.error = None
        self.start()
        self.sync_now()
        self._notify()

    def sign_out(self):
        token = self.state.get("access_token")
        if token:
            try:
                self._request("POST", "/auth/v1/logout", {}, token, timeout=8)
            except CloudError:
                pass
        self._forget_session()
        self.error = None
        self.last_sync = None
        self._notify()

    def delete_account(self):
        self._authed("POST", "/rest/v1/rpc/delete_my_account", {})
        self._forget_session()
        self.error = None
        self.last_sync = None
        self._notify()

    # ---------- eşitleme ----------

    def start(self):
        if self._thread is None and self.configured:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="cloud-sync")
            self._thread.start()

    def sync_now(self):
        self._wake.set()

    def _library_changed(self):
        if self._applying or not self.state.get("refresh_token"):
            return
        with self._lock:
            if self._push_timer:
                self._push_timer.cancel()
            self._push_timer = threading.Timer(PUSH_DELAY, self._wake.set)
            self._push_timer.daemon = True
            self._push_timer.start()

    def _loop(self):
        while True:
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()
            if not self.state.get("refresh_token"):
                continue
            self.syncing = True
            try:
                self._sync()
                self.error = None
                self.last_sync = time.time()
            except CloudError as error:
                self.error = str(error)
            except Exception as error:  # eşitleme hiçbir zaman uygulamayı düşürmesin
                self.error = f"Eşitleme hatası: {error}"
            finally:
                self.syncing = False
                self._notify()

    def _sync(self):
        first = not self.state.get("merged")
        self._pull(merge=first)
        self._push()
        if first:
            self.state["merged"] = True
            self._save_state()

    def documents(self):
        """Kitaplığın sunucuya giden hâli: anahtar → değer."""
        lib = self.lib
        with lib._lock:
            data = lib.data
            tracks = data["tracks"]
            docs = {}
            for track_id in data["favorites"]:
                if track_id in tracks:
                    docs["fav:" + track_id] = {"track": _meta(tracks[track_id])}
            docs["order:favorites"] = {"ids": [i for i in data["favorites"] if i in tracks]}
            for album_id, album in data["albums"].items():
                ids = list(album["tracks"])
                docs["album:" + album_id] = {
                    "name": album["name"], "folder": album.get("folder"), "created": album.get("created"),
                    "source": album.get("source"), "tracks": ids,
                    "meta": {i: _meta(tracks[i]) for i in ids if i in tracks},
                }
            for folder_id, folder in data["folders"].items():
                docs["folder:" + folder_id] = {"name": folder["name"], "created": folder.get("created")}
        return docs

    def _push(self):
        docs = self.documents()
        known = self.state.setdefault("known", {})
        rows = []
        for key, value in docs.items():
            digest = _digest(value)
            if known.get(key) != digest:
                rows.append(({"key": key, "value": value, "deleted": False}, digest))
        for key in list(known):
            if key not in docs:
                rows.append(({"key": key, "value": None, "deleted": True}, None))
        if not rows:
            return
        user_id = self.user["id"]
        device = self.state["device"]
        for start in range(0, len(rows), 200):
            chunk = rows[start:start + 200]
            self._authed("POST", "/rest/v1/library_items?on_conflict=user_id,key",
                         [{**row, "user_id": user_id, "device": device} for row, _ in chunk],
                         {"Prefer": "resolution=merge-duplicates,return=minimal"})
            for row, digest in chunk:
                if digest is None:
                    known.pop(row["key"], None)
                else:
                    known[row["key"]] = digest
            self._save_state()

    def _pull(self, merge=False):
        cursor = self.state.get("cursor")
        rows = []
        while True:
            query = {"select": "key,value,deleted,device,updated_at", "order": "updated_at.asc,key.asc", "limit": "1000",
                     "offset": str(len(rows))}
            if cursor:
                query["updated_at"] = "gt." + cursor
            page = self._authed("GET", "/rest/v1/library_items?" + urllib.parse.urlencode(query)) or []
            rows.extend(page)
            if len(page) < 1000:
                break
        if not rows:
            return
        known = self.state.setdefault("known", {})
        changes = {}
        for row in rows:
            key, value, deleted = row["key"], row.get("value"), row.get("deleted")
            if deleted:
                if merge or key not in known:
                    continue  # ilk birleştirmede yerelde olan bir şey silinmesin
                changes[key] = None
            else:
                if known.get(key) == _digest(value):
                    continue  # zaten bizde olan (çoğunlukla bizim gönderdiğimiz) hâl
                changes[key] = value
        if changes:
            self._apply(changes, merge)
            for key, value in changes.items():
                if value is None:
                    known.pop(key, None)
                elif not merge:
                    known[key] = _digest(value)
        # İmleç: son satırın zamanından 5 sn geri (aynı anda yazılıp geç görünen satırlar kaçmasın);
        # tekrar gelen satırlar özet karşılaştırmasıyla atlanır
        last = _parse_time(rows[-1]["updated_at"]) - timedelta(seconds=5)
        if not cursor or last > _parse_time(cursor):
            self.state["cursor"] = last.isoformat()
        self._save_state()

    def _apply(self, changes, merge):
        fav_add, fav_del, order, albums, folders = [], [], None, {}, {}
        for key, value in changes.items():
            kind, _, item = key.partition(":")
            if kind == "fav":
                if value is None:
                    fav_del.append(item)
                elif value.get("track", {}).get("id"):
                    fav_add.append(value["track"])
            elif kind == "order" and item == "favorites" and value is not None:
                order = value.get("ids") or []
            elif kind == "album":
                albums[item] = value
            elif kind == "folder":
                folders[item] = value
        self._applying = True
        try:
            self.lib.apply_cloud(fav_add, fav_del, order, albums, folders, merge=merge)
        finally:
            self._applying = False


class _Unauthorized(CloudError):
    pass


def _parse_time(text):
    text = text.replace("Z", "+00:00")
    if "." in text:  # Python 3.10 öncesi kesirli saniyede 6 basamak ister
        head, _, rest = text.partition(".")
        digits = "".join(ch for ch in rest if ch.isdigit())
        zone = rest[len(digits):]
        text = f"{head}.{digits[:6].ljust(6, '0')}{zone}"
    return datetime.fromisoformat(text)
