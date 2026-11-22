"""Email the PDF receipt / status statement to the customer.

DEFAULT IS DEMO MODE: no real email is ever sent. Setu checks the transaction and the address and
tells the customer the PDF will be sent to their (masked) address. Real sending only happens if
EMAIL_MODE=send is set on purpose AND the Gmail settings below exist.

Optional real sending (Gmail SMTP):

Setup (one time): use a Gmail account for sending, turn on 2-Step Verification, create an
"App Password" (Google Account > Security > App passwords) and put these in secrets / env:
    SMTP_USER = "your.sender@gmail.com"
    SMTP_APP_PASSWORD = "the 16-letter app password"
Optional: SMTP_HOST (default smtp.gmail.com), SMTP_PORT (default 465), SMTP_FROM_NAME.
The normal Gmail password is never used. If these are not set, emailing is switched off safely.
"""
import os
import re
import smtplib
import ssl
from email.message import EmailMessage

_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
_EMAIL_IN_TEXT = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,24})")


def settings() -> dict:
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        "port": int(os.getenv("SMTP_PORT", "465") or 465),
        "user": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_APP_PASSWORD", "").replace(" ", "").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "PaySetu Wallet (demo)").strip(),
    }


def real_sending_enabled() -> bool:
    """True only when someone deliberately turned real email on (EMAIL_MODE=send)."""
    return os.getenv("EMAIL_MODE", "demo").strip().lower() == "send"


def is_configured() -> bool:
    s = settings()
    return bool(s["user"] and s["password"])


def clean_email(address: str) -> str | None:
    """Return a normalised address, or None if it does not look like a real email."""
    a = (address or "").strip().strip("<>").lower()
    if not _EMAIL.match(a) or ".." in a:
        return None
    return a


def mask_email(address: str) -> str:
    """y***@gmail.com - for logs, tickets and screens."""
    return _EMAIL_IN_TEXT.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", address or "")


def send_document(to: str, pdf: bytes, filename: str, txn: dict, title: str) -> None:
    """Send one email with the PDF attached. Raises on any failure (caller handles it)."""
    s = settings()
    msg = EmailMessage()
    msg["Subject"] = f"Your PaySetu {title} for {txn['txn_id']} (demo)"
    msg["From"] = f"{s['from_name']} <{s['user']}>"
    msg["To"] = to
    msg.set_content(
        "Hello,\n\n"
        f"As requested in your chat with Setu, here is the {title.lower()} for transaction {txn['txn_id']} "
        f"({txn.get('type', '')}, INR {txn.get('amount_inr', '')}, {txn.get('date', '')}, status {txn.get('status', '')}).\n\n"
        "The PDF is attached.\n\n"
        "PaySetu will never ask for your UPI PIN, OTP, CVV or card number.\n\n"
        "DEMO NOTICE: PaySetu Wallet is a made-up business from a practice project. This is a fictional "
        "transaction and not a real payment confirmation.\n\n"
        "- Setu, PaySetu Wallet support (demo)\n"
    )
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    with smtplib.SMTP_SSL(s["host"], s["port"], context=ssl.create_default_context(), timeout=20) as server:
        server.login(s["user"], s["password"])
        server.send_message(msg)
