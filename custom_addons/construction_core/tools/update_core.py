"""Обновления программы через интернет (GitHub Releases) или из файла.

Пакет обновления StroyERP-update-<версия>.zip:
    update.json   {"version", "sha256" (payload.zip), "sig", "notes", "date"}
    payload.zip   папка addons (модули Actually_team)
Подпись sig = Ed25519("<version>|<sha256>") тем же ключом, что и лицензии.
Установку делает tools\\update.ps1 (задача Windows «StroyERP-update»).
"""
import base64
import hashlib
import json
import os
import subprocess
import zipfile

from .license_pubkey import PUBLIC_KEY
from .update_config import UPDATE_URL

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_root():
    """C:\\StroyERP для установленной программы, иначе None (режим разработки)."""
    root = os.path.dirname(os.path.dirname(MODULE_DIR))
    return root if os.path.isfile(os.path.join(root, "VERSION")) else None


def current_version():
    root = app_root()
    if not root:
        return None
    with open(os.path.join(root, "VERSION"), encoding="utf-8-sig") as f:
        return f.read().strip()


def vtuple(v):
    out = []
    for part in (v or "0").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out + [0] * (4 - len(out)))


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_package(path):
    """-> update.json (dict) или ValueError."""
    if not PUBLIC_KEY:
        raise ValueError("В программе не задан ключ проверки.")
    try:
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read("update.json"))
            payload = z.read("payload.zip")
    except Exception:
        raise ValueError("Файл не является пакетом обновления «Строительной ERP».")
    sha = hashlib.sha256(payload).hexdigest()
    if sha != meta.get("sha256"):
        raise ValueError("Пакет повреждён (контрольная сумма не совпадает).")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(_b64d(PUBLIC_KEY)).verify(
            _b64d(meta["sig"]), ("%s|%s" % (meta["version"], sha)).encode())
    except Exception:
        raise ValueError("Подпись пакета не совпадает — это не официальное обновление.")
    return meta


def fetch_latest(timeout=15):
    if not UPDATE_URL:
        raise ValueError("Адрес обновлений не настроен.")
    import requests
    r = requests.get(UPDATE_URL, timeout=timeout)
    r.raise_for_status()
    return r.json()


def download(url, version):
    import requests
    folder = os.path.join(app_root(), "updates")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "StroyERP-update-%s.zip" % version)
    tmp = path + ".part"
    with requests.get(url, timeout=60, stream=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    os.replace(tmp, path)
    return path


def start_install(package):
    """Передать пакет задаче Windows «StroyERP-update» (работает от SYSTEM)."""
    folder = os.path.join(app_root(), "updates")
    with open(os.path.join(folder, "request.json"), "w", encoding="utf-8") as f:
        json.dump({"package": package}, f)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    res = subprocess.run(["schtasks", "/Run", "/TN", "StroyERP-update"],
                         capture_output=True, creationflags=flags)
    if res.returncode != 0:
        raise ValueError("Не удалось запустить установку (задача StroyERP-update). "
                         "Переустановите программу последней версией exe.")


def last_status():
    root = app_root()
    path = root and os.path.join(root, "updates", "status.json")
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}
