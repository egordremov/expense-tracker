import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Session
from mail_rules import normalize_sender

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "expenses.db"))
os.makedirs(os.path.dirname(DB_PATH), mode=0o700, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"timeout": 30})

DEFAULT_STORE = "Maxima"


class Base(DeclarativeBase):
    pass


class Store(Base):
    __tablename__ = "stores"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    senders = Column(Text)                          # From patterns separated by commas or newlines: maxima.lt, wolt.com
    parser = Column(String, default="auto")         # auto | maxima | wolt | generic
    default_category = Column(String, default="")   # empty = categorize each item using the dictionary
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    def sender_list(self):
        return [s.strip().lower() for s in (self.senders or "").replace("\n", ",").split(",") if s.strip()]

    def as_dict(self):
        return {"id": self.id, "name": self.name, "senders": ", ".join(self.sender_list()), "parser": self.parser or "auto",
                "default_category": self.default_category or "", "enabled": bool(self.enabled)}


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(Text)


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    email_uid = Column(String, index=True)
    store = Column(String, index=True)
    category = Column(String, index=True)
    amount = Column(Float)
    description = Column(String)
    description_lt = Column(String)
    date = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.now)


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"
    uid = Column(String, primary_key=True)          # email Message-ID (or folder:uidvalidity:uid)
    imap_uid = Column(String)
    store = Column(String)
    fingerprint = Column(String, index=True)
    subject = Column(String)
    date = Column(DateTime)
    expenses_count = Column(Integer, default=0)
    parse_mode = Column(String)                     # rules | wolt | claude | generic | fallback | newsletter | unparsed | failed | duplicate
    preview = Column(Text)                          # start of the email text for investigating problem receipts in the UI
    processed_at = Column(DateTime, default=datetime.now)


class FailedEmail(Base):
    """Emails with parsing exceptions: retry from saved text without IMAP, up to MAX_FAILED_ATTEMPTS."""
    __tablename__ = "failed_emails"
    uid = Column(String, primary_key=True)
    imap_uid = Column(String)
    store = Column(String)
    subject = Column(String)
    sender = Column(String)
    date = Column(DateTime)
    body = Column(Text)
    pdf_text = Column(Text)
    attachment_error = Column(Text)
    has_message_id = Column(Boolean, default=True)
    error = Column(Text)
    attempts = Column(Integer, default=1)
    first_failed_at = Column(DateTime, default=datetime.now)
    last_failed_at = Column(DateTime, default=datetime.now)

    def as_mail(self):
        return {"uid": self.uid, "imap_uid": self.imap_uid, "store": self.store, "subject": self.subject or "",
                "from": self.sender or "", "date": self.date.isoformat(), "body": self.body or "",
                "pdf_text": self.pdf_text or "", "attachment_error": self.attachment_error or "",
                "has_message_id": bool(self.has_message_id), "attachments": []}


class Translation(Base):
    __tablename__ = "translations"
    lt = Column(String, primary_key=True)
    ru = Column(String)
    source = Column(String)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, index=True)
    finished_at = Column(DateTime)
    status = Column(String)                         # success | partial | error | skipped
    trigger = Column(String)                        # startup | schedule | retry | manual | reprocess
    message = Column(String)
    mails = Column(Integer, default=0)
    new = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    details = Column(Text)                          # JSON counters used by the UI to build a localized message


_MIGRATIONS = {  # create_all does not add columns to existing tables
    "processed_emails": {"imap_uid": "VARCHAR", "fingerprint": "VARCHAR", "parse_mode": "VARCHAR", "store": "VARCHAR", "preview": "TEXT"},
    "expenses": {"description_lt": "VARCHAR", "store": "VARCHAR"},
    "sync_runs": {"details": "TEXT"},
    "failed_emails": {"attachment_error": "TEXT"},
}


def init_db():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, cols in _MIGRATIONS.items():
            existing = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
            for col, typ in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_processed_emails_fingerprint ON processed_emails (fingerprint)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_expenses_store ON expenses (store)"))
        conn.execute(text("UPDATE processed_emails SET imap_uid = uid WHERE imap_uid IS NULL AND parse_mode IS NULL"))
        # Everything collected before store support was added belongs to Maxima.
        conn.execute(text("UPDATE expenses SET store = :s WHERE store IS NULL OR store = ''"), {"s": DEFAULT_STORE})
        conn.execute(text("UPDATE processed_emails SET store = :s WHERE store IS NULL OR store = ''"), {"s": DEFAULT_STORE})
    seed_default_store()
    migrate_order_fingerprints()


