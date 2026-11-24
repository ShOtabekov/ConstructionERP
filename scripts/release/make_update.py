"""Выпуск обновления «Строительной ERP» (только для разработчика).

    python make_update.py init <владелец>/<репозиторий>   — один раз: куда выкладывать
    python make_update.py                                 — собрать обновление версии из installer\\VERSION

Результат в папке dist\\: StroyERP-update-<версия>.zip и latest.json.
Подпись — секретным ключом лицензий (%USERPROFILE%\\StroyERP-keys\\private_key.txt).
"""
import base64
import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADDONS = os.path.join(ROOT, "custom_addons")
VERSION_FILE = os.path.join(ROOT, "installer", "VERSION")
CONFIG = os.path.join(ADDONS, "construction_core", "tools", "update_config.py")
PRIVATE = os.path.join(os.path.expanduser("~"), "StroyERP-keys", "private_key.txt")
DIST = os.path.join(ROOT, "dist")


def b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def read_config():
    ns = {}
    with open(CONFIG, encoding="utf-8") as f:
        exec(f.read(), ns)
    return ns.get("UPDATE_REPO", "")


def init(repo):
    repo = repo.strip().strip("/")
    if repo.count("/") != 1:
        sys.exit("Укажите так: владелец/репозиторий, например actually-team/stroyerp-updates")
    with open(CONFIG, "w", encoding="utf-8") as f:
        f.write("# Адрес описания последней версии (GitHub Releases). Создан make_update.py init.\n"
                'UPDATE_REPO = "%s"\n'
                'UPDATE_URL = "https://github.com/%s/releases/latest/download/latest.json"\n' % (repo, repo))
    print("Записано в", CONFIG)
    print("Дальше: git commit, обновить модуль, собрать exe — у клиентов появится проверка обновлений.")


def payload_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk(ADDONS):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for name in files:
                if name.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(folder, name)
                rel = os.path.relpath(full, ADDONS)
                z.write(full, os.path.join("addons", rel))
    return buf.getvalue()


def build():
    repo = read_config()
    if not repo:
        sys.exit("Сначала: release.bat init <владелец>/<репозиторий>")
    if not os.path.exists(PRIVATE):
        sys.exit("Нет секретного ключа: " + PRIVATE)
    with open(PRIVATE) as f:
        sk = Ed25519PrivateKey.from_private_bytes(b64d(f.read().strip()))
    with open(VERSION_FILE, encoding="utf-8-sig") as f:
        version = f.read().strip()
    print("Версия:", version, "(installer\\VERSION — увеличьте перед выпуском)")
    notes = ask("Что нового (одной строкой, можно пусто): ")
    payload = payload_zip()
    sha = hashlib.sha256(payload).hexdigest()
    date = datetime.date.today().strftime("%d.%m.%Y")
    meta = {"version": version, "sha256": sha, "notes": notes, "date": date,
            "sig": b64e(sk.sign(("%s|%s" % (version, sha)).encode()))}
    os.makedirs(DIST, exist_ok=True)
    name = "StroyERP-update-%s.zip" % version
    pkg = os.path.join(DIST, name)
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_STORED) as z:
        z.writestr("update.json", json.dumps(meta, ensure_ascii=False, indent=1))
        z.writestr("payload.zip", payload)
    latest = {"version": version, "date": date, "notes": notes,
              "url": "https://github.com/%s/releases/download/v%s/%s" % (repo, version, name)}
    with open(os.path.join(DIST, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=1)
    print("\nГотово:", pkg, "(%.1f МБ)" % (os.path.getsize(pkg) / 1e6))
    print("        ", os.path.join(DIST, "latest.json"))
    cmd = ["gh", "release", "create", "v" + version, pkg, os.path.join(DIST, "latest.json"),
           "--repo", repo, "--title", "Строительная ERP " + version, "--notes", notes or version]
    if shutil.which("gh") and ask("\nОпубликовать на GitHub сейчас? (y/n): ").lower() == "y":
        subprocess.run(cmd, check=False)
    else:
        print("\nОпубликуйте на GitHub: Releases -> Draft a new release, тег v%s," % version)
        print("приложите оба файла из dist и нажмите Publish. Или командой:")
        print(" ".join('"%s"' % c if " " in c else c for c in cmd))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "init":
        init(sys.argv[2])
    else:
        build()
