"""PDF receipt / status statement for ONE verified fictional transaction.

Security: make_pdf() re-checks the transaction ID AND phone last 4 against data/transactions.csv
before drawing anything, so it can never produce a document for an unverified or someone else's
transaction. Only a Success gets a "Payment Receipt"; every other status gets a
"Transaction Status Statement" that says plainly it is not a successful payment.
Every page carries a DEMO / FICTIONAL TRANSACTION watermark.
"""
import csv
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from fpdf import FPDF

from . import config

NAVY, TEAL, INK, INK2, LINE = (11, 37, 64), (14, 140, 140), (11, 37, 64), (82, 96, 109), (220, 230, 239)
STATUS_COLORS = {"Success": ((227, 245, 236), (15, 138, 95)), "Failed": ((253, 232, 232), (180, 35, 24)),
                 "Pending": ((255, 244, 219), (138, 90, 0)), "Reversed": ((224, 242, 254), (7, 89, 133))}
STATUS_NOTES = {
    "Failed": "This payment FAILED. This statement is not a payment receipt. PaySetu policy: failed payments "
              "are reversed to the bank automatically within 3 working days.",
    "Pending": "This payment is PENDING and has not completed. This statement is not a payment receipt. "
               "PaySetu policy: a pending payment completes or is reversed on its own within 48 hours.",
    "Reversed": "This payment was REVERSED and did not complete. This statement is not a payment receipt.",
}


class ReceiptError(ValueError):
    """The transaction could not be verified, so no document is made."""


def verify(txn_id: str, phone_last4: str) -> dict:
    """Return the CSV row only if BOTH values match the same row; otherwise raise ReceiptError."""
    txn = re.sub(r"\s", "", str(txn_id or "")).upper()
    last4 = re.sub(r"\D", "", str(phone_last4 or ""))
    if not re.fullmatch(r"PS\d{10}", txn) or len(last4) != 4:
        raise ReceiptError("Transaction not verified.")
    with config.TRANSACTIONS_FILE.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["txn_id"].strip().upper() == txn and row["phone_last4"].strip() == last4:
                return {k: v.strip() for k, v in row.items()}
    raise ReceiptError("Transaction not verified.")


def _inr(amount: str) -> str:
    # Core PDF fonts have no ₹ glyph, so amounts are written as "INR".
    try:
        return f"INR {float(str(amount).replace(',', '')):,.2f}"
    except ValueError:
        return f"INR {amount}"


def make_pdf(txn_id: str, phone_last4: str, compress: bool = True) -> tuple[bytes, str]:
    """Build the PDF for a verified transaction. Returns (pdf bytes, file name)."""
    row = verify(txn_id, phone_last4)
    status = row["status"]
    is_receipt = status == "Success"
    title = "Payment Receipt" if is_receipt else "Transaction Status Statement"
    generated = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%b-%Y %H:%M IST")

    pdf = FPDF(format=(148, 210))  # A5 in mm
    pdf.set_compression(compress)
    pdf.set_title(f"PaySetu {title} {row['txn_id']} (DEMO)")
    pdf.set_author("PaySetu Wallet (fictional demo)")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    w = pdf.w

    # Watermark first, so everything else sits on top of it.
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(246, 206, 202)
    with pdf.rotation(32, x=w / 2, y=pdf.h / 2):
        pdf.set_xy(0, pdf.h / 2 - 16)
        pdf.cell(w, 14, "DEMO / FICTIONAL", align="C")
        pdf.set_xy(0, pdf.h / 2)
        pdf.cell(w, 14, "TRANSACTION", align="C")

    # Header band
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 0, w, 30, style="F")
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, w * 0.42, 30, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 8)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(80, 8, "PaySetu Wallet")
    pdf.set_xy(10, 16)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(60, 5, "UPI payments  |  wallet  |  bills")
    pdf.set_xy(w - 90, 11)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(80, 8, title, align="R")

    # Amount and status
    pdf.set_text_color(*INK)
    pdf.set_xy(0, 40)
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(w, 12, _inr(row["amount_inr"]), align="C")
    bg, fg = STATUS_COLORS.get(status, ((238, 241, 244), INK2))
    label = f"Status: {status}" if is_receipt else f"Status: {status} - not a successful payment"
    pdf.set_font("Helvetica", "B", 9.5)
    pill_w = pdf.get_string_width(label) + 12
    pdf.set_fill_color(*bg)
    pdf.set_text_color(*fg)
    pdf.set_xy((w - pill_w) / 2, 55)
    pdf.cell(pill_w, 7, label, align="C", fill=True)

    # Details table
    rows = [("Transaction ID", row["txn_id"]), ("Transaction date", row["date"]), ("Type", row["type"]),
            ("Amount", _inr(row["amount_inr"])), ("Status", status),
            ("Registered phone", "XXXXXX" + row["phone_last4"]), ("Document generated", generated)]
    y = 70
    pdf.set_draw_color(*LINE)
    for name, value in rows:
        pdf.set_xy(12, y)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*INK2)
        pdf.cell(55, 8, name)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*INK)
        pdf.cell(w - 24 - 55, 8, value, align="R")
        pdf.line(12, y + 8.5, w - 12, y + 8.5)
        y += 10

    # Status note (non-success) and disclaimer
    y += 4
    if not is_receipt:
        pdf.set_xy(12, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*fg)
        pdf.multi_cell(w - 24, 5, STATUS_NOTES.get(status, "This is not a payment receipt."))
        y = pdf.get_y() + 4
    pdf.set_xy(12, max(y, pdf.h - 32))
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*INK2)
    pdf.multi_cell(w - 24, 4, "DEMO DOCUMENT: PaySetu Wallet is a made-up business and this is a fictional "
                              "transaction from a practice project. This is not a real payment confirmation, "
                              "no money moved, and it cannot be used as proof of payment.")
    name = f"PaySetu_{'Receipt' if is_receipt else 'Statement'}_{row['txn_id']}_DEMO.pdf"
    return bytes(pdf.output()), name
