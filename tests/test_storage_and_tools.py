"""Chat log schema, secret redaction, outcome labels and the two code-only tools."""
import csv

from paysetu_agent import config, storage, tools
from paysetu_agent.chat import BUSY_REPLY, classify_outcome
from paysetu_agent.prompts import NO_INFO_REPLY
from paysetu_agent.safety import redact


# ---------- chat log ----------
def test_chat_log_keeps_brief_columns_first_and_adds_new_ones(tmp_logs):
    storage.log_chat("hi", "hello", "none", session_id="s1", outcome="Other", response_ms=120)
    with config.CHAT_LOG_FILE.open() as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0])[:4] == ["time", "message", "reply", "source"]
    assert rows[0]["session_id"] == "s1" and rows[0]["response_ms"] == "120"


def test_old_chat_log_is_upgraded(tmp_logs):
    with config.CHAT_LOG_FILE.open("w", newline="") as f:
        csv.writer(f).writerows([["time", "message", "reply", "source"], ["t", "old q", "old a", "none"]])
    storage.log_chat("new q", "new a", "none", session_id="s2")
    rows = storage.read_rows(config.CHAT_LOG_FILE)
    assert [r["message"] for r in rows] == ["old q", "new q"]
    assert rows[0]["session_id"] == "" and rows[1]["session_id"] == "s2"


# ---------- redaction (original guardrail regression) ----------
def test_redaction_removes_secrets_but_keeps_lookup_details():
    cases = {
        "My UPI PIN is 4821": "4821",
        "otp: 552311 aaya hai": "552311",
        "मेरा पिन 1234 है": "1234",
        "card 4111 1111 1111 1111 cvv 123": "4111",
        "account number 123456789012": "123456789012",
    }
    for text, secret in cases.items():
        safe, found = redact(text)
        assert secret not in safe and found, text
    safe, found = redact("Transaction ID PS9995683007, phone ends in 7938")
    assert "PS9995683007" in safe and "7938" in safe and not found


# ---------- outcomes ----------
def test_outcome_labels():
    assert classify_outcome(BUSY_REPLY, "none", []) == "Service busy"
    assert classify_outcome("Your ticket ID is TKT-1001.", "none", ["TKT-1001"]) == "Ticket created"
    assert classify_outcome("₹1,00,000 a day. (Source: FAQ: x)", "FAQ: x", []) == "Answered from help docs"
    assert classify_outcome(NO_INFO_REPLY, "none", []) == "Not in help docs"
    assert classify_outcome("I'm sorry, I can only help with PaySetu questions.", "none", []) == "Off-topic declined"


# ---------- transaction lookup (original optional feature) ----------
def test_lookup_needs_both_details_on_same_row(tool_ctx):
    ok = tools.get_transaction_status("PS9995683007", "7938", tool_ctx)
    assert ok["status"] == "found" and ok["transaction"]["status"] == "Success"
    assert tools.get_transaction_status("PS9995683007", "0000", tool_ctx) == {"status": "not found"}
    # right phone digits but from a different row
    assert tools.get_transaction_status("PS9995683007", "3067", tool_ctx) == {"status": "not found"}


def test_lookup_rejects_bad_input_and_limits_attempts(tool_ctx):
    assert tools.get_transaction_status("all", "7938", tool_ctx) == {"status": "not found"}
    assert tools.get_transaction_status("PS9995683007", "79", tool_ctx) == {"status": "not found"}
    for _ in range(3):
        tools.get_transaction_status("PS0000000000", "1111", tool_ctx)
    assert tools.get_transaction_status("PS9995683007", "7938", tool_ctx)["status"] == "limit reached"


def test_failed_transaction_needs_action(tool_ctx):
    r = tools.get_transaction_status("PS6543961946", "3067", tool_ctx)
    assert r["transaction"]["status"] == "Failed" and r["needs_action"] is True


# ---------- create_ticket tool ----------
def test_create_ticket_tool_links_session_and_returns_code_made_id(tmp_logs, tool_ctx):
    r = tools.create_ticket("Unauthorised ₹20,000 debit", "Fraud or hacked account", "normal", tool_ctx)
    assert r["status"] == "created" and r["ticket_id"] == "TKT-1001" and r["priority"] == "high"
    saved = storage.read_rows(config.TICKETS_FILE)[0]
    assert saved["session_id"] == "session-test-1"
