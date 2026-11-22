"""PaySetu Wallet Support - Streamlit web app.

Run locally:  .venv/bin/streamlit run app.py
Every page sits behind APP_PASSCODE. Admin pages additionally need ADMIN_PASSCODE.
"""
import streamlit as st

from ui_shared import apply_style, load_secrets, require_passcode

st.set_page_config(page_title="PaySetu Wallet Support", page_icon="💠", layout="centered")
load_secrets()  # must run before the agent is imported (it needs GOOGLE_API_KEY)
apply_style()
require_passcode()  # stops here until the right passcode is entered

nav = st.navigation({
    "Support": [
        st.Page("views/chat.py", title="Chat with Setu", icon="💬", default=True),
        st.Page("views/dashboard.py", title="Dashboard", icon="📊"),
    ],
    "Admin": [
        st.Page("views/admin_tickets.py", title="Ticket management", icon="🎫"),
    ],
})
nav.run()
