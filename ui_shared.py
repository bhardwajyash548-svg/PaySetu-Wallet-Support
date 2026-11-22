"""Shared Streamlit helpers: secrets, passcode gate, styling and the tickets sidebar."""
import os
import time

import streamlit as st

BRAND_CSS = """
<style>
:root { --ps-navy:#0B2540; --ps-blue:#1554A6; --ps-teal:#0E8C8C; --ps-mint:#E6F6F4; --ps-line:#D9E4EE; }
.block-container { padding-top: 1.6rem; max-width: 880px; }
.ps-hero { background: linear-gradient(120deg, var(--ps-blue) 0%, var(--ps-teal) 100%);
  color: #fff; border-radius: 18px; padding: 18px 22px; margin-bottom: 18px;
  display:flex; align-items:center; gap:14px; box-shadow: 0 6px 20px rgba(14,140,140,.18); }
.ps-hero .logo { width:44px; height:44px; border-radius:12px; background:rgba(255,255,255,.18);
  display:flex; align-items:center; justify-content:center; font-weight:800; font-size:20px; }
.ps-hero h1 { font-size: 1.35rem; margin: 0; color:#fff; padding:0; }
.ps-hero p { margin: 2px 0 0; opacity: .9; font-size: .9rem; }
/* Chat bubbles */
[data-testid="stChatMessage"] { border-radius: 16px; padding: 12px 14px; margin-bottom: 10px;
  border: 1px solid var(--ps-line); background: #fff; }
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {
  flex-direction: row-reverse; text-align: right; background: var(--ps-mint); border-color: #BFE6E1;
  margin-left: auto; max-width: 88%; width: fit-content; box-sizing: border-box; }
[data-testid="stChatMessage"]:not(:has([aria-label="Chat message from user"])) { max-width: 88%; box-sizing: border-box; }
/* Ticket cards in sidebar */
.ps-ticket { border:1px solid var(--ps-line); border-radius:12px; padding:8px 10px; margin-bottom:8px; background:#fff; }
.ps-ticket .id { font-weight:700; color: var(--ps-navy); }
.ps-badge { font-size:.72rem; font-weight:700; padding:2px 8px; border-radius:999px; float:right; }
.ps-high { background:#FDE8E8; color:#B42318; }
.ps-normal { background:#E0F2FE; color:#075985; }
.ps-ticket .reason { font-size:.8rem; color:#475467; margin-top:2px; }
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] { text-align:right; }
.ps-qa { font-size:.72rem; color:#0E8C8C; }

/* ---------- App wallpaper (all pages) ---------- */
[data-testid="stAppViewContainer"] {
  background-color: #F2F6FB;
  background-image:
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1440' height='420' viewBox='0 0 1440 420' preserveAspectRatio='none'%3E%3Cg fill='none' stroke-width='2'%3E%3Cpath stroke='%231554A6' stroke-opacity='.16' d='M0 170 C 260 70 520 270 780 170 S 1200 60 1440 150'/%3E%3Cpath stroke='%230E8C8C' stroke-opacity='.16' d='M0 230 C 300 130 560 330 840 220 S 1240 120 1440 210'/%3E%3Cpath stroke='%231554A6' stroke-opacity='.10' d='M0 290 C 320 200 600 380 900 280 S 1260 190 1440 270'/%3E%3C/g%3E%3C/svg%3E"),
    radial-gradient(rgba(11,37,64,.07) 1px, transparent 1.2px),
    radial-gradient(900px 480px at 8% -8%, rgba(21,84,166,.16), transparent 62%),
    radial-gradient(820px 520px at 100% 4%, rgba(14,140,140,.16), transparent 60%),
    radial-gradient(700px 420px at 60% 110%, rgba(21,84,166,.08), transparent 60%),
    linear-gradient(180deg, #F5F9FD 0%, #EDF3F8 100%);
  background-size: 100% 420px, 22px 22px, auto, auto, auto, auto;
  background-repeat: no-repeat, repeat, no-repeat, no-repeat, no-repeat, no-repeat;
  background-attachment: fixed;
}
[data-testid="stHeader"] { background: transparent; }

/* Hero banner: add a soft light sweep */
.ps-hero { position: relative; overflow: hidden; }
.ps-hero::after { content: ""; position: absolute; right: -60px; top: -80px; width: 260px; height: 260px;
  border-radius: 50%; background: radial-gradient(circle, rgba(255,255,255,.22), transparent 65%); }

/* ---------- Sidebar: deep navy fintech panel ---------- */
[data-testid="stSidebar"] {
  background: linear-gradient(185deg, #0B2540 0%, #0F355A 55%, #0E5560 100%);
  border-right: 1px solid rgba(255,255,255,.06);
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #E7F0F8 !important; }
[data-testid="stSidebarNav"] a { border-radius: 10px; }
[data-testid="stSidebarNav"] a:hover { background: rgba(255,255,255,.08); }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: rgba(255,255,255,.14); }
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.18); color: #fff; }
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
  background: rgba(255,255,255,.16); border-color: rgba(255,255,255,.35); }
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg { color: #E7F0F8; }
/* sidebar ticket cards keep dark text on white */
[data-testid="stSidebar"] .ps-ticket { border-color: rgba(255,255,255,.0); box-shadow: 0 4px 14px rgba(0,0,0,.18); }
[data-testid="stSidebar"] .ps-ticket span.ps-badge.ps-high { color:#B42318 !important; }
[data-testid="stSidebar"] .ps-ticket span.ps-badge.ps-normal { color:#075985 !important; }
[data-testid="stSidebar"] .ps-ticket .id { color: var(--ps-navy) !important; }
[data-testid="stSidebar"] .ps-ticket .reason { color:#475467 !important; }

/* Login card and chat input: white, lifted */
[data-testid="stForm"] { background: #fff; border: 1px solid #DCE6EF; border-radius: 16px;
  box-shadow: 0 8px 26px rgba(11,37,64,.08); }
[data-testid="stChatInput"] { box-shadow: 0 6px 20px rgba(11,37,64,.08); border-radius: 14px; }
[data-testid="stBottom"] > div { background: transparent; }
</style>
"""


