"""Ana sayfa önerileri: dinlediklerinden YouTube "Mix" listeleri, yeni kullanıcı için popüler aramalar."""
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest

import yt_dlp

from searcher import radio, remove_duplicates, search_albums, search_playlists, search_tracks, track_from_entry

COLD_START = [
    ("Popüler Türkçe Pop", "türkçe pop hit şarkılar"),
    ("Dünya listeleri", "global top hits songs"),
    ("Türkçe Rap", "türkçe rap hit"),
]


def youtube_mix(track_id, limit=25):
    """YouTube'un "Mix" listesi (yt-dlp ile; YouTube Music'e ulaşılamazsa da çalışır)."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": limit,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={track_id}&list=RD{track_id}", download=False)
    return [track_from_entry(e) for e in info.get("entries") or []
            if e and len(e.get("id") or "") == 11 and e["id"] != track_id]


def mix_for(track_id, limit=25):
    """Bir şarkıya benzer şarkılar: YouTube Music radyosu ile YouTube Mix harmanı (3'e 1).
    Biri çalışmazsa diğeri tek başına kullanılır; ikisi de çalışmazsa hata verir."""
    with ThreadPoolExecutor(2) as pool:
        radio_job = pool.submit(radio, track_id, limit)
        mix_job = pool.submit(youtube_mix, track_id, limit)
    radio_tracks, mix_tracks, error = [], [], None
    try:
        radio_tracks = radio_job.result()
    except Exception as e:
        error = e
    try:
        mix_tracks = mix_job.result()
    except Exception as e:
        error = error or e
    if not radio_tracks and not mix_tracks:
        if error:
            raise error
        return []
    mix_tracks = remove_duplicates(mix_tracks, radio_tracks)
    blended, seen = [], set()
    r, m = iter(radio_tracks), iter(mix_tracks)
    while len(blended) < limit:
        group = [t for t in (next(r, None), next(r, None), next(r, None), next(m, None)) if t]
        if not group:
            break
        for t in group:
            if t["id"] not in seen:
                seen.add(t["id"])
                blended.append(t)
    return blended[:limit]


def _albums(query):
    try:
        albums = search_albums(query, 12)
        if albums:
            return albums
    except Exception:
        pass
    return search_playlists(query, 12)


def _interleave(pools):
    return [t for group in zip_longest(*pools) for t in group if t]


def build_home(recent, top_artists, known_ids):
    """Ana sayfa bölümlerini üretir. (bölümler, yeni_kullanıcı_mı) döner."""
    seen = set(known_ids)

    def take(tracks, count):
        picked = []
        for track in tracks:
            if track["id"] not in seen:
                seen.add(track["id"])
                picked.append(track)
                if len(picked) == count:
                    break
        return picked

    seeds = [t["id"] for t in recent[:3]]
    artist_seeds = [(artist, track["id"]) for artist, track in top_artists[:2]]
    sections, errors = [], []

    # Albüm / liste önerileri: en çok dinlenen sanatçı, yoksa popüler albümler
    album_query = f"{top_artists[0][0]} albüm" if top_artists else "türkçe pop albüm"
    album_job_pool = ThreadPoolExecutor(1)
    album_job = album_job_pool.submit(_albums, album_query)
    album_job_pool.shutdown(wait=False)

    def album_section():
        try:
            albums = album_job.result()
        except Exception as error:
            errors.append(error)
            return None
        if not albums:
            return None
        title = f"{top_artists[0][0]} albümleri ve listeleri" if top_artists else "Popüler albümler ve listeler"
        return {"key": "albums", "type": "albums", "title": title,
                "subtitle": "Sürükleyip kitaplığına bırakabilirsin", "albums": albums}

    if seeds:
        with ThreadPoolExecutor(5) as pool:
            jobs = {seed: pool.submit(mix_for, seed) for seed in seeds + [s for _, s in artist_seeds]}
        mixes = {}
        for seed, job in jobs.items():
            try:
                mixes[seed] = job.result()
            except Exception as error:
                errors.append(error)

        picks = take(_interleave([mixes.get(seed, []) for seed in seeds]), 14)
        if picks:
            sections.append({"key": "for-you", "title": "Senin için önerilenler",
                             "subtitle": "Son dinlediklerine göre", "tracks": picks})
        albums = album_section()
        if albums:
            sections.append(albums)
        for artist, seed in artist_seeds:
            picks = take(mixes.get(seed, []), 12)
            if picks:
                sections.append({"key": f"artist:{artist}", "title": f"{artist} sevenlere",
                                 "subtitle": "Benzer sanatçılar ve şarkılar", "tracks": picks})

    if not sections:
        with ThreadPoolExecutor(3) as pool:
            jobs = [(title, pool.submit(search_tracks, query, 16)) for title, query in COLD_START]
        for title, job in jobs:
            try:
                picks = take(job.result(), 12)
            except Exception as error:
                errors.append(error)
                continue
            if picks:
                sections.append({"key": f"discover:{title}", "title": title,
                                 "subtitle": "Keşfetmeye başla", "tracks": picks})
        albums = album_section()
        if albums:
            sections.insert(min(1, len(sections)), albums)
        if sections:
            return sections, True

    if not sections and errors:
        raise errors[0]
    return sections, not seeds
