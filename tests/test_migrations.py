from sqlalchemy import text

from tests.support import DatabaseTestCase, db


class MigrationTests(DatabaseTestCase):
    def test_old_fingerprints_migrate_idempotently(self):
        for name in ["Shop", "store", "Name:With:Colons"]:
            with self.subTest(name=name):
                store = self.store(name)
                mail = self.mail(name, store=name, subject="Order #12345")
                db.store_email_expenses(mail, [{"category": "food", "amount": 10,
                                               "description": "food", "date": mail["date"]}],
                                        "generic", fingerprint=f"ref:{name}:12345")
                db.init_db()
                db.init_db()
                self.assertEqual(self.processed(name).fingerprint, db.order_fingerprint(store.id, "12345"))
                self.process({**mail, "uid": name + "-invoice"}, store)
        self.assertEqual(self.total(), 30)

    def test_fingerprint_from_previously_renamed_store_is_migrated(self):
        store = self.store("New name")
        mail = self.mail(store=store.name, subject="Order #12345")
        db.store_email_expenses(mail, [{"category": "food", "amount": 10, "description": "food", "date": mail["date"]}],
                                "generic", fingerprint="ref:Old name:12345")
        db.init_db()
        self.process({**mail, "uid": "invoice"}, store)
        self.assertEqual(self.total(), 10)

    def test_existing_schema_gets_new_columns(self):
        db.failed_record(self.mail(), RuntimeError("old error"))
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE failed_emails DROP COLUMN attachment_error"))
            connection.execute(text("ALTER TABLE sync_runs DROP COLUMN details"))
        db.init_db()
        db.init_db()
        self.assertEqual(db.failed_list()[0].as_mail()["attachment_error"], "")
        with self.engine.connect() as connection:
            columns = {r[1] for r in connection.execute(text("PRAGMA table_info(sync_runs)"))}
        self.assertIn("details", columns)
