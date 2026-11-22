"""E6 security hardening: each fix from the security review has a test."""
from pathlib import Path

import pytest

from paysetu_agent import config, storage, ticket_manager as tm
from paysetu_agent.storage import csv_safe

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("value,expected", [
    ("=HYPERLINK(\"http://x\",\"click\")", "'=HYPERLINK(\"http://x\",\"click\")"),
    ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
    ("@SUM(1+1)", "'@SUM(1+1)"),
    ("-2+3", "'-2+3"),
    ("-0.67", "-0.67"),          # real numbers stay numbers
    ("What is the daily UPI limit?", "What is the daily UPI limit?"),
    (120, 120),
])
def test_csv_formula_injection_is_neutralised(value, expected):
    assert csv_safe(value) == expected


def test_logged_formula_is_stored_safely(tmp_logs):
    storage.log_chat("=HYPERLINK(\"http://evil\",\"x\")", "reply", "none", sentiment_score=-0.5)
    row = storage.read_rows(config.CHAT_LOG_FILE)[0]
    assert row["message"].startswith("'=") and row["sentiment_score"] == "-0.5"


def test_ai_written_ticket_text_is_cleaned(tmp_logs):
    t = tm.create_ticket("Customer said UPI PIN is 4821 and phone 9876543210", "Fraud or hacked account", "high")
    assert "4821" not in t["customer_message"] and "9876543210" not in t["customer_message"]
    assert "XXXXXX3210" in t["customer_message"]


def test_customer_start_error_hides_details():
    src = (ROOT / "views" / "chat.py").read_text()
    assert 'st.error(f"Setu could not start: {exc}")' not in src
    assert "Setu is unavailable right now" in src


def test_admin_passcode_must_differ_and_sessions_time_out():
    src = (ROOT / "ui_shared.py").read_text()
    assert "ADMIN_PASSCODE must be different from APP_PASSCODE" in src
    assert "ADMIN_IDLE_SECONDS = 30 * 60" in src and "admin_timeout" in src


def test_chat_has_a_message_cap():
    src = (ROOT / "views" / "chat.py").read_text()
    assert "MAX_MESSAGES_PER_CHAT = 60" in src and "reached its message limit" in src


def test_local_passcodes_differ():
    """The laptop secrets file (if present) must not reuse the customer passcode for admin."""
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if not secrets.exists():
        pytest.skip("no local secrets file")
    vals = dict(line.split(" = ", 1) for line in secrets.read_text().splitlines() if " = " in line)
    if "ADMIN_PASSCODE" in vals:
        assert vals["ADMIN_PASSCODE"].strip() != vals.get("APP_PASSCODE", "").strip()