def order_fingerprint(store_id, reference):
    return f"ref:store:{store_id}:{reference}"


def migrate_order_fingerprints():
    with Session(engine) as s:
        for store in s.scalars(select(Store)):
            rows = s.scalars(select(ProcessedEmail).where(
                ProcessedEmail.store == store.name,
                func.substr(ProcessedEmail.fingerprint, 1, 4) == "ref:"))
            for row in rows:
                reference = row.fingerprint.rsplit(":", 1)[-1]
                if reference:
                    row.fingerprint = order_fingerprint(store.id, reference)
        s.commit()


def seed_default_store():
    with Session(engine) as s:
        if s.scalar(select(func.count(Store.id))) == 0:
            sender = normalize_sender(os.getenv("MAXIMA_FROM") or "maxima.lt")
            s.add(Store(name=DEFAULT_STORE, senders=sender, parser="maxima", default_category="", enabled=True))
            s.commit()


# ---------------- stores ----------------
def stores_list(enabled_only=False):
    with Session(engine) as s:
        stmt = select(Store).order_by(Store.id)
        if enabled_only:
            stmt = stmt.where(Store.enabled.is_(True))
        return list(s.scalars(stmt).all())


def store_get(store_id):
    with Session(engine) as s:
        return s.get(Store, store_id)


def store_save(data, store_id=None):
    if any(k in data and not isinstance(data[k], str) for k in ("name", "senders", "parser", "default_category")):
        raise ValueError("Store fields must be strings")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Store name is required")
    senders = [x.strip() for x in str(data.get("senders") or "").replace("\n", ",").split(",") if x.strip()]
    if not senders:
        raise ValueError(f"{name}: specify at least one sender address or domain, such as receipts@wolt.com or wolt.com")
    if len(name) > 100 or len(senders) > 50 or len(data.get("default_category", "")) > 60:
        raise ValueError("Store settings exceed the length or sender count limit")
    senders = [normalize_sender(x) for x in senders]
    parser = data.get("parser") or "auto"
    if parser not in ("auto", "maxima", "wolt", "generic"):
        raise ValueError("parser: auto | maxima | wolt | generic")
    with Session(engine) as s:
        dup = s.scalar(select(Store).where(func.lower(Store.name) == name.lower()))
        if dup and dup.id != store_id:
            raise ValueError(f"Store {name!r} already exists")
        st = s.get(Store, store_id) if store_id else Store()
        if st is None:
            raise ValueError("Store not found")
        old_name = st.name
        st.name, st.senders, st.parser = name, ", ".join(senders), parser
        st.default_category = (data.get("default_category") or "").strip()
        st.enabled = bool(data.get("enabled", True))
        s.add(st)
        if old_name and old_name != name:   # rename expenses, processed emails, and deferred emails in one transaction
            s.query(Expense).filter(Expense.store == old_name).update({Expense.store: name})
            s.query(ProcessedEmail).filter(ProcessedEmail.store == old_name).update({ProcessedEmail.store: name})
            s.query(FailedEmail).filter(FailedEmail.store == old_name).update({FailedEmail.store: name})
        s.commit()
        return st.as_dict()


def store_delete(store_id):
    with Session(engine) as s:
        st = s.get(Store, store_id)
        if st is None:
            return False
        n = (s.scalar(select(func.count(Expense.id)).where(Expense.store == st.name)) or 0) \
            + (s.scalar(select(func.count(ProcessedEmail.uid)).where(ProcessedEmail.store == st.name)) or 0) \
            + (s.scalar(select(func.count(FailedEmail.uid)).where(FailedEmail.store == st.name)) or 0)
        if n:
            raise ValueError(f"Store {st.name!r} already has processed emails; disable it instead of deleting it")
        s.delete(st)
        s.commit()
        return True


# ---------------- settings ----------------
def settings_all():
    with Session(engine) as s:
        return {r.key: r.value for r in s.scalars(select(Setting)).all()}


def settings_set(key, value):
    with Session(engine) as s:
        s.merge(Setting(key=key, value=value))
        s.commit()


def settings_delete(key):
    with Session(engine) as s:
        obj = s.get(Setting, key)
        if obj:
            s.delete(obj)
            s.commit()


