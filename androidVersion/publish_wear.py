"""Saat (Wear OS) yayın APK'sını GitHub'a koyar ve update/wear.json'ı yazar. Kullanım: build_wear.bat release, sonra python publish_wear.py

APK, telefon APK'sı gibi main'den bağımsız bir etikette (wear-<sürüm>) durur. Saatler yeni sürümü update/wear.json commit edilip
mobile dalına gönderilince görür (Updater.kt 6 saatte bir bakar).
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

REMOTE = "https://github.com/Sefikak/SOUND.git"
OUTPUT = os.path.join(os.environ["LOCALAPPDATA"], "SOUNDbuild", "wear", "outputs", "apk", "release")
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "update", "wear.json")
GITHUB_LIMIT = 100 * 1024 * 1024


def main():
    with open(os.path.join(OUTPUT, "output-metadata.json"), encoding="utf-8") as file:
        element = json.load(file)["elements"][0]
    code, name = element["versionCode"], element["versionName"]
    apk = os.path.join(OUTPUT, element["outputFile"])
    published = 0
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as file:
            published = json.load(file)["versionCode"]
    if code <= published:
        sys.exit(f"versionCode {code}, yayındaki {published} sayısından büyük olmalı")
    if os.path.getsize(apk) >= GITHUB_LIMIT:
        sys.exit("APK GitHub'ın 100 MB dosya sınırını aşıyor")
    with open(apk, "rb") as file:
        sha = hashlib.sha256(file.read()).hexdigest()

    tag, filename = f"wear-{name}", f"SOUND-watch-{name}.apk"
    with tempfile.TemporaryDirectory() as bare:
        def git(*args, stdin=None):
            return subprocess.run(["git", "-C", bare, *args], check=True, capture_output=True, input=stdin).stdout.decode().strip()
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        blob = git("hash-object", "-w", apk)
        tree = git("mktree", stdin=f"100644 blob {blob}\t{filename}\n".encode())
        commit = git("-c", "user.name=Sefikak", "-c", "user.email=aksefik55@gmail.com", "commit-tree", tree, "-m", f"SOUND Galaxy Watch {name}")
        git("tag", tag, commit)
        git("push", "-q", REMOTE, f"refs/tags/{tag}")

    url = f"https://github.com/Sefikak/SOUND/raw/{tag}/{filename}"
    for _ in range(6):  # yeni etiket GitHub'da birkaç saniye 404 verebilir
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as response:
                if int(response.headers["Content-Length"]) != os.path.getsize(apk):
                    sys.exit(f"{url} APK ile aynı boyutta değil")
            break
        except Exception:
            import time
            time.sleep(5)
    else:
        sys.exit(f"{url} doğrulanamadı")
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as file:
        json.dump({"versionCode": code, "versionName": name, "sha256": sha, "url": url}, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"{tag} yayında: {url}\nSaatlere açmak için update/wear.json dosyasını commit edip mobile dalına gönder.")


if __name__ == "__main__":
    main()
