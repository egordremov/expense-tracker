import json
import os
import stat
from unittest.mock import patch

from tests.support import ADMIN_TOKEN, DatabaseTestCase, cfg, db


class SettingsTests(DatabaseTestCase):
    def test_blank_daily_schedule_is_persisted(self):
        cfg.set_many({"SYNC_DAILY_AT": "10:00"})
        cfg.set_many({"SYNC_DAILY_AT": ""})
        cfg.invalidate()
        self.assertEqual(cfg.get_time(), "")
        self.assertEqual(db.settings_all()["SYNC_DAILY_AT"], "")
        self.assertEqual(cfg.source("SYNC_DAILY_AT"), "db")

    def test_blank_environment_schedule_means_interval(self):
        with patch.dict(os.environ, {"SYNC_DAILY_AT": ""}):
            cfg.invalidate()
            self.assertEqual(cfg.get_time(), "")
            self.assertEqual(cfg.source("SYNC_DAILY_AT"), "env")

    def test_clear_overrides_environment_for_every_secret(self):
        for key in ("IMAP_PASSWORD", "ANTHROPIC_API_KEY"):
            with self.subTest(key=key), patch.dict(os.environ, {key: "environment-secret"}):
                cfg.set_many({key: "saved-secret"})
                self.assertEqual(cfg.get(key), "saved-secret")
                cfg.set_many({key: "__clear__"})
                cfg.invalidate()
                self.assertEqual(cfg.get(key), "")
                self.assertFalse(cfg.describe()[key]["set"])
                self.assertEqual(cfg.source(key), "secrets")
                cfg.set_many({key: "__reset__"})
                self.assertEqual(cfg.get(key), "environment-secret")

    def test_blank_secret_keeps_value_and_file_permissions(self):
        cfg.set_many({"ADMIN_TOKEN": ADMIN_TOKEN})
        cfg.set_many({"ADMIN_TOKEN": ""})
        self.assertEqual(cfg.get("ADMIN_TOKEN"), ADMIN_TOKEN)
        self.assertEqual(stat.S_IMODE(os.stat(cfg.SECRETS_PATH).st_mode), 0o600)
        self.assertNotIn(ADMIN_TOKEN, json.dumps(cfg.describe()))

    def test_invalid_settings_leave_existing_value(self):
        cfg.set_many({"SYNC_RETRY_MAX": "5"})
        with self.assertRaises(ValueError):
            cfg.set_many({"SYNC_RETRY_MAX": "-1"})
        self.assertEqual(cfg.get_int("SYNC_RETRY_MAX"), 5)
