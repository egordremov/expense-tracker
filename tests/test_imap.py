import io
import ssl
from email.message import EmailMessage
from unittest.mock import Mock, patch

from pypdf import PdfWriter

from tests.support import DatabaseTestCase, db
import imap_client


class ImapTests(DatabaseTestCase):
    def test_tls_checks_certificate_and_hostname(self):
        with patch.object(imap_client.imaplib, "IMAP4_SSL") as connect:
            imap_client.IMAPClient()._connect()
        context = connect.call_args.kwargs["ssl_context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_bad_or_empty_pdf_is_visible_as_problem(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buffer = io.BytesIO()
        writer.write(buffer)
        store = self.store()
        for uid, payload in [("broken", b"invalid PDF"), ("blank", buffer.getvalue())]:
            with self.subTest(uid=uid):
                message = EmailMessage()
                message.set_content("Your invoice is attached.")
                message.add_attachment(payload, maintype="application", subtype="pdf", filename="invoice.pdf")
                body, pdf, names, error = imap_client._body_and_attachments(message)
                self.assertTrue(error)
                mail = self.mail(uid, body=body, pdf_text=pdf, attachments=names, attachment_error=error)
                self.process(mail, store)
                self.assertEqual(self.processed(uid).parse_mode, "unparsed")
                self.assertIn(error, self.processed(uid).preview)
        self.assertEqual(db.problem_count()["unparsed"], 2)
        self.assertEqual(self.total(), 0)

    def test_partial_pdf_failure_does_not_silently_reduce_total(self):
        message = EmailMessage()
        message.set_content("Invoice total: 25.00 EUR")
        for name in ["food.pdf", "delivery.pdf"]:
            message.add_attachment(b"fixture", maintype="application", subtype="pdf", filename=name)
        with patch.object(imap_client, "_pdf_text", side_effect=["Total amount: 20.00 EUR", ValueError("broken")]):
            body, pdf, names, error = imap_client._body_and_attachments(message)
        store = self.store()
        self.process(self.mail(body=body, pdf_text=pdf, attachments=names, attachment_error=error), store)
        self.assertEqual(self.total(), 0)
        self.assertEqual(self.processed("first").parse_mode, "unparsed")

    def test_pdf_error_survives_failed_email_round_trip(self):
        mail = self.mail(attachment_error="invoice.pdf: no text")
        db.failed_record(mail, RuntimeError("DB save failed"))
        self.assertEqual(db.failed_list()[0].as_mail()["attachment_error"], mail["attachment_error"])

    def test_html_disguised_as_plain_text_is_extracted(self):
        message = EmailMessage()
        message.set_content("<html><body><div>Total amount: 10.00 EUR</div></body></html>")
        body, pdf, names, error = imap_client._body_and_attachments(message)
        self.assertIn("Total amount: 10.00 EUR", body)
        self.assertNotIn("<html>", body)
        self.assertEqual((pdf, names, error), ("", [], ""))

    def test_fetch_propagates_pdf_error_to_receipt_processing(self):
        store = self.store()
        message = EmailMessage()
        message["From"] = "Shop <shop@example.invalid>"
        message["Message-ID"] = "<pdf-problem@example.invalid>"
        message["Subject"] = "Invoice"
        message.set_content("Please see the attached invoice.")
        message.add_attachment(b"bad PDF", maintype="application", subtype="pdf", filename="invoice.pdf")
        connection = Mock()
        connection.response.return_value = ("UIDVALIDITY", [b"123"])
        raw = message.as_bytes()
        connection.uid.side_effect = lambda command, uid, query: ("OK", [f"1 (RFC822.SIZE {len(raw)})".encode()]) if query == "(RFC822.SIZE)" else ("OK", [(b"1 (BODY[])", raw)])
        client = imap_client.IMAPClient()
        with patch.object(client, "_connect", return_value=connection), \
                patch.object(client, "_select_folder", return_value=("INBOX", None)), \
                patch.object(client, "_search", return_value=[b"1"]):
            mails, skipped, info = client.fetch_recent(30, [store])
        self.assertEqual(skipped, 0)
        self.assertEqual(info["per_store"], {"Shop": 1})
        self.assertEqual(len(mails), 1)
        self.assertTrue(mails[0]["attachment_error"])
        self.process(mails[0], store)
        self.assertEqual(self.processed(mails[0]["uid"]).parse_mode, "unparsed")