# ---------------- emails / expenses ----------------
def receipt_fingerprint(mail, expenses):
    """Receipt fingerprint: email timestamp + total + items. Only for emails without a Message-ID."""
    total = round(sum(e["amount"] for e in expenses), 2)
    head = "|".join(sorted(e.get("description_lt") or e["description"] for e in expenses)[:5])
    return hashlib.sha1(f"{mail['date'][:19]}|{total:.2f}|{head}".encode()).hexdigest()


def is_processed(uid, imap_uid=None):
    with Session(engine) as s:
        if s.get(ProcessedEmail, uid) is not None:
            return True
        if imap_uid:
            legacy = s.get(ProcessedEmail, imap_uid)
            return legacy is not None and legacy.parse_mode is None
        return False


def fingerprint_exists(fp):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(ProcessedEmail).where(ProcessedEmail.fingerprint == fp)) > 0


def processed_by_fingerprint(fp):
    with Session(engine) as s:
        return s.scalar(select(ProcessedEmail).where(ProcessedEmail.fingerprint == fp))


def store_email_expenses(mail, expenses, parse_mode="rules", fingerprint=None, replaces_uid=None):
    fp = fingerprint or (receipt_fingerprint(mail, expenses) if expenses and not mail.get("has_message_id") else None)
    preview = ((mail.get("body") or "")[:1500] + ("\n\n[PDF]\n" + mail["pdf_text"][:1500] if mail.get("pdf_text") else ""))
    if mail.get("attachment_error"):
        preview = mail["attachment_error"][:2000] + "\n\n" + preview
    with Session(engine) as s:
        if replaces_uid:
            s.query(Expense).filter(Expense.email_uid == replaces_uid).delete()
            old = s.get(ProcessedEmail, replaces_uid)
            if old:
                old.expenses_count, old.parse_mode, old.fingerprint = 0, "superseded", None
        for e in expenses:
            s.add(Expense(email_uid=mail["uid"], store=mail.get("store") or DEFAULT_STORE, category=e["category"],
                          amount=e["amount"], description=e["description"], description_lt=e.get("description_lt", ""),
                          date=datetime.fromisoformat(e["date"])))
        s.merge(ProcessedEmail(uid=mail["uid"], imap_uid=mail.get("imap_uid"), store=mail.get("store") or DEFAULT_STORE,
                               fingerprint=fp, subject=(mail.get("subject") or "")[:200], date=datetime.fromisoformat(mail["date"]),
                               expenses_count=len(expenses), parse_mode=parse_mode,
                               preview=preview if parse_mode in ("unparsed", "failed", "fallback", "generic") else None))
        s.commit()


def processed_count(since=None, stores=None):
    with Session(engine) as s:
        stmt = select(func.count(ProcessedEmail.uid))
        if since:
            stmt = stmt.where(ProcessedEmail.date >= since)
        if stores:
            stmt = stmt.where(ProcessedEmail.store.in_(list(stores)))
        return s.scalar(stmt) or 0


def missing_known_emails(mails, stores, since):
    fetched = {m["uid"] for m in mails}
    legacy = {m.get("imap_uid") for m in mails}
    with Session(engine) as s:
        rows = s.scalars(select(ProcessedEmail).where(
            ProcessedEmail.store.in_(stores), ProcessedEmail.date >= since))
        missing = [r.uid for r in rows if r.uid not in fetched and not (r.parse_mode is None and r.uid in legacy)]
        pending = s.scalars(select(FailedEmail).where(FailedEmail.store.in_(stores), FailedEmail.date >= since))
        missing.extend(r.uid for r in pending if r.uid not in fetched)
        return missing


def problem_receipts(days=30, limit=50):
    since = datetime.now() - timedelta(days=days)
    with Session(engine) as s:
        rows = s.scalars(select(ProcessedEmail).where(ProcessedEmail.parse_mode.in_(["unparsed", "failed"]),
                                                      ProcessedEmail.date >= since).order_by(ProcessedEmail.date.desc()).limit(limit)).all()
        return [{"uid": r.uid, "store": r.store, "subject": r.subject, "date": r.date.isoformat(), "mode": r.parse_mode,
                 "preview": r.preview or ""} for r in rows]


