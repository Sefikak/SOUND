"""yt-dlp'yi APK'dan bağımsız güncel tutar: YouTube değişince yeni uygulama sürümü beklenmez.

Yeni sürüm PyPI'dan iner, SHA-256 denetlenir, veri klasörüne açılır ve bir sonraki açılışta APK'daki sürümün önüne geçer.
Yeni sürüm önce aday sayılır. Açılışta yüklenemezse, uygulamayı düşürürse ya da gerçek bir videoyu çözemezse
bir daha kullanılmaz ve son sağlam sürüme (o da yoksa APK'daki sürüme) dönülür.

Yalnızca yt-dlp güncellenir: yt-dlp-ejs JavaScript çalışma ortamı ister, telefonda o yok. Paket saf Python'dur,
bağımlılığı yoktur. Python 3.11'i bırakan sürümler indirilmez, son uyumlu sürümde kalınır.
"""
import compileall
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
FILES_PREFIX = "https://files.pythonhosted.org/"
EVERY = 24 * 3600
MAX_TRIES = 2  # aday bu kadar açılışta yüklenmeyi bitiremediyse uygulamayı düşürüyor demektir
MAX_FAILS = 2  # tek seferlik YouTube hatası sürümü yakmasın
HEALTH_VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

_root = None
_running = None  # etkin indirilmiş sürüm; None ise APK'daki çalışıyor


def _key(version):
    return tuple(int(part) for part in re.findall(r"\d+", version or ""))


def _path(version):
    return os.path.join(_root, version)


def _load():
    try:
        with open(os.path.join(_root, "state.json"), encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return {}


def _save(state):
    os.makedirs(_root, exist_ok=True)
    path = os.path.join(_root, "state.json")
    with open(path + ".tmp", "w", encoding="utf-8") as file:
        json.dump(state, file)
    os.replace(path + ".tmp", path)


def _bundled_version():
    try:
        from importlib.metadata import version
        return version("yt-dlp")
    except Exception:
        return None


def _forget_import(folder):
    if folder in sys.path:
        sys.path.remove(folder)
    for name in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
        del sys.modules[name]


def _mark_bad(state, version):
    state["bad"] = sorted(set(state.get("bad") or []) | {version})
    if state.get("candidate") == version:
        state.update(candidate=None, tries=0, fails=0)
    if state.get("good") == version:
        state["good"] = None


def activate(data_dir):
    """yt_dlp ilk kez içe aktarılmadan önce çağrılır. Hangi sürüm olursa olsun yt_dlp yüklenmiş olarak döner."""
    global _root, _running
    _root = os.path.join(data_dir, "ytdlp")
    state = _load()
    bundled = _key(_bundled_version())

    candidate = state.get("candidate")
    if candidate and state.get("tries", 0) >= MAX_TRIES:
        _mark_bad(state, candidate)  # önceki açılışlar yt_dlp yüklenirken yarıda kaldı
        _save(state)
        candidate = None

    for version in (candidate, state.get("good")):
        if not version or not os.path.isdir(_path(version)) or (bundled and _key(version) <= bundled):
            continue  # uygulama güncellenince APK'daki sürüm daha yeni olabilir
        if version == candidate:
            state["tries"] = state.get("tries", 0) + 1
            _save(state)  # yükleme süreci öldürürse bir sonraki açılış bunu buradan anlar
        folder = _path(version)
        sys.path.insert(0, folder)
        try:
            import yt_dlp  # noqa: F401
            from yt_dlp.version import __version__
            if __version__ != version:
                raise ImportError(f"Beklenen {version}, yüklenen {__version__}")
        except (Exception, SystemExit):
            _forget_import(folder)
            _mark_bad(state, version)
            _save(state)
            continue
        if version == candidate:
            state["tries"] = 0
            _save(state)
        _running = version
        break
    import yt_dlp  # noqa: F401, F811  (hiçbiri olmadıysa APK'daki)
    if os.path.isdir(_root):
        _cleanup(state)  # bırakılan sürümler ve yarım kalmış indirmeler yer kaplamasın


def running_version():
    from yt_dlp.version import __version__
    return __version__


def verify():
    """Aday gerçekten çalışıyor mu? Açılıştan sonra arka planda bir kez gerçek bir videoyu çözer.
    İnternet yoksa ya da YouTube robot denetimi yapıyorsa sürüm suçlanmaz, sonraki açılışta yeniden denenir."""
    state = _load()
    if not _running or state.get("candidate") != _running:
        return None
    import urllib.request
    import yt_dlp
    try:
        urllib.request.urlopen("https://www.youtube.com/generate_204", timeout=15).close()
    except Exception:
        return None
    error = None
    for client in ({"extractor_args": {"youtube": {"player_client": ["visionos"]}}}, {}):
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                                   "format": "bestaudio/best", **client}) as ydl:
                if ydl.extract_info(HEALTH_VIDEO, download=False).get("url"):
                    state.update(good=_running, candidate=None, tries=0, fails=0)
                    _save(state)
                    _cleanup(state)
                    return True
        except Exception as failure:
            error = failure
    if "not a bot" in str(error):
        return None
    state["fails"] = state.get("fails", 0) + 1
    if state["fails"] >= MAX_FAILS:
        _mark_bad(state, _running)  # bir sonraki açılışta son sağlam sürüme dönülür
    _save(state)
    return False


