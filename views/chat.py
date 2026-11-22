"""Chat page: talk to Setu."""
import html

import streamlit as st

from ui_shared import hero, tickets_sidebar

MAX_MESSAGES_PER_CHAT = 60  # protects the Gemini quota from one runaway session

USER_MARK = '<span class="ps-user"></span>'  # lets CSS style customer bubbles

JOURNEY_CSS = """
<style>
.ps-journey { border:1px solid #DCE6EF; border-radius:14px; padding:12px 14px; margin-top:8px; background:#FBFDFF; }
.ps-journey .top { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:.84rem; color:#52606D; margin-bottom:10px; }
.ps-journey .top b { color:#0B2540; }
.ps-journey .ok { background:#E3F5EC; color:#0f8a5f; border-radius:999px; padding:1px 8px; font-weight:700; font-size:.75rem; }
.ps-steps { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }
@media (max-width:640px) { .ps-steps { grid-template-columns:minmax(0,1fr); } }
.ps-step { border:1px solid #DCE6EF; border-radius:12px; padding:8px 10px; background:#fff; min-width:0; }
.ps-step .k { font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; color:#8394A5; font-weight:700; }
.ps-step .v { font-weight:700; margin-top:2px; color:#0B2540; }
.ps-step .d { font-size:.78rem; color:#52606D; }
.ps-step.policy { border-style:dashed; }
.ps-step.ok { background:#E3F5EC; border-color:#BDE5CF; } .ps-step.ok .v { color:#0f8a5f; }
.ps-step.bad { background:#FDE8E8; border-color:#F3C2C2; } .ps-step.bad .v { color:#B42318; }
.ps-step.wait { background:#FFF4DB; border-color:#F5D08A; } .ps-step.wait .v { color:#8A5A00; }
.ps-journey .next { font-size:.86rem; margin-top:10px; color:#0B2540; }
.ps-journey .note { font-size:.74rem; color:#8394A5; margin-top:4px; }
</style>
"""

EXAMPLES = [
    "What is the daily UPI limit?",
    "₹20,000 was taken from my account and I didn't do it!",
    "Check my transaction PS9995683007, phone ends in 7938",
    "Cashback kab milega?",
]


@st.cache_resource(show_spinner="Preparing Setu (first start builds the help docs index)...")
def load_engine():
    from paysetu_agent import chat, config  # heavy import: agents + index

    return chat, config


def render_journey(m: dict, idx: int) -> None:
    """Payment journey card + PDF download for a transaction verified in THIS chat."""
    from paysetu_agent.receipt_generator import ReceiptError, make_pdf

    j = m.get("journey")
    if not j:
        return
    e = html.escape
    steps = "".join(
        f'<div class="ps-step {"policy" if s["kind"] == "policy" else s["tone"]}"><div class="k">{e(s["label"])}</div>'
        f'<div class="v">{e(s["value"])}</div><div class="d">{e(s["detail"])}</div></div>' for s in j["steps"])
    st.markdown(
        f'<div class="ps-journey"><div class="top"><span>Payment journey</span><span>ID <b>{e(j["txn_id"])}</b></span>'
        f'<span>{e(j["facts"]["type"])} · <b>{e(j["facts"]["amount"])}</b></span>'
        f'<span class="ok">Verified: ID + phone last 4</span></div><div class="ps-steps">{steps}</div>'
        f'<div class="next"><b>Next:</b> {e(j["next_action"])}</div>'
        f'<div class="note">Shows only PaySetu records and policy (Source: {e(j["source"])}). '
        f'No live bank updates are shown.</div></div>', unsafe_allow_html=True)

    from paysetu_agent import emailer

    cols = st.columns(2)
    r = m.get("receipt") or {}
    doc = "receipt" if j["facts"]["status"] == "Success" else "status statement"
    if emailer.is_configured():
        # Setu emails the PDF: it asks for the address, then calls send_receipt_email.
        if cols[0].button(f"📧 Email me this {doc}", key=f"mail{idx}", use_container_width=True):
            st.session_state.pending_prompt = f"Please email the {doc} for transaction {j['txn_id']} to me."
            st.rerun()
    else:
        # Fallback when email is not set up on this server, so the demo always works.
        try:
            data, name = make_pdf(r.get("txn_id", ""), r.get("phone_last4", ""))  # re-verifies both values
            cols[0].download_button(f"⬇ Download {doc} (PDF)", data=data, file_name=name, mime="application/pdf",
                                    key=f"pdf{idx}", use_container_width=True)
        except ReceiptError:
            cols[0].caption("Document unavailable: transaction not verified.")
    if j["needs_ticket"] and not m.get("ticketed"):
        if cols[1].button("Raise a ticket for this payment", key=f"tkt{idx}", use_container_width=True):
            st.session_state.pending_prompt = f"Please raise a ticket for transaction {j['txn_id']}."
            m["ticketed"] = True
            st.rerun()


