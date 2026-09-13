import asyncio
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event

from tests.support import DatabaseTestCase, cfg, db, main


class RebuildTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.shop = self.store()
        self.mails = [self.mail(f"order-{i}", subject=f"Order #{12345+i}") for i in range(3)]
        for mail in self.mails:
            self.process(mail, self.shop)

    def test_fetch_failure_preserves_all_receipts_even_with_force(self):
        for force in [False, True]:
            with self.subTest(force=force):
                result = self.sync(self.mails[:2], skipped=1, reset=True, force=force)
                self.assertEqual(result["status"], "error")
                self.assertEqual(self.total(), 30)
                self.assertTrue(db.is_processed("order-2"))
                self.assertFalse(main._health_payload()["ok"])

    def test_missing_old_uid_cannot_be_hidden_by_many_new_mails(self):
        new = [self.mail(f"new-{i}", subject=f"Order #{22345+i}") for i in range(5)]
        result = self.sync(self.mails[:2] + new, reset=True)
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.total(), 30)

    def test_empty_or_wrong_folder_does_not_clear_history(self):
        for mails, warning in [([], None), (self.mails, "Wrong folder")]:
            with self.subTest(warning=warning):
                result = self.sync(mails, warning=warning, reset=True)
                self.assertEqual(result["status"], "error")
                self.assertEqual(self.total(), 30)

    def test_unparsed_receipt_rolls_back_whole_rebuild(self):
        changed = [{**self.mails[0], "body": "Total amount: 15.00 EUR"},
                   self.mails[1], {**self.mails[2], "attachment_error": "broken PDF"}]
        result = self.sync(changed, reset=True, force=True)
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.total(), 30)
        self.assertEqual(self.processed("order-2").parse_mode, "generic")
        self.assertIs(db.engine, self.engine)

    def test_parser_exception_rolls_back_whole_rebuild(self):
        original = main.parse_expenses

        def sometimes_broken(mail, store):
            if mail["uid"] == "order-1":
                raise RuntimeError("parser fixture failed")
            return original(mail, store)

        with patch.object(main, "parse_expenses", side_effect=sometimes_broken):
            result = self.sync(self.mails, reset=True)
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.total(), 30)
        self.assertEqual(db.failed_count(), 0)

    def test_successful_rebuild_preserves_disabled_store_and_backup(self):
        disabled = self.store("Disabled", enabled=False)
        self.process(self.mail("disabled", store=disabled.name, amount=5), disabled)
        changed = [{**m, "body": "Total amount: 12.00 EUR"} for m in self.mails]
        result = self.sync(changed, reset=True)
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.total(), 41)
        self.assertTrue(db.is_processed("disabled"))
        backups = list((self.path / "backup").glob("expenses-pre-reprocess-*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as connection:
            self.assertEqual(connection.execute("SELECT SUM(amount) FROM expenses").fetchone()[0], 35)

    def test_force_allows_intentionally_removed_mail(self):
        result = self.sync(self.mails[:2], reset=True, force=True)
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.total(), 20)

    def test_readers_see_old_data_until_commit(self):
        with db.rebuild_expenses([self.shop.name]):
            self.process({**self.mails[0], "body": "Total amount: 15.00 EUR"}, self.shop)
            with closing(sqlite3.connect(self.db_path)) as reader:
                self.assertEqual(reader.execute("SELECT SUM(amount) FROM expenses").fetchone()[0], 30)
        self.assertEqual(self.total(), 15)

    def test_insert_failure_rolls_back_outer_transaction(self):
        def fail_insert(mapper, connection, target):
            if target.email_uid == "order-1":
                raise RuntimeError("simulated SQL write failure")

        event.listen(db.Expense, "before_insert", fail_insert)
        try:
            result = self.sync(self.mails, reset=True)
        finally:
            event.remove(db.Expense, "before_insert", fail_insert)
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.total(), 30)
        self.assertIs(db.engine, self.engine)

    def test_old_pending_mail_is_included_in_window_and_completeness_check(self):
        db.failed_record(self.mail("old-failed", ago=700), RuntimeError("previous failure"))
        self.assertGreaterEqual(main._window(30, reset=True), 700)
        result = self.sync(self.mails, reset=True)
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.total(), 30)
        self.assertEqual(db.failed_count(), 1)