def _secret(name: str) -> str:
    """Read a setting from Streamlit secrets (Streamlit Cloud / local secrets.toml),
    falling back to an environment variable (Render and other hosts)."""
    try:
        value = str(st.secrets.get(name, "")).strip()
    except Exception:  # no secrets.toml on this machine
        value = ""
    return value or os.environ.get(name, "").strip()


def load_secrets() -> None:
    """API key: Streamlit secrets on Streamlit Cloud, env var on Render, .env on a laptop."""
    for name in ("GOOGLE_API_KEY", "SMTP_USER", "SMTP_APP_PASSWORD", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM_NAME"):
        value = _secret(name)
        if value and not os.environ.get(name):
            os.environ[name] = value


def apply_style() -> None:
    st.markdown(BRAND_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="ps-hero"><div class="logo">₹</div><div><h1>{title}</h1><p>{subtitle}</p></div></div>',
        unsafe_allow_html=True,
    )


ADMIN_IDLE_SECONDS = 30 * 60


def _guard(key: str):
    from paysetu_agent.auth import LoginGuard

    if key not in st.session_state:
        st.session_state[key] = LoginGuard()
    return st.session_state[key]


def _locked_message(guard) -> None:
    mins, secs = divmod(guard.seconds_left(), 60)
    st.error(f"Too many wrong passcodes. Locked for {mins} min {secs:02d} s. Please try again later.")


def require_passcode() -> None:
    """Stop the page until the right APP_PASSCODE is entered (5 wrong tries = 5-minute lock)."""
    if st.session_state.get("unlocked"):
        return
    expected = _secret("APP_PASSCODE")
    hero("PaySetu Wallet Support", "Secure support chat with Setu")
    if not expected:
        st.error("APP_PASSCODE is not set. Add it to .streamlit/secrets.toml (laptop) or the app's Secrets (cloud).")
        st.stop()
    guard = _guard("app_guard")
    if guard.is_locked():
        _locked_message(guard)
        st.stop()
    with st.form("passcode_form"):
        entered = st.text_input("Enter passcode to continue", type="password")
        submitted = st.form_submit_button("Unlock", type="primary")
    if submitted:
        result = guard.attempt(entered, expected)
        if result == "ok":
            st.session_state.unlocked = True
            st.rerun()
        time.sleep(1)  # slows down guessing
        if result == "locked":
            _locked_message(guard)
        else:
            st.error(f"Wrong passcode. The chat stays locked. ({guard.tries_left()} tries left)")
    st.stop()


def require_admin() -> str:
    """Stop the page until an admin signs in with ADMIN_PASSCODE. Returns the admin's audit name."""
    from paysetu_agent import ticket_manager
    from paysetu_agent.auth import admin_actor, clean_admin_name

    if st.session_state.get("admin_ok") and time.time() - st.session_state.get("admin_seen", 0) > ADMIN_IDLE_SECONDS:
        ticket_manager.audit(admin_actor(st.session_state), "admin_timeout", "-", "signed out after 30 min idle")
        st.session_state.admin_ok = False
        st.session_state.admin_timed_out = True
    if st.session_state.get("admin_ok"):
        st.session_state.admin_seen = time.time()
        with st.sidebar:
            st.caption(f"Signed in as {st.session_state.admin_name} (admin)")
            if st.button("Sign out of admin", use_container_width=True):
                ticket_manager.audit(admin_actor(st.session_state), "admin_sign_out", "-")
                st.session_state.admin_ok = False
                st.rerun()
        return admin_actor(st.session_state)

    hero("Admin sign-in", "Ticket management and analytics are for PaySetu support staff only")
    if st.session_state.pop("admin_timed_out", False):
        st.info("You were signed out after 30 minutes without activity. Please sign in again.")
    expected = _secret("ADMIN_PASSCODE")
    if expected and expected.strip() == _secret("APP_PASSCODE").strip():
        st.error("ADMIN_PASSCODE must be different from APP_PASSCODE, otherwise every customer could open the "
                 "admin pages. Change it in secrets / environment settings.")
        st.stop()
    if not expected:
        st.error("ADMIN_PASSCODE is not set. Add it to .streamlit/secrets.toml (laptop) or the app's "
                 "Secrets / environment (cloud). Admin pages stay locked until then.")
        st.stop()
    guard = _guard("admin_guard")
    if guard.is_locked():
        _locked_message(guard)
        st.stop()
    with st.form("admin_form"):
        name = st.text_input("Your name (for the audit log)", max_chars=30)
        entered = st.text_input("Admin passcode", type="password")
        submitted = st.form_submit_button("Sign in as admin", type="primary")
    if submitted:
        clean = clean_admin_name(name)
        if not clean:
            st.error("Please enter your name. It is recorded with every admin action.")
            st.stop()
        result = guard.attempt(entered, expected)
        if result == "ok":
            st.session_state.admin_ok, st.session_state.admin_name = True, clean
            st.session_state.admin_seen = time.time()
            ticket_manager.audit(f"{clean} (admin)", "admin_sign_in", "-", "success")
            st.rerun()
        ticket_manager.audit(f"{clean} (unverified)", "admin_sign_in_failed", "-",
                             "locked for 5 minutes" if result == "locked" else "wrong passcode")
        time.sleep(1)
        if result == "locked":
            _locked_message(guard)
        else:
            st.error(f"Wrong admin passcode. ({guard.tries_left()} tries left)")
    st.stop()


def tickets_sidebar(session_id: str) -> None:
    """Open tickets from THIS chat only - customers never see other customers' tickets."""
    import html

    from paysetu_agent import ticket_manager

    st.sidebar.markdown("### Your open tickets")
    tickets = ticket_manager.open_tickets(session_id=session_id)
    if not tickets:
        st.sidebar.caption("No open tickets in this chat.")
        return
    for t in reversed(tickets[-15:]):  # newest first
        pr = t.get("priority", "normal") if t.get("priority") in ("high", "normal") else "normal"
        st.sidebar.markdown(
            f'<div class="ps-ticket"><span class="ps-badge ps-{pr}">{pr.upper()}</span>'
            f'<div class="id">{html.escape(t["ticket_id"])}</div>'
            f'<div class="reason">{html.escape(t.get("reason", ""))}</div></div>',
            unsafe_allow_html=True,
        )
