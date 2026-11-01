"""Şarkı sözleri: LRCLIB (lrclib.net, ücretsiz ve açık). Zamanlı sözler varsa satır satır, yoksa düz metin.

YouTube başlıkları dağınık ("TARKAN - Dudu (Official Music Video)"), önce sanatçı ve şarkı adını ayıklarız."""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://lrclib.net/api/search"
NOISE = re.compile(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}]")  # (Official Video), [Lyrics], {HD} ...
TAIL = re.compile(r"\s*(\||//|official|lyrics?|video ?clip|music video|klip|audio|hd|4k)\b.*$", re.I)
CHANNEL = re.compile(r"\s*(-\s*topic|vevo|official|music|tv|records)\s*$", re.I)


def candidates(track):
    """(sanatçı, şarkı adı) tahminleri, en olasıdan başlayarak."""
    title = NOISE.sub("", track.get("title") or "")
    title = TAIL.sub("", title).strip(" -–|")
    artist = CHANNEL.sub("", track.get("artist") or "").strip()
    parts = [p.strip(" -–") for p in re.split(r"\s+[-–—|]\s+|:\s+", title) if p.strip(" -–")]
    guesses = []
    if len(parts) >= 2:
        guesses.append((parts[0], " - ".join(parts[1:])))
        if len(parts) >= 3:  # "Dizi adı - Sanatçı - Şarkı"
            guesses.append((parts[-2], parts[-1]))
    guesses.append((artist, parts[-1] if parts else title))
    return [g for i, g in enumerate(guesses) if g[1] and g not in guesses[:i]]


def clean(track):
    return candidates(track)[0]


def parse_synced(text):
    lines = []
    for raw in (text or "").splitlines():
        stamps = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", raw)
        words = re.sub(r"\[[^\]]*\]", "", raw).strip()
        for minutes, seconds in stamps:
            lines.append([round(int(minutes) * 60 + float(seconds), 2), words])
    return sorted(lines)


def _search(params, attempts=3):
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "SOUND music player (masaüstü)"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == attempts - 1:
                raise
            time.sleep(1.5 * (attempt + 1))  # servis meşgul: biraz bekle, tekrar dene


def find(track):
    """{"synced": [[saniye, satır], ...] | None, "plain": str | None, "artist", "title"} ya da {"none": True}."""
    duration = track.get("duration") or 0
    results = []
    for artist, title in candidates(track):
        results = _search({"track_name": title, "artist_name": artist}) if artist else []
        if not results:
            results = _search({"q": f"{artist} {title}".strip()})
        if results:
            break
    if not results:
        return {"none": True}

    def score(item):
        gap = abs((item.get("duration") or 0) - duration) if duration else 0
        return (gap > 8, not item.get("syncedLyrics"), gap)

    best = min(results, key=score)
    if duration and abs((best.get("duration") or 0) - duration) > 20:
        return {"none": True}  # başka bir şarkının sözleri olabilir
    synced = parse_synced(best.get("syncedLyrics"))
    plain = best.get("plainLyrics")
    if not synced and not plain:
        return {"none": True}
    return {"synced": synced or None, "plain": plain, "artist": best.get("artistName"), "title": best.get("trackName")}
