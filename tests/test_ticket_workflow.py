"""Smart classification, status workflow, history and audit log."""
import pytest

from paysetu_agent import config, storage, ticket_manager as tm
from paysetu_agent.ticket_manager import TicketError


@pytest.mark.parametrize("message,reason,txn,fraud,category", [
    ("money taken", "Fraud or hacked account", None, "Low", "Fraud"),
    ("upset", "Angry or upset customer", None, "High", "Fraud"),
    ("KYC got rejected", "KYC rejected", None, "Low", "KYC"),
    ("PAN card rejected", "", None, "Low", "KYC"),
    ("bill payment failed", "Transaction needs action", {"status": "Failed"}, "Low", "Payment Failure"),
    ("payment failed, money deducted 5 days ago", "Failed payment not reversed after 3 working days", None, "Low",
     "Payment Failure"),
    ("payment stuck", "Transaction needs action", {"status": "Pending"}, "Low", "Pending Payment"),
    ("my payment is pending since yesterday", "Customer asked for a person", None, "Low", "Pending Payment"),
    ("electricity bill shows unpaid", "Customer asked for a person", None, "Low", "Bills"),
    ("cashback not received", "Angry or upset customer", None, "Low", "Cashback"),
    ("wallet limit raise", "Answer not in help docs", None, "Low", "Wallet"),
    ("loyalty points?", "Answer not in help docs", None, "Low", "Other"),
    ("my company expanded", "Answer not in help docs", None, "Low", "Other"),  # "pan" inside a word
    ("मेरा बिजली का बिल", "", None, "Low", "Bills"),
])
def test_classification(message, reason, txn, fraud, category):
    assert tm.classify(message, reason, txn, fraud) == category


def test_new_ticket_is_classified_and_has_history(tmp_logs):
    t = tm.create_ticket("My KYC was rejected twice", "KYC rejected", "normal")
    assert t["category"] == "KYC" and t["priority"] == "normal"
    h = tm.history(t["ticket_id"])
    assert len(h) == 1 and (h[0]["from_status"], h[0]["to_status"], h[0]["changed_by"]) == ("", "open", "system")


def test_full_lifecycle_with_history_and_audit(tmp_logs):
    tid = tm.create_ticket("fraud", "Fraud or hacked account", "high")["ticket_id"]
    tm.change_status(tid, "in_progress", "admin", "Called customer")
    tm.change_status(tid, "Resolved", "admin")           # label form accepted
    tm.change_status(tid, "closed", "admin", "Confirmed with bank")
    assert tm.get_ticket(tid)["status"] == "closed"
    steps = [(h["from_status"], h["to_status"]) for h in tm.history(tid)]
    assert steps == [("", "open"), ("open", "in_progress"), ("in_progress", "resolved"), ("resolved", "closed")]
    audit = storage.read_rows(config.AUDIT_LOG_FILE)
    assert len(audit) == 3 and all(a["actor"] == "admin" and a["target"] == tid for a in audit)
    assert "In Progress -> Resolved" in audit[1]["details"]
    # original fields untouched
    t = tm.get_ticket(tid)
    assert (t["ticket_id"], t["reason"], t["priority"], t["customer_message"]) == (tid, "Fraud or hacked account",
                                                                                 "high", "fraud")


def test_reopen_is_allowed(tmp_logs):
    tid = tm.create_ticket("x", "KYC rejected", "normal")["ticket_id"]
    tm.change_status(tid, "closed", "admin")
    tm.change_status(tid, "open", "admin", "Customer replied")
    assert tm.get_ticket(tid)["status"] == "open"


@pytest.mark.parametrize("ticket_id,status,actor,message", [
    ("TKT-1001", "in_progress", "", "Only an authenticated admin"),      # no admin
    ("TKT-1001", "in_progress", "   ", "Only an authenticated admin"),
    ("TKT-1001", "deleted", "admin", "Unknown status"),
    ("TKT-1001", "open", "admin", "already Open"),
    ("TKT-9999", "closed", "admin", "not found"),
])
def test_bad_changes_are_refused(tmp_logs, ticket_id, status, actor, message):
    tm.create_ticket("x", "KYC rejected", "normal")
    with pytest.raises(TicketError, match=message):
        tm.change_status(ticket_id, status, actor)
    assert tm.get_ticket("TKT-1001")["status"] == "open"
    assert storage.read_rows(config.AUDIT_LOG_FILE) == []  # nothing logged for refused changes


def test_closed_cannot_jump_to_resolved(tmp_logs):
    tid = tm.create_ticket("x", "KYC rejected", "normal")["ticket_id"]
    tm.change_status(tid, "closed", "admin")
    with pytest.raises(TicketError, match="Cannot move"):
        tm.change_status(tid, "resolved", "admin")


def test_ids_still_unique_after_status_changes(tmp_logs):
    a = tm.create_ticket("a", "KYC rejected", "normal")["ticket_id"]
    tm.change_status(a, "closed", "admin")
    b = tm.create_ticket("b", "KYC rejected", "normal")["ticket_id"]
    assert (a, b) == ("TKT-1001", "TKT-1002")


def test_old_tickets_get_a_category_when_read(tmp_logs):
    import csv
    with config.TICKETS_FILE.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(tm.ORIGINAL_FIELDS)
        w.writerow(["TKT-1001", "2026-11-22 05:28:06", "unauthorised debit", "Fraud or hacked account", "high", "open"])
    assert tm.all_tickets()[0]["category"] == "Fraud"
