"""Генератор лицензионных ключей Строительной ERP (только для разработчика).

    python keygen.py init     — один раз: создать пару ключей
    python keygen.py          — выдать ключ клиенту (спросит код, компанию, срок)

Секретный ключ: %USERPROFILE%\\StroyERP-keys\\private_key.txt
СДЕЛАЙТЕ ЕГО КОПИЮ НА ФЛЕШКУ. Потеряете — не сможете выдавать ключи
для уже проданных программ. Никому не отправляйте и не кладите в git.
"""
import base64
import csv
import datetime
import json
import os
import re
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEYS_DIR = os.path.join(os.path.expanduser("~"), "StroyERP-keys")
PRIVATE = os.path.join(KEYS_DIR, "private_key.txt")
ISSUED = os.path.join(KEYS_DIR, "issued.csv")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUBFILE = os.path.join(ROOT, "custom_addons", "construction_core", "tools", "license_pubkey.py")


def b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def write_pubfile(pub_b64):
    with open(PUBFILE, "w", encoding="utf-8") as f:
        f.write("# Открытый ключ для проверки лицензий (создан keygen.py init).\n"
                "# Секретный ключ хранится ТОЛЬКО у разработчика и в git не попадает.\n"
                'PUBLIC_KEY = "%s"\n' % pub_b64)


def current_pubkey():
    try:
        with open(PUBFILE, encoding="utf-8") as f:
            m = re.search(r'PUBLIC_KEY\s*=\s*"([^"]+)"', f.read())
            return m.group(1) if m else ""
    except OSError:
        return ""


def init():
    if current_pubkey():
        print("В проекте уже есть открытый ключ — пара ключей создана раньше.")
        print("НЕ создаю новую: иначе все выданные ключи и обновления перестанут работать.")
        print("На этом компьютере просто положите private_key.txt с флешки в", KEYS_DIR)
        return
    if os.path.exists(PRIVATE):
        print("Ключи уже созданы:", PRIVATE)
        print("Повторно не создаю — иначе старые лицензии перестанут работать.")
        return
    os.makedirs(KEYS_DIR, exist_ok=True)
    sk = Ed25519PrivateKey.generate()
    raw = sk.private_bytes_raw()
    pub = b64e(sk.public_key().public_bytes_raw())
    with open(PRIVATE, "w") as f:
        f.write(b64e(raw) + "\n")
    write_pubfile(pub)
    print("Готово.")
    print("Секретный ключ:", PRIVATE, " <- СКОПИРУЙТЕ НА ФЛЕШКУ")
    print("Открытый ключ записан в", PUBFILE)
    print("Дальше: git add + commit, обновить модуль construction_core, пересобрать exe.")


def load_key():
    if not os.path.exists(PRIVATE):
        sys.exit("На этом компьютере нет секретного ключа.\n\n"
                 "Скопируйте файл private_key.txt с флешки (или с рабочего ПК) в папку:\n%s\n\n"
                 "Новую пару ключей НЕ создавайте — старые ключи перестанут работать." % KEYS_DIR)
    with open(PRIVATE) as f:
        return Ed25519PrivateKey.from_private_bytes(b64d(f.read().strip()))


def parse_until(s):
    s = s.strip().lower()
    today = datetime.date.today()
    if s in ("", "0", "бессрочно", "forever"):
        return None
    m = re.fullmatch(r"(\d+)\s*(г|y|м|m|д|d)", s)
    if m:
        n, u = int(m.group(1)), m.group(2)
        if u in ("г", "y"):
            return today.replace(year=today.year + n) if not (today.month == 2 and today.day == 29) \
                else today + datetime.timedelta(days=365 * n)
        if u in ("м", "m"):
            return today + datetime.timedelta(days=30 * n)
        return today + datetime.timedelta(days=n)
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError("Не понял срок: " + s)


CODE_RE = r"[A-Z2-7]{4}-[A-Z2-7]{4}-[A-Z2-7]{4}"


def make_key(sk, code, company, until):
    """Ключ для клиента. until — date или None (бессрочно)."""
    payload = {"v": 1, "m": code, "c": company,
               "e": until.isoformat() if until else None,
               "i": datetime.date.today().isoformat()}
    body = b64e(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    return body + "." + b64e(sk.sign(body.encode())), payload


def save_issued(payload, key):
    os.makedirs(KEYS_DIR, exist_ok=True)
    new = not os.path.exists(ISSUED)
    with open(ISSUED, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if new:
            w.writerow(["Дата", "Компания", "Код компьютера", "Срок", "Ключ"])
        w.writerow([payload["i"], payload["c"], payload["m"], payload["e"] or "бессрочно", key])


def read_issued():
    if not os.path.exists(ISSUED):
        return []
    with open(ISSUED, encoding="utf-8-sig") as f:
        return list(csv.reader(f, delimiter=";"))[1:]


def issue():
    sk = load_key()
    code = input("Код компьютера клиента (XXXX-XXXX-XXXX): ").strip().upper()
    if not re.fullmatch(CODE_RE, code):
        sys.exit("Неверный код компьютера.")
    company = input("Компания: ").strip()
    while True:
        s = input("Срок (Enter = бессрочно; 1г, 6м, 30д или дата 31.12.2027): ")
        try:
            until = parse_until(s)
            break
        except ValueError as e:
            print(e)
    key, payload = make_key(sk, code, company, until)
    print("\n=== КЛЮЧ ДЛЯ КЛИЕНТА (скопируйте целиком) ===\n")
    print(key)
    print("\nСрок:", until.strftime("%d.%m.%Y") if until else "бессрочно")
    save_issued(payload, key)
    print("Записано в", ISSUED)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init()
    else:
        issue()
