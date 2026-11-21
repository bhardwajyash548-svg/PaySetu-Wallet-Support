"""Chat page: talk to Setu."""
import html

import streamlit as st

from ui_shared import hero, tickets_sidebar

USER_MARK = '<span class="ps-user"></span>'  # lets CSS style customer bubbles

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


def main():
    hero("PaySetu Wallet Support", "Setu answers from PaySetu's official help docs · English & हिंदी")
    try:
        chat, config = load_engine()
    except Exception as exc:
        st.error(f"Setu could not start: {exc}")
        st.stop()

    if "setu" not in st.session_state:
        st.session_state.setu = chat.SetuChat()
        st.session_state.messages = [{"role": "assistant", "content": config.GREETING}]

    with st.sidebar:
        if st.button("➕ New chat", use_container_width=True):
            for k in ("setu", "messages"):
                st.session_state.pop(k, None)
            st.rerun()
        if st.button("🔒 Lock", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    tickets_sidebar()

    for m in st.session_state.messages:
        with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "💠"):
            if m["role"] == "user":
                st.markdown(html.escape(m["content"]) + USER_MARK, unsafe_allow_html=True)
            else:
                st.markdown(m["content"])
            if m.get("qa"):
                st.markdown(f'<div class="ps-qa">{m["qa"]}</div>', unsafe_allow_html=True)

    # Quick example buttons on a fresh chat (handy for demos).
    clicked = None
    if len(st.session_state.messages) == 1:
        st.caption("Try one of these:")
        cols = st.columns(2)
        for i, ex in enumerate(EXAMPLES):
            if cols[i % 2].button(ex, key=f"ex{i}", use_container_width=True):
                clicked = ex

    prompt = st.chat_input("Ask about payments, UPI, wallet, KYC, bills, cashback...") or clicked
    if not prompt:
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
    st.session_state.messages.append({"role": "assistant", "content": result["reply"], "qa": qa_note})
    st.rerun()  # refresh so new tickets appear in the sidebar


main()
