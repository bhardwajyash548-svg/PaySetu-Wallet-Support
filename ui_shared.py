"""Shared Streamlit helpers: secrets, passcode gate, styling and the tickets sidebar."""
import hmac
import os

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
  margin-left: 12%; }
[data-testid="stChatMessage"]:not(:has([aria-label="Chat message from user"])) { margin-right: 12%; }
/* Ticket cards in sidebar */
.ps-ticket { border:1px solid var(--ps-line); border-radius:12px; padding:8px 10px; margin-bottom:8px; background:#fff; }
.ps-ticket .id { font-weight:700; color: var(--ps-navy); }
.ps-badge { font-size:.72rem; font-weight:700; padding:2px 8px; border-radius:999px; float:right; }
.ps-high { background:#FDE8E8; color:#B42318; }
.ps-normal { background:#E0F2FE; color:#075985; }
.ps-ticket .reason { font-size:.8rem; color:#475467; margin-top:2px; }
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] { text-align:right; }
.ps-qa { font-size:.72rem; color:#0E8C8C; }
</style>
"""


def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:  # no secrets.toml on this machine
        return ""


def load_secrets() -> None:
    """On Streamlit Cloud the API key lives in secrets; locally it comes from .env."""
    key = _secret("GOOGLE_API_KEY")
    if key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = key


def apply_style() -> None:
    st.markdown(BRAND_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="ps-hero"><div class="logo">₹</div><div><h1>{title}</h1><p>{subtitle}</p></div></div>',
        unsafe_allow_html=True,
    )


def require_passcode() -> None:
    """Stop the page until the right APP_PASSCODE is entered."""
    if st.session_state.get("unlocked"):
        return
    expected = _secret("APP_PASSCODE")
    hero("PaySetu Wallet Support", "Secure support chat with Setu")
    if not expected:
        st.error("APP_PASSCODE is not set. Add it to .streamlit/secrets.toml (laptop) or the app's Secrets (cloud).")
        st.stop()
    with st.form("passcode_form"):
        entered = st.text_input("Enter passcode to continue", type="password")
        submitted = st.form_submit_button("Unlock", type="primary")
    if submitted:
        if hmac.compare_digest(entered.strip(), expected):
            st.session_state.unlocked = True
            st.rerun()
        st.error("Wrong passcode. The chat stays locked.")
    st.stop()


def tickets_sidebar() -> None:
    from paysetu_agent import storage

    st.sidebar.markdown("### Open support tickets")
    tickets = storage.open_tickets()
    if not tickets:
        st.sidebar.caption("No open tickets yet.")
        return
    for t in reversed(tickets[-15:]):  # newest first
        pr = t.get("priority", "normal")
        st.sidebar.markdown(
            f'<div class="ps-ticket"><span class="ps-badge ps-{pr}">{pr.upper()}</span>'
            f'<div class="id">{t["ticket_id"]}</div><div class="reason">{t.get("reason", "")}</div></div>',
            unsafe_allow_html=True,
        )
    if len(tickets) > 15:
        st.sidebar.caption(f"Showing 15 newest of {len(tickets)} open tickets.")
