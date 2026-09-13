"""Store senders are mailbox addresses or domain names, never display-name fragments."""
import re
from email.utils import parseaddr

_DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_LOCAL = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+")


def normalize_sender(value):
    value = value.strip().lower()
    if value == "maxima":
        value = "maxima.lt"
    local, sep, domain = value.rpartition("@")
    domain = domain if sep else value
    if len(value) > 254 or not _DOMAIN.fullmatch(domain) or (sep and not _LOCAL.fullmatch(local)):
        raise ValueError("Sender: specify a full email address or domain, such as receipts@shop.lt or shop.lt")
    return value


def sender_matches(from_header, pattern):
    try:
        pattern = normalize_sender(pattern)
        _, address = parseaddr(from_header or "")
        address = address.lower()
        local, separator, domain = address.rpartition("@")
        if not separator or not local or not _DOMAIN.fullmatch(domain):
            return False
        if "@" in pattern:
            return address == pattern
        return domain == pattern or domain.endswith("." + pattern)
    except ValueError:
        return False