def main():
    hero("PaySetu Wallet Support", "Setu answers from PaySetu's official help docs · English & हिंदी")
    try:
        chat, config = load_engine()
    except Exception as exc:
        import logging
        logging.exception("Setu could not start: %s", exc)  # details go to the server log only
        st.error("Setu is unavailable right now. Please try again in a few minutes.")
        st.stop()

    if "setu" not in st.session_state:
        st.session_state.setu = chat.SetuChat()
        st.session_state.messages = [{"role": "assistant", "content": config.GREETING}]

    with st.sidebar:
        if st.button("➕ New chat", use_container_width=True):
            for k in ("setu", "messages", "pending_prompt"):
                st.session_state.pop(k, None)
            st.rerun()
        if st.button("🔒 Lock", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    tickets_sidebar(st.session_state.setu.session_id)

    st.markdown(JOURNEY_CSS, unsafe_allow_html=True)
    for i, m in enumerate(st.session_state.messages):
        with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "💠"):
            if m["role"] == "user":
                st.markdown(html.escape(m["content"]) + USER_MARK, unsafe_allow_html=True)
            else:
                st.markdown(m["content"])
            if m.get("qa"):
                st.markdown(f'<div class="ps-qa">{m["qa"]}</div>', unsafe_allow_html=True)
            render_journey(m, i)

    # Quick example buttons on a fresh chat (handy for demos).
    clicked = None
    if len(st.session_state.messages) == 1:
        st.caption("Try one of these:")
        cols = st.columns(2)
        for i, ex in enumerate(EXAMPLES):
            if cols[i % 2].button(ex, key=f"ex{i}", use_container_width=True):
                clicked = ex

    prompt = (st.chat_input("Ask about payments, UPI, wallet, KYC, bills, cashback...") or clicked
              or st.session_state.pop("pending_prompt", None))
    if not prompt:
        return
    if sum(1 for m in st.session_state.messages if m["role"] == "user") >= MAX_MESSAGES_PER_CHAT:
        st.warning("This chat has reached its message limit. Start a new chat from the sidebar to continue.")
        return

    from paysetu_agent.safety import redact

    safe_prompt = redact(prompt)[0]  # secrets never shown on screen
    with st.chat_message("user", avatar="🧑"):
        st.markdown(html.escape(safe_prompt) + USER_MARK, unsafe_allow_html=True)
    with st.chat_message("assistant", avatar="💠"):
        with st.spinner("Setu is checking..."):
            result = st.session_state.setu.respond(prompt)
        st.markdown(result["reply"])

    qa_note = ""
    if result["qa_result"] == "PASS":
        qa_note = "✓ Checked by QA reviewer"
    elif result["qa_result"] == "FAIL":
        qa_note = "✓ Rewritten after QA review"
    st.session_state.messages.append({"role": "user", "content": safe_prompt})
    st.session_state.messages.append({"role": "assistant", "content": result["reply"], "qa": qa_note,
                                      "journey": result.get("journey"), "receipt": result.get("receipt")})
    st.rerun()  # refresh so new tickets appear in the sidebar


main()
