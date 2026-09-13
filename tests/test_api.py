from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tests.support import ADMIN_TOKEN, DatabaseTestCase, cfg, db, main


class ApiTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.enterContext(TestClient(main.app, headers={"X-Admin-Token": ADMIN_TOKEN}))

    def test_pages_and_translation_asset_are_served(self):
        for path, content in [("/", "storeChart"), ("/settings", "saveAll"), ("/static/i18n.js", "CATS_I18N")]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(content, response.text)

    def test_admin_token_protects_settings_and_is_not_exposed(self):
        token = "replacement-test-admin-token-with-32-characters"
        cfg.set_many({"ADMIN_TOKEN": token, "IMAP_PASSWORD": "test-password"})
        self.assertEqual(self.client.get("/api/settings", headers={"X-Admin-Token": ""}).status_code, 401)
        response = self.client.get("/api/settings", headers={"X-Admin-Token": token})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(token, response.text)
        self.assertNotIn("test-password", response.text)
        self.assertTrue(response.json()["settings"]["ADMIN_TOKEN"]["set"])

    def test_settings_save_and_store_crud(self):
        response = self.client.put("/api/settings", json={"SYNC_DAILY_AT": "", "SYNC_INTERVAL_MINUTES": "15"})
        self.assertEqual(response.status_code, 200)
        health = self.client.get("/api/health").json()
        self.assertEqual(health["schedule_i18n"], {"every": 15})
        data = {"name": "API Store", "senders": "shop.example", "parser": "generic"}
        created = self.client.post("/api/stores", json=data)
        self.assertEqual(created.status_code, 200)
        store_id = created.json()["id"]
        changed = self.client.put(f"/api/stores/{store_id}", json={**data, "name": "Renamed"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["name"], "Renamed")
        self.assertEqual(self.client.delete(f"/api/stores/{store_id}").status_code, 200)

    def test_mutations_and_sync_return_busy_while_worker_owns_lock(self):
        store = self.store()
        data = {"name": "New", "senders": "new.example", "parser": "generic"}
        with main._lock:
            responses = [
                self.client.put("/api/settings", json={"SYNC_INTERVAL_MINUTES": "15"}),
                self.client.post("/api/stores", json=data),
                self.client.put(f"/api/stores/{store.id}", json=data),
                self.client.delete(f"/api/stores/{store.id}"),
                self.client.post("/api/sync"),
            ]
        self.assertEqual([r.status_code for r in responses], [409] * 5)
        self.assertEqual(cfg.get_int("SYNC_INTERVAL_MINUTES"), 60)
        self.assertEqual(db.store_get(store.id).name, "Shop")

    def test_stats_and_expenses_agree_on_period_and_store(self):
        first, second = self.store(), self.store("Another")
        self.process(self.mail("one"), first)
        self.process(self.mail("two", store=second.name, amount=7, ago=3), second)
        day = datetime.now().date().isoformat()
        query = {"store": first.name, "from": day, "to": day}
        stats = self.client.get("/api/stats", params=query).json()
        expenses = self.client.get("/api/expenses", params=query).json()
        self.assertEqual(stats["total"], 10)
        self.assertEqual(stats["receipts"], 1)
        self.assertEqual(sum(e["amount"] for e in expenses), stats["total"])
        self.assertEqual(self.client.get("/api/stats?from=invalid").status_code, 400)

    def test_pdf_problem_is_visible_in_health_and_admin_api(self):
        store = self.store()
        self.process(self.mail(attachment_error="Cannot read invoice.pdf"), store)
        main._state.update(status="success", last_success_at=datetime.now().isoformat())
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 503)
        self.assertIn("unparsed", [p["code"] for p in health.json()["problems_i18n"]])
        problems = self.client.get("/api/receipts/problems").json()
        self.assertIn("Cannot read invoice.pdf", problems[0]["preview"])

    def test_manual_and_reprocess_routes_use_supervised_worker(self):
        result = {**main._state, "status": "success"}
        with patch.object(main, "run_sync", new_callable=AsyncMock, return_value=result) as run:
            self.assertEqual(self.client.post("/api/sync?days=90").status_code, 200)
            run.assert_awaited_with(90, "manual")
            self.assertEqual(self.client.post("/api/reprocess").status_code, 400)
            self.assertEqual(self.client.post("/api/reprocess?confirm=yes&force=yes").status_code, 200)
            run.assert_awaited_with(None, "reprocess", True, True)
