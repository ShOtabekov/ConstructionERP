"""Проверка лицензии: код компьютера, подпись ключа Ed25519, пробный период."""
import base64
import datetime
import hashlib
import json
import os
import sys
import time

from .license_pubkey import PUBLIC_KEY

TRIAL_DAYS = 14
_CACHE = {}          # dbname -> (expires_at, status)
CACHE_SECONDS = 60


def _b64d(s):
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _raw_machine_id():
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return winreg.QueryValueEx(k, "MachineGuid")[0]
        except OSError:
            pass
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path) as f:
                v = f.read().strip()
                if v:
                    return v
        except OSError:
            pass
    import uuid
    return "%012x" % uuid.getnode()


def machine_code():
    h = hashlib.sha256(("stroyerp|" + _raw_machine_id()).encode()).digest()
    s = base64.b32encode(h).decode()[:12]
    return "-".join(s[i:i + 4] for i in (0, 4, 8))


def decode_key(key):
    """-> payload dict или исключение ValueError с понятным текстом."""
    if not PUBLIC_KEY:
        raise ValueError("В этой сборке не задан ключ проверки лицензий.")
    key = "".join((key or "").split())
    if "." not in key:
        raise ValueError("Неверный формат ключа.")
    body, sig = key.split(".", 1)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(_b64d(PUBLIC_KEY)).verify(_b64d(sig), body.encode())
        payload = json.loads(_b64d(body))
    except Exception:
        raise ValueError("Ключ недействителен (подпись не совпадает).")
    if payload.get("m") != machine_code():
        raise ValueError("Ключ выдан для другого компьютера.")
    return payload


def _trial_file():
    base = os.environ.get("PROGRAMDATA") or os.path.expanduser("~")
    return os.path.join(base, "StroyERP", ".trial")


def trial_start(env, write=False):
    """Дата начала пробного периода: самая ранняя из базы и файла на компьютере.
    write=True — сохранить её (только из обычной, не read-only транзакции)."""
    ICP = env["ir.config_parameter"].sudo()
    dates = []
    v = ICP.get_param("construction_license.trial_start")
    if v:
        try:
            dates.append(datetime.date.fromisoformat(v))
        except ValueError:
            pass
    path = _trial_file()
    try:
        with open(path) as f:
            dates.append(datetime.date.fromisoformat(f.read().strip()))
    except (OSError, ValueError):
        pass
    start = min(dates) if dates else datetime.date.today()
    if not write:
        return start
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(start.isoformat())
        except OSError:
            pass
    if v != start.isoformat():
        ICP.set_param("construction_license.trial_start", start.isoformat())
    return start


def today(env, write=False):
    """Сегодня, но не раньше последней виденной даты (защита от перевода часов назад)."""
    ICP = env["ir.config_parameter"].sudo()
    t = datetime.date.today()
    last = ICP.get_param("construction_license.last_seen")
    try:
        last = datetime.date.fromisoformat(last) if last else None
    except ValueError:
        last = None
    if last and last > t:
        return last
    if write and last != t:
        ICP.set_param("construction_license.last_seen", t.isoformat())
    return t


def compute_status(env):
    """{'state': licensed|trial|expired, 'days_left', 'until', 'company', 'machine', 'message'}"""
    code = machine_code()
    now = today(env)
    key = env["ir.config_parameter"].sudo().get_param("construction_license.key")
    res = {"machine": code, "company": "", "until": False, "days_left": False}
    if key:
        try:
            p = decode_key(key)
            until = datetime.date.fromisoformat(p["e"]) if p.get("e") else None
            res["company"] = p.get("c", "")
            if until is None or until >= now:
                res.update(state="licensed", until=until.isoformat() if until else False,
                           days_left=(until - now).days if until else False,
                           message=("Лицензия бессрочная" if until is None
                                    else "Лицензия действует до %s" % until.strftime("%d.%m.%Y")))
                return res
            res["message"] = "Срок лицензии закончился %s." % until.strftime("%d.%m.%Y")
            res.update(state="expired", until=until.isoformat())
            return res
        except ValueError as e:
            res["message"] = str(e)
    left = TRIAL_DAYS - (now - trial_start(env)).days
    if left > 0:
        res.update(state="trial", days_left=left,
                   message="Пробный период: осталось %d дн." % left)
    else:
        res.update(state="expired",
                   message=res.get("message") or "Пробный период закончился.")
    return res


def get_status(env, fresh=False):
    db = env.cr.dbname
    hit = _CACHE.get(db)
    if not fresh and hit and hit[0] > time.time():
        return hit[1]
    st = compute_status(env)
    _CACHE[db] = (time.time() + CACHE_SECONDS, st)
    if hit and hit[1]["state"] != st["state"]:
        env.registry.clear_cache()     # меню кешируются — перестроить при смене состояния
    return st


def touch(env):
    """Запомнить начало пробного периода и сегодняшнюю дату. Вызывается при установке,
    раз в день по расписанию и при открытии программы."""
    trial_start(env, write=True)
    today(env, write=True)


def clear_cache(env):
    _CACHE.pop(env.cr.dbname, None)
    env.registry.clear_cache()
