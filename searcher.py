import re
import urllib.parse

import yt_dlp

PLAYLIST_FILTER = "EgIQAw%253D%253D"  # YouTube aramasında "yalnızca oynatma listeleri"


def thumbnail_url(video_id):
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"


JUNK_NAMES = {"null", "none", "undefined", "nan", "n/a", "-", "unknown", "?"}


def clean_channel(name):
    """"Tarkan - Topic", "TarkanVEVO" gibi kanal adlarını sanatçı adına çevir.
    "null" gibi anlamsız kanal adları (gerçekten böyle adlı kanallar var) boş döner."""
    name = re.sub(r"\s*-\s*Topic$", "", (name or "").strip())
    if name.casefold() in JUNK_NAMES:
        return ""
    return re.sub(r"(?<=[a-zçğıöşü0-9])\s*VEVO$", "", name, flags=re.I) if name.upper() != "VEVO" else name


def artist_from_title(title):
    """"Zeki Müren - Bulamazsın" → "Zeki Müren". Ayraç yoksa boş döner."""
    parts = re.split(r"\s+[-–—|]\s+|\s{2,}", (title or "").strip(), maxsplit=1)
    if len(parts) == 2 and 1 < len(parts[0]) <= 40:
        return parts[0].strip()
    return ""


def guess_artist(channel, title):
    return clean_channel(channel) or artist_from_title(title) or "Bilinmeyen sanatçı"


