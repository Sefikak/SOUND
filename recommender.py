"""Ana sayfa önerileri: dinlediklerinden YouTube "Mix" listeleri, yeni kullanıcı için popüler aramalar.
Ayrıca akıllı sıra (smart_queue) ve albümü dolduran öneriler (album_suggestions)."""
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest

from library import LazyModule

yt_dlp = LazyModule("yt_dlp")  # ilk kullanımda yüklenir (telefonda açılışı hızlandırır)

from searcher import VERSION, _norm, radio, remove_duplicates, search_albums, search_playlists, search_tracks, track_from_entry

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


def _artist_albums(artist):
    """(sanatçı, albümler). Arama sanatçının adına benzeyen başka sanatçıları da getiriyor ("Global Records"
    → "Global Music Station"); en az 3 albüm gerçekten ona ait değilse popüler albümlere düş."""
    if artist:
        key = _norm(artist)
        own = [a for a in _albums(f"{artist} albüm") if key and key in _norm(a.get("artist"))]
        if len(own) >= 3:
            return artist, own
    return None, _albums("türkçe pop albüm")


def _distinct_covers(lists, keep=6):
    """YouTube listenin kapağı olarak ilk videoyu veriyor; aynı hit ile başlayan listeler aynı görünüyor.
    Kapağı tekrar edenleri ele, yeterince liste kalmazsa sona koy."""
    unique, repeats, covers = [], [], set()
    for item in lists:
        cover = item.get("thumbnail")
        if cover and cover in covers:
            repeats.append(item)
        else:
            covers.add(cover)
            unique.append(item)
    return unique if len(unique) >= keep else unique + repeats[:keep - len(unique)]


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
    album_job_pool = ThreadPoolExecutor(1)
    album_job = album_job_pool.submit(_artist_albums, top_artists[0][0] if top_artists else None)
    album_job_pool.shutdown(wait=False)

    def album_section():
        try:
            artist, albums = album_job.result()
        except Exception as error:
            errors.append(error)
            return None
        if not albums:
            return None
        title = f"{artist} albümleri ve listeleri" if artist else "Popüler albümler ve listeler"
        return {"key": "albums", "type": "albums", "title": title,
                "subtitle": "Sürükleyip kitaplığına bırakabilirsin", "albums": albums}

    def playlist_section():
        query = f"{top_artists[0][0]} şarkıları" if top_artists else "türkçe hit listesi"
        try:
            lists = search_playlists(query, 12)
        except Exception as error:
            errors.append(error)
            return None
        lists = _distinct_covers(lists)
        if not lists:
            return None
        return {"key": "playlists", "type": "albums", "title": "Senin için listeler",
                "subtitle": "Dinlediklerine yakın çalma listeleri", "albums": lists}

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
        lists = playlist_section()
        if lists:
            sections.append(lists)
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
        lists = playlist_section()
        if lists:
            sections.insert(min(2, len(sections)), lists)
        if sections:
            return sections, True

    if not sections and errors:
        raise errors[0]
    return sections, not seeds


# ---------- akıllı sıra: seçilen şarkıya gerçekten benzeyen, sana göre ayarlanmış devam ----------
#
# Tek bir kaynağa (yalnız YouTube Music radyosu ya da yalnız YouTube Mix) güvenmek yerine birkaç kaynaktan aday toplanır ve
# her aday puanlanır:
#   1. Benzerlik: şarkının radyosu (ağırlık 1), YouTube Mix'i (0,7), az önce çalınanların radyoları (0,35) ve radyonun
#      en üstteki iki şarkısının radyoları (0,45, "ikinci halka"). Sıralamada üstte olan daha çok puan alır
#      (karşılıklı sıra toplamı: ağırlık / (10 + sıra)).
#   2. Uzlaşma: birden çok kaynağın önerdiği şarkı daha güvenilirdir, puanı katlanır.
#   3. Zevk: çok dinlediğin ya da favorilerindeki sanatçılara biraz artı; hep atladığın sanatçılara eksi,
#      atladığın şarkılar hiç gelmez. Bu oturumda atladıkların da sayılır.
#   4. Tür uyumu: seçilen şarkı canlı/remix/sped up değilse öyle sürümler aşağı iner; çok uzun derlemeler elenir.
#   5. "Beğenmedim": o şarkı gelmez; radyosunda üst sıralarda olan (yani ona benzeyen) şarkılar da geri plana düşer.
# Sonra sıra çeşitlendirilir (aynı sanatçı arka arkaya gelmez, 20 şarkıda en fazla 3 kez çıkar) ve yumuşak geçiş için
# enerjiye göre dizilir: sakin bir şarkıdan sonra birden sert bir şarkı gelmez (flow).

