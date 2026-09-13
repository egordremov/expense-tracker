from email.message import EmailMessage
from unittest.mock import Mock, patch

from tests.support import DatabaseTestCase
import imap_client
import resource_limits
from mail_rules import normalize_sender, sender_matches


class MailSecurityTests(DatabaseTestCase):
    def message(self, sender="Shop <shop@example.invalid>"):
        message = EmailMessage()
        message["From"] = sender
        message["Subject"] = "Invoice"
        message["Message-ID"] = "<security@example.invalid>"
        message.set_content("Total amount: 12.00 EUR")
        return message

    def fetch(self, message, reported_size=None):
        store = self.store()
        raw = message.as_bytes()
        connection = Mock()
        connection.response.return_value = ("UIDVALIDITY", [b"123"])
        def uid(command, uid, query):
            if query == "(RFC822.SIZE)":
                return "OK", [f"1 (RFC822.SIZE {reported_size if reported_size is not None else len(raw)})".encode()]
            return "OK", [(b"1 (BODY[])", raw)]
        connection.uid.side_effect = uid
        client = imap_client.IMAPClient()
        with patch.object(client, "_connect", return_value=connection), \
                patch.object(client, "_select_folder", return_value=("INBOX", None)), \
                patch.object(client, "_search", return_value=[b"1"]):
            result = client.fetch_recent(30, [store])
        return store, result, connection

    def test_sender_matching_uses_mailbox_domain_boundaries(self):
        for address in ("sender@wolt.com", "Sender <sender@mail.wolt.com>"):
            self.assertTrue(sender_matches(address, "wolt.com"))
        for address in ('"wolt.com billing" <sender@untrusted.invalid>', "sender@notwolt.com",
                        "sender@wolt.com.untrusted.invalid", "wolt.com", "bad@@wolt.com"):
            self.assertFalse(sender_matches(address, "wolt.com"), address)
        self.assertTrue(sender_matches("Receipts <receipts@wolt.com>", "receipts@wolt.com"))
        self.assertFalse(sender_matches("other@wolt.com", "receipts@wolt.com"))
        self.assertEqual(normalize_sender("maxima"), "maxima.lt")
        for fragment in ("wolt", "wolt.com) ALL", 'wolt.com"', "@wolt.com"):
            with self.assertRaises(ValueError):
                normalize_sender(fragment)

    def test_imap_search_result_does_not_override_sender_validation(self):
        message = self.message('"example.invalid" <sender@untrusted.invalid>')
        with patch.object(imap_client, "_body_and_attachments", side_effect=AssertionError("Forged mail parsed")):
            _, (mails, skipped, _), _ = self.fetch(message)
        self.assertEqual(mails, [])
        self.assertEqual(skipped, 0)

    def test_oversized_email_downloads_only_headers_and_becomes_problem(self):
        with patch.object(imap_client, "_body_and_attachments", side_effect=AssertionError("Oversized mail parsed")):
            store, (mails, skipped, _), connection = self.fetch(self.message(), imap_client.MAX_MESSAGE_BYTES + 1)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(mails), 1)
        self.assertTrue(mails[0]["attachment_error"])
        self.assertIn("HEADER.FIELDS", connection.uid.call_args.args[2])
        self.process(mails[0], store)
        self.assertEqual(self.processed(mails[0]["uid"]).parse_mode, "unparsed")

    def test_normal_email_fetch_is_bounded_and_does_not_mark_seen(self):
        _, (mails, skipped, _), connection = self.fetch(self.message())
        self.assertEqual((len(mails), skipped), (1, 0))
        self.assertIn("BODY.PEEK[]<0.", connection.uid.call_args.args[2])

    def test_batch_budget_stops_before_parsing(self):
        with patch.object(imap_client, "MAX_BATCH_BYTES", 1), \
                patch.object(imap_client, "_body_and_attachments", side_effect=AssertionError("Batch parsed")), \
                self.assertRaises(MemoryError):
            self.fetch(self.message())

    def test_mail_count_limit_precedes_fetch(self):
        store = self.store()
        connection = Mock()
        connection.response.return_value = ("UIDVALIDITY", [b"123"])
        client = imap_client.IMAPClient()
        with patch.object(client, "_connect", return_value=connection), \
                patch.object(client, "_select_folder", return_value=("INBOX", None)), \
                patch.object(client, "_search", return_value=[b"1", b"2"]), \
                patch.object(imap_client, "MAX_SYNC_MAILS", 1), self.assertRaises(ValueError):
            client.fetch_recent(30, [store])
        connection.uid.assert_not_called()
        connection.logout.assert_called_once()

    def test_mime_and_decoded_content_limits_report_errors(self):
        message = self.message()
        message.add_attachment(b"fixture", maintype="application", subtype="pdf", filename="invoice.pdf")
        with patch.object(imap_client, "MAX_MIME_PARTS", 1):
            self.assertIn("part count", imap_client._body_and_attachments(message)[3])
        with patch.object(imap_client, "MAX_DECODED_BYTES", 1):
            self.assertIn("size limit", imap_client._body_and_attachments(message)[3])
        with patch.object(imap_client, "MAX_ATTACHMENTS", 0):
            self.assertIn("attachment count", imap_client._body_and_attachments(message)[3])

    def test_pdf_limits_precede_expensive_extraction(self):
        with patch.object(imap_client, "MAX_ATTACHMENT_BYTES", 1), patch("pypdf.PdfReader") as reader:
            with self.assertRaises(ValueError):
                imap_client._pdf_text(b"too big")
            reader.assert_not_called()
        page = Mock()
        page.get_contents.return_value.get_data.return_value = b"123456"
        with patch("pypdf.PdfReader") as reader:
            reader.return_value.pages = [page, page]
            with patch.object(imap_client, "MAX_PDF_PAGES", 1), self.assertRaises(ValueError):
                imap_client._pdf_text(b"fixture")
            reader.return_value.pages = [page]
            with patch.object(imap_client, "MAX_PDF_STREAM_BYTES", 5), self.assertRaises(ValueError):
                imap_client._pdf_text(b"fixture")
        page.extract_text.assert_not_called()

    def test_linux_worker_has_hard_memory_limit(self):
        import resource
        with patch.object(resource_limits.sys, "platform", "linux"), \
                patch.object(resource, "getrlimit", return_value=(resource.RLIM_INFINITY, resource.RLIM_INFINITY)), \
                patch.object(resource, "setrlimit") as set_limit:
            resource_limits.apply_worker_limits()
        set_limit.assert_called_once_with(resource.RLIMIT_AS,
                                          (resource_limits.WORKER_MEMORY_BYTES, resource_limits.WORKER_MEMORY_BYTES))
