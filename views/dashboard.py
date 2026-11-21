"""Dashboard page: tickets and chat activity."""
import altair as alt
import pandas as pd
import streamlit as st

from paysetu_agent import config
from ui_shared import hero


def load(path, columns):
    try:
        return pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame(columns=columns)
    except Exception as exc:
        st.warning(f"Could not read {path.name}: {exc}")
        return pd.DataFrame(columns=columns)


hero("Support Dashboard", "Tickets and customer questions at a glance")

tickets = load(config.TICKETS_FILE, ["ticket_id", "time", "customer_message", "reason", "priority", "status"])
chats = load(config.CHAT_LOG_FILE, ["time", "message", "reply", "source"])
qa = load(config.QA_LOG_FILE, ["time", "message", "draft", "result", "reason"])
open_t = tickets[tickets["status"] == "open"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Open tickets", len(open_t))
c2.metric("High priority open", int((open_t["priority"] == "high").sum()))
c3.metric("Chat messages", len(chats))
pass_rate = f"{(qa['result'] == 'PASS').mean():.0%}" if len(qa) else "—"
c4.metric("QA first-pass rate", pass_rate)

def hbar(series, color, label):
    df = series.rename_axis(label).reset_index(name="tickets")
    chart = (
        alt.Chart(df)
        .mark_bar(color=color, cornerRadiusEnd=4)
        .encode(
            x=alt.X("tickets:Q", title="Tickets", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)),
            tooltip=[label, "tickets"],
        )
    )
    st.altair_chart(chart, use_container_width=True, height=max(110, 44 * len(df) + 50))


st.subheader("Tickets by reason")
if len(tickets):
    hbar(tickets["reason"].value_counts(), "#0E8C8C", "reason")
else:
    st.info("No tickets yet.")

st.subheader("Tickets by priority")
if len(tickets):
    hbar(tickets["priority"].value_counts(), "#1554A6", "priority")
else:
    st.caption("No tickets yet.")

st.subheader("Top 5 customer questions")
if len(chats):
    q = chats["message"].str.strip()
    top = q.str.lower().value_counts().head(5).rename_axis("question").reset_index(name="times asked")
    first_seen = {s.lower(): s for s in q[::-1]}  # show original wording
    top["question"] = top["question"].map(first_seen)
    st.dataframe(top, hide_index=True, use_container_width=True,
                 column_config={"question": st.column_config.TextColumn(width="large")})
else:
    st.caption("No chats yet.")

st.subheader("Recent tickets")
if len(tickets):
    st.dataframe(tickets.iloc[::-1].head(20), hide_index=True, use_container_width=True)
else:
    st.caption("No tickets yet.")
