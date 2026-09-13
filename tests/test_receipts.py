from unittest.mock import patch

from sqlalchemy import event

from tests.support import DatabaseTestCase, db, main
import expense_parser as parser


class ReceiptTests(DatabaseTestCase):
    def test_distinct_purchases_with_equal_totals_are_kept(self):
        store = self.store()
        self.process(self.mail("first"), store)
        self.process(self.mail("second", ago=1), store)
        self.assertEqual(self.total(), 20)
        self.assertEqual(db.get_stats()["receipts"], 2)

    def test_total_matching_previous_category_is_not_duplicate(self):
        store = self.store()
        first = self.mail("rich", amount=20)
        db.store_email_expenses(first, [dict(category=c, amount=a, description=c, date=first["date"])
                                        for c, a in [("food", 7), ("drink", 13)]], "rules")
        self.process(self.mail("separate", amount=7), store)
        self.assertEqual(self.total(), 27)

    def test_order_dedup_survives_rename(self):
        store = self.store()
        self.process(self.mail("confirmation", subject="Order #12345"), store)
        db.store_save(dict(name="Renamed", senders="example.invalid", parser="generic"), store.id)
        store = db.store_get(store.id)
        self.process(self.mail("invoice", store="Renamed", subject="Invoice #12345"), store)
        self.assertEqual(self.total(), 10)
        self.assertEqual(self.processed("invoice").parse_mode, "duplicate")
        self.assertEqual(self.processed("confirmation").store, "Renamed")

    def test_same_order_number_in_different_stores_is_kept(self):
        for name in ["Shop", "Another"]:
            store = self.store(name)
            self.process(self.mail(name, store=name, subject="Order #12345"), store)
        self.assertEqual(self.total(), 20)

    def test_same_message_id_is_idempotent_across_syncs(self):
        self.store()
        self.sync([self.mail()])
        self.sync([self.mail()])
        self.assertEqual(self.total(), 10)
        self.assertEqual(db.get_stats()["receipts"], 1)

    def test_cancelled_receipts_do_not_reach_format_parsers(self):
        examples = [
            ("maxima", {"body": "Apsipirkimo suma: 10.00 EUR\nKvitas baz\u0117je\nDuona  10,00\n----"}),
            ("wolt", {"pdf_text": "Wolt\nSoup 21% 1 8.26 10.00 10.00\nTotal in EUR (incl. VAT) 10.00"}),
        ]
        for kind, content in examples:
            with self.subTest(parser=kind):
                store = self.store(kind + " fixture", parser=kind)
                valid = self.mail(kind, store=store.name, **content)
                rows, _ = parser.parse_expenses(valid, store)
                self.assertEqual(sum(row["amount"] for row in rows), 10)
                for subject in ["Order cancelled", "Payment refund", "Payment failed", "Payment reminder"]:
                    with self.subTest(subject=subject):
                        rows, mode = parser.parse_expenses({**valid, "subject": subject}, store)
                        self.assertEqual(rows, [])
                        self.assertEqual(mode, "newsletter")

    def test_richer_receipt_replaces_total_once(self):
        store = self.store()
        self.process(self.mail("old", subject="Order #12345"), store)
        new = self.mail("new", subject="Order #12345")
        rows = [dict(category="food", amount=11, description="food", date=new["date"])]
        with patch.object(main, "parse_expenses", return_value=(rows, "rules")):
            result = self.process(new, store)
        self.assertEqual(result["superseded"], 1)
        self.assertEqual(self.total(), 11)
        self.assertEqual(self.processed("old").parse_mode, "superseded")
        self.assertIsNone(self.processed("old").fingerprint)

    def test_failed_replacement_rolls_back_old_receipt(self):
        store = self.store()
        self.process(self.mail("old", subject="Order #12345"), store)
        new = self.mail("new", subject="Order #12345")
        rows = [dict(category="food", amount=11, description="food", date=new["date"])]

        def reject_new_expense(mapper, connection, target):
            if target.email_uid == "new":
                raise RuntimeError("simulated insert failure")

        event.listen(db.Expense, "before_insert", reject_new_expense)
        try:
            with patch.object(main, "parse_expenses", return_value=(rows, "rules")):
                with self.assertRaisesRegex(RuntimeError, "insert failure"):
                    self.process(new, store)
        finally:
            event.remove(db.Expense, "before_insert", reject_new_expense)
        self.assertEqual(self.total(), 10)
        self.assertEqual(self.processed("old").parse_mode, "generic")
        self.assertIsNone(self.processed("new"))
