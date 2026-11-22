"""Payment journey: facts only, correct policy per status, honest next steps."""
from datetime import date

import pytest

from paysetu_agent.payment_journey import build_journey, parse_date, working_days_after

TODAY = date(2026, 11, 22)  # a Sunday
TXNS = {
    "Success": {"txn_id": "PS9995683007", "type": "Send money", "amount_inr": "860", "date": "11-Nov-2026", "status": "Success"},
    "Failed": {"txn_id": "PS6543961946", "type": "Bill payment", "amount_inr": "4000", "date": "16-Nov-2026", "status": "Failed"},
    "Pending": {"txn_id": "PS3499814198", "type": "Bill payment", "amount_inr": "750", "date": "20-Nov-2026", "status": "Pending"},
    "Reversed": {"txn_id": "PS7798006033", "type": "Bill payment", "amount_inr": "750", "date": "17-Nov-2026", "status": "Reversed"},
}


def test_working_days_skip_weekends():
    assert working_days_after(date(2026, 11, 16), date(2026, 11, 22)) == 4   # Mon -> Sun: Tue-Fri
    assert working_days_after(date(2026, 11, 20), date(2026, 11, 23)) == 1   # Fri -> Mon
    assert working_days_after(date(2026, 11, 22), date(2026, 11, 22)) == 0
    assert parse_date("16-Nov-2026") == date(2026, 11, 16) and parse_date("bad") is None


@pytest.mark.parametrize("status,needs_ticket,title", [
    ("Success", False, "Payment Receipt"),
    ("Failed", True, "Transaction Status Statement"),     # 4 working days > 3
    ("Pending", False, "Transaction Status Statement"),   # 2 days, within 48 h
    ("Reversed", False, "Transaction Status Statement"),
])
def test_each_status(status, needs_ticket, title):
    j = build_journey(TXNS[status], TODAY)
    assert j["needs_ticket"] is needs_ticket and j["receipt_title"] == title
    facts = [s for s in j["steps"] if s["kind"] == "fact"]
    assert [s["value"] for s in facts] == [TXNS[status]["date"], status]   # only real facts
    assert j["steps"][-1]["kind"] == "policy" and j["source"] == "Failed, pending and wrong payments policy"


def test_failed_within_window_says_wait():
    j = build_journey(TXNS["Failed"], date(2026, 11, 18))  # 2 working days
    assert not j["needs_ticket"] and "wait up to 1 more working day" in j["next_action"]


def test_pending_past_48_hours_needs_ticket():
    j = build_journey(TXNS["Pending"], date(2026, 11, 24))
    assert j["needs_ticket"] and "48" in j["next_action"]


def test_no_invented_events():
    for status, txn in TXNS.items():
        text = str(build_journey(txn, TODAY)).lower()
        for word in ("npci", "bank confirmed", "credited at", "processing at bank", "utr"):
            assert word not in text, (status, word)


def test_amount_is_formatted_exactly():
    assert build_journey(TXNS["Failed"], TODAY)["facts"]["amount"] == "₹4,000"
