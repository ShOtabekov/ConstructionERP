"""Проверка и распаковка пакета обновления (вызывается из update.ps1).
    python verify_update.py <пакет.zip> <текущая папка addons> <куда распаковать>
Печатает версию. Код возврата 0 — пакет подписан разработчиком и цел."""
import base64, hashlib, io, json, os, re, sys, zipfile


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def main(package, addons, out):
    # Ключ берём из УСТАНОВЛЕННОЙ версии, а не из пакета
    with open(os.path.join(addons, "construction_core", "tools", "license_pubkey.py"), encoding="utf-8") as f:
        pub = re.search(r'PUBLIC_KEY\s*=\s*"([^"]+)"', f.read()).group(1)
    with zipfile.ZipFile(package) as z:
        meta = json.loads(z.read("update.json"))
        payload = z.read("payload.zip")
    sha = hashlib.sha256(payload).hexdigest()
    if sha != meta["sha256"]:
        sys.exit("Пакет повреждён")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(b64d(pub)).verify(
            b64d(meta["sig"]), ("%s|%s" % (meta["version"], sha)).encode())
    except Exception:
        sys.exit("Подпись не совпадает — это не официальное обновление")
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        z.extractall(out)
    with open(os.path.join(out, "update.json"), "w", encoding="utf-8") as f:
        json.dump({k: meta.get(k) for k in ("version", "notes", "date")}, f, ensure_ascii=False)
    print(meta["version"])


if __name__ == "__main__":
    main(*sys.argv[1:4])
