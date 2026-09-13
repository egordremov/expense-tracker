import ast
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from tests.support import ADMIN_TOKEN, DatabaseTestCase, cfg, db, main

ROOT = Path(__file__).resolve().parents[1]
CYRILLIC = re.compile(r"[\u0400-\u04ff]")


class BackendSourceLanguageTests(unittest.TestCase):
    def test_return_and_exception_literals_do_not_contain_cyrillic(self):
        sources = [*ROOT.glob("*.py"), *(ROOT / "tests").rglob("*.py")]
        for path in sources:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Return, ast.Raise)):
                    continue
                for value in ast.walk(node):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        with self.subTest(file=str(path.relative_to(ROOT)), line=value.lineno):
                            self.assertIsNone(CYRILLIC.search(value.value), value.value)


class BackendMessageTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.enterContext(TestClient(main.app, headers={"X-Admin-Token": ADMIN_TOKEN}))

    def test_validation_errors_are_english(self):
        responses = [
            (self.client.post("/api/stores", json={}), "Store name is required"),
            (self.client.put("/api/settings", json={"SYNC_INTERVAL_MINUTES": "invalid"}),
             "SYNC_INTERVAL_MINUTES: an integer is required"),
            (self.client.get("/api/stats?from=invalid"), "from/to must use YYYY-MM-DD format"),
            (self.client.post("/api/settings/test-imap", json={"IMAP_HOST": 123}), "IMAP parameters must be strings"),
        ]
        for response, expected in responses:
            with self.subTest(expected=expected):
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"], expected)

    def test_health_and_settings_messages_are_english(self):
        cfg.set_many({"IMAP_PASSWORD": "__clear__"})
        health = self.client.get("/api/health").json()
        self.assertIn("Mail is not configured (IMAP user/password)", health["problems"])
        self.assertEqual(health["schedule"], "Daily at 08:00")
        self.assertIn("imap_not_configured", [p["code"] for p in health["problems_i18n"]])
        cfg.set_many({"SYNC_DAILY_AT": ""})
        self.assertEqual(self.client.get("/api/health").json()["schedule"], "Every 60 minutes")
        self.assertEqual(self.client.get("/api/settings").json()["env_file_hint"],
                         "Values from .env apply until overridden here")
        for template in main._PROBLEM_EN.values():
            self.assertTrue(template.isascii(), template)

    def test_sync_results_and_journal_messages_are_english(self):
        self.store()
        result = self.sync([self.mail()], days=30)
        self.assertEqual(result["status"], "success")
        self.assertIn("Emails in 400 days: 1", result["message"])
        self.assertIn("expenses added: 1", result["message"])
        self.assertTrue(result["message"].isascii())
        self.assertEqual(db.recent_runs(1)[0]["message"], result["message"])
        with main._lock:
            self.assertEqual(main.sync()["message"], "Synchronisation is already running")

    def test_imap_errors_and_folder_warning_are_english(self):
        for error, expected in [
            ("Application-specific password required", "Gmail requires an app password"),
            ("AUTHENTICATIONFAILED", "IMAP rejected the credentials"),
            ("getaddrinfo failed", "IMAP server not found"),
        ]:
            with self.subTest(error=error):
                self.assertTrue(main._friendly_imap_error(Exception(error)).startswith(expected))
        connection = Mock()
        connection.select.return_value = ("OK", [])
        client = main.IMAPClient(host="imap.gmail.com")
        with patch.object(client, "_all_mail_folder", return_value=None):
            folder, warning = client._select_folder(connection)
        self.assertEqual(folder, "INBOX")
        self.assertEqual(warning, "Gmail All Mail folder not found; reading INBOX only (archived emails are not visible)")
