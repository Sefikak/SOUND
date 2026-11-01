"""Başka uygulamalardaki kayıtlı listeleri ve beğenilen şarkıları okur.

YouTube Music: bağlı YouTube hesabının çerezleriyle (Ayarlar > YouTube hesabı) kitaplık okunur.
Spotify: hesap açmadan iki yol var:
  * liste / albüm bağlantısı: herkese açık sayfadan okunur (Spotify en fazla 100 şarkı gösteriyor),
  * Spotify'ın "hesap verileri" dosyası (my_spotify_data.zip) ya da Exportify CSV'si: beğenilenler dahil hepsi.
Spotify şarkıları YouTube Music'te aranıp en iyi eşleşen sürüm alınır."""
import csv
import io
import json
import os
import re
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import MozillaCookieJar

import downloader
from searcher import _norm, search_songs, track_from_song

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


class ImportError_(Exception):
    """Kullanıcıya gösterilecek açıklamalı hata."""


# ---------- YouTube Music ----------

def _youtube_cookies():
    auth = downloader.auth_options()
    if "cookiefile" in auth:
        jar = MozillaCookieJar(auth["cookiefile"])
        jar.load(ignore_discard=True, ignore_expires=True)
    elif "cookiesfrombrowser" in auth:
        from yt_dlp.cookies import extract_cookies_from_browser
        jar = extract_cookies_from_browser(auth["cookiesfrombrowser"][0])
    else:
        raise ImportError_("Önce YouTube hesabını bağla.")
    cookies = {c.name: c.value for c in jar if c.domain.endswith("youtube.com")}
    if "__Secure-3PAPISID" not in cookies and "SAPISID" not in cookies:
        raise ImportError_("YouTube oturumu bulunamadı ya da süresi dolmuş. Hesabını yeniden bağla.")
    cookies.setdefault("__Secure-3PAPISID", cookies.get("SAPISID", ""))
    return cookies


def _ytm_client():
    from ytmusicapi import YTMusic
    cookies = _youtube_cookies()
    # "authorization" başlığı ytmusicapi'ye bunun tarayıcı oturumu olduğunu söyler; asıl imzayı kendisi üretir
    return YTMusic(auth={"cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
                         "x-goog-authuser": "0", "authorization": "SAPISIDHASH 0",
                         "origin": "https://music.youtube.com"})


def _songs(items):
    return [track_from_song(t) for t in items or [] if t and t.get("videoId")]


def youtube_music(progress):
    """(beğenilenler, [(kaynak, ad, şarkılar)])"""
    ytm = _ytm_client()
    progress("YouTube Music: beğenilen şarkılar okunuyor…")
    try:
        liked = _songs(ytm.get_liked_songs(limit=None).get("tracks"))
    except Exception as error:
        raise ImportError_("YouTube Music kitaplığına ulaşılamadı. Hesabını yeniden bağlamayı dene.") from error
    lists = [p for p in ytm.get_library_playlists(limit=None) if p.get("playlistId") not in (None, "LM", "SE")]
    playlists = []
    for i, p in enumerate(lists, 1):
        progress(f"YouTube Music: “{p.get('title')}” okunuyor ({i}/{len(lists)})…", i, len(lists))
        try:
            tracks = _songs(ytm.get_playlist(p["playlistId"], limit=None).get("tracks"))
        except Exception:
            continue
        playlists.append((f"ytm:{p['playlistId']}", p.get("title") or "YouTube Music listesi", tracks))
    return liked, playlists


# ---------- Spotify ----------

SPOTIFY_LINK = re.compile(r"open\.spotify\.com/(?:intl-\w+/)?(?:embed/)?(playlist|album)/([A-Za-z0-9]{10,})")


def spotify_links(text):
    """Metindeki bütün Spotify liste / albüm bağlantıları: [(tür, kimlik)]"""
    seen, out = set(), []
    for kind, item_id in SPOTIFY_LINK.findall(text or ""):
        if item_id not in seen:
            seen.add(item_id)
            out.append((kind, item_id))
    return out


