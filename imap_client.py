import base64
import codecs
import collections
import email
import imaplib
import io
import re
import ssl
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime

from bs4 import BeautifulSoup

import settings as cfg
from mail_rules import normalize_sender, sender_matches
from resource_limits import (MAX_MESSAGE_BYTES, MAX_ATTACHMENT_BYTES, MAX_DECODED_BYTES,
                             MAX_MIME_PARTS, MAX_ATTACHMENTS, MAX_PDF_PAGES, MAX_PDF_STREAM_BYTES,
                             MAX_PDF_TEXT_CHARS, MAX_SYNC_MAILS, MAX_BATCH_BYTES)

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_RECEIPT_SUBJECT = re.compile(r"kvit|čekis|cekis|receipt|invoice|sąskait|saskait|faktūr|order|užsakym|uzsakym|bill|чек|dokument|payment|apmok|pirkin|заказ|счет|счёт", re.I)


def _safe_bytes_decode(b, enc):
    try:
        codecs.lookup(enc or "utf-8")
    except LookupError:
        enc = "latin-1"
    return b.decode(enc or "utf-8", errors="replace")


def _decode(value):
    if not value:
        return ""
    try:
        return "".join(_safe_bytes_decode(c, e) if isinstance(c, bytes) else c for c, e in decode_header(str(value)))
    except Exception:
        return str(value)


def _html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "head"]):
        t.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"[​‌‍‎‏﻿͏ ]", " ", text)


def _is_pdf(part):
    return part.get_content_type() == "application/pdf" or (part.get_filename() or "").lower().endswith(".pdf")


def _pdf_text(data):
    from pypdf import PdfReader
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError("PDF exceeds attachment size limit")
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError("PDF exceeds page count limit")
    texts, total = [], 0
    for page in reader.pages:
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > MAX_PDF_STREAM_BYTES:
            raise ValueError("PDF content stream exceeds size limit")
        text = page.extract_text() or ""
        total += len(text)
        if total > MAX_PDF_TEXT_CHARS:
            raise ValueError("PDF text exceeds size limit")
        texts.append(text)
    return "\n".join(texts)


def _body_and_attachments(msg):
    """-> (body, PDF text, attachment names, PDF errors)."""
    plain, html, pdfs, names, errors = [], [], [], [], []
    decoded = 0
    for part_index, part in enumerate(msg.walk()):
        if part_index >= MAX_MIME_PARTS:
            errors.append("Email exceeds MIME part count limit")
            break
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        disp = str(part.get("Content-Disposition", ""))
        attachment = _is_pdf(part) or disp.startswith("attachment") or bool(part.get_filename())
        if attachment:
            names.append((part.get_filename() or "attachment.pdf")[:200])
            if len(names) > MAX_ATTACHMENTS:
                errors.append("Email exceeds attachment count limit")
                break
        if not _is_pdf(part) and (disp.startswith("attachment") or ctype not in ("text/plain", "text/html")):
            continue
        payload = part.get_payload(decode=True) or b""
        decoded += len(payload)
        if decoded > MAX_DECODED_BYTES or (attachment and len(payload) > MAX_ATTACHMENT_BYTES):
            errors.append("Email exceeds decoded content size limit")
            break
        if _is_pdf(part):
            try:
                text = _pdf_text(payload)
                if not text.strip():
                    raise ValueError("PDF contains no extractable text")
                if sum(map(len, pdfs)) + len(text) > MAX_PDF_TEXT_CHARS:
                    raise ValueError("Combined PDF text exceeds size limit")
                pdfs.append(text)
            except Exception as e:
                error = f"Cannot read PDF {names[-1]!r}: {e}"
                errors.append(error)
                print(error)
            continue
        text = _safe_bytes_decode(payload, part.get_content_charset())
        if ctype == "text/html" or re.match(r"\s*<(!doctype|html|table|div|body)", text[:300], re.I):
            html.append(text)
        else:
            plain.append(text)
    body = "\n".join(plain) if any(p.strip() for p in plain) else ""
    if len(body.strip()) < 40 and html:
        body = _html_to_text("\n".join(html))
    body = re.sub(r"[​‌‍‎‏﻿͏]", "", body)
    return body, "\n\n".join(pdfs), names, "; ".join(errors)


