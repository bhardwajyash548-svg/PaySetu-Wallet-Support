"""Admin: analytics. Every number is calculated from the app's own logs (see paysetu_agent/analytics.py)."""
import html

import altair as alt
import pandas as pd
import streamlit as st

from charts import (C_AQUA, C_BLUE, C_MAGENTA, C_ORANGE, C_YELLOW, CHART_CSS, INK, card, donut, hbar, line,
                    style)
from paysetu_agent import analytics, ticket_manager as tm
from ui_shared import hero, require_admin

admin = require_admin()  # stops here unless an admin is signed in
st.markdown(CHART_CSS, unsafe_allow_html=True)
hero("Admin analytics", "Every number is calculated from the app's own logs")
e = html.escape

s = analytics.summary()
res, rt = s["resolution"], s["response"]


def pct(v):
    return "—" if v is None else f"{v:.0%}"


def tile(label, value, sub, accent, meter=None):
    bar = f'<div class="ps-meter"><span style="width:{meter * 100:.0f}%"></span></div>' if meter is not None else ""
    return (f'<div class="ps-kpi" style="--accent:{accent}"><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div><div class="sub">{sub}</div>{bar}</div>')


open_count = s["tickets_by_status"].get("open", 0)
alerts = s["fraud_alerts"]
st.markdown('<div class="ps-kpis">' + "".join([
    tile("💬 Conversations", res["conversations"], f'{s["messages"]} messages', C_BLUE),
    tile("🤖 AI resolution rate", pct(res["rate"]), f'{res["resolved"]} of {res["conversations"]} with no person needed',
         C_AQUA, res["rate"]),
    tile("⏱ Avg response time", "—" if rt["avg_s"] is None else f'{rt["avg_s"]} s',
         "—" if rt["p90_s"] is None else f'median {rt["median_s"]} s · 90% under {rt["p90_s"]} s', C_YELLOW),
    tile("🎫 Tickets", s["tickets_total"], f"{open_count} open", C_ORANGE),
]) + "</div>", unsafe_allow_html=True)
st.markdown('<div class="ps-kpis">' + "".join([
    tile("🚨 Fraud alerts", alerts.get("High", 0) + alerts.get("Medium", 0),
         f'{alerts.get("High", 0)} High · {alerts.get("Medium", 0)} Medium', C_ORANGE),
    tile("✅ QA first-pass rate", pct(s["qa_pass_rate"]), f'{s["qa_reviewed"]} replies reviewed', C_AQUA,
         s["qa_pass_rate"]),
    tile("🎯 Test score", "—" if s["test_avg"] is None else f'{s["test_avg"]} / 5', "latest run_tests.py result", C_BLUE,
         None if s["test_avg"] is None else s["test_avg"] / 5),
    tile("📚 Answers with a source", pct(s["source_rate"]), "replies answered from the help docs", C_MAGENTA,
         s["source_rate"]),
]) + "</div>", unsafe_allow_html=True)
st.caption("AI resolution rate: " + analytics.RESOLUTION_DEFINITION)

if not s["messages"] and not s["tickets_total"]:
    st.info("No chats or tickets yet. Numbers and charts appear as soon as customers use the chat.")
    st.stop()

# ---------- tickets ----------
left, right = st.columns(2, gap="medium")
with left:
    box = card("Tickets by status", f'{s["tickets_total"]} tickets')
    d = pd.DataFrame({"status": [tm.STATUS_LABELS[k] for k in tm.STATUSES],
                      "count": [s["tickets_by_status"][k] for k in tm.STATUSES]})
    d = d[d["count"] > 0]
    if len(d):
        box.altair_chart(donut(d, "status", "count", list(tm.STATUS_LABELS.values()),
                               [C_BLUE, C_YELLOW, C_AQUA, "#9AA9B8"], str(s["tickets_total"]), "tickets"),
                         use_container_width=True)
    else:
        box.caption("No tickets yet.")
    hrs = s["resolution_hours"]
    box.caption("Average time to resolve: " + ("not enough resolved tickets yet" if hrs is None else f"{hrs} hours"))
with right:
    box = card("Tickets by category", "Smart classification of every ticket")
    if s["tickets_by_category"]:
        d = pd.DataFrame(list(s["tickets_by_category"].items()), columns=["category", "tickets"])
        box.altair_chart(hbar(d, "category", "tickets", C_BLUE), use_container_width=True)
    else:
        box.caption("No tickets yet.")
    pr = s["tickets_by_priority"]
    box.markdown(f'<span class="ps-pill-high">High priority: <b>{pr["high"]}</b></span> &nbsp; '
                 f'<span class="ps-pill-normal">Normal: <b>{pr["normal"]}</b></span>', unsafe_allow_html=True)

# ---------- customers ----------
left, right = st.columns(2, gap="medium")
with left:
    box = card("Customer sentiment", "Messages by mood (rule-based)")
    sent = s["sentiment"]
    total = sum(sent.values())
    if total:
        d = pd.DataFrame(list(sent.items()), columns=["sentiment", "messages"])
        d = d[d["messages"] > 0]
        box.altair_chart(donut(d, "sentiment", "messages", ["Positive", "Neutral", "Negative", "Angry"],
                               [C_AQUA, C_BLUE, C_YELLOW, C_ORANGE], str(total), "messages"),
                         use_container_width=True)
    else:
        box.caption("No sentiment recorded yet.")