def problem_count(days=30):
    since = datetime.now() - timedelta(days=days)
    with Session(engine) as s:
        rows = s.execute(select(ProcessedEmail.parse_mode, func.count()).where(
            ProcessedEmail.parse_mode.in_(["unparsed", "failed"]), ProcessedEmail.date >= since).group_by(ProcessedEmail.parse_mode)).all()
        return dict(rows)


def last_receipt_date():
    """Date of the most recent email from which expenses were extracted."""
    with Session(engine) as s:
        return s.scalar(select(func.max(ProcessedEmail.date)).where(ProcessedEmail.expenses_count > 0))


def last_processed_email_date():
    with Session(engine) as s:
        return s.scalar(select(func.max(ProcessedEmail.date)))


def first_known_email_date():
    with Session(engine) as s:
        dates = [s.scalar(select(func.min(ProcessedEmail.date))), s.scalar(select(func.min(FailedEmail.date)))]
        return min((d for d in dates if d is not None), default=None)


# ---------------- failed emails ----------------
def failed_record(mail, error):
    with Session(engine) as s:
        row = s.get(FailedEmail, mail["uid"])
        if row is None:
            row = FailedEmail(uid=mail["uid"], imap_uid=mail.get("imap_uid"), store=mail.get("store"), subject=(mail.get("subject") or "")[:200],
                              sender=(mail.get("from") or "")[:200], date=datetime.fromisoformat(mail["date"]), body=(mail.get("body") or "")[:60000],
                              pdf_text=(mail.get("pdf_text") or "")[:60000], attachment_error=mail.get("attachment_error"),
                              has_message_id=bool(mail.get("has_message_id")), attempts=0)
        row.attempts = (row.attempts or 0) + 1
        row.error = str(error)[:1000]
        row.last_failed_at = datetime.now()
        s.add(row)
        s.commit()
        return row.attempts


def failed_list():
    with Session(engine) as s:
        return list(s.scalars(select(FailedEmail).order_by(FailedEmail.first_failed_at)).all())


def failed_delete(uid):
    with Session(engine) as s:
        row = s.get(FailedEmail, uid)
        if row:
            s.delete(row)
            s.commit()


def failed_count():
    with Session(engine) as s:
        return s.scalar(select(func.count(FailedEmail.uid))) or 0


# ---------------- journal, backups ----------------
def record_sync_run(started_at, status, trigger, message, mails=0, new=0, failed=0, details=None):
    with Session(engine) as s:
        s.add(SyncRun(started_at=started_at, finished_at=datetime.now(), status=status, trigger=trigger,
                      message=message[:800], mails=mails, new=new, failed=failed,
                      details=json.dumps(details, ensure_ascii=False) if details else None))
        s.commit()


def last_success_at():
    with Session(engine) as s:
        return s.scalar(select(func.max(SyncRun.finished_at)).where(SyncRun.status.in_(["success", "partial"])))


def recent_runs(limit=30):
    with Session(engine) as s:
        rows = s.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(limit)).all()
        out = []
        for r in rows:
            try:
                details = json.loads(r.details) if r.details else None
            except ValueError:
                details = None
            out.append({"started_at": r.started_at.isoformat(timespec="seconds"), "finished_at": r.finished_at.isoformat(timespec="seconds"),
                        "status": r.status, "trigger": r.trigger, "message": r.message, "mails": r.mails, "new": r.new, "failed": r.failed,
                        "details": details})
        return out


def _sqlite_copy(dest):
    src = sqlite3.connect(DB_PATH)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def backup_db(keep=14):
    bdir = os.path.join(os.path.dirname(DB_PATH), "backup")
    os.makedirs(bdir, mode=0o700, exist_ok=True)
    dest = os.path.join(bdir, f"expenses-{date.today().isoformat()}.db")
    _sqlite_copy(dest)
    for name in sorted(os.listdir(bdir)):
        if name.startswith("expenses-") and name[9:13].isdigit() and name.endswith(".db"):
            try:
                if (date.today() - date.fromisoformat(name[9:19])).days > keep:
                    os.remove(os.path.join(bdir, name))
            except ValueError:
                pass
    return dest