SOURCE_CACHE_SECONDS = 1800
_source_cache, _source_lock = {}, threading.Lock()
_SPLIT_ARTISTS = re.compile(r"\s*(?:,|&|\bfeat\.?|\bft\.?|\bx\b|\bve\b|\band\b)\s*", re.I)
_NOISE = re.compile(r"[(\[].*?[)\]]|\b(official|video|audio|lyrics?|clip|klip|hd|4k|mv|şarkı sözleri|sözleri)\b", re.I)


def _cached(kind, track_id, fetch):
    key = (kind, track_id)
    with _source_lock:
        hit = _source_cache.get(key)
        if hit and time.time() - hit[0] < SOURCE_CACHE_SECONDS:
            return hit[1]
    value = fetch()
    with _source_lock:
        if len(_source_cache) > 300:
            _source_cache.clear()
        _source_cache[key] = (time.time(), value)
    return value


def _radio(track_id, limit=50):
    return _cached("radio", track_id, lambda: radio(track_id, limit))


def _mix(track_id):
    return _cached("mix", track_id, lambda: youtube_mix(track_id, 40))


def main_artist(track):
    name = (track.get("artist") or "").strip()
    return _norm(_SPLIT_ARTISTS.split(name)[0]) if name else ""


def song_key(track):
    """Aynı şarkının farklı yüklemeleri (klip, sözlü, resmi ses) aynı anahtarı alır."""
    title = track.get("title") or ""
    if " - " in title:
        head, tail = title.split(" - ", 1)
        artist = _norm(track.get("artist"))
        if not artist or main_artist(track) in _norm(head) or _norm(head) in artist:
            title = tail
    title = _NOISE.sub(" ", title)
    title = re.split(r"\s(?:feat\.?|ft\.?)\s", title, flags=re.I)[0]
    return _norm(title) or track.get("id")


class Taste:
    """Kullanıcının zevki: dinleme geçmişinden (listens), favorilerden ve bu oturumdaki atlamalardan."""

    def __init__(self, liked_artists=(), favorite_ids=(), skipped_ids=(), artist_skips=None, artist_plays=None, disliked=()):
        self.liked_artists = set(liked_artists)
        self.favorite_ids = set(favorite_ids)
        self.skipped_ids = set(skipped_ids)
        self.artist_skips = dict(artist_skips or {})
        self.artist_plays = dict(artist_plays or {})
        self.disliked = [d for d in disliked if isinstance(d, dict) and d.get("id")]  # en yeni birkaç "beğenmedim"

    def with_session(self, skipped=()):
        """Bu oturumda erken geçilen şarkılar: şarkı hiç gelmez, sanatçısı iki atlama sayılır."""
        taste = Taste(self.liked_artists, self.favorite_ids, self.skipped_ids, self.artist_skips, self.artist_plays, self.disliked)
        for track in skipped or ():
            if not isinstance(track, dict) or not track.get("id"):
                continue
            taste.skipped_ids.add(track["id"])
            artist = main_artist(track)
            if artist:
                taste.artist_skips[artist] = taste.artist_skips.get(artist, 0) + 2
        return taste

    def factor(self, track):
        artist = main_artist(track)
        factor = 1.0
        if artist in self.liked_artists:
            factor *= 1.15
        if track["id"] in self.favorite_ids:
            factor *= 1.05  # tanıdık şarkı arada iyi gelir ama sırayı doldurmasın
        skips, plays = self.artist_skips.get(artist, 0), self.artist_plays.get(artist, 0)
        if skips >= 2 and skips > plays:
            factor *= max(0.25, 1 - 0.18 * (skips - plays))
        return factor


