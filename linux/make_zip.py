"""SOUND-linux.zip'i üretir (depo kökünde, README'deki indirme bağlantısı). GitHub .sh dosyalarını tarayıcıda
düz metin olarak açıyor; zip doğrudan iner. Dosyalar git'teki hâliyle (LF satır sonlarıyla) ve çalıştırılabilir
izinle eklenir. Kullanım: python linux/make_zip.py  (install.sh / uninstall.sh değişince yeniden çalıştır)"""
import os
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = {"install.sh": 0o755, "uninstall.sh": 0o755, "README.md": 0o644}


def from_git(name):
    # çalışma kopyasında Windows CRLF'ye çevrilmiş olabilir; bash CRLF'li betiği çalıştıramaz
    data = subprocess.run(["git", "show", f"HEAD:linux/{name}"], cwd=ROOT, capture_output=True, check=True).stdout
    return data.replace(b"\r\n", b"\n")


with zipfile.ZipFile(os.path.join(ROOT, "SOUND-linux.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for name, mode in FILES.items():
        info = zipfile.ZipInfo(f"SOUND-linux/{name}", date_time=(2026, 1, 1, 0, 0, 0))
        info.external_attr = (0o100000 | mode) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, from_git(name))
print("SOUND-linux.zip hazır")
