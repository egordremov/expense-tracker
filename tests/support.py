import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine

# Importing database creates its directory; keep even that outside project data.
_import_dir = tempfile.TemporaryDirectory(prefix="expense-test-import-")
os.environ["DB_PATH"] = str(Path(_import_dir.name) / "import.db")

import database as db
import main
import settings as cfg
from security import limiter

INITIAL_STATE = dict(main._state)
ADMIN_TOKEN = "test-only-admin-token-with-32-characters"


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        limiter.clear()
        self.temp = tempfile.TemporaryDirectory(prefix="expense-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.db_path = str(self.path / "expenses.db")
        self.engine = create_engine(f"sqlite:///{self.db_path}", connect_args={"timeout": 1})
        self.addCleanup(self.engine.dispose)
        self.enterContext(patch.dict(os.environ, {
            **cfg.DEFAULTS, "DB_PATH": self.db_path, "IMAP_HOST": "example.invalid",
            "IMAP_USER": "review@example.invalid", "IMAP_PASSWORD": "dummy-password",
            "ANTHROPIC_API_KEY": "", "ADMIN_TOKEN": ADMIN_TOKEN, "MAXIMA_FROM": "maxima.lt",
        }))
        self.enterContext(patch.object(db, "DB_PATH", self.db_path))
        self.enterContext(patch.object(db, "engine", self.engine))
        self.enterContext(patch.object(cfg, "SECRETS_PATH", str(self.path / "secrets.json")))
        self.enterContext(patch.object(main, "_state", dict(INITIAL_STATE)))
        self.enterContext(patch.object(main, "_wake", None))
        self.enterContext(patch("imaplib.IMAP4_SSL", side_effect=AssertionError("Real IMAP is forbidden in tests")))
        db.init_db()
        cfg.invalidate()
        self.addCleanup(cfg.invalidate)

    def store(self, name="Shop", parser="generic", enabled=True):
        result = db.store_save(dict(name=name, senders="example.invalid", parser=parser, enabled=enabled))
        return db.store_get(result["id"])

    def mail(self, uid="first", store="Shop", amount=10, ago=0, subject="Purchase receipt", **extra):
        return {"uid": uid, "imap_uid": uid, "store": store, "has_message_id": True,
                "date": (datetime.now() - timedelta(days=ago)).isoformat(), "subject": subject,
                "body": f"Total amount: {amount:.2f} EUR", "pdf_text": "", "attachments": [], **extra}

    def process(self, mail, store):
        counters = dict(dup=0, suspicious=0, new_mails=0, new_expenses=0, per_store_new={})
        main._process_mail(mail, store, counters)
        return counters

    def total(self):
        return db.get_stats()["total"]

    def processed(self, uid):
        with db.Session(db.engine) as session:
            return session.get(db.ProcessedEmail, uid)

    def sync(self, mails, skipped=0, warning=None, **kwargs):
        info = {"folder": "INBOX", "warning": warning, "per_store": {}}
        for mail in mails:
            info["per_store"][mail["store"]] = info["per_store"].get(mail["store"], 0) + 1
        with patch.object(main.IMAPClient, "fetch_recent", return_value=(mails, skipped, info)):
            return main.sync(**kwargs)
