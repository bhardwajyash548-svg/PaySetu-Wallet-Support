"""Passcodes, lockout, admin identity and unauthorized-access protection."""
from pathlib import Path

import pytest

from paysetu_agent import config, storage, ticket_manager as tm
from paysetu_agent.auth import (LOCK_SECONDS, MAX_ATTEMPTS, LoginGuard, admin_actor, clean_admin_name,
                                passcode_matches)

ROOT = Path(__file__).resolve().parent.parent


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def test_passcode_matching():
    assert passcode_matches("1234", "1234") and passcode_matches(" 1234 ", "1234")
    assert not passcode_matches("1235", "1234")
    assert not passcode_matches("", "")          # an unset passcode never opens anything
    assert not passcode_matches("anything", "")


def test_lockout_after_five_wrong_tries_even_for_right_passcode():
    clock = Clock()
    g = LoginGuard(now=clock)
    for i in range(MAX_ATTEMPTS - 1):
        assert g.attempt("wrong", "secret") == "wrong"
    assert g.tries_left() == 1
    assert g.attempt("wrong", "secret") == "locked"
    assert g.attempt("secret", "secret") == "locked"      # right passcode refused while locked
    assert 0 < g.seconds_left() <= LOCK_SECONDS
    clock.t += LOCK_SECONDS + 1
    assert g.attempt("secret", "secret") == "ok"           # works again after the lock


def test_success_resets_the_counter():
    g = LoginGuard(now=Clock())
    g.attempt("x", "secret"), g.attempt("x", "secret")
    assert g.attempt("secret", "secret") == "ok" and g.tries_left() == MAX_ATTEMPTS


def test_admin_name_is_cleaned():
    assert clean_admin_name("  Yash <script>alert(1)</script> ") == "Yash scriptalert1script"
    assert clean_admin_name("A" * 50) == "A" * 30
    assert clean_admin_name("   ") == ""


@pytest.mark.parametrize("state", [{}, {"admin_ok": False, "admin_name": "Yash"}, {"admin_ok": True, "admin_name": ""}])
def test_admin_actor_requires_sign_in(state):
    with pytest.raises(PermissionError):
        admin_actor(state)


def test_signed_in_admin_can_change_tickets_and_is_audited(tmp_logs):
    tid = tm.create_ticket("x", "KYC rejected", "normal")["ticket_id"]
    actor = admin_actor({"admin_ok": True, "admin_name": "Yash"})
    tm.change_status(tid, "in_progress", actor, "checking")
    a = storage.read_rows(config.AUDIT_LOG_FILE)[-1]
    assert (a["actor"], a["action"], a["target"]) == ("Yash (admin)", "change_status", tid)


def test_customer_cannot_change_tickets(tmp_logs):
    tid = tm.create_ticket("x", "KYC rejected", "normal")["ticket_id"]
    with pytest.raises(PermissionError):
        tm.change_status(tid, "closed", admin_actor({"unlocked": True}))  # customer session, no admin
    assert tm.get_ticket(tid)["status"] == "open"


def test_admin_pages_check_sign_in_before_reading_any_ticket():
    src = (ROOT / "views" / "admin_tickets.py").read_text()
    gate = src.index("admin = require_admin()")
    for data_call in ("tm.all_tickets()", "tm.get_ticket(", "read_rows(", "tm.change_status("):
        assert gate < src.index(data_call), data_call


def test_every_page_is_behind_the_app_passcode():
    src = (ROOT / "app.py").read_text()
    assert src.index("require_passcode()") < src.index("st.navigation(")


def test_admin_passcode_is_never_committed():
    ignored = (ROOT / ".gitignore").read_text()
    assert ".streamlit/secrets.toml" in ignored and ".env" in ignored
    for f in ("render.yaml", "README.md", "app.py", "ui_shared.py"):
        text = (ROOT / f).read_text()
        assert 'ADMIN_PASSCODE = "admin-' not in text


def test_customer_dashboard_shows_no_customer_text():
    src = (ROOT / "views" / "dashboard.py").read_text()
    table = src[src.index('st.subheader("Recent tickets")') if 'st.subheader("Recent tickets")' in src
                else src.index('card("Recent tickets")'):]
    assert '"customer_message"' not in table and '"summary"' not in table
