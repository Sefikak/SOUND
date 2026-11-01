"""SOUND'un kendini GitHub'dan güncellemesi.

Uygulama klasörü bir git deposu ve GitHub'daki depoya bağlıysa: arka planda `git fetch` ile yeni
commit var mı bakılır, varsa `git pull --ff-only` ile indirilir. requirements.txt değiştiyse yeni
paketler de kurulur. Yeni kod bir sonraki açılışta (ya da "Yeniden başlat" ile hemen) etkin olur.

Güvenlik kuralları:
  - Yalnızca ileri sarma (fast-forward): yereldeki commit'ler asla silinmez / birleştirilmez.
  - Takip edilen dosyalarda kaydedilmemiş değişiklik varsa dokunulmaz (geliştirirken kod ezilmesin).
  - data/ .gitignore'da: kitaplık, çerezler, müzikler güncellemeden etkilenmez.
"""
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _git(*args, timeout=60):
    result = subprocess.run(["git", "-C", BASE_DIR, *args], capture_output=True, text=True, encoding="utf-8",
                            errors="replace", creationflags=NO_WINDOW, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"git {args[0]} başarısız")
    return result.stdout.strip()


def available():
    """Klasör bir git deposu, git kurulu ve bir uzak dal izleniyor mu."""
    if not shutil.which("git") or not os.path.isdir(os.path.join(BASE_DIR, ".git")):
        return False
    try:
        _git("rev-parse", "--abbrev-ref", "@{u}", timeout=15)
        return True
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return False


def current_version():
    """Kurulu sürüm: kısa commit kimliği ve tarihi (ör. 'a1b2c3d · 01.11.2026')."""
    try:
        return _git("log", "-1", "--format=%h · %cd", "--date=format:%d.%m.%Y", timeout=15)
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None


def check_and_update():
    """Yeni sürüm varsa indirir.

    Döner: {"status": "unavailable" | "uptodate" | "updated" | "dirty" | "diverged" | "error", ...}
    "updated" ise "from", "to", "notes" (commit başlıkları) ve "packages" (paketler kuruldu mu) da gelir."""
    if not available():
        return {"status": "unavailable"}
    try:
        _git("fetch", "--quiet", timeout=90)
        behind = int(_git("rev-list", "--count", "HEAD..@{u}") or 0)
        if not behind:
            return {"status": "uptodate"}
        ahead = int(_git("rev-list", "--count", "@{u}..HEAD") or 0)
        if ahead:
            return {"status": "diverged"}  # yerelde gönderilmemiş commit var: elle birleştirilmeli
        if _git("status", "--porcelain", "--untracked-files=no"):
            return {"status": "dirty"}  # kaydedilmemiş yerel değişiklik var
        old = _git("rev-parse", "--short", "HEAD")
        notes = _git("log", "--format=%s", "HEAD..@{u}").splitlines()
        changed = _git("diff", "--name-only", "HEAD", "@{u}").splitlines()
        _git("pull", "--ff-only", "--quiet", timeout=120)
        packages = None
        if "requirements.txt" in changed:
            result = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                                     "-r", os.path.join(BASE_DIR, "requirements.txt")],
                                    capture_output=True, creationflags=NO_WINDOW, timeout=900)
            packages = result.returncode == 0
        return {"status": "updated", "from": old, "to": _git("rev-parse", "--short", "HEAD"),
                "notes": notes[:8], "count": behind, "packages": packages}
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        return {"status": "error", "message": str(error)[:300]}


def restart():
    """Uygulamayı yeniden başlatır (yeni süreç açılır; çağıran süreç kendini kapatmalı)."""
    # Yeni süreç, eskisi kapanıp tarayıcı verilerini (data/webview) bırakana kadar biraz bekler
    vbs = os.path.join(BASE_DIR, "run.vbs")
    if os.name == "nt" and os.path.exists(vbs):
        launch = f"subprocess.Popen(['wscript.exe', {vbs!r}], cwd={BASE_DIR!r})"
    else:
        launch = f"subprocess.Popen([{sys.executable!r}, {os.path.join(BASE_DIR, 'main.py')!r}], cwd={BASE_DIR!r})"
    subprocess.Popen([sys.executable, "-c", f"import subprocess, time; time.sleep(2.5); {launch}"],
                     cwd=BASE_DIR, creationflags=NO_WINDOW | 0x00000008)  # DETACHED_PROCESS
