"""Derlenmiş yayın APK'sını GitHub'a koyar ve sürüm dosyasını yazar. Kullanım: python publish.py "not 1" "not 2"

APK, main'den bağımsız bir etikette durur: dallara girmediği için masaüstü kullanıcılarının `git fetch`'i onu indirmez.
Telefonlar yeni sürümü ancak update/android.json commit edilip mobile dalına gönderilince görür; o adım bilerek elle.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

REMOTE = "https://github.com/Sefikak/SOUND.git"
OUTPUT = os.path.join(os.environ["LOCALAPPDATA"], "SOUNDbuild", "app", "outputs", "apk", "release")
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "update", "android.json")
GITHUB_LIMIT = 100 * 1024 * 1024


def main(notes):
    # sürüm APK'nın yanındaki kayıttan okunur: gradle dosyasıyla eski bir APK yanlış numarayla yayınlanamasın
    with open(os.path.join(OUTPUT, "output-metadata.json"), encoding="utf-8") as file:
        element = json.load(file)["elements"][0]
    code, name = element["versionCode"], element["versionName"]
    apk = os.path.join(OUTPUT, element["outputFile"])
    with open(MANIFEST, encoding="utf-8") as file:
        published = json.load(file)["versionCode"] if os.path.getsize(MANIFEST) else 0
    if code <= published:
        sys.exit(f"versionCode {code}, yayındaki {published} sayısından büyük olmalı")
    if os.path.getsize(apk) >= GITHUB_LIMIT:
        sys.exit("APK GitHub'ın 100 MB dosya sınırını aşıyor")
    with open(apk, "rb") as file:
        sha = hashlib.sha256(file.read()).hexdigest()

    tag, filename = f"android-{name}", f"SOUND-android-{name}.apk"
    with tempfile.TemporaryDirectory() as bare:  # büyük dosya kalıcı depolara (OneDrive) girmesin
        def git(*args, **kwargs):
            return subprocess.run(["git", "-C", bare, *args], check=True, capture_output=True, text=True, **kwargs).stdout.strip()
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        blob = git("hash-object", "-w", apk)
        tree = git("mktree", input=f"100644 blob {blob}\t{filename}\n")
        commit = git("-c", "user.name=Sefikak", "-c", "user.email=aksefik55@gmail.com", "commit-tree", tree, "-m", f"SOUND Android {name}")
        git("tag", tag, commit)
        git("push", "-q", REMOTE, f"refs/tags/{tag}")

    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as file:
        json.dump({"versionCode": code, "versionName": name, "sha256": sha,
                   "url": f"https://github.com/Sefikak/SOUND/raw/{tag}/{filename}", "notes": notes},
                  file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"{tag} yayında. Telefonlara açmak için update/android.json dosyasını commit edip mobile dalına gönder.")


if __name__ == "__main__":
    main(sys.argv[1:])
