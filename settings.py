"""Settings: the database (settings table) and secrets file take precedence over environment variables (.env), then defaults."""
import json
import os
import re
import tempfile
import threading

import database as db

SECRET_KEYS = ("IMAP_PASSWORD", "ANTHROPIC_API_KEY", "ADMIN_TOKEN")
_IMAP_BINDING = "_IMAP_IDENTITY"
DEFAULTS = {
    "IMAP_HOST": "imap.gmail.com", "IMAP_USER": "", "IMAP_FOLDER": "", "IMAP_TIMEOUT_SECONDS": "60",
    "SYNC_DAILY_AT": "08:00", "SYNC_INTERVAL_MINUTES": "60", "SYNC_TIMEOUT_MINUTES": "30",
    "SYNC_RETRY_MINUTES": "30", "SYNC_RETRY_MAX": "16", "STALE_AFTER_HOURS": "26",
    "NO_RECEIPTS_ALERT_DAYS": "21", "SYNC_WINDOW_DAYS": "30", "SYNC_WINDOW_MAX_DAYS": "400",
    "MAX_FAILED_ATTEMPTS": "3", "CLAUDE_MODEL": "claude-haiku-4-5-20251001",
}
INT_RANGES = {  # key: (min, max)
    "IMAP_TIMEOUT_SECONDS": (5, 600), "SYNC_INTERVAL_MINUTES": (5, 1440), "SYNC_TIMEOUT_MINUTES": (5, 180),
    "SYNC_RETRY_MINUTES": (5, 240), "SYNC_RETRY_MAX": (0, 48), "STALE_AFTER_HOURS": (2, 240),
    "NO_RECEIPTS_ALERT_DAYS": (1, 365), "SYNC_WINDOW_DAYS": (1, 3650), "SYNC_WINDOW_MAX_DAYS": (30, 3650),
    "MAX_FAILED_ATTEMPTS": (1, 20),
}
SECRETS_PATH = os.path.join(os.path.dirname(db.DB_PATH), "secrets.json")

_lock = threading.Lock()
_cache = None            # {key: value} from the database
_secrets_cache = None    # {key: value} from the file
_secrets_broken = False  # file exists but cannot be read; do not overwrite it


def _load():
    global _cache, _secrets_cache, _secrets_broken
    with _lock:
        if _cache is None:
            _cache = db.settings_all()
        if _secrets_cache is None:
            try:
                with open(SECRETS_PATH) as f:
                    raw = f.read(65537)
                if len(raw) > 65536:
                    raise ValueError("secrets file exceeds size limit")
                values = json.loads(raw)
                if not isinstance(values, dict) or any(
                    k in SECRET_KEYS and v is not None and not isinstance(v, str) for k, v in values.items()
                ):
                    raise ValueError("invalid secrets structure")
                binding = values.get(_IMAP_BINDING)
                if binding is not None and (not isinstance(binding, list) or len(binding) != 3 or
                                            not isinstance(binding[0], str) or not isinstance(binding[1], int) or
                                            not isinstance(binding[2], str)):
                    raise ValueError("invalid IMAP credential binding")
                _secrets_cache = {k: v for k, v in values.items() if k in (*SECRET_KEYS, _IMAP_BINDING)}
                _secrets_broken = False
            except FileNotFoundError:
                _secrets_cache = {}
                _secrets_broken = False
            except Exception as e:
                print(f"Cannot read secrets.json: {e!r}")
                _secrets_cache = {}
                _secrets_broken = True


def secrets_broken():
    _load()
    return _secrets_broken


def invalidate():
    global _cache, _secrets_cache
    with _lock:
        _cache = None
        _secrets_cache = None


def source(key):
    """Source of the value: db | secrets | env | default."""
    _load()
    if key in SECRET_KEYS:
        if key in _secrets_cache:
            return "secrets"
        return "env" if os.getenv(key) else "default"
    if key in _cache:
        return "db"
    if os.getenv(key) not in (None, "") or (key == "SYNC_DAILY_AT" and key in os.environ):
        return "env"
    return "default"


def get(key, default=None):
    _load()
    if key in SECRET_KEYS:
        if _secrets_broken:
            return ""
        if key == "IMAP_PASSWORD" and _secrets_cache.get(_IMAP_BINDING):
            if _secrets_cache[_IMAP_BINDING] != [*imap_endpoint(get("IMAP_HOST")), get("IMAP_USER")]:
                return ""
        if key in _secrets_cache:
            return _secrets_cache[key] or ""
        return os.getenv(key) or default or ""
    if key in _cache:
        return _cache[key]
    v = os.getenv(key)
    if v not in (None, "") or (key == "SYNC_DAILY_AT" and v is not None):
        return v
    return DEFAULTS.get(key, default) if default is None else default


def get_int(key):
    lo, hi = INT_RANGES.get(key, (0, 10 ** 9))
    raw = str(get(key)).strip()
    try:
        return min(max(int(raw), lo), hi)
    except ValueError:
        print(f"Invalid {key}={raw!r}; using {DEFAULTS[key]}")
        return int(DEFAULTS[key])


def get_time(key="SYNC_DAILY_AT"):
    """HH:MM or '' (interval mode)."""
    raw = str(get(key)).strip()
    if not raw:
        return ""
    m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", raw)
    if m and 0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    print(f"Invalid {key}={raw!r}; using 08:00")
    return "08:00"