def due():
    if not _root:
        return False
    return time.time() - _load().get("checked", 0) > EVERY


def _python_ok(spec):
    for part in filter(None, (p.strip() for p in (spec or "").split(","))):
        match = re.fullmatch(r">=\s*(\d+)\.(\d+)(?:\.\d+)?", part)
        if not match or (int(match[1]), int(match[2])) > sys.version_info[:2]:
            return False  # bilinmeyen koşul: emin olmadan kurma
    return True


def _pick(releases, bad):
    """En yeni uyumlu sürümün tekerlek (wheel) dosyası: (sürüm, dosya bilgisi) ya da None"""
    for version in sorted(releases, key=_key, reverse=True):
        if version in bad or re.search(r"[a-z]", version.replace("post", "").replace(".dev", "a")):
            continue  # ön sürümler ve daha önce sorun çıkaranlar
        for item in releases[version]:
            if (item.get("filename", "").endswith("-py3-none-any.whl") and not item.get("yanked")
                    and _python_ok(item.get("requires_python"))):
                return version, item
    return None


def _compile(folder):
    """Önceden derlenir ki ilk açılış binlerce dosyayla uzamasın. Derlenen kaynak silinir: telefonda yer kaplamasın."""
    compileall.compile_dir(folder, quiet=2, legacy=True)
    for parent, _, names in os.walk(folder):
        for name in names:
            if name.endswith(".py") and os.path.exists(os.path.join(parent, name + "c")):
                os.remove(os.path.join(parent, name))


def _install(requests, version, item):
    """Yarım ya da bozuk dosya asla etkin olmasın: geçici klasöre açılır, doğrulanınca adı değişir."""
    url = item["url"]
    if not url.startswith(FILES_PREFIX):
        raise ValueError("Paket adresi PyPI dışında")
    os.makedirs(_root, exist_ok=True)
    wheel, temp = os.path.join(_root, "download.whl"), _path(version) + ".tmp"
    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=30) as response:
        response.raise_for_status()
        with open(wheel, "wb") as file:
            for block in response.iter_content(1 << 16):
                digest.update(block)
                file.write(block)
    try:
        if digest.hexdigest() != item["digests"]["sha256"].lower():
            raise ValueError("İndirilen paket doğrulanamadı")
        shutil.rmtree(temp, ignore_errors=True)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(temp, [n for n in archive.namelist() if n.startswith("yt_dlp/")])
        if not os.path.exists(os.path.join(temp, "yt_dlp", "__init__.py")):
            raise ValueError("Pakette yt_dlp yok")
        _compile(temp)
        shutil.rmtree(_path(version), ignore_errors=True)
        os.replace(temp, _path(version))
    finally:
        shutil.rmtree(temp, ignore_errors=True)
        if os.path.exists(wheel):
            os.remove(wheel)


def _cleanup(state):
    keep = {state.get("good"), state.get("candidate"), _running, "state.json"}
    for name in os.listdir(_root):
        if name not in keep:
            path = os.path.join(_root, name)
            shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)


def update():
    """Masaüstündeki updater.update ile aynı sözleşme: (eski_sürüm, yeni_sürüm). Değişmediyse ikisi aynıdır.
    Boyut birkaç MB olduğundan mobil veride de iner: yt-dlp eskiyince şarkılar hiç çalmayabilir."""
    import requests
    before = running_version()
    state = _load()
    response = requests.get(PYPI_URL, timeout=30)
    response.raise_for_status()
    picked = _pick(response.json().get("releases") or {}, set(state.get("bad") or []))
    state["checked"] = time.time()
    newest = max(_key(before), _key(state.get("candidate")))
    if not picked or _key(picked[0]) <= newest:
        _save(state)
        return before, before
    version, item = picked
    _install(requests, version, item)
    state.update(candidate=version, tries=0, fails=0)
    _save(state)
    _cleanup(state)
    return before, version