def _rank(sources, exclude_ids, exclude_keys, taste, seed_tracks):
    """sources: [(ağırlık, [şarkı, ...]), ...] → puana göre sıralı [(puan, şarkı), ...]"""
    seed_is_version = any(VERSION.search(t.get("title") or "") for t in seed_tracks)
    longest = max([t.get("duration") or 0 for t in seed_tracks] + [0])
    max_seconds = max(600, longest * 1.6)
    scores, hits, best = {}, {}, {}
    for weight, tracks in sources:
        seen_here = set()
        for rank, track in enumerate(tracks or []):
            if not track or not track.get("id") or track["id"] in exclude_ids or track["id"] in taste.skipped_ids:
                continue
            key = song_key(track)
            if key in exclude_keys or key in seen_here:
                continue
            seen_here.add(key)
            scores[key] = scores.get(key, 0.0) + weight / (10 + rank)
            hits[key] = hits.get(key, 0) + 1
            # aynı şarkının YouTube Music kaydı (temiz başlık, doğru sanatçı) klipten iyidir: ilk gelen (radyo) kalır
            best.setdefault(key, track)
    ranked = []
    for key, score in scores.items():
        track = best[key]
        duration = track.get("duration") or 0
        if duration and (duration < 45 or duration > max_seconds):
            continue  # kısa tanıtım ya da saatlik derleme
        score *= 1 + 0.3 * (hits[key] - 1)  # uzlaşma
        if not seed_is_version and VERSION.search(track.get("title") or ""):
            score *= 0.3
        score *= taste.factor(track)
        ranked.append((score, track))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def _diversify(ranked, limit, first_artists=(), per_artist=3, gap=2):
    """Puan sırasını fazla bozmadan çeşitlendirir: aynı sanatçı `gap` şarkı içinde tekrar etmez, en çok `per_artist` kez çıkar."""
    pool = list(ranked)
    picked, recent, counts = [], ([a for a in first_artists if a][-gap:] if gap else []), {}
    while pool and len(picked) < limit:
        choice = None
        for i, (_, track) in enumerate(pool[:12]):  # puanı çok düşük olanı öne almamak için ilk 12'ye bakılır
            artist = main_artist(track)
            if counts.get(artist, 0) >= per_artist or (artist and artist in recent):
                continue
            choice = i
            break
        if choice is None:
            # kural yüzünden kimse seçilemiyor: sınırı aşmayan ilk şarkı, o da yoksa en iyisi
            choice = next((i for i, (_, t) in enumerate(pool) if counts.get(main_artist(t), 0) < per_artist), None)
            if choice is None:
                break
        _, track = pool.pop(choice)
        artist = main_artist(track)
        counts[artist] = counts.get(artist, 0) + 1
        recent = (recent + [artist])[-gap:] if gap else []
        picked.append(track)
    return picked


def _gather(jobs):
    """[(ağırlık, iş)] → [(ağırlık, şarkılar)]; çöken kaynak atlanır, hepsi çökerse ilk hata yükselir."""
    sources, error = [], None
    for weight, job in jobs:
        try:
            sources.append((weight, job.result()))
        except Exception as e:
            error = error or e
    if not any(tracks for _, tracks in sources) and error:
        raise error
    return sources


_CALM = re.compile(r"\b(slowed|ak[uü]sti[kc]|acoustic|piano|piyano|unplugged|lo-?fi|ballad|balad|reverb|sakin|uyku|sleep)\b", re.I)
_HYPE = re.compile(r"\b(sped up|speed up|remix|club|bass ?boost(ed)?|phonk|hardstyle|techno|drill|trap|party|dance)\b", re.I)


