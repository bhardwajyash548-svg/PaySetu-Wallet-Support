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
