import asyncio
import json
import os
import stat
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from tests.support import ADMIN_TOKEN, DatabaseTestCase, cfg, db, main
import security


class SecurityTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.enterContext(TestClient(main.app))
        self.headers = {"X-Admin-Token": ADMIN_TOKEN}

    def test_every_data_and_operation_route_requires_authentication(self):
        routes = [("GET", path) for path in (
            "/api/health", "/api/expenses", "/api/categories", "/api/stats", "/api/stores",
            "/api/runs", "/api/settings", "/api/receipts/problems", "/api/new-route")]
        routes += [("POST", "/api/sync"), ("POST", "/api/reprocess?confirm=yes"),
                   ("POST", "/api/discover"), ("POST", "/api/settings/test-imap"),
                   ("PUT", "/api/settings"), ("POST", "/api/stores"),
                   ("PUT", "/api/stores/1"), ("DELETE", "/api/stores/1")]
        with patch.object(main, "run_sync", new_callable=AsyncMock) as run:
            for method, path in routes:
                with self.subTest(method=method, path=path):
                    self.assertEqual(self.client.request(method, path).status_code, 401)
            run.assert_not_called()
        self.assertEqual(self.client.get("/api/live").json(), {"ok": True})
        self.assertEqual(self.client.get("/api/expenses", headers=self.headers).status_code, 200)

    def test_missing_token_and_invalid_secret_storage_fail_closed(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
            self.assertEqual(self.client.get("/api/settings", headers=self.headers).status_code, 503)
        for raw in ("{", "[]", '{"ADMIN_TOKEN": 123}', '{"IMAP_PASSWORD": {}}'):
            with self.subTest(raw=raw):
                Path(cfg.SECRETS_PATH).write_text(raw)
                cfg.invalidate()
                self.assertEqual(self.client.get("/api/settings", headers=self.headers).status_code, 503)
                self.assertEqual(self.client.post("/api/stores", headers=self.headers, json={}).status_code, 503)
                self.assertTrue(cfg.secrets_broken())
                with self.assertRaises(ValueError):
                    cfg.set_many({"SYNC_RETRY_MAX": "4"})

    def test_token_cannot_be_cleared_or_reset_to_empty(self):
        for value in ("__clear__", "short", " " * 40):
            with self.subTest(value=value):
                self.assertEqual(self.client.put("/api/settings", headers=self.headers,
                                                json={"ADMIN_TOKEN": value}).status_code, 400)
                self.assertEqual(cfg.get("ADMIN_TOKEN"), ADMIN_TOKEN)
        cfg.set_many({"ADMIN_TOKEN": ADMIN_TOKEN})
        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}), self.assertRaises(ValueError):
            cfg.set_many({"ADMIN_TOKEN": "__reset__"})

    def test_token_rotation_and_environment_reset(self):
        replacement = "replacement-test-token-at-least-32-characters"
        response = self.client.put("/api/settings", headers=self.headers, json={"ADMIN_TOKEN": replacement})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(replacement, response.text)
        self.assertEqual(self.client.get("/api/stats", headers=self.headers).status_code, 401)
        response = self.client.put("/api/settings", headers={"X-Admin-Token": replacement}, json={"ADMIN_TOKEN": "__reset__"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/stats", headers=self.headers).status_code, 200)

    def test_unauthorized_body_is_never_parsed(self):
        with patch.object(Request, "json", side_effect=AssertionError("JSON parsed before authorization")):
            response = self.client.put("/api/settings", content=b"{" * 1000,
                                       headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 401)

    def test_body_limit_precedes_json_and_handles_chunked_uploads(self):
        with patch.object(Request, "json", side_effect=AssertionError("Oversized JSON parsed")):
            response = self.client.put("/api/settings", headers=self.headers,
                                       json={"IMAP_USER": "x" * security.MAX_REQUEST_BYTES})
        self.assertEqual(response.status_code, 413)

        async def chunked_request():
            app = AsyncMock()
            middleware = security.SecurityMiddleware(app)
            receive = AsyncMock(side_effect=[
                {"type": "http.request", "body": b"a" * security.MAX_REQUEST_BYTES, "more_body": True},
                {"type": "http.request", "body": b"b", "more_body": False},
            ])
            send = AsyncMock()
            scope = {"type": "http", "method": "PUT", "path": "/api/settings",
                     "headers": [(b"x-admin-token", ADMIN_TOKEN.encode())]}
            await middleware(scope, receive, send)
            app.assert_not_called()
            self.assertEqual(send.call_args_list[0].args[0]["status"], 413)
        asyncio.run(chunked_request())

    def test_slow_body_has_a_deadline(self):
        async def slow_request():
            app = AsyncMock()
            async def receive():
                await asyncio.sleep(1)
            send = AsyncMock()
            scope = {"type": "http", "method": "PUT", "path": "/api/settings",
                     "headers": [(b"x-admin-token", ADMIN_TOKEN.encode())]}
            with patch.object(security, "BODY_TIMEOUT_SECONDS", 0.01):
                await security.SecurityMiddleware(app)(scope, receive, send)
            app.assert_not_called()
            self.assertEqual(send.call_args_list[0].args[0]["status"], 408)
        asyncio.run(slow_request())

    def test_new_imap_destination_requires_explicit_password(self):
        cfg.set_many({"IMAP_PASSWORD": "saved-test-password"})
        for values in ({"IMAP_HOST": "imap.gmail.com"}, {"IMAP_USER": "other@example.invalid"},
                       {"IMAP_HOST": "example.invalid:994"}):
            with self.subTest(values=values), patch.object(main.IMAPClient, "test_connection") as connect:
                response = self.client.post("/api/settings/test-imap", headers=self.headers, json=values)
                self.assertEqual(response.status_code, 400)
                connect.assert_not_called()
                with self.assertRaises(ValueError):
                    cfg.set_many(values)
        with patch.object(main.IMAPClient, "test_connection", autospec=True, return_value={"ok": True}) as connect:
            response = self.client.post("/api/settings/test-imap", headers=self.headers,
                                        json={"IMAP_HOST": "imap.gmail.com", "IMAP_PASSWORD": "explicit-test-password"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(connect.call_args.args[0].password, "explicit-test-password")
        with patch.object(main.IMAPClient, "test_connection", autospec=True, return_value={"ok": True}) as connect:
            self.assertEqual(self.client.post("/api/settings/test-imap", headers=self.headers, json={}).status_code, 200)
            self.assertEqual(connect.call_args.args[0].password, "saved-test-password")

    def test_failed_config_write_cannot_rebind_mail_password(self):
        cfg.set_many({"IMAP_PASSWORD": "initial-test-password"})
        with patch.object(db, "settings_set", side_effect=OSError("fixture write failure")), self.assertRaises(OSError):
            cfg.set_many({"IMAP_HOST": "imap.gmail.com", "IMAP_PASSWORD": "replacement-test-password"})
        self.assertEqual(cfg.get("IMAP_HOST"), "example.invalid")
        self.assertEqual(cfg.get("IMAP_PASSWORD"), "")
        cfg.set_many({"SYNC_RETRY_MAX": "5"})
        self.assertEqual(cfg.get("IMAP_PASSWORD"), "")
        with self.assertRaises(ValueError):
            cfg.set_many({"IMAP_HOST": "imap.gmail.com"})

    def test_secret_tempfile_is_private_before_serialization_and_cleaned_on_failure(self):
        original = cfg.json.dump
        seen = []
        def inspect_permissions(values, stream):
            seen.append(stat.S_IMODE(os.fstat(stream.fileno()).st_mode))
            return original(values, stream)
        old_mask = os.umask(0o022)
        try:
            with patch.object(cfg.json, "dump", side_effect=inspect_permissions):
                cfg.set_many({"IMAP_PASSWORD": "private-test-password"})
        finally:
            os.umask(old_mask)
        self.assertEqual(seen, [0o600])
        with patch.object(cfg.os, "replace", side_effect=OSError("fixture rename failure")), self.assertRaises(OSError):
            cfg.set_many({"IMAP_PASSWORD": "replacement-test-password"})
        self.assertEqual(list(self.path.glob(".secrets-*.tmp")), [])
        cfg.invalidate()
        self.assertEqual(cfg.get("IMAP_PASSWORD"), "private-test-password")

    def test_sync_and_login_rate_limits(self):
        with patch.object(main, "run_sync", new_callable=AsyncMock, return_value={"status": "success"}) as run:
            responses = [self.client.post("/api/sync", headers=self.headers).status_code for _ in range(6)]
            self.assertEqual(responses, [200] * 5 + [429])
            self.assertEqual(run.await_count, 5)
        for _ in range(20):
            self.assertEqual(self.client.get("/api/stats").status_code, 401)
        self.assertEqual(self.client.get("/api/stats").status_code, 429)
        self.assertEqual(self.client.get("/api/stats", headers=self.headers).status_code, 200)

    def test_private_responses_are_not_cacheable(self):
        response = self.client.get("/api/stats", headers=self.headers)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