def is_secret_set(key):
    return bool(get(key))


def validate(key, value):
    value = "" if value is None else str(value).strip()
    if len(value) > 1000:
        raise ValueError(f"{key}: value is too long")
    if key in INT_RANGES:
        if value == "":
            return value
        if not value.isdigit():
            raise ValueError(f"{key}: an integer is required")
        lo, hi = INT_RANGES[key]
        if not lo <= int(value) <= hi:
            raise ValueError(f"{key}: allowed range is {lo}-{hi}")
    elif key == "SYNC_DAILY_AT":
        m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", value) if value else None
        if value and not (m and int(m.group(1)) < 24 and int(m.group(2)) < 60):
            raise ValueError("SYNC_DAILY_AT: use HH:MM, such as 08:00 (leave empty for interval scheduling)")
        if value:
            value = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    elif key == "IMAP_HOST":
        if not re.fullmatch(r"[A-Za-z0-9.-]+(:\d+)?", value or "x") or (":" in value and not 1 <= int(value.rsplit(":", 1)[1]) <= 65535):
            raise ValueError("IMAP_HOST: invalid hostname or port")
    elif key == "IMAP_USER":
        if any(ch.isspace() or ord(ch) < 32 for ch in value):
            raise ValueError("IMAP_USER: whitespace and control characters are not allowed")
    elif key == "IMAP_FOLDER":
        if any(ch in value for ch in '"\\\r\n'):
            raise ValueError("IMAP_FOLDER: invalid characters")
    return value


def imap_endpoint(host):
    host, _, port = (host or "imap.gmail.com").lower().rstrip(".").partition(":")
    return host.rstrip("."), int(port or 993)


def set_many(values):
    """values: {key: value}. Empty regular setting = restore the default/.env fallback.
    An empty SYNC_DAILY_AT enables interval mode.
    Secrets: empty = keep, '__clear__' = disable, '__reset__' = restore the .env fallback."""
    _load()
    if _secrets_broken:
        raise ValueError("Secret storage is unreadable or invalid; restore it locally")
    plain, secrets = {}, dict(_secrets_cache)
    for key, value in values.items():
        if key in SECRET_KEYS:
            v = "" if value is None else str(value)
            if v == "":
                continue
            if len(v) > 4096:
                raise ValueError(f"{key}: value is too long")
            if key == "ADMIN_TOKEN":
                candidate = os.getenv(key, "") if v == "__reset__" else v.strip()
                if v == "__clear__" or len(candidate) < 32 or not candidate.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in candidate):
                    raise ValueError("ADMIN_TOKEN: at least 32 printable ASCII characters without spaces; authentication cannot be disabled")
            if v == "__clear__":
                secrets[key] = None
            elif v == "__reset__":
                secrets.pop(key, None)
            else:
                secrets[key] = v.strip()
        elif key in DEFAULTS:
            plain[key] = validate(key, value)
        else:
            raise ValueError(f"Unknown setting: {key}")
    next_host = plain.get("IMAP_HOST", get("IMAP_HOST")) or os.getenv("IMAP_HOST") or DEFAULTS["IMAP_HOST"]
    next_user = plain.get("IMAP_USER", get("IMAP_USER")) or os.getenv("IMAP_USER") or ""
    changed_identity = imap_endpoint(next_host) != imap_endpoint(get("IMAP_HOST")) or next_user != get("IMAP_USER")
    supplied_password = values.get("IMAP_PASSWORD")
    stored_password = _secrets_cache.get("IMAP_PASSWORD", os.getenv("IMAP_PASSWORD", ""))
    if changed_identity and stored_password and (not supplied_password or supplied_password == "__reset__"):
        raise ValueError("Re-enter or clear the password when changing the IMAP server, port or user")
    if changed_identity and isinstance(supplied_password, str) and not supplied_password.strip():
        raise ValueError("Re-enter the password when changing the IMAP server, port or user")
    explicit_password = supplied_password not in (None, "", "__clear__", "__reset__")
    if secrets.get("IMAP_PASSWORD") and (explicit_password or not secrets.get(_IMAP_BINDING)):
        secrets[_IMAP_BINDING] = [*imap_endpoint(next_host), next_user]
    elif not secrets.get("IMAP_PASSWORD") and "IMAP_PASSWORD" in values:
        secrets.pop(_IMAP_BINDING, None)
    if secrets != _secrets_cache:
        fd, tmp = tempfile.mkstemp(prefix=".secrets-", suffix=".tmp", dir=os.path.dirname(SECRETS_PATH))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(secrets, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, SECRETS_PATH)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    try:
        for key, v in plain.items():
            if v == "" and key != "SYNC_DAILY_AT":
                db.settings_delete(key)
            else:
                db.settings_set(key, v)
    finally:
        invalidate()


def describe():
    """For the UI: regular setting values with their sources; for secrets, only whether they are set."""
    out = {}
    for key in DEFAULTS:
        out[key] = {"value": get(key), "source": source(key), "default": DEFAULTS[key]}
    for key in SECRET_KEYS:
        out[key] = {"set": is_secret_set(key), "source": source(key), "secret": True}
    return out
