"""Tickets: IDs, priority rules, reasons, session privacy and old-file upgrade."""
import csv

from paysetu_agent import config, ticket_manager as tm


def test_ids_are_sequential_and_unique(tmp_logs):
    ids = [tm.create_ticket("issue", "Customer asked for a person", "normal")["ticket_id"] for _ in range(5)]
    assert ids == ["TKT-1001", "TKT-1002", "TKT-1003", "TKT-1004", "TKT-1005"]
    assert len(set(ids)) == 5


def test_fraud_is_always_high_priority(tmp_logs):
    t = tm.create_ticket("money taken", "Fraud or hacked account", "normal")
    assert t["priority"] == "high"
    t = tm.create_ticket("payment I did not do", "unknown transaction", "normal")
    assert (t["reason"], t["priority"]) == ("Unknown transaction", "high")


def test_bad_priority_falls_back_to_normal(tmp_logs):
    assert tm.create_ticket("x", "KYC rejected", "urgent!!")["priority"] == "normal"


def test_reason_normalisation():
    assert tm.normalise_reason("kyc got rejected") == "KYC rejected"
    assert tm.normalise_reason("customer is very angry") == "Angry or upset customer"
    assert tm.normalise_reason("wants a human") == "Customer asked for a person"
    assert tm.normalise_reason("something odd") == "Answer not in help docs"


def test_new_ticket_has_original_and_new_fields(tmp_logs):
    t = tm.create_ticket("issue", "KYC rejected", "normal", session_id="s1")
    for f in tm.ORIGINAL_FIELDS:
        assert f in t
    assert t["status"] == "open" and t["session_id"] == "s1" and t["updated_at"]
    with config.TICKETS_FILE.open() as f:
        header = next(csv.reader(f))
    assert header[:6] == tm.ORIGINAL_FIELDS  # brief's columns stay first


def test_customer_sees_only_own_session_tickets(tmp_logs):
    tm.create_ticket("mine", "KYC rejected", "normal", session_id="me")
    tm.create_ticket("someone else", "Fraud or hacked account", "high", session_id="other")
    mine = tm.open_tickets(session_id="me")
    assert [t["customer_message"] for t in mine] == ["mine"]
    assert len(tm.open_tickets()) == 2  # admin view sees all


def test_old_ticket_file_is_upgraded_without_losing_rows(tmp_logs):
    with config.TICKETS_FILE.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(tm.ORIGINAL_FIELDS)
        w.writerow(["TKT-1001", "2026-11-22 05:28:06", "old ticket", "Fraud or hacked account", "high", "open"])
    t = tm.create_ticket("new ticket", "KYC rejected", "normal")
    assert t["ticket_id"] == "TKT-1002"  # numbering continues
    rows = tm.all_tickets()
    assert [r["customer_message"] for r in rows] == ["old ticket", "new ticket"]
    assert rows[0]["session_id"] == "" and "summary" in rows[0]


def test_update_fields_only_touches_allowed_columns(tmp_logs):
    t = tm.create_ticket("issue", "KYC rejected", "normal")
    updated = tm.update_fields(t["ticket_id"], summary="handoff text", time="1999-01-01", bogus="x")
    assert updated["summary"] == "handoff text"
    saved = tm.get_ticket("TKT-1001")
    assert saved["summary"] == "handoff text"
    assert saved["time"] == t["time"]  # creation time can never be rewritten
    assert "bogus" not in saved
    assert tm.update_fields("TKT-4040", summary="nope") is None