@contextmanager
def rebuild_expenses(stores, keep_copies=3):
    """Sync process only: all Session instances join the shared rebuild transaction."""
    global engine
    if not stores:
        raise ValueError("No stores specified for rebuilding")
    bdir = os.path.join(os.path.dirname(DB_PATH), "backup")
    os.makedirs(bdir, mode=0o700, exist_ok=True)
    _sqlite_copy(os.path.join(bdir, f"expenses-pre-reprocess-{datetime.now():%Y%m%d-%H%M%S-%f}.db"))
    old = sorted(n for n in os.listdir(bdir) if n.startswith("expenses-pre-reprocess-"))
    for n in old[:-keep_copies]:
        os.remove(os.path.join(bdir, n))
    original_engine = engine
    with original_engine.begin() as connection:
        engine = connection
        try:
            with Session(connection) as s:
                names = list(stores)
                s.query(Expense).filter(Expense.store.in_(names)).delete(synchronize_session=False)
                s.query(ProcessedEmail).filter(ProcessedEmail.store.in_(names)).delete(synchronize_session=False)
                s.query(FailedEmail).filter(FailedEmail.store.in_(names)).delete(synchronize_session=False)
                s.query(Translation).filter(Translation.source == "dict").delete()
                s.commit()
            yield
        finally:
            engine = original_engine


def translations_get(names):
    if not names:
        return {}
    with Session(engine) as s:
        rows = s.scalars(select(Translation).where(Translation.lt.in_(names))).all()
        return {r.lt: r.ru for r in rows}


def translations_put(mapping, source):
    if not mapping:
        return
    with Session(engine) as s:
        for lt, ru in mapping.items():
            s.merge(Translation(lt=lt, ru=ru, source=source))
        s.commit()


# ---------------- UI queries ----------------
def _q(stmt, start=None, end=None, store=None):
    if start:
        stmt = stmt.where(Expense.date >= datetime.combine(start, time.min))
    if end:
        stmt = stmt.where(Expense.date < datetime.combine(end + timedelta(days=1), time.min))
    if store:
        stmt = stmt.where(Expense.store == store)
    return stmt


def first_expense_date():
    with Session(engine) as s:
        d = s.scalar(select(func.min(Expense.date)))
        return d.date() if d else None


def get_all_expenses(start=None, end=None, store=None, limit=5000):
    with Session(engine) as s:
        rows = s.scalars(_q(select(Expense), start, end, store).order_by(Expense.date.desc()).limit(limit)).all()
        return [{"id": r.id, "store": r.store, "category": r.category, "amount": r.amount, "description": r.description,
                 "description_lt": r.description_lt or "", "date": r.date.isoformat()} for r in rows]


def _grouped(expr, start, end, store, order=None):
    with Session(engine) as s:
        stmt = _q(select(expr, func.sum(Expense.amount)), start, end, store).group_by(expr)
        rows = s.execute(stmt.order_by(order if order is not None else expr)).all()
        return {k: round(a, 2) for k, a in rows}


def get_by_category(start=None, end=None, store=None):
    return _grouped(Expense.category, start, end, store, order=func.sum(Expense.amount).desc())


def get_by_store(start=None, end=None, store=None):
    return _grouped(Expense.store, start, end, store, order=func.sum(Expense.amount).desc())


def get_by_month(start=None, end=None, store=None):
    return _grouped(func.strftime("%Y-%m", Expense.date), start, end, store)


def get_by_day(start=None, end=None, store=None):
    return _grouped(func.strftime("%Y-%m-%d", Expense.date), start, end, store)


def get_stats(start=None, end=None, store=None):
    end = end or date.today()
    start = start or first_expense_date() or end
    with Session(engine) as s:
        total, records, receipts = s.execute(_q(select(
            func.coalesce(func.sum(Expense.amount), 0), func.count(Expense.id),
            func.count(func.distinct(Expense.email_uid))), start, end, store)).one()
        emails = s.scalar(select(func.count(ProcessedEmail.uid)))
        last = s.scalar(select(func.max(ProcessedEmail.processed_at)))
    span = max((end - start).days + 1, 1)
    return {"from": start.isoformat(), "to": end.isoformat(), "days": span, "store": store or "",
            "total": round(total, 2), "records": records, "receipts": receipts,
            "avg_receipt": round(total / receipts, 2) if receipts else 0, "per_day": round(total / span, 2),
            "emails_processed": emails, "last_sync": last.isoformat() if last else None,
            "by_category": get_by_category(start, end, store), "by_store": get_by_store(start, end, store),
            "by_month": get_by_month(start, end, store), "by_day": get_by_day(start, end, store)}