def guess_energy(track):
    """Ölçülmemiş şarkının enerjisi için başlık ipucu; ipucu yoksa None."""
    title = track.get("title") or ""
    if _CALM.search(title):
        return 0.25
    if _HYPE.search(title):
        return 0.8
    return None


def flow(tracks, energy, start=None, window=5):
    """Yumuşak geçiş: puan sırasını çok bozmadan, her adımda enerjisi bir öncekine en yakın olanı seçer (ilk `window`
    aday arasından). Enerjisi bilinmeyen şarkı tarafsızdır; bilinenlerde büyük sıçrama cezalandırılır."""
    def level(track):
        value = energy.get(track["id"])
        return value if value is not None else guess_energy(track)
    if sum(1 for t in tracks if level(t) is not None) < 3:
        return list(tracks)  # yeterli bilgi yok: puan sırası kalır
    pool, ordered, previous, waited = list(tracks), [], start, {}
    while pool:
        best, best_cost = 0, None
        overdue = next((i for i, t in enumerate(pool[:window]) if waited.get(t["id"], 0) >= 4), None)
        for i, track in enumerate(pool[:window] if overdue is None else []):
            current = level(track)
            jump = abs(current - previous) if current is not None and previous is not None else 0.12
            cost = jump + 0.07 * i  # öndeki (daha benzer) şarkılar öncelikli kalsın
            if best_cost is None or cost < best_cost:
                best, best_cost = i, cost
        if overdue is not None:
            best = overdue  # iyi öneri sonsuza dek bekletilmesin
        for t in pool[:window]:
            waited[t["id"]] = waited.get(t["id"], 0) + 1
        track = pool.pop(best)
        ordered.append(track)
        if level(track) is not None:
            previous = level(track) if previous is None else previous * 0.4 + level(track) * 0.6
    return ordered


def _dislike_penalty(ranked, taste, seed_id):
    """Beğenilmeyen şarkıların radyolarının üst sırasındakiler (onlara benzeyenler) geri plana düşer."""
    if not taste.disliked:
        return ranked
    near = set()
    for item in taste.disliked[-3:]:
        try:
            near |= {song_key(t) for t in _radio(item["id"])[:15]}
        except Exception:
            pass
    if not near:
        return ranked
    try:
        own = {song_key(t) for t in _radio(seed_id)[:8]}  # seçtiğin şarkıya çok yakın olanlar yine de kalabilir
    except Exception:
        own = set()
    out = [(score * (0.35 if song_key(t) in near and song_key(t) not in own else 1), t) for score, t in ranked]
    out.sort(key=lambda item: item[0], reverse=True)
    return out


def smart_queue(seed, taste=None, context=(), exclude=(), limit=25, energies=None):
    """Seçilen şarkıdan sonra çalınacak, ona ve sana uygun şarkılar.
    context: bu oturumda az önce çalınanlar (en yenisi sonda); exclude: sırada olan ya da yeni çalınmış kimlikler;
    energies: kimlik listesi → {kimlik: enerji} (ölçülmüş enerjiler, yumuşak geçiş için)."""
    taste = taste or Taste()
    context = [t for t in context or () if isinstance(t, dict) and t.get("id") and t["id"] != seed["id"]][-2:]
    seed_artist = main_artist(seed)
    with ThreadPoolExecutor(4) as pool:
        direct_job = pool.submit(_radio, seed["id"])
        jobs = [(1.0, direct_job), (0.7, pool.submit(_mix, seed["id"]))]
        jobs += [(0.35, pool.submit(_radio, t["id"])) for t in context]
        sources = _gather(jobs)
        # ikinci halka: radyonun en üstündeki, başka sanatçıya ait iki şarkının radyoları. Ortak çıkan şarkılar
        # tesadüf değil, gerçekten aynı türdendir.
        try:
            direct = direct_job.result()
        except Exception:
            direct = []
        hop, hop_artists = [], set()
        for track in direct:
            artist = main_artist(track)
            if artist and artist != seed_artist and artist not in hop_artists:
                hop.append(track)
                hop_artists.add(artist)
            if len(hop) == 2:
                break
        if hop:
            try:
                sources += _gather([(0.45, pool.submit(_radio, t["id"])) for t in hop])
            except Exception:
                pass
    exclude_ids = set(exclude or ()) | {seed["id"]}
    exclude_keys = {song_key(seed)} | {song_key(t) for t in context}
    ranked = _dislike_penalty(_rank(sources, exclude_ids, exclude_keys, taste, [seed]), taste, seed["id"])
    picked = _diversify(ranked, limit, first_artists=[main_artist(t) for t in context] + [seed_artist])
    if energies:
        try:
            known = energies([seed["id"]] + [t["id"] for t in picked])
            picked = flow(picked, known, known.get(seed["id"], guess_energy(seed)))
        except Exception:
            pass
    return picked


