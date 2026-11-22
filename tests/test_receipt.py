"""PDF receipts: only for verified transactions, honest titles, watermark, no leaks."""
import pytest

from paysetu_agent.receipt_generator import ReceiptError, make_pdf


def text_of(pdf: bytes) -> str:
    """All text drawn on the page, wrapped lines joined with spaces (needs compress=False)."""
    import re
    raw = pdf.decode("latin-1")
    parts = re.findall(r"\((.*?)(?<!\\)\)\s*Tj", raw)
    return " ".join(p.replace("\\(", "(").replace("\\)", ")") for p in parts) + " " + raw


def test_success_gets_payment_receipt():
    pdf, name = make_pdf("PS9995683007", "7938", compress=False)
    t = text_of(pdf)
    assert pdf.startswith(b"%PDF") and name == "PaySetu_Receipt_PS9995683007_DEMO.pdf"
    assert "Payment Receipt" in t and "Status: Success" in t and "INR 860.00" in t
    assert "DEMO / FICTIONAL" in t and "TRANSACTION" in t and "PaySetu Wallet" in t


@pytest.mark.parametrize("txn,phone,status", [
    ("PS6543961946", "3067", "Failed"),
    ("PS3499814198", "8561", "Pending"),
    ("PS7798006033", "7572", "Reversed"),
])
def test_non_success_is_never_called_a_receipt(txn, phone, status):
    pdf, name = make_pdf(txn, phone, compress=False)
    t = text_of(pdf)
    assert "Transaction Status Statement" in t and "Payment Receipt" not in t
    assert f"Status: {status} - not a successful payment" in t
    assert "not a payment receipt" in t and "Statement" in name


@pytest.mark.parametrize("txn,phone", [
    ("PS9995683007", "0000"),   # wrong phone
    ("PS9995683007", "3067"),   # phone from a DIFFERENT row
    ("PS0000000000", "7938"),   # unknown ID
    ("all", "7938"),            # not an ID
    ("PS9995683007", ""),       # missing phone
])
def test_unverified_requests_get_nothing(txn, phone):
    with pytest.raises(ReceiptError):
        make_pdf(txn, phone)


def test_receipt_masks_phone_and_hides_other_customers():
    t = text_of(make_pdf("PS9995683007", "7938", compress=False)[0])
    assert "XXXXXX7938" in t
    for other in ("PS6543961946", "PS4348326222", "3067"):
        assert other not in t


def test_lookup_tool_returns_phone_for_reverification(tool_ctx):
    from paysetu_agent import tools
    r = tools.get_transaction_status("PS9995683007", "7938", tool_ctx)
    assert r["transaction"]["phone_last4"] == "7938"
    assert make_pdf(r["transaction"]["txn_id"], r["transaction"]["phone_last4"])[0].startswith(b"%PDF")


def test_pipeline_attaches_journey_and_receipt(fake_setu, monkeypatch):
    txn = {"txn_id": "PS6543961946", "type": "Bill payment", "amount_inr": "4000", "date": "16-Nov-2026",
           "status": "Failed", "phone_last4": "3067"}
    chat, _ = fake_setu(draft="It shows Failed.",
                        tool_results=[("get_transaction_status", {"status": "found", "transaction": txn})])
    out = chat.respond("PS6543961946, phone 3067")
    assert out["journey"]["txn_id"] == "PS6543961946" and out["receipt"] == {"txn_id": "PS6543961946",
                                                                           "phone_last4": "3067"}
    from paysetu_agent import chat as chat_mod
    monkeypatch.setattr(chat_mod, "_run", lambda runner, sid, text: ("You're welcome!", []))
    later = chat.respond("thanks")
    assert later["journey"] is None and later["receipt"] is None  # only shown when looked up