def track_from_entry(entry):
    video_id = entry["id"]
    return {
        "id": video_id,
        "title": entry.get("title") or "Adsız parça",
        "artist": guess_artist(entry.get("channel") or entry.get("uploader"), entry.get("title")),
        "duration": int(entry.get("duration") or 0),
        "thumbnail": thumbnail_url(video_id),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def search_tracks(query, limit=20):
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        results = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

    tracks = []
    for entry in results.get("entries") or []:
        # Kanal / oynatma listesi sonuçlarını ve canlı yayınları atla
        if not entry or len(entry.get("id") or "") != 11:
            continue
        if entry.get("live_status") in ("is_live", "is_upcoming"):
            continue
        tracks.append(track_from_entry(entry))

    return tracks


def album_from_entry(entry):
    thumbnail = None
    for thumb in reversed(entry.get("thumbnails") or []):
        match = re.search(r"/vi/([\w-]{11})/", thumb.get("url") or "")
        if match:
            thumbnail = thumbnail_url(match.group(1))
            break
    return {
        "id": entry["id"],
        "kind": "playlist",
        "title": entry.get("title") or "Adsız liste",
        "artist": entry.get("channel") or entry.get("uploader") or "YouTube",
        "thumbnail": thumbnail,
        "url": f"https://www.youtube.com/playlist?list={entry['id']}",
    }


def search_playlists(query, limit=10):
    """YouTube'daki albüm / çalma listesi sonuçları."""
    options = {"quiet": True, "no_warnings": True, "extract_flat": True,
               "skip_download": True, "playlistend": limit}
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&sp={PLAYLIST_FILTER}"
    with yt_dlp.YoutubeDL(options) as ydl:
        results = ydl.extract_info(url, download=False)
    return [album_from_entry(e) for e in results.get("entries") or []
            if e and e.get("id") and e.get("ie_key") == "YoutubeTab"]


def playlist_tracks(playlist_id, limit=200):
    options = {"quiet": True, "no_warnings": True, "extract_flat": True,
               "skip_download": True, "playlistend": limit}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    tracks = [track_from_entry(e) for e in info.get("entries") or []
              if e and len(e.get("id") or "") == 11 and e.get("title")
              and e.get("title") not in ("[Deleted video]", "[Private video]")]
    return tracks


# ---------- YouTube Music ----------
# Şarkılar, albümler ve benzer şarkı radyosu YouTube Music'ten: resmi sürümler, kare kapaklar, düzgün
# sanatçı adları. Her şarkının bir YouTube video kimliği var; çalma ve indirme aynen çalışır.

_ytmusic = None


def ytmusic():
    global _ytmusic
    if _ytmusic is None:
        from ytmusicapi import YTMusic
        _ytmusic = YTMusic()
    return _ytmusic


def _art(thumbnails, size=544):
    """En büyük kapak; Google'ın adresindeki boyutu istediğimiz büyüklüğe çevir."""
    if not thumbnails:
        return None
    return re.sub(r"=w\d+-h\d+", f"=w{size}-h{size}", thumbnails[-1]["url"])


def _seconds(text):
    parts = [int(p) for p in (text or "").split(":") if p.isdigit()]
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def track_from_song(song):
    video_id = song["videoId"]
    return {
        "id": video_id,
        "title": song.get("title") or "Adsız parça",
        "artist": ", ".join(a["name"] for a in song.get("artists") or [] if a.get("name")) or "Bilinmeyen sanatçı",
        "duration": int(song.get("duration_seconds") or _seconds(song.get("duration") or song.get("length"))),
        "thumbnail": _art(song.get("thumbnails") or song.get("thumbnail")) or thumbnail_url(video_id),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def search_songs(query, limit=20):
    results = ytmusic().search(query, filter="songs", limit=limit)
    return [track_from_song(r) for r in results if r.get("videoId")]


def search_albums(query, limit=10):
    albums = []
    for r in ytmusic().search(query, filter="albums", limit=limit):
        if not r.get("playlistId"):
            continue
        artists = ", ".join(a["name"] for a in r.get("artists") or [] if a.get("name"))
        albums.append({"id": r["playlistId"], "kind": "playlist", "title": r.get("title") or "Albüm",
                       "artist": artists or r.get("type") or "Albüm", "thumbnail": _art(r.get("thumbnails")),
                       "url": f"https://www.youtube.com/playlist?list={r['playlistId']}"})
    return albums


def search_artists(query, limit=6):
    artists = []
    for r in ytmusic().search(query, filter="artists", limit=limit):
        if r.get("browseId") and r.get("artist"):
            artists.append({"id": r["browseId"], "kind": "artist", "name": r["artist"],
                            "thumbnail": _art(r.get("thumbnails"), 300)})
    return artists[:limit]


def find_artist(name):
    """Ada göre sanatçı: önce birebir eşleşen, yoksa ilk sonuç."""
    found = search_artists(name, 5)
    for artist in found:
        if _norm(artist["name"]) == _norm(name):
            return artist
    return found[0] if found else None


def _releases(section, artist_name, label):
    out = []
    for r in (section or {}).get("results") or []:
        playlist_id = r.get("audioPlaylistId") or r.get("playlistId")
        if not playlist_id:
            continue
        out.append({"id": playlist_id, "kind": "playlist", "title": r.get("title") or label, "artist": artist_name,
                    "year": r.get("year"), "label": label, "thumbnail": _art(r.get("thumbnails")),
                    "url": f"https://www.youtube.com/playlist?list={playlist_id}"})
    return out


def artist_page(browse_id):
    """Sanatçı sayfası: popüler şarkılar, albümler, single'lar, benzer sanatçılar."""
    a = ytmusic().get_artist(browse_id)
    name = a.get("name") or "Sanatçı"
    songs_section = a.get("songs") or {}
    songs = [track_from_song(s) for s in songs_section.get("results") or [] if s.get("videoId")]
    more = songs_section.get("browseId")
    if more:  # yalnızca 5 şarkı geliyor; "tümü" listesinden ilk 25'i al
        try:
            full = ytmusic().get_playlist(more[2:] if more.startswith("VL") else more, limit=25)
            extra = [track_from_song(s) for s in full.get("tracks") or [] if s.get("videoId")]
            if len(extra) > len(songs):
                songs = extra[:25]
        except Exception:
            pass
    related = [{"id": r["browseId"], "kind": "artist", "name": r.get("title") or "Sanatçı",
                "subscribers": r.get("subscribers"), "thumbnail": _art(r.get("thumbnails"), 300)}
               for r in (a.get("related") or {}).get("results") or [] if r.get("browseId")]
    thumbs = a.get("thumbnails") or []
    return {
        "id": browse_id, "name": name,
        "banner": thumbs[-1]["url"] if thumbs else None,
        "thumbnail": _art(thumbs, 300) if thumbs else (songs[0]["thumbnail"] if songs else None),
        "subscribers": a.get("subscribers"), "listeners": a.get("monthlyListeners"),
        "description": a.get("description"), "radio": a.get("radioId"),
        "songs": songs,
        "albums": _releases(a.get("albums"), name, "Albüm"),
        "singles": _releases(a.get("singles"), name, "Single"),
        "related": related,
    }


def artist_radio(radio_id, limit=50):
    result = ytmusic().get_watch_playlist(playlistId=radio_id, limit=limit)
    return [track_from_song(t) for t in result.get("tracks") or [] if t.get("videoId")]


def radio(video_id, limit=25):
    """Bir şarkıya benzer şarkılar (YouTube Music radyosu)."""
    result = ytmusic().get_watch_playlist(video_id, limit=limit, radio=True)
    return [track_from_song(t) for t in result.get("tracks") or [] if t.get("videoId") and t["videoId"] != video_id]


# ---------- çakışmalar: aynı şarkının YouTube Music ve YouTube'daki kopyaları ----------

VERSION = re.compile(r"\b(live|canl[ıi]|konser|concert|ak[uü]sti[kc]|acoustic|remix|cover|karaoke|sped up|slowed|"
                     r"instrumental|enstr[uü]mantal|version|versiyon|mashup)\b", re.I)
_TR = str.maketrans("ıİşŞğĞüÜöÖçÇâÂ", "iissgguuooccaa")


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").translate(_TR).casefold())


def same_song(video, song):
    """YouTube videosu, YouTube Music'teki şarkının bir başka yüklemesi mi? (klip, resmi ses, sözlü...)"""
    if video["id"] == song["id"]:
        return True
    from lyricsfinder import candidates
    if VERSION.search(video["title"]) and not VERSION.search(song["title"]):
        return False  # canlı, akustik, remix, cover...: ayrı bir kayıt, videolarda kalsın
    title = _norm(song["title"])
    artist = _norm(song["artist"].split(",")[0])
    haystack = _norm(video["title"] + " " + video.get("artist", ""))
    if not title or not artist or artist not in haystack:
        return False
    return any(_norm(t) == title for _, t in candidates(video))


def same_recording(candidate, original):
    """Yedek yükleme asıl şarkının yerine geçer mi? Klip adı ("A - B (Official Video)") ile şarkı adı ("B")
    karşılaştırılabilir; canlı, cover, remix gibi farklı kayıtlar, asılları da öyle değilse geçmez."""
    from lyricsfinder import candidates
    if bool(VERSION.search(candidate["title"])) != bool(VERSION.search(original["title"])):
        return False

    def names(track):
        return {_norm(track["title"])} | {_norm(title) for _, title in candidates(track)}

    if not (names(candidate) & names(original)) - {""}:
        return False
    haystack = _norm(f"{candidate['title']} {candidate.get('artist', '')}")
    artist = _norm((original.get("artist") or "").split(",")[0])
    from_title = [_norm(a) for a, _ in candidates(original)]  # kanal adı sanatçı olmayabilir: başlıktan çıkan da sayılır
    return any(a and a in haystack for a in [artist, *from_title])


def remove_duplicates(videos, songs):
    return [v for v in videos if not any(same_song(v, s) for s in songs)]