def album_suggestions(album_tracks, taste=None, count=10, seeds=6):
    """Albümdeki şarkılara uyan şarkılar. Albümün birçok şarkısına birden benzeyen öne çıkar (uzlaşma), albümde sık geçen
    sanatçılara yakın olanlara artı verilir; albümde zaten olanlar ve aynı şarkının başka yüklemeleri gelmez."""
    taste = taste or Taste()
    album_tracks = [t for t in album_tracks if t and t.get("id")]
    if not album_tracks:
        return []
    # tohumlar albüme yayılsın: son eklenenler (albümün şimdiki yönü) ağırlıklı, baştan sona da birkaç şarkı
    step = max(1, len(album_tracks) // seeds)
    seed_tracks, seen = [], set()
    for track in album_tracks[::-1][:max(2, seeds // 2)] + album_tracks[::step]:
        if track["id"] not in seen:
            seen.add(track["id"])
            seed_tracks.append(track)
        if len(seed_tracks) == seeds:
            break
    with ThreadPoolExecutor(min(7, len(seed_tracks) + 1)) as pool:
        jobs = [(1.0, pool.submit(_radio, t["id"])) for t in seed_tracks]
        jobs.append((0.5, pool.submit(_mix, seed_tracks[0]["id"])))
        sources = _gather(jobs)
    ranked = _rank(sources, {t["id"] for t in album_tracks}, {song_key(t) for t in album_tracks}, taste, album_tracks)
    artists = {}
    for track in album_tracks:
        artist = main_artist(track)
        artists[artist] = artists.get(artist, 0) + 1
    boosted = [(score * (1 + min(0.5, artists.get(main_artist(track), 0) / len(album_tracks))), track) for score, track in ranked]
    boosted.sort(key=lambda item: item[0], reverse=True)
    # albüm tek sanatçılıksa o sanatçıdan çok şarkı gelebilir; karışıksa çeşitlilik korunur
    top_share = max(artists.values()) / len(album_tracks)
    if top_share >= 0.5:
        return _diversify(boosted, count, per_artist=max(2, math.ceil(count * top_share)), gap=0)
    return _diversify(boosted, count, per_artist=2, gap=2)


# ---------- Spotify tarzı mixler ----------
#
# Günlük Mix 1–4: en çok dinlediğin şarkılar, radyoları birbirine benzeyenler bir arada olacak şekilde gruplara ayrılır
#   (rap ayrı, rock ayrı…). Her mix o grubun bildiğin şarkılarıyla ona uyan yeni şarkıları karışık çalar. Her gün yenilenir.
# Haftalık Keşif: hiç dinlemediğin, zevkine uygun 30 şarkı; çok dinlediğin sanatçılar geri planda. Her hafta yenilenir.
# Yeni Çıkanlar: en çok dinlediğin sanatçıların son bir yılda çıkardıkları. Her hafta yenilenir.
# (Tekrar Tekrar ve Unutulan Favoriler yalnızca dinleme geçmişinden, webapp'ta anında hesaplanır.)

MIX_COLORS = ["#e0457b", "#2f9e6e", "#3d7be0", "#d8892b", "#8a4fe0", "#16a3b8"]


def _artist_names(tracks, count=3):
    names, seen = [], set()
    for track in tracks:
        name = _SPLIT_ARTISTS.split((track.get("artist") or "").strip())[0].strip()
        key = _norm(name)
        if name and key not in seen and name != "Bilinmeyen sanatçı":
            seen.add(key)
            names.append(name)
        if len(names) == count:
            break
    return names


def _covers(tracks, count=4):
    covers, seen = [], set()
    for track in tracks:
        artist = main_artist(track)
        if track.get("thumbnail") and artist not in seen:
            seen.add(artist)
            covers.append(track["thumbnail"])
        if len(covers) == count:
            break
    return covers


def _clusters(seeds, radios, max_groups=4):
    """Dinlediğin şarkıları radyolarının örtüşmesine göre gruplar. seeds: [{"track","plays"}] çoktan aza."""
    keys = {s["track"]["id"]: {song_key(t) for t in (radios.get(s["track"]["id"]) or [])[:30]} for s in seeds}

    def similar(a, b):
        ka, kb = keys[a["id"]], keys[b["id"]]
        score = len(ka & kb) / max(1, min(len(ka), len(kb))) if ka and kb else 0
        if main_artist(a) and main_artist(a) == main_artist(b):
            score += 0.5
        if song_key(b) in ka or song_key(a) in kb:
            score += 0.4
        return score

    groups, used = [], set()
    for seed in seeds:
        track = seed["track"]
        if track["id"] in used or not keys[track["id"]]:
            continue
        group = [seed]
        used.add(track["id"])
        for other in seeds:
            if other["track"]["id"] not in used and keys[other["track"]["id"]] and similar(track, other["track"]) >= 0.2:
                group.append(other)
                used.add(other["track"]["id"])
        groups.append(group)
    big = [g for g in groups if len(g) >= 2]
    # tek kalanlar en benzediği gruba katılır
    for group in groups:
        if len(group) == 1 and big:
            best = max(big, key=lambda g: similar(g[0]["track"], group[0]["track"]))
            if similar(best[0]["track"], group[0]["track"]) > 0.05:
                best.append(group[0])
    big.sort(key=lambda g: sum(s["plays"] for s in g), reverse=True)
    return big[:max_groups]


def daily_mixes(listened, taste=None, energies=None, size=30):
    """listened: listened_tracks(60 gün). [{"key","title","subtitle","tracks","covers","color"}]"""
    taste = taste or Taste()
    seeds = [s for s in listened if s["track"].get("id")][:16]
    if len(seeds) < 4:
        return []
    with ThreadPoolExecutor(6) as pool:
        jobs = {s["track"]["id"]: pool.submit(_radio, s["track"]["id"]) for s in seeds}
    radios = {}
    for track_id, job in jobs.items():
        try:
            radios[track_id] = job.result()
        except Exception:
            radios[track_id] = []
    heard = {s["track"]["id"] for s in listened}
    heard_keys = {song_key(s["track"]) for s in listened}
    mixes = []
    for n, group in enumerate(_clusters(seeds, radios), 1):
        group_artists = {main_artist(s["track"]) for s in group}
        familiar = [s["track"] for s in group]
        # aynı sanatçıların dinlediğin diğer şarkıları da bu mixe girer
        familiar += [s["track"] for s in listened if s not in group and main_artist(s["track"]) in group_artists][:6]
        familiar = familiar[:size // 2]
        sources = [(1.0, radios.get(s["track"]["id"]) or []) for s in group]
        ranked = _rank(sources, heard, heard_keys, taste, [s["track"] for s in group])
        fresh = _diversify(ranked, size - len(familiar), per_artist=2, gap=2)
        # bildik – yeni – yeni – bildik … karışık
        tracks, f, r = [], iter(familiar), iter(fresh)
        while len(tracks) < size:
            group_next = [t for t in (next(f, None), next(r, None), next(r, None)) if t]
            if not group_next:
                break
            tracks += group_next
        if energies:
            try:
                tracks = flow(tracks, energies([t["id"] for t in tracks]))
            except Exception:
                pass
        names = _artist_names([s["track"] for s in group] + fresh)
        mixes.append({"key": f"daily{n}", "kind": "daily", "title": f"Günlük Mix {n}",
                      "subtitle": ", ".join(names) + " ve daha fazlası", "tracks": tracks[:size],
                      "covers": _covers([s["track"] for s in group] + fresh), "color": MIX_COLORS[(n - 1) % len(MIX_COLORS)]})
    return mixes


def discover_weekly(listened, taste=None, known_ids=(), size=30):
    """Hiç dinlemediğin, zevkine uygun şarkılar. Çok dinlediğin sanatçılar geri planda (keşif için)."""
    taste = taste or Taste()
    seeds = [s for s in listened if s["track"].get("id")][:12]
    if len(seeds) < 3:
        return None
    with ThreadPoolExecutor(6) as pool:
        jobs = [(1.0 - i * 0.05, pool.submit(_radio, s["track"]["id"])) for i, s in enumerate(seeds)]
        sources = _gather(jobs)
    heard = set(known_ids) | {s["track"]["id"] for s in listened}
    heard_keys = {song_key(s["track"]) for s in listened}
    familiar_artists = {main_artist(s["track"]) for s in listened[:40]}
    ranked = _rank(sources, heard, heard_keys, taste, [s["track"] for s in seeds])
    ranked = [(score * (0.45 if main_artist(t) in familiar_artists else 1), t) for score, t in ranked]
    ranked.sort(key=lambda item: item[0], reverse=True)
    tracks = _diversify(ranked, size, per_artist=1, gap=3)
    if len(tracks) < size:  # yeni sanatçı azsa sanatçı başına ikinci şarkıya izin ver
        have = {t["id"] for t in tracks}
        tracks += [t for t in _diversify(ranked, size * 2, per_artist=2, gap=2) if t["id"] not in have][:size - len(tracks)]
    return {"key": "weekly", "kind": "weekly", "title": "Haftalık Keşif", "subtitle": "Henüz dinlemediğin, sevebileceğin şarkılar",
            "tracks": tracks, "covers": _covers(tracks), "color": "#1f6f5c"}


def release_radar(artist_names, known_ids=(), size=30, year=None):
    """En çok dinlediğin sanatçıların son çıkardıkları (YouTube Music sanatçı sayfası: single ve albümler)."""
    from searcher import artist_page, find_artist, release_songs
    year = year or time.localtime().tm_year

    def for_artist(name):
        artist = find_artist(name)
        if not artist or _norm(artist.get("name")) != _norm(name):
            return []
        page = artist_page(artist["id"])
        releases = []
        for release in (page.get("singles") or [])[:3] + (page.get("albums") or [])[:2]:
            try:
                if int(str(release.get("year") or 0)[:4]) >= year - 1:
                    releases.append(release)
            except ValueError:
                pass
        songs = []
        for release in releases[:3]:
            try:
                songs += release_songs(release["id"], 4)[:3 if release.get("label") == "Albüm" else 2]
            except Exception:
                pass
        return songs

    with ThreadPoolExecutor(4) as pool:
        jobs = [pool.submit(for_artist, name) for name in artist_names[:8]]
    pools = []
    for job in jobs:
        try:
            pools.append(job.result())
        except Exception:
            pass
    known = set(known_ids)
    tracks, seen = [], set()
    for track in _interleave(pools):  # sanatçılar sırayla
        key = song_key(track)
        if key not in seen:
            seen.add(key)
            track = dict(track, new=track["id"] not in known)
            tracks.append(track)
    if len(tracks) < 3:
        return None
    return {"key": "radar", "kind": "radar", "title": "Yeni Çıkanlar", "subtitle": "Dinlediğin sanatçılardan yeni şarkılar",
            "tracks": tracks[:size], "covers": _covers(tracks), "color": "#c2410c"}