def spotify_page(kind, item_id):
    """Herkese açık Spotify listesi: (ad, [(başlık, sanatçı, süre_sn)])"""
    req = urllib.request.Request(f"https://open.spotify.com/embed/{kind}/{item_id}", headers={"User-Agent": UA})
    try:
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S).group(1)
        entity = json.loads(data)["props"]["pageProps"]["state"]["data"]["entity"]
    except Exception as error:
        raise ImportError_("Spotify listesi okunamadı. Bağlantının herkese açık bir listeye ait olduğundan emin ol.") from error
    items = [(t.get("title"), (t.get("subtitle") or "").replace("\xa0", " "), (t.get("duration") or 0) // 1000)
             for t in entity.get("trackList") or [] if t.get("title")]
    return entity.get("name") or "Spotify listesi", items


def _from_export_json(name, data, liked, playlists):
    """Spotify hesap verileri: YourLibrary.json (beğenilenler) ve Playlist*.json (listeler)."""
    base = os.path.basename(name).lower()
    if base.startswith("yourlibrary") and isinstance(data, dict):
        for t in data.get("tracks") or []:
            if t.get("track"):
                liked.append((t["track"], t.get("artist") or "", 0))
    elif base.startswith("playlist") and isinstance(data, dict):
        for p in data.get("playlists") or []:
            items = []
            for entry in p.get("items") or []:
                t = entry.get("track") or {}
                if t.get("trackName"):
                    items.append((t["trackName"], t.get("artistName") or "", 0))
            if items:
                playlists.append((p.get("name") or "Spotify listesi", items))


def _from_csv(name, text, liked, playlists):
    """Exportify CSV'si: her dosya bir liste; "Liked Songs" beğenilenlerdir."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return
    title_col = next((c for c in rows[0] if c and c.lower() in ("track name", "name", "title")), None)
    artist_col = next((c for c in rows[0] if c and c.lower() in ("artist name(s)", "artist name", "artist", "artists")), None)
    dur_col = next((c for c in rows[0] if c and "duration" in c.lower()), None)
    if not title_col:
        return
    items = []
    for r in rows:
        if r.get(title_col):
            duration = int(r.get(dur_col) or 0) // 1000 if dur_col and (r.get(dur_col) or "").isdigit() else 0
            items.append((r[title_col], (r.get(artist_col) or "").replace(";", ", "), duration))
    playlist_name = os.path.splitext(os.path.basename(name))[0].replace("_", " ")
    if playlist_name.casefold() in ("liked songs", "beğenilen şarkılar", "begenilen sarkilar"):
        liked.extend(items)
    else:
        playlists.append((playlist_name, items))


def spotify_files(paths):
    """Seçilen dosyalardan (zip / json / csv): (beğenilenler, [(ad, şarkılar)])"""
    liked, playlists = [], []

    def handle(name, raw):
        lower = name.lower()
        try:
            if lower.endswith(".json"):
                _from_export_json(name, json.loads(raw.decode("utf-8-sig")), liked, playlists)
            elif lower.endswith(".csv"):
                _from_csv(name, raw.decode("utf-8-sig"), liked, playlists)
        except (ValueError, UnicodeDecodeError):
            pass

    for path in paths:
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    handle(name, z.read(name))
        else:
            with open(path, "rb") as f:
                handle(path, f.read())
    if not liked and not playlists:
        raise ImportError_("Dosyada Spotify listesi bulunamadı. Spotify'ın hesap verileri zip'ini "
                           "(my_spotify_data.zip) ya da Exportify CSV'lerini seç.")
    return liked, playlists


# ---------- Spotify şarkısını YouTube Music'te bulma ----------

def _best(results, title, artist, duration):
    want_title, want_artists = _norm(title), [_norm(a) for a in re.split(r",|&| feat\.? ", artist) if a.strip()]

    def score(t):
        s = 0
        got_title = _norm(t["title"])
        if got_title == want_title:
            s += 3
        elif want_title and (want_title in got_title or got_title in want_title):
            s += 1
        if any(a and a in _norm(t["artist"]) for a in want_artists):
            s += 2
        if duration and t.get("duration") and abs(t["duration"] - duration) <= 8:
            s += 1
        return s

    scored = sorted(results, key=score, reverse=True)
    return scored[0] if scored and score(scored[0]) >= 2 else None


def match(items, cache, progress, label):
    """[(başlık, sanatçı, süre)] → YouTube Music şarkıları (bulunamayanlar atlanır). cache: {anahtar: şarkı|None}"""
    out = [None] * len(items)
    done = [0]

    def find(index):
        title, artist, duration = items[index]
        key = f"{_norm(title)}|{_norm(artist)}"
        if key not in cache:
            try:
                results = search_songs(f"{title} {artist}".strip(), 5)
                cache[key] = _best(results, title, artist, duration)
            except Exception:
                return  # bağlantı sorunu: önbelleğe yazma, bir dahaki sefere tekrar denensin
        out[index] = cache[key]
        done[0] += 1
        if done[0] % 5 == 0 or done[0] == len(items):
            progress(f"{label}: şarkılar YouTube Music'te eşleştiriliyor ({done[0]}/{len(items)})…", done[0], len(items))

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(find, range(len(items))))
    return [t for t in out if t]


# ---------- Spotify hesabıyla giriş (resmi Web API, OAuth + PKCE) ----------
# Spotify, resmi girişi kullanan her uygulamadan bir "Client ID" ister. Kullanıcı bunu developer.spotify.com'da
# bir kez oluşturur; yönlendirme adresi olarak aşağıdaki SPOTIFY_REDIRECT'i ekler.

SPOTIFY_PORT = 43117
SPOTIFY_REDIRECT = f"http://127.0.0.1:{SPOTIFY_PORT}/callback"
SPOTIFY_SCOPES = "user-library-read playlist-read-private playlist-read-collaborative"


def spotify_pkce():
    import base64
    import hashlib
    import secrets
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge, secrets.token_urlsafe(16)


def spotify_auth_url(client_id, challenge, state):
    import urllib.parse
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": SPOTIFY_REDIRECT, "scope": SPOTIFY_SCOPES,
        "code_challenge_method": "S256", "code_challenge": challenge, "state": state, "show_dialog": "true"})


def spotify_token(client_id, code, verifier):
    import urllib.parse
    body = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "redirect_uri": SPOTIFY_REDIRECT,
                                   "client_id": client_id, "code_verifier": verifier}).encode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())["access_token"]
    except Exception as error:
        raise ImportError_("Spotify girişi tamamlanamadı. Client ID'yi ve yönlendirme adresini kontrol et.") from error


def _spotify_get(token, url):
    import urllib.error
    if not url.startswith("https://"):
        url = "https://api.spotify.com/v1/" + url
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError(error.code) from error
        raise


def _spotify_items(token, url, limit):
    """Sayfalı bir uç noktanın bütün öğeleri."""
    out = []
    page = _spotify_get(token, url)
    while True:
        out += page.get("items") or []
        if not page.get("next") or len(out) >= limit:
            return out[:limit]
        page = _spotify_get(token, page["next"])


def _spotify_track(item):
    t = item.get("track") or item.get("item") or {}
    if not t or t.get("type", "track") != "track" or not t.get("name"):
        return None
    artists = ", ".join(a.get("name", "") for a in t.get("artists") or [] if a.get("name"))
    return t["name"], artists, (t.get("duration_ms") or 0) // 1000


def spotify_account(token, progress):
    """Giriş yapılan hesabın beğenilenleri ve listeleri: (beğenilenler, [(kaynak, ad, şarkılar)], okunamayan_liste_sayısı)"""
    try:
        me = _spotify_get(token, "me")
    except PermissionError as error:
        raise ImportError_("Spotify hesabına erişilemedi. Uygulamanın Developer Dashboard'unda hesabının "
                           "“User Management” listesine ekli olduğundan emin ol.") from error
    progress(f"Spotify ({me.get('display_name') or me.get('id')}): beğenilen şarkılar okunuyor…")
    liked = [t for t in map(_spotify_track, _spotify_items(token, "me/tracks?limit=50", 10000)) if t]
    lists = _spotify_items(token, "me/playlists?limit=50", 1000)
    playlists, failed = [], 0
    for i, p in enumerate(lists, 1):
        progress(f"Spotify: “{p.get('name')}” okunuyor ({i}/{len(lists)})…", i, len(lists))
        items = None
        for path in (f"playlists/{p['id']}/items?limit=100", f"playlists/{p['id']}/tracks?limit=100"):
            try:
                items = _spotify_items(token, path, 10000)
                break
            except PermissionError:
                continue  # Spotify'ın kendi listeleri (Discover Weekly vb.) uygulamalara kapalı
            except Exception:
                continue
        if items is None:
            failed += 1
            continue
        tracks = [t for t in map(_spotify_track, items) if t]
        if tracks:
            playlists.append((f"spotify:{p['id']}", p.get("name") or "Spotify listesi", tracks))
    return liked, playlists, failed