with right:
    box = card("Sentiment trend", "Average mood score (−1 angry … +1 happy)")
    trend = s["sentiment_trend"]
    if len(trend) >= 2:
        box.altair_chart(line(trend, "time", "avg_score", C_BLUE, "Avg score", (-1, 1)), use_container_width=True)
    elif len(trend) == 1:
        box.caption(f'Only one time period so far: average score {trend["avg_score"].iloc[0]}.')
    else:
        box.caption("No sentiment recorded yet.")

# ---------- fraud ----------
left, right = st.columns([1, 1.4], gap="medium")
with left:
    box = card("Fraud risk distribution", "Every customer message is checked")
    risk = s["risk"]
    if sum(risk.values()):
        d = pd.DataFrame(list(risk.items()), columns=["risk", "messages"])
        chart = alt.Chart(d).encode(
            y=alt.Y("risk:N", sort=["Low", "Medium", "High"], title=None, axis=alt.Axis(ticks=False, domain=False)),
            x=alt.X("messages:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d")),
            tooltip=["risk", "messages"])
        bars = chart.mark_bar(cornerRadiusEnd=4, height={"band": 0.6}).encode(
            color=alt.Color("risk:N", scale=alt.Scale(domain=["Low", "Medium", "High"],
                                                      range=[C_AQUA, C_YELLOW, C_ORANGE]), legend=None))
        text = chart.mark_text(align="left", dx=6, color=INK, fontWeight="bold").encode(text="messages:Q")
        box.altair_chart(style(bars + text).properties(height=150), use_container_width=True)
        box.caption("High needs real harm: a payment the customer didn't make, a hacked account or a shared OTP/PIN.")
    else:
        box.caption("No fraud checks recorded yet.")
with right:
    box = card("Latest fraud alerts", "Medium and High only")
    if s["fraud_latest"]:
        d = pd.DataFrame(s["fraud_latest"])[["time", "level", "ticket_ids", "reasons", "message"]]
        box.dataframe(d, hide_index=True, use_container_width=True, column_config={
            "time": "Time", "level": "Risk", "ticket_ids": "Ticket",
            "reasons": st.column_config.TextColumn("Why", width="large"),
            "message": st.column_config.TextColumn("Message (secrets removed)", width="medium")})
    else:
        box.caption("No fraud alerts.")

# ---------- Setu ----------
left, right = st.columns(2, gap="medium")
with left:
    box = card("Top 5 customer questions", "Most asked, by exact wording")
    if s["top_questions"]:
        mx = s["top_questions"][0][1]
        box.markdown("".join(
            f'<div class="ps-q"><div class="rank">{i}</div><div><div class="txt">{e(q)}</div>'
            f'<div class="bar"><span style="width:{n / mx * 100:.0f}%"></span></div></div><div class="n">{n}</div></div>'
            for i, (q, n) in enumerate(s["top_questions"], 1)), unsafe_allow_html=True)
    else:
        box.caption("No chats yet.")
with right:
    box = card("Setu performance", "Share of replies, from the chat and QA logs")
    rows = [("Answered from help docs", s["source_rate"]), ("QA approved first time", s["qa_pass_rate"]),
            ("Answered by backup model", s["backup_rate"]), ("Service busy", s["busy_rate"])]
    d = pd.DataFrame([(k, round(v * 100)) for k, v in rows if v is not None], columns=["metric", "percent"])
    if len(d):
        chart = alt.Chart(d).encode(
            y=alt.Y("metric:N", sort=None, title=None, axis=alt.Axis(labelLimit=220, ticks=False, domain=False)),
            x=alt.X("percent:Q", title=None, scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(format="d")),
            tooltip=["metric", alt.Tooltip("percent:Q", title="%")])
        bars = chart.mark_bar(color=C_AQUA, cornerRadiusEnd=4, height={"band": 0.6})
        text = chart.mark_text(align="left", dx=6, color=INK, fontWeight="bold").encode(
            text=alt.Text("percent:Q", format="d"))
        box.altair_chart(style(bars + text).properties(height=180), use_container_width=True)
    if s["test_by_type"]:
        box.caption("Test score by type: " + " · ".join(f"{k} {v}" for k, v in s["test_by_type"].items()))

with st.expander("How each number is calculated"):
    st.markdown(f"""
- **Conversations:** distinct chat sessions in `chat_log.csv` (older messages without a session count as one each).
- **AI resolution rate:** {analytics.RESOLUTION_DEFINITION}
- **Response time:** time from the customer's message to Setu's final reply (including the QA review),
  logged per message. Median and 90th percentile shown.
- **Tickets:** `tickets.csv`; status changes from `ticket_history.csv`. Average time to resolve = creation to the first
  Resolved/Closed status.
- **Sentiment / fraud risk:** rule-based checks run on every customer message (explainable word and pattern rules,
  not a trained model).
- **QA first-pass rate:** share of reviewed replies the QA reviewer approved without a rewrite (`qa_log.csv`).
- **Test score:** average judge score in the latest `results.csv` from `run_tests.py`.
- Logs on a free Render instance reset when it restarts, so numbers cover the time since the last restart.
""")