class IMAPClient:
    def __init__(self, host=None, user=None, password=None, folder=None, timeout=None):
        self.host = (host or cfg.get("IMAP_HOST") or "imap.gmail.com").strip()
        self.user = (user if user is not None else cfg.get("IMAP_USER") or "").strip()
        self.password = password if password is not None else cfg.get("IMAP_PASSWORD")
        self.folder = (folder if folder is not None else cfg.get("IMAP_FOLDER") or "").strip()
        self.timeout = timeout or cfg.get_int("IMAP_TIMEOUT_SECONDS")

    def configured(self):
        return bool(self.user and self.password)

    def _connect(self):
        host, _, port = self.host.partition(":")
        conn = imaplib.IMAP4_SSL(host, int(port) if port else 993, timeout=self.timeout,
                               ssl_context=ssl.create_default_context())
        conn.login(self.user, self.password)
        return conn

    @staticmethod
    def _encode_mutf7(name):
        """Folder name with non-ASCII characters -> modified UTF-7 (RFC 3501); otherwise imaplib fails to encode the command."""
        if name.isascii():
            return name
        out, buf = [], ""

        def flush():
            nonlocal buf
            if buf:
                out.append("&" + base64.b64encode(buf.encode("utf-16-be")).decode().rstrip("=").replace("/", ",") + "-")
                buf = ""
        for ch in name:
            if 0x20 <= ord(ch) <= 0x7E:
                flush()
                out.append("&-" if ch == "&" else ch)
            else:
                buf += ch
        flush()
        return "".join(out)

    @staticmethod
    def _decode_mutf7(name):
        try:
            return name.replace("&-", "\x00").replace("&", "+").replace(",", "/").encode("ascii").decode("utf-7").replace("\x00", "&")
        except Exception:
            return name

    @staticmethod
    def _all_mail_folder(conn):
        """Find Gmail's "All Mail" folder by its \\All attribute (the name is localized)."""
        status, boxes = conn.list()
        if status != "OK" or not boxes:
            return None
        for raw in boxes:
            if not raw:
                continue
            line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
            m = re.match(r'\((?P<attrs>[^)]*)\)\s+"?(?P<delim>[^"\s]*)"?\s+(?P<name>.+)$', line)
            if m and "\\All" in m.group("attrs"):
                return m.group("name").strip().strip('"')
        return None

    def _select_folder(self, conn):
        """-> (folder name, warning or None). An explicitly configured folder must exist."""
        if self.folder:
            encoded = self._encode_mutf7(self.folder)
            status, _ = conn.select(f'"{encoded}"', readonly=True)
            if status != "OK":
                raise imaplib.IMAP4.error(f"Folder IMAP_FOLDER={self.folder!r} not found")
            return encoded, None
        if "gmail" in self.host:
            name = self._all_mail_folder(conn)
            if name:
                status, _ = conn.select(f'"{name}"', readonly=True)
                if status == "OK":
                    return name, None
            status, _ = conn.select("INBOX", readonly=True)
            if status != "OK":
                raise imaplib.IMAP4.error("Could not open either All Mail or INBOX")
            return "INBOX", "Gmail All Mail folder not found; reading INBOX only (archived emails are not visible)"
        status, _ = conn.select("INBOX", readonly=True)
        if status != "OK":
            raise imaplib.IMAP4.error("Could not open INBOX")
        return "INBOX", None

    @staticmethod
    def _since(days):
        d = datetime.now() - timedelta(days=days)
        return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"

    @staticmethod
    def _search(conn, criteria):
        status, data = conn.uid("search", None, criteria)
        if status != "OK":                       # tagged NO (e.g. [UNAVAILABLE]) is a server failure, not "0 emails"
            raise imaplib.IMAP4.error(f"UID SEARCH {criteria}: {status} {data!r}")
        return data[0].split() if data and data[0] else []

    @staticmethod
    def match_store(from_header, stores):
        for st in stores:
            if any(sender_matches(from_header, p) for p in st.sender_list()):
                return st
        return None

    def fetch_recent(self, days, stores):
        """-> (emails, skipped, info). Emails from all enabled stores within the window; each email has a store key.
        Network errors propagate (sync failure, retries needed); only email parsing errors are caught per email."""
        stores = [st for st in stores if st.sender_list()]
        if not stores:
            raise ValueError("No enabled stores with senders configured")
        conn = self._connect()
        emails, skipped = [], 0
        batch_bytes = 0
        try:
            folder, warning = self._select_folder(conn)
            uv = conn.response("UIDVALIDITY")[1]
            uidvalidity = uv[0].decode() if uv and uv[0] else "0"
            since = self._since(days)
            uid_store = {}
            per_store = collections.Counter()
            for st in stores:
                for pattern in st.sender_list():
                    pattern = normalize_sender(pattern)
                    for uid in self._search(conn, f'(FROM "{pattern}" SINCE {since})'):
                        uid_store.setdefault(uid, st)
                        if len(uid_store) > MAX_SYNC_MAILS:
                            raise ValueError("Too many matching emails; reduce SYNC_WINDOW_MAX_DAYS and the fetch window")
            for uid in sorted(uid_store, key=int):
                status, sizes = conn.uid("fetch", uid, "(RFC822.SIZE)")
                metadata = b" ".join(p for p in (sizes or []) if isinstance(p, bytes))
                size_match = re.search(rb"\bRFC822.SIZE (\d+)", metadata)
                if status != "OK" or not size_match:
                    skipped += 1
                    continue
                oversized = int(size_match[1]) > MAX_MESSAGE_BYTES
                query = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]<0.8192>)" if oversized else f"(BODY.PEEK[]<0.{MAX_MESSAGE_BYTES + 1}>)"
                status, parts = conn.uid("fetch", uid, query)
                if status != "OK" or not parts or not parts[0]:
                    skipped += 1
                    continue
                try:
                    raw = parts[0][1]
                    if len(raw) > (8192 if oversized else MAX_MESSAGE_BYTES):
                        raise ValueError("IMAP response exceeds requested size limit")
                    batch_bytes += len(raw)
                    if batch_bytes > MAX_BATCH_BYTES:
                        raise MemoryError("Email batch exceeds size limit; reduce the fetch window")
                    msg = email.message_from_bytes(raw)
                    if len(msg.get_all("From", [])) != 1:
                        continue
                    try:
                        date = parsedate_to_datetime(msg.get("Date"))
                    except Exception:
                        date = datetime.now()
                    from_h = _decode(msg.get("From"))
                    store = self.match_store(from_h, stores)
                    if store is None:
                        continue
                    if oversized:
                        body, pdf_text, names, attachment_error = "", "", [], "Email exceeds 10 MiB size limit"
                    else:
                        body, pdf_text, names, attachment_error = _body_and_attachments(msg)
                    message_id = (msg.get("Message-ID") or "").strip()
                    uid_s = uid.decode()
                    per_store[store.name] += 1
                    emails.append({
                        "uid": message_id or f"{folder}:{uidvalidity}:{uid_s}",
                        "has_message_id": bool(message_id), "imap_uid": uid_s, "store": store.name,
                        "subject": _decode(msg.get("Subject")), "from": from_h,
                        "date": date.replace(tzinfo=None).isoformat(),
                        "body": body[:30000], "pdf_text": pdf_text[:60000], "attachments": names,
                        "attachment_error": attachment_error[:2000],
                    })
                except MemoryError:
                    raise
                except Exception as e:
                    skipped += 1
                    print(f"imap: could not parse email uid={uid!r}: {e!r}")
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return emails, skipped, {"folder": self._decode_mutf7(folder), "warning": warning, "per_store": dict(per_store)}

    def test_connection(self, stores=None, days=30):
        """For the "Test connection" button: login, folder, and email counts per store for the period specified by days."""
        conn = self._connect()
        try:
            folder, warning = self._select_folder(conn)
            counts = {}
            for st in (stores or []):
                counts[st.name] = len({u for p in st.sender_list() for u in self._search(conn, f'(FROM "{normalize_sender(p)}" SINCE {self._since(days)})')})
            return {"ok": True, "folder": self._decode_mutf7(folder), "warning": warning, "days": days, "per_store": counts}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def discover_senders(self, days=90, max_mails=6000):
        """Store candidates: senders of emails with receipt-like subjects or PDF attachments."""
        conn = self._connect()
        try:
            folder, _ = self._select_folder(conn)
            uids = self._search(conn, f"(SINCE {self._since(days)})")
            truncated = len(uids) > max_mails
            uids = uids[-max_mails:]
            by = collections.defaultdict(lambda: {"count": 0, "pdf": 0, "subjects": collections.Counter(), "name": "", "address": ""})
            for uid in uids:
                status, parts = conn.uid("fetch", uid, "(BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)]<0.8192>)")
                if status != "OK" or not parts or not isinstance(parts[0], tuple):
                    continue
                if len(parts[0][1]) > 8192:
                    raise ValueError("IMAP header exceeds size limit")
                meta = parts[0][0].decode("latin-1").lower()
                hdr = email.message_from_bytes(parts[0][1])
                frm = _decode(hdr.get("From"))
                name, addr = parseaddr(frm)
                subj = _decode(hdr.get("Subject"))
                has_pdf = '"pdf"' in meta or ".pdf" in meta
                if not (has_pdf or _RECEIPT_SUBJECT.search(subj)):
                    continue
                domain = addr.lower().split("@")[-1] if "@" in addr else (addr or frm).lower()
                e = by[domain]
                e["count"] += 1
                e["pdf"] += has_pdf
                e["subjects"][re.sub(r"\d+", "#", subj)[:70]] += 1
                e["name"] = e["name"] or name or addr
                e["address"] = e["address"] or addr
            out = []
            for domain, e in sorted(by.items(), key=lambda x: -x[1]["count"]):
                out.append({"sender": domain, "name": e["name"], "address": e["address"], "count": e["count"], "pdf": e["pdf"],
                            "subjects": [s for s, _ in e["subjects"].most_common(3)]})
            return {"days": days, "folder": self._decode_mutf7(folder), "scanned": len(uids), "truncated": truncated, "candidates": out}
        finally:
            try:
                conn.logout()
            except Exception:
                pass
