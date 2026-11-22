"""Fraud detection: explainable rules, three levels, reasons always given."""
import pytest

from paysetu_agent.fraud_detection import assess, combine

CASES = [
    ("₹20,000 was taken from my account and I didn't do it!", "High"),
    ("I think my account is hacked", "High"),
    ("I shared my OTP with a caller and now ₹8,000 is gone", "High"),
    ("Maine nahi kiya ye payment, ₹3,000 kat gaye", "High"),
    ("मैंने नहीं किया, पैसे कट गए", "High"),
    ("Someone called for KYC update and asked for my OTP, I did not share", "Medium"),
    ("I got a lottery message, is it a scam?", "Medium"),
    ("A customer care number asked me to install AnyDesk", "Medium"),
    ("What is the daily UPI limit?", "Low"),
    ("My payment failed but money was deducted", "Low"),
    ("Is my wallet safe? any fraud protection?", "Low"),
    ("I sent ₹500 to my friend by mistake. Reverse it.", "Low"),
]


@pytest.mark.parametrize("text,level", CASES)
def test_levels(text, level):
    r = assess(text)
    assert r["level"] == level, r
    assert r["reasons"]  # always explained


def test_big_amount_alone_is_not_fraud():
    assert assess("I want to send ₹50,000 to my brother")["level"] == "Low"


def test_typed_secret_adds_risk():
    plain = assess("someone asked for my otp")["points"]
    assert assess("someone asked for my otp", removed_secrets=["OTP"])["points"] == plain + 1


def test_verified_transaction_strengthens_report():
    txn = {"txn_id": "PS9995683007", "status": "Success", "amount_inr": "860"}
    with_txn = assess("I did not do this payment", transaction=txn)
    assert with_txn["level"] == "High"
    assert any("PS9995683007" in r for r in with_txn["reasons"])
    assert combine(assess("I did not do this payment"), with_txn) is with_txn


def test_scam_without_loss_is_capped_at_medium():
    r = assess("lottery prize scam fraud asking for otp, click the link")
    assert r["level"] == "Medium" and any("capped" in x for x in r["reasons"])
