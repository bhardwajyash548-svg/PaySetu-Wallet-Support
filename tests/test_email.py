"""Emailing the PDF: only verified transactions, only real addresses, fake mail server (nothing really sent)."""
import pytest

from paysetu_agent import config, emailer, storage, tools


class FakeSMTP:
    sent = []

    def __init__(self, host, port, context=None, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        assert user == "sender@gmail.com" and password == "abcdabcdabcdabcd"

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def mail(monkeypatch, tmp_logs):
    FakeSMTP.sent = []
    monkeypatch.setenv("SMTP_USER", "sender@gmail.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "abcd abcd abcd abcd")   # Google shows it with spaces
    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(config, "EMAIL_LOG_FILE", tmp_logs / "email_log.csv")
    return FakeSMTP


def verify(tool_ctx, txn="PS9995683007", phone="7938"):
    assert tools.get_transaction_status(txn, phone, tool_ctx)["status"] == "found"


def test_sends_receipt_with_pdf_to_customer(mail, tool_ctx):
    verify(tool_ctx)
    r = tools.send_receipt_email("PS9995683007", "Yash.Customer@Gmail.com", tool_ctx)
    assert r["status"] == "sent" and r["document"] == "Payment Receipt" and r["to"] == "y***@gmail.com"
    msg = mail.sent[0]
    assert msg["To"] == "yash.customer@gmail.com" and "PS9995683007" in msg["Subject"]
    pdf = [p for p in msg.iter_attachments()][0]
    assert pdf.get_filename() == "PaySetu_Receipt_PS9995683007_DEMO.pdf"
    assert pdf.get_content().startswith(b"%PDF")
    assert "never ask for your UPI PIN" in msg.get_body(("plain",)).get_content()


def test_failed_payment_gets_status_statement(mail, tool_ctx):
    verify(tool_ctx, "PS6543961946", "3067")
    r = tools.send_receipt_email("PS6543961946", "a@gmail.com", tool_ctx)
    assert r["document"] == "Transaction Status Statement"
    assert "Statement" in [p for p in mail.sent[0].iter_attachments()][0].get_filename()


def test_unverified_transaction_is_never_emailed(mail, tool_ctx):
    r = tools.send_receipt_email("PS9995683007", "a@gmail.com", tool_ctx)   # not looked up in this chat
    assert r["status"] == "not_verified" and mail.sent == []
    verify(tool_ctx)                                                     # verifying a DIFFERENT txn...
    assert tools.send_receipt_email("PS6543961946", "a@gmail.com", tool_ctx)["status"] == "not_verified"
    assert mail.sent == []


def test_wrong_phone_does_not_verify(mail, tool_ctx):
    assert tools.get_transaction_status("PS9995683007", "0000", tool_ctx)["status"] == "not found"
    assert tools.send_receipt_email("PS9995683007", "a@gmail.com", tool_ctx)["status"] == "not_verified"


@pytest.mark.parametrize("bad", ["", "not-an-email", "a@b", "a@@gmail.com", "a..b@gmail.com", "x@gmail.com\nBcc: y@z.com"])
def test_bad_addresses_are_refused(mail, tool_ctx, bad):
    verify(tool_ctx)
    assert tools.send_receipt_email("PS9995683007", bad, tool_ctx)["status"] == "invalid_email"
    assert mail.sent == []


def test_limit_three_emails_per_chat(mail, tool_ctx):
    verify(tool_ctx)
    for _ in range(3):
        assert tools.send_receipt_email("PS9995683007", "a@gmail.com", tool_ctx)["status"] == "sent"
    assert tools.send_receipt_email("PS9995683007", "a@gmail.com", tool_ctx)["status"] == "limit_reached"
    assert len(mail.sent) == 3


def test_not_configured_is_safe(tool_ctx, tmp_logs, monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_APP_PASSWORD", raising=False)
    monkeypatch.setattr(config, "EMAIL_LOG_FILE", tmp_logs / "email_log.csv")
    verify(tool_ctx)
    assert tools.send_receipt_email("PS9995683007", "a@gmail.com", tool_ctx)["status"] == "email_not_configured"


def test_send_failure_is_reported_not_crashed(mail, tool_ctx, monkeypatch):
    class Broken(FakeSMTP):
        def login(self, user, password):
            raise OSError("connection refused")
    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", Broken)
    verify(tool_ctx)
    assert tools.send_receipt_email("PS9995683007", "a@gmail.com", tool_ctx)["status"] == "send_failed"


def test_email_log_keeps_addresses_masked(mail, tool_ctx):
    verify(tool_ctx)
    tools.send_receipt_email("PS9995683007", "yash.customer@gmail.com", tool_ctx)
    row = storage.read_rows(config.EMAIL_LOG_FILE)[-1]
    assert row["to"] == "y***@gmail.com" and row["status"] == "sent" and "yash.customer" not in str(row)


def test_chat_log_and_summary_mask_emails(tmp_logs):
    from paysetu_agent.conversation_summary import sanitize
    storage.log_chat("send it to yash.customer@gmail.com", "Sent to yash.customer@gmail.com", "none")
    row = storage.read_rows(config.CHAT_LOG_FILE)[0]
    assert "yash.customer" not in row["message"] + row["reply"] and "y***@gmail.com" in row["message"]
    assert sanitize("email yash.customer@gmail.com") == "email y***@gmail.com"