class SyncTests(DatabaseTestCase):
    def test_failed_mail_is_retried_and_then_saved(self):
        self.store()
        mail = self.mail()
        with patch.object(main, "parse_expenses", side_effect=RuntimeError("temporary failure")):
            self.sync([mail])
        self.assertEqual(db.failed_count(), 1)
        self.sync([])
        self.assertEqual(db.failed_count(), 0)
        self.assertEqual(self.total(), 10)

    def test_retry_limit_marks_failed_receipt_visible(self):
        self.store()
        cfg.set_many({"MAX_FAILED_ATTEMPTS": "2"})
        with patch.object(main, "parse_expenses", side_effect=RuntimeError("persistent failure")):
            self.sync([self.mail()])
            self.sync([])
        self.assertEqual(db.failed_count(), 0)
        self.assertEqual(db.problem_count()["failed"], 1)
        self.assertFalse(main._health_payload()["ok"])

    def test_legacy_recovery_mark_survives_partial_sync(self):
        self.store()
        db.settings_set(main.REPROCESS_MARK, "legacy rebuild")
        self.sync([self.mail()], skipped=1)
        self.assertIn(main.REPROCESS_MARK, db.settings_all())
        self.sync([self.mail()])
        self.assertNotIn(main.REPROCESS_MARK, db.settings_all())


class WorkerTests(DatabaseTestCase):
    def worker_fixture(self, name):
        return str(Path(__file__).parent / "fixtures" / name)

    def test_timeout_kills_worker_and_releases_lock(self):
        asyncio.run(self.timeout_scenario())

    async def timeout_scenario(self):
        spawn = asyncio.create_subprocess_exec
        processes = []

        async def fixture_worker(executable, script, **kwargs):
            process = await spawn(executable, self.worker_fixture("slow_sync.py"), **kwargs)
            processes.append(process)
            return process

        original = cfg.get_int
        with patch.object(main.asyncio, "create_subprocess_exec", side_effect=fixture_worker), \
                patch.object(cfg, "get_int", side_effect=lambda k: 0.01 if k == "SYNC_TIMEOUT_MINUTES" else original(k)):
            result = await main.run_sync()
        self.assertEqual(result["status"], "error")
        self.assertIsNotNone(processes[0].returncode)
        self.assertFalse(main._lock.locked())
        self.assertEqual(db.recent_runs()[0]["status"], "error")
        with patch.dict(os.environ, {"IMAP_USER": "", "IMAP_PASSWORD": ""}):
            cfg.invalidate()
            next_result = await main.run_sync()
        self.assertNotEqual(next_result["status"], "busy")
        self.assertEqual(next_result["consecutive_failures"], 2)

    def test_real_worker_returns_error_when_mail_is_unconfigured(self):
        with patch.dict(os.environ, {"IMAP_USER": "", "IMAP_PASSWORD": ""}):
            cfg.invalidate()
            result = asyncio.run(main.run_sync(trigger="startup"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["trigger"], "startup")
        self.assertEqual(len(db.recent_runs()), 1)
        self.assertFalse(main._lock.locked())

    def test_cancellation_reaps_worker(self):
        asyncio.run(self.cancellation_scenario())

    async def cancellation_scenario(self):
        spawn = asyncio.create_subprocess_exec
        started = asyncio.Event()
        processes = []

        async def fixture_worker(executable, script, **kwargs):
            process = await spawn(executable, self.worker_fixture("slow_sync.py"), **kwargs)
            processes.append(process)
            started.set()
            return process

        with patch.object(main.asyncio, "create_subprocess_exec", side_effect=fixture_worker):
            task = asyncio.create_task(main.run_sync())
            await asyncio.wait_for(started.wait(), timeout=5)
            busy = await main.run_sync()
            self.assertEqual(busy["status"], "busy")
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIsNotNone(processes[0].returncode)
        self.assertFalse(main._lock.locked())

    def test_killed_rebuild_rolls_back_database(self):
        store = self.store()
        self.process(self.mail(), store)
        asyncio.run(self.killed_rebuild_scenario())
        self.assertEqual(self.total(), 10)

    async def killed_rebuild_scenario(self):
        spawn = asyncio.create_subprocess_exec
        marker = self.path / "transaction-started"

        async def fixture_worker(executable, script, **kwargs):
            kwargs["env"]["TEST_MARKER"] = str(marker)
            return await spawn(executable, self.worker_fixture("open_transaction.py"), **kwargs)

        original = cfg.get_int
        with patch.object(main.asyncio, "create_subprocess_exec", side_effect=fixture_worker), \
                patch.object(cfg, "get_int", side_effect=lambda k: 0.03 if k == "SYNC_TIMEOUT_MINUTES" else original(k)):
            result = await main.run_sync(reset=True)
        self.assertTrue(marker.exists(), "fixture never opened its write transaction")
        self.assertEqual(result["status"], "error")
