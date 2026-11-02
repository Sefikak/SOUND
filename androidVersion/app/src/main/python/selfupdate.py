"""Android'de güncelleme: masaüstünün git'i yerine GitHub'daki sürüm dosyasına bakılır, yeni APK indirilir.

Arayüz masaüstüyle aynı sözleşmeyi kullanır ("updated" = indirildi, restart() = etkinleştir). Android bir uygulamanın
kendini onaysız kurmasına izin vermez: restart() sistemin yükleme ekranını açar, kullanıcı onaylar. Kitaplık silinmez.

Güvenlik: yalnızca kendi deposundan HTTPS ile indirilir, SHA-256 denetlenir; Android de APK'nın kurulu uygulamayla
aynı anahtarla imzalı olmasını şart koşar.
"""
import hashlib
import os
import shutil

MANIFEST_URL = "https://raw.githubusercontent.com/Sefikak/SOUND/mobile/update/android.json"
APK_PREFIX = "https://github.com/Sefikak/SOUND/raw/"

_native = None
_folder = None
_ready = None  # indirilmiş ve doğrulanmış APK'nın yolu
allow_metered = False  # mobil veride yalnızca kullanıcı "Şimdi denetle" derse indirilir


def init(native, folder):
    global _native, _folder
    _native = native
    _folder = folder


def available():
    return _native is not None


def current_version():
    return f"Android {_native.versionName()}"


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(requests, url, path, expected):
    """Bozuk ya da yarım dosya asla kurulum yerine geçmesin: önce .part'a iner, doğrulanınca adı değişir."""
    if not url.startswith(APK_PREFIX):
        raise ValueError("Sürüm dosyasındaki adres SOUND deposunun dışında")
    shutil.rmtree(_folder, ignore_errors=True)
    os.makedirs(_folder)
    part = path + ".part"
    with requests.get(url, stream=True, timeout=30) as response:
        response.raise_for_status()
        with open(part, "wb") as file:
            for block in response.iter_content(1 << 20):
                file.write(block)
    if _sha256(part) != expected:
        os.remove(part)
        raise ValueError("İndirilen dosya doğrulanamadı, yeniden denenecek")
    os.replace(part, path)


def check_and_update():
    """Döner: {"status": "uptodate" | "waiting_wifi" | "updated" | "error", ...}"""
    global _ready
    try:
        import requests
        response = requests.get(MANIFEST_URL, timeout=20)
        response.raise_for_status()
        info = response.json()
        code = int(info["versionCode"])
        if code <= int(_native.versionCode()):
            shutil.rmtree(_folder, ignore_errors=True)  # kurulmuş güncellemenin dosyası yer kaplamasın
            return {"status": "uptodate"}
        path = os.path.join(_folder, f"SOUND-{code}.apk")
        expected = info["sha256"].lower()
        if not (os.path.exists(path) and _sha256(path) == expected):
            if _native.isMetered() and not allow_metered:
                return {"status": "waiting_wifi"}
            _download(requests, info["url"], path, expected)
        _ready = path
        return {"status": "updated", "from": _native.versionName(), "to": info["versionName"],
                "notes": list(info.get("notes") or [])[:8], "count": 1, "packages": None}
    except Exception as error:  # ağ, bozuk sürüm dosyası, disk: arka plan döngüsü ölmesin, sonra yeniden dener
        return {"status": "error", "message": str(error)[:200]}


def restart():
    if _ready:
        _native.installApk(_ready)
