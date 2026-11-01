import copy
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MUSIC_DIR = os.path.join(DATA_DIR, "music")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")
VIDEO_DIR = os.path.join(DATA_DIR, "videos")
LIBRARY_FILE = os.path.join(DATA_DIR, "library.json")  # eski biçim: ilk açılışta veritabanına aktarılır
DB_FILE = os.path.join(DATA_DIR, "library.db")

for folder in (MUSIC_DIR, CACHE_DIR, THUMB_DIR, VIDEO_DIR):
    os.makedirs(folder, exist_ok=True)

TRACK_FIELDS = ("id", "title", "artist", "duration", "thumbnail", "url", "file", "video_file", "downloaded_at")
SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (id TEXT PRIMARY KEY, title TEXT, artist TEXT, duration INTEGER, thumbnail TEXT,
    url TEXT, file TEXT, video_file TEXT, downloaded_at REAL);
CREATE TABLE IF NOT EXISTS favorites (pos INTEGER, track_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS albums (id TEXT PRIMARY KEY, name TEXT, folder TEXT, created REAL, source TEXT);
CREATE TABLE IF NOT EXISTS album_tracks (album_id TEXT, pos INTEGER, track_id TEXT, PRIMARY KEY (album_id, track_id));
CREATE TABLE IF NOT EXISTS folders (id TEXT PRIMARY KEY, name TEXT, created REAL);
CREATE TABLE IF NOT EXISTS history (pos INTEGER, track_id TEXT PRIMARY KEY, at REAL, plays INTEGER);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS lyrics (track_id TEXT PRIMARY KEY, data TEXT, fetched REAL);
"""
DEFAULT_SETTINGS = {"crossfade": False, "crossfade_seconds": 6, "gapless": True, "cache_mb": 1500, "autoplay": True}


class Library:
    """Favoriler, indirilenler, albümler, klasörler, geçmiş ve ayarlar.

    Kalıcı kayıt data/library.db (SQLite): her değişiklik yalnızca ilgili satırları yazar, yarıda kesilse
    bile veritabanı bozulmaz. Okuma hızlı olsun diye her şeyin bir kopyası bellekte (self.data) tutulur."""

    def __init__(self):
        self._listeners = []
        self._lock = threading.RLock()
        self.data = {
            "tracks": {},
            "favorites": [],
            "albums": {},
            "folders": {},
            "recent_searches": [],
            "history": [],
            "home_cache": None,
            "volume": 0.7,
            "youtube_auth": None,
            "settings": dict(DEFAULT_SETTINGS),
        }
        self._undo = []  # geri alma: son değişikliklerden önceki kitaplık düzeni (yalnızca bu oturumda)
        fresh = not os.path.exists(DB_FILE)
        self.db = sqlite3.connect(DB_FILE, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        if fresh:
            self._import_json()
        self._load()

    # ---------- kayıt ----------

    def _import_json(self):
        """Eski library.json'u (bozuksa .bak'ı) veritabanına aktar."""
        stored = None
        for path in (LIBRARY_FILE, LIBRARY_FILE + ".bak"):
            if not os.path.exists(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    stored = json.load(f)
                break
            except (OSError, json.JSONDecodeError):
                continue
        if not stored:
            return
        with self._tx():
            for track in stored.get("tracks", {}).values():
                self._write_track(track)
            self._write_list("favorites", stored.get("favorites", []))
            for album_id, album in stored.get("albums", {}).items():
                self.db.execute("INSERT INTO albums VALUES (?,?,?,?,?)", (album_id, album["name"], album.get("folder"),
                                                                         album.get("created", 0), album.get("source")))
                self._write_album_tracks(album_id, album["tracks"])
            for folder_id, folder in stored.get("folders", {}).items():
                self.db.execute("INSERT INTO folders VALUES (?,?,?)", (folder_id, folder["name"], folder.get("created", 0)))
            self._write_history(stored.get("history", []))
            for key in ("recent_searches", "home_cache", "volume", "youtube_auth"):
                if key in stored:
                    self._write_kv(key, stored[key])
        try:
            shutil.copy2(LIBRARY_FILE, LIBRARY_FILE + ".tasindi")  # yedek olarak kalsın
        except OSError:
            pass

    def _load(self):
        db, data = self.db, self.data
        for row in db.execute(f"SELECT {','.join(TRACK_FIELDS)} FROM tracks"):
            track = dict(zip(TRACK_FIELDS, row))
            if not track["downloaded_at"]:
                track.pop("downloaded_at")
            if not track["video_file"]:
                track.pop("video_file")
            data["tracks"][track["id"]] = track
        data["favorites"] = [r[0] for r in db.execute("SELECT track_id FROM favorites ORDER BY pos")]
        for album_id, name, folder, created, source in db.execute("SELECT id, name, folder, created, source FROM albums"):
            data["albums"][album_id] = {"name": name, "folder": folder, "created": created, "source": source, "tracks": []}
        for album_id, track_id in db.execute("SELECT album_id, track_id FROM album_tracks ORDER BY album_id, pos"):
            if album_id in data["albums"]:
                data["albums"][album_id]["tracks"].append(track_id)
        for folder_id, name, created in db.execute("SELECT id, name, created FROM folders"):
            data["folders"][folder_id] = {"name": name, "created": created}
        data["history"] = [{"id": t, "at": at, "plays": plays}
                           for t, at, plays in db.execute("SELECT track_id, at, plays FROM history ORDER BY pos")]
        for key, value in db.execute("SELECT key, value FROM kv"):
            data[key] = json.loads(value)
        data["settings"] = {**DEFAULT_SETTINGS, **(data.get("settings") or {})}
        from searcher import JUNK_NAMES, guess_artist
        for track in data["tracks"].values():
            if not track.get("artist") or track["artist"].strip().casefold() in JUNK_NAMES:
                track["artist"] = guess_artist(None, track.get("title"))
                db.execute("UPDATE tracks SET artist=? WHERE id=?", (track["artist"], track["id"]))
            if track.get("file") and not os.path.exists(os.path.join(MUSIC_DIR, track["file"])):
                track["file"] = None
            if track.get("video_file") and not os.path.exists(os.path.join(VIDEO_DIR, track["video_file"])):
                track["video_file"] = None

    class _Tx:
        def __init__(self, lib):
            self.lib = lib

        def __enter__(self):
            self.lib._lock.acquire()
            self.lib.db.execute("BEGIN")

        def __exit__(self, kind, value, tb):
            try:
                self.lib.db.execute("ROLLBACK" if kind else "COMMIT")
            finally:
                self.lib._lock.release()

    def _tx(self):
        return self._Tx(self)

    def _write_track(self, track):
        self.db.execute(f"INSERT OR REPLACE INTO tracks VALUES ({','.join('?' * len(TRACK_FIELDS))})",
                        tuple(track.get(k) for k in TRACK_FIELDS))

    def _write_list(self, table, ids):
        self.db.execute(f"DELETE FROM {table}")
        self.db.executemany(f"INSERT OR IGNORE INTO {table} VALUES (?,?)", list(enumerate(ids)))

    def _write_album_tracks(self, album_id, ids):
        self.db.execute("DELETE FROM album_tracks WHERE album_id=?", (album_id,))
        self.db.executemany("INSERT OR IGNORE INTO album_tracks VALUES (?,?,?)",
                            [(album_id, pos, track_id) for pos, track_id in enumerate(ids)])

    def _write_history(self, history):
        self.db.execute("DELETE FROM history")
        self.db.executemany("INSERT OR IGNORE INTO history VALUES (?,?,?,?)",
                            [(pos, e["id"], e.get("at", 0), e.get("plays", 1)) for pos, e in enumerate(history)])

    def _write_kv(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def _prune(self):
        # Hiçbir yerde kullanılmayan şarkı bilgilerini at
        keep = set(self.data["favorites"])
        keep.update(entry["id"] for entry in self.data["history"])
        for album in self.data["albums"].values():
            keep.update(album["tracks"])
        tracks = self.data["tracks"]
        for track_id in list(tracks):
            if track_id not in keep and not tracks[track_id].get("file") and not tracks[track_id].get("video_file"):
                del tracks[track_id]
                self.db.execute("DELETE FROM tracks WHERE id=?", (track_id,))

    def subscribe(self, callback):
        self._listeners.append(callback)

    def _notify(self):
        for callback in self._listeners:
            callback()

    # ---------- şarkılar ----------

    def remember(self, track):
        stored = self.data["tracks"].get(track["id"])
        if stored is None:
            stored = {key: track.get(key) for key in ("id", "title", "artist", "duration", "thumbnail", "url")}
            stored["file"] = None
            self.data["tracks"][track["id"]] = stored
            self._write_track(stored)
        return stored

    def get(self, track_id):
        return self.data["tracks"].get(track_id)

    def local_path(self, track_id):
        track = self.get(track_id)
        if track and track.get("file"):
            path = os.path.join(MUSIC_DIR, track["file"])
            if os.path.exists(path):
                return path
        return None

    def is_downloaded(self, track_id):
        return self.local_path(track_id) is not None

    def set_downloaded(self, track, filename):
        with self._tx():
            stored = self.remember(track)
            stored["file"] = filename
            stored["downloaded_at"] = time.time()
            self._write_track(stored)
        self._notify()

    def replace_file(self, track_id, filename):
        """İndirilen dosyanın yerine yenisi geldi (ör. MP3 → Opus); indirme tarihi aynı kalır."""
        with self._tx():
            track = self.data["tracks"][track_id]
            track["file"] = filename
            self._write_track(track)
        self._notify()

    def forget_files(self, track_ids):
        """Dosyaları silinmiş indirmeleri kitaplıkta "indirilmemiş" yap (şarkılar albümlerde kalır)."""
        with self._tx():
            for track_id in track_ids:
                track = self.data["tracks"].get(track_id)
                if track:
                    track["file"] = None
                    self._write_track(track)
            self._prune()
        self._notify()

    def remove_download(self, track_id):
        path = self.local_path(track_id)
        with self._tx():
            track = self.get(track_id)
            if track:
                track["file"] = None
                self._write_track(track)
            self._prune()
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
        self._notify()

    def files_by_name(self):
        return {t["file"]: dict(t) for t in self.data["tracks"].values() if t.get("file")}

    def restore_downloads(self, entries):
        """Müzik klasöründe olup kitaplıkta görünmeyen dosyaları (etiketlerinden) geri ekle."""
        known = {t.get("file") for t in self.data["tracks"].values() if t.get("file")}
        added = 0
        with self._tx():
            for filename, meta in entries:
                if filename in known:
                    continue
                stored = self.remember(meta)
                stored["file"] = filename
                stored["downloaded_at"] = os.path.getmtime(os.path.join(MUSIC_DIR, filename))
                self._write_track(stored)
                added += 1
        if added:
            self._notify()
        return added

    def video_path(self, track_id):
        track = self.get(track_id)
        if track and track.get("video_file"):
            path = os.path.join(VIDEO_DIR, track["video_file"])
            if os.path.exists(path):
                return path
        return None

    def set_video(self, track, filename):
        with self._tx():
            stored = self.remember(track)
            stored["video_file"] = filename
            stored.setdefault("downloaded_at", time.time())
            self._write_track(stored)
        self._notify()

    def remove_video(self, track_id):
        path = self.video_path(track_id)
        with self._tx():
            track = self.get(track_id)
            if track:
                track["video_file"] = None
                self._write_track(track)
            self._prune()
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
        self._notify()

    def downloaded_tracks(self):
        items = [t for t in self.data["tracks"].values() if t.get("file")]
        return sorted(items, key=lambda t: t.get("downloaded_at") or 0, reverse=True)

    # ---------- favoriler ----------

    def is_favorite(self, track_id):
        return track_id in self.data["favorites"]

    def toggle_favorite(self, track):
        favorites = self.data["favorites"]
        with self._tx():
            if track["id"] in favorites:
                favorites.remove(track["id"])
                added = False
            else:
                self.remember(track)
                favorites.insert(0, track["id"])
                added = True
            self._write_list("favorites", favorites)
            self._prune()
        self._notify()
        return added

    @staticmethod
    def _move(ids, track_id, target_id, after):
        if track_id == target_id or track_id not in ids or target_id not in ids:
            return False
        ids.remove(track_id)
        ids.insert(ids.index(target_id) + (1 if after else 0), track_id)
        return True

    def reorder_favorites(self, track_id, target_id, after):
        if self._move(self.data["favorites"], track_id, target_id, after):
            with self._tx():
                self._write_list("favorites", self.data["favorites"])
            self._notify()

    def favorite_tracks(self):
        tracks = self.data["tracks"]
        return [tracks[i] for i in self.data["favorites"] if i in tracks]

    # ---------- albümler ----------

    def album(self, album_id):
        return self.data["albums"].get(album_id)

    def albums(self, folder_id=None):
        items = [(aid, a) for aid, a in self.data["albums"].items() if a.get("folder") == folder_id]
        return sorted(items, key=lambda item: item[1]["created"])

    def all_albums(self):
        return sorted(self.data["albums"].items(), key=lambda item: item[1]["name"].lower())

    def _save_album(self, album_id):
        album = self.data["albums"][album_id]
        self.db.execute("INSERT OR REPLACE INTO albums VALUES (?,?,?,?,?)",
                        (album_id, album["name"], album.get("folder"), album["created"], album.get("source")))

    def create_album(self, name, folder_id=None, source=None, tracks=()):
        album_id = uuid.uuid4().hex[:10]
        album = {"name": name, "folder": folder_id, "tracks": [], "created": time.time(),
                 "source": source}  # source: YouTube'dan kaydedilen albümün liste kimliği
        with self._tx():
            self.data["albums"][album_id] = album
            for track in tracks:
                self.remember(track)
                if track["id"] not in album["tracks"]:
                    album["tracks"].append(track["id"])
            self._save_album(album_id)
            self._write_album_tracks(album_id, album["tracks"])
        self._notify()
        return album_id

    def album_by_source(self, source):
        for album_id, album in self.data["albums"].items():
            if album.get("source") == source:
                return album_id
        return None

    def add_tracks_to_album(self, album_id, tracks):
        album = self.data["albums"][album_id]
        added = 0
        with self._tx():
            for track in tracks:
                if track["id"] not in album["tracks"]:
                    self.remember(track)
                    album["tracks"].append(track["id"])
                    added += 1
            if added:
                self._write_album_tracks(album_id, album["tracks"])
        if added:
            self._notify()
        return added

    def rename_album(self, album_id, name):
        with self._tx():
            self.data["albums"][album_id]["name"] = name
            self._save_album(album_id)
        self._notify()

    def delete_album(self, album_id):
        with self._tx():
            self.data["albums"].pop(album_id, None)
            self.db.execute("DELETE FROM albums WHERE id=?", (album_id,))
            self.db.execute("DELETE FROM album_tracks WHERE album_id=?", (album_id,))
            self._prune()
        self._notify()

    def move_album(self, album_id, folder_id):
        with self._tx():
            self.data["albums"][album_id]["folder"] = folder_id
            self._save_album(album_id)
        self._notify()

    def add_to_album(self, album_id, track):
        album = self.data["albums"][album_id]
        if track["id"] in album["tracks"]:
            return False
        with self._tx():
            self.remember(track)
            album["tracks"].append(track["id"])
            self._write_album_tracks(album_id, album["tracks"])
        self._notify()
        return True

    def remove_from_album(self, album_id, track_id):
        album = self.data["albums"][album_id]
        if track_id in album["tracks"]:
            with self._tx():
                album["tracks"].remove(track_id)
                self._write_album_tracks(album_id, album["tracks"])
                self._prune()
            self._notify()

    def reorder_album(self, album_id, track_id, target_id, after):
        if self._move(self.data["albums"][album_id]["tracks"], track_id, target_id, after):
            with self._tx():
                self._write_album_tracks(album_id, self.data["albums"][album_id]["tracks"])
            self._notify()

    def album_tracks(self, album_id):
        tracks = self.data["tracks"]
        return [tracks[i] for i in self.data["albums"][album_id]["tracks"] if i in tracks]

    # ---------- klasörler ----------

    def folder(self, folder_id):
        return self.data["folders"].get(folder_id)

    def folders(self):
        return sorted(self.data["folders"].items(), key=lambda item: item[1]["created"])

    def create_folder(self, name):
        folder_id = uuid.uuid4().hex[:10]
        with self._tx():
            self.data["folders"][folder_id] = {"name": name, "created": time.time()}
            self.db.execute("INSERT INTO folders VALUES (?,?,?)", (folder_id, name, self.data["folders"][folder_id]["created"]))
        self._notify()
        return folder_id

    def rename_folder(self, folder_id, name):
        with self._tx():
            self.data["folders"][folder_id]["name"] = name
            self.db.execute("UPDATE folders SET name=? WHERE id=?", (name, folder_id))
        self._notify()

    def delete_folder(self, folder_id):
        # İçindeki albümler silinmez, kitaplığın köküne taşınır
        with self._tx():
            self.data["folders"].pop(folder_id, None)
            self.db.execute("DELETE FROM folders WHERE id=?", (folder_id,))
            for album_id, album in self.data["albums"].items():
                if album.get("folder") == folder_id:
                    album["folder"] = None
                    self._save_album(album_id)
        self._notify()

    # ---------- geri alma ----------

    def checkpoint(self, label):
        """Bir değişiklikten hemen önce çağrılır: favoriler, albümler ve klasörlerin o anki hâlini saklar."""
        with self._lock:
            used = set(self.data["favorites"])
            for album in self.data["albums"].values():
                used.update(album["tracks"])
            tracks = self.data["tracks"]
            self._undo.append({
                "label": label,
                "favorites": list(self.data["favorites"]),
                "albums": copy.deepcopy(self.data["albums"]),
                "folders": copy.deepcopy(self.data["folders"]),
                "tracks": {i: dict(tracks[i]) for i in used if i in tracks},
            })
            del self._undo[:-30]

    def drop_checkpoint(self):
        with self._lock:
            if self._undo:
                self._undo.pop()

    @property
    def undo_label(self):
        return self._undo[-1]["label"] if self._undo else None

    def undo(self):
        with self._lock:
            if not self._undo:
                return None
            snap = self._undo.pop()
            with self._tx():
                for track in snap["tracks"].values():
                    self.remember(track)
                self.data["favorites"] = snap["favorites"]
                self.data["albums"] = snap["albums"]
                self.data["folders"] = snap["folders"]
                self._write_list("favorites", snap["favorites"])
                self.db.execute("DELETE FROM albums")
                self.db.execute("DELETE FROM album_tracks")
                self.db.execute("DELETE FROM folders")
                for album_id, album in snap["albums"].items():
                    self._save_album(album_id)
                    self._write_album_tracks(album_id, album["tracks"])
                for folder_id, folder in snap["folders"].items():
                    self.db.execute("INSERT INTO folders VALUES (?,?,?)", (folder_id, folder["name"], folder["created"]))
                self._prune()
        self._notify()
        return snap["label"]

    # ---------- içe aktarma (YouTube Music / Spotify) ----------

    @staticmethod
    def song_key(track):
        """Aynı şarkının farklı yüklemelerini yakalamak için: sade başlık + ilk sanatçı."""
        title = re.sub(r"\(.*?\)|\[.*?\]", "", (track.get("title") or "").casefold())
        artist = (track.get("artist") or "").split(",")[0].casefold()
        return re.sub(r"\W", "", title) + "|" + re.sub(r"\W", "", artist)

    def _fresh(self, ids, tracks):
        """ids listesinde olmayan (ne aynı kimlikle ne de aynı ad/sanatçıyla) şarkılar."""
        have = set(ids)
        known = [self.data["tracks"][i] for i in ids if i in self.data["tracks"]]
        keys = {self.song_key(t) for t in known}
        # YouTube videosu olarak kaydedilmiş kopyalar: "Sanatçı - Şarkı (Official Video)" gibi başlıklar
        hay = [re.sub(r"\W", "", (t.get("title", "") + " " + (t.get("artist") or "")).casefold()) for t in known]
        out = []
        for track in tracks:
            key = self.song_key(track)
            title, artist = key.split("|")
            if track["id"] in have or key in keys or (
                    len(title) >= 3 and artist and any(title in h and artist in h for h in hay)):
                continue
            have.add(track["id"])
            keys.add(key)
            hay.append(title + artist)
            out.append(track)
        return out

    def import_collection(self, liked, playlists):
        """Beğenilenleri favorilere, listeleri albümlere ekler; zaten olanları atlar.
        playlists: [(kaynak, ad, şarkılar)] — aynı kaynaktan ya da aynı adla bir albüm varsa onun içine eklenir."""
        stats = {"liked": 0, "liked_skipped": 0, "albums_new": 0, "albums_merged": 0, "tracks": 0, "skipped": 0}
        with self._tx():
            new = self._fresh(self.data["favorites"], liked)
            stats["liked_skipped"] = len(liked) - len(new)
            for track in new:
                self.remember(track)
                self.data["favorites"].append(track["id"])
            stats["liked"] = len(new)
            if new:
                self._write_list("favorites", self.data["favorites"])
            for source, name, tracks in playlists:
                if not tracks:
                    continue
                album_id = self.album_by_source(source) or next(
                    (aid for aid, a in self.data["albums"].items() if a["name"].casefold() == name.casefold()), None)
                if album_id:
                    stats["albums_merged"] += 1
                else:
                    album_id = uuid.uuid4().hex[:10]
                    self.data["albums"][album_id] = {"name": name, "folder": None, "tracks": [],
                                                     "created": time.time(), "source": source}
                    self._save_album(album_id)
                    stats["albums_new"] += 1
                album = self.data["albums"][album_id]
                fresh = self._fresh(album["tracks"], tracks)
                stats["skipped"] += len(tracks) - len(fresh)
                for track in fresh:
                    self.remember(track)
                    album["tracks"].append(track["id"])
                stats["tracks"] += len(fresh)
                self._write_album_tracks(album_id, album["tracks"])
        self._notify()
        return stats

    # ---------- dinleme geçmişi ----------

    def add_history(self, track):
        history = self.data["history"]
        with self._tx():
            self.remember(track)
            plays = 1
            for entry in history:
                if entry["id"] == track["id"]:
                    plays = entry.get("plays", 1) + 1
                    history.remove(entry)
                    break
            history.insert(0, {"id": track["id"], "at": time.time(), "plays": plays})
            del history[100:]
            self._write_history(history)

    def recent_tracks(self, limit=20):
        tracks = self.data["tracks"]
        return [tracks[e["id"]] for e in self.data["history"][:limit] if e["id"] in tracks]

    def history_ids(self):
        return {entry["id"] for entry in self.data["history"]}

    def top_artists(self, limit=8):
        """En çok dinlenen sanatçılar: [(sanatçı, en çok dinlenen şarkısı), ...]"""
        tracks = self.data["tracks"]
        totals, best = {}, {}
        for entry in self.data["history"]:
            track = tracks.get(entry["id"])
            if not track or track["artist"] == "Bilinmeyen sanatçı":
                continue
            artist = track["artist"]
            plays = entry.get("plays", 1)
            totals[artist] = totals.get(artist, 0) + plays
            if artist not in best or plays > best[artist][0]:
                best[artist] = (plays, track)
        ranked = sorted(totals, key=totals.get, reverse=True)[:limit]
        return [(artist, best[artist][1]) for artist in ranked]

    @property
    def home_cache(self):
        return self.data.get("home_cache")

    def set_home_cache(self, sections, cold):
        self._set("home_cache", {"at": time.time(), "cold": cold, "sections": sections})

    # ---------- şarkı sözleri ----------

    def lyrics(self, track_id):
        row = self.db.execute("SELECT data FROM lyrics WHERE track_id=?", (track_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_lyrics(self, track_id, data):
        with self._lock:
            self.db.execute("INSERT OR REPLACE INTO lyrics VALUES (?,?,?)",
                            (track_id, json.dumps(data, ensure_ascii=False), time.time()))

    # ---------- diğer ----------

    def _set(self, key, value):
        with self._lock:
            self.data[key] = value
            self._write_kv(key, value)

    @property
    def recent_searches(self):
        return self.data["recent_searches"]

    def add_recent_search(self, query):
        recent = [q for q in self.data["recent_searches"] if q.lower() != query.lower()]
        self._set("recent_searches", [query] + recent[:7])

    def remove_recent_search(self, query):
        self._set("recent_searches", [q for q in self.data["recent_searches"] if q != query])

    def clear_recent_searches(self):
        self._set("recent_searches", [])

    def set_youtube_auth(self, settings):
        self._set("youtube_auth", settings)

    @property
    def settings(self):
        return self.data["settings"]

    def update_settings(self, changes):
        self._set("settings", {**self.data["settings"], **changes})
        return self.data["settings"]

    @property
    def volume(self):
        return self.data.get("volume", 0.7)

    @volume.setter
    def volume(self, value):
        self._set("volume", value)
