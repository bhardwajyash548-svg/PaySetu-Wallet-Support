"""Dashboard page: tickets and chat activity, with charts."""
import html
from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from paysetu_agent import config, ticket_manager
from ui_shared import hero

# Chart colours: fixed categorical order (validated palette), used by role, never cycled.
C_BLUE, C_ORANGE, C_AQUA, C_YELLOW, C_MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
INK, INK_2, GRID = "#0B2540", "#52606D", "#E6EDF3"

DASH_CSS = """
<style>
.block-container { max-width: 1180px !important; }
/* White cards around each chart (the bordered block that directly holds a card title) */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .ps-card-title) {
  background: #fff; border: 1px solid #DCE6EF !important; border-radius: 16px;
  box-shadow: 0 4px 18px rgba(11,37,64,.06); padding: 16px 18px;
}
.ps-card-title { font-weight: 700; color: #0B2540; font-size: 1.02rem; margin: 0 0 2px; }
.ps-card-sub { color: #52606D; font-size: .82rem; margin: 0 0 6px; }
/* KPI tiles */
.ps-kpis { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 14px; margin: 4px 0 18px; }
@media (max-width: 900px) { .ps-kpis { grid-template-columns: repeat(2, minmax(0,1fr)); } }
.ps-kpi { background: #fff; border: 1px solid #DCE6EF; border-radius: 16px; padding: 14px 16px;
  box-shadow: 0 4px 18px rgba(11,37,64,.06); position: relative; overflow: hidden; }
.ps-kpi::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 5px; background: var(--accent); }
.ps-kpi .lbl { color: #52606D; font-size: .82rem; display: flex; gap: 6px; align-items: center; }
.ps-kpi .val { color: #0B2540; font-size: 1.9rem; font-weight: 800; line-height: 1.15; margin-top: 4px; }
.ps-kpi .sub { color: #52606D; font-size: .76rem; }
.ps-meter { height: 6px; background: #E6EDF3; border-radius: 99px; margin-top: 8px; overflow: hidden; }
.ps-meter > span { display: block; height: 100%; background: #1baf7a; border-radius: 99px; }
/* Top questions list */
.ps-q { display: grid; grid-template-columns: 26px 1fr auto; gap: 10px; align-items: center;
  padding: 8px 0; border-bottom: 1px solid #EEF2F6; }
.ps-q:last-child { border-bottom: 0; }
.ps-q .rank { width: 26px; height: 26px; border-radius: 8px; background: #E8F1FB; color: #1554A6;
  font-weight: 800; font-size: .8rem; display: flex; align-items: center; justify-content: center; }
.ps-q .txt { color: #0B2540; font-size: .9rem; }
.ps-q .bar { height: 5px; background: #E6EDF3; border-radius: 99px; margin-top: 5px; }
.ps-q .bar > span { display: block; height: 100%; background: #2a78d6; border-radius: 99px; }
.ps-q .n { color: #0B2540; font-weight: 700; font-size: .9rem; }
.ps-sample { background: #FFF7E6; border: 1px solid #F5D08A; color: #7A4B00; border-radius: 12px;
  padding: 8px 12px; font-size: .85rem; margin-bottom: 12px; }
.ps-empty { color: #52606D; font-size: .88rem; padding: 18px 0; text-align: center; }
</style>
"""

OUTCOME_ORDER = ["Answered from help docs", "Ticket created", "Not in help docs", "Off-topic declined", "Other"]
OUTCOME_COLORS = [C_BLUE, C_ORANGE, C_AQUA, C_YELLOW, C_MAGENTA]


# ---------- data ----------
def load(path, columns):
    try:
        return pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame(columns=columns)
    except Exception as exc:
        st.warning(f"Could not read {path.name}: {exc}")
        return pd.DataFrame(columns=columns)


def sample_data():
    """Clearly-labelled SAMPLE data so the charts can be previewed on an empty server."""
    now = datetime.now()
    reasons = ["Fraud or hacked account"] * 3 + ["Failed payment not reversed after 3 working days"] * 2 + \
              ["KYC rejected", "Customer asked for a person", "Disputed amount above ₹5,000", "Angry or upset customer"]
    tickets = pd.DataFrame([{
        "ticket_id": f"TKT-{1001 + i}", "time": (now - timedelta(hours=9 - i)).strftime("%Y-%m-%d %H:%M:%S"),
        "customer_message": "(sample)", "reason": r,
        "priority": "high" if r.startswith("Fraud") else "normal", "status": "open"} for i, r in enumerate(reasons)])
    qs = (["What is the daily UPI limit?"] * 5 + ["Cashback kab milega?"] * 4 + ["How do I complete KYC?"] * 3 +
          ["My payment is pending. What should I do?"] * 3 + ["Which bills can I pay?"] * 2 +
          ["₹20,000 was taken from my account and I didn't do it!"] * 2 + ["Which crypto coin should I buy?"] +
          ["Do you have a loyalty points program?"])
    srcs = (["FAQ: What is the daily UPI limit?"] * 5 + ["FAQ: When will I get cashback?"] * 4 +
            ["FAQ: How do I complete KYC?"] * 3 + ["Failed, pending and wrong payments policy"] * 3 +
            ["FAQ: Which bills can I pay?"] * 2 + ["none"] * 4)
    replies = ["(source)"] * 17 + ["Your ticket ID is TKT-1001."] * 2 + \
              ["I can only help with PaySetu questions."] + ["I don't have that information."]
    chats = pd.DataFrame([{"time": (now - timedelta(minutes=27 * (len(qs) - i))).strftime("%Y-%m-%d %H:%M:%S"),
                           "message": q, "reply": r, "source": s} for i, (q, r, s) in enumerate(zip(qs, replies, srcs))])
    qa = pd.DataFrame({"result": ["PASS"] * 19 + ["FAIL"] * 2})
    return tickets, chats, qa


def outcome(row) -> str:
    reply = row["reply"]
    if "TKT-" in reply:
        return "Ticket created"
    if row["source"] and row["source"] != "none":
        return "Answered from help docs"
    if "don't have that information" in reply or "I don't have" in reply:
        return "Not in help docs"
    if "only help with PaySetu" in reply:
        return "Off-topic declined"
    return "Other"


# ---------- chart helpers ----------
def card(title, subtitle=""):
    box = st.container(border=True)
    box.markdown(f'<p class="ps-card-title">{title}</p>' + (f'<p class="ps-card-sub">{subtitle}</p>' if subtitle else ""),
                 unsafe_allow_html=True)
    return box


def style(chart):
    return (chart.configure(background="transparent").configure_view(stroke=None)
            .configure_axis(labelColor=INK_2, titleColor=INK_2, gridColor=GRID, domainColor=GRID, tickColor=GRID,
                            labelFontSize=12, titleFontSize=12)
            .configure_legend(labelColor=INK, titleColor=INK_2, labelFontSize=12, symbolType="circle"))


def hbar(df, label, value, color, height=None):
    base = alt.Chart(df).encode(
        y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=330, ticks=False, domain=False)),
        x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d", grid=True)),
        tooltip=[alt.Tooltip(f"{label}:N", title=label.capitalize()), alt.Tooltip(f"{value}:Q", title="Count")],
    )
    bars = base.mark_bar(color=color, cornerRadiusEnd=4, height={"band": 0.62})
    text = base.mark_text(align="left", dx=6, color=INK, fontWeight="bold").encode(text=f"{value}:Q")
    return style(bars + text).properties(height=height or max(120, 38 * len(df)))


def donut(df):
    chart = alt.Chart(df).mark_arc(innerRadius=62, outerRadius=110, stroke="#fff", strokeWidth=2).encode(
        theta=alt.Theta("count:Q", stack=True),
        color=alt.Color("outcome:N", scale=alt.Scale(domain=OUTCOME_ORDER, range=OUTCOME_COLORS),
                        legend=alt.Legend(title=None, orient="right")),
        order=alt.Order("order:Q"),
        tooltip=[alt.Tooltip("outcome:N", title="Outcome"), alt.Tooltip("count:Q", title="Chats"),
                 alt.Tooltip("share:Q", title="Share", format=".0%")],
    )
    total = int(df["count"].sum())
    center = alt.Chart(pd.DataFrame({"t": [f"{total}"], "s": ["chats"]})).mark_text(
        fontSize=28, fontWeight="bold", color=INK, dy=-8).encode(text="t:N")
    center2 = alt.Chart(pd.DataFrame({"s": ["chats"]})).mark_text(fontSize=12, color=INK_2, dy=16).encode(text="s:N")
    return style(chart + center + center2).properties(height=260)


def priority_bar(open_t):
    """Tall segmented bar: one whole (open tickets) split into High / Normal."""
    counts = open_t["priority"].value_counts()
    df = pd.DataFrame({"priority": ["High", "Normal"],
                       "count": [int(counts.get("high", 0)), int(counts.get("normal", 0))]})
    df = df[df["count"] > 0].reset_index(drop=True)
    df["share"] = df["count"] / df["count"].sum()
    df["end"] = df["share"].cumsum()
    df["start"] = df["end"] - df["share"]
    df["mid"] = (df["start"] + df["end"]) / 2
    df["label"] = df.apply(lambda r: f"{r['priority']} · {r['count']}" if r["share"] >= 0.12 else "", axis=1)
    x = alt.X("start:Q", axis=None, scale=alt.Scale(domain=[0, 1]))
    bars = alt.Chart(df).mark_bar(height=40, stroke="#fff", strokeWidth=2, cornerRadius=4).encode(
        x=x, x2="end:Q",
        color=alt.Color("priority:N", scale=alt.Scale(domain=["High", "Normal"], range=[C_ORANGE, C_BLUE]),
                        legend=alt.Legend(title=None, orient="bottom", direction="horizontal")),
        tooltip=[alt.Tooltip("priority:N", title="Priority"), alt.Tooltip("count:Q", title="Open tickets"),
                 alt.Tooltip("share:Q", title="Share", format=".0%")],
    )
    text = alt.Chart(df).mark_text(color="#fff", fontWeight="bold", fontSize=13).encode(
        x=alt.X("mid:Q", axis=None, scale=alt.Scale(domain=[0, 1])), text="label:N")
    return style(bars + text).properties(height=110)


def activity(chats):
    t = pd.to_datetime(chats["time"], errors="coerce").dropna()
    if t.empty:
        return None
    span = t.max() - t.min()
    freq, fmt, title = ("h", "%H:%M", "Messages per hour") if span <= pd.Timedelta(days=2) else ("D", "%d %b", "Messages per day")
    s = t.dt.floor(freq).value_counts().sort_index()
    step = pd.Timedelta(hours=1) if freq == "h" else pd.Timedelta(days=1)
    idx = pd.date_range(s.index.min() - step, s.index.max() + step, freq=freq)
    df = s.reindex(idx, fill_value=0).rename_axis("time").reset_index(name="messages")
    df = df.tail(24)  # last 24 buckets keeps the columns readable
    df["slot"] = df["time"].dt.strftime(fmt if freq == "D" else "%d %b %H:00")
    df["tick"] = df["time"].dt.strftime(fmt)
    base = alt.Chart(df).encode(
        x=alt.X("slot:O", sort=None, title=None,
                axis=alt.Axis(labelAngle=0, labelExpr="split(datum.label, ' ')[2] || datum.label")),
        y=alt.Y("messages:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d")),
        tooltip=[alt.Tooltip("slot:O", title="Time"), alt.Tooltip("messages:Q", title="Messages")],
    )
    bars = base.mark_bar(color=C_BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, width={"band": 0.6})
    text = base.mark_text(dy=-8, color=INK, fontWeight="bold").encode(
        text=alt.condition("datum.messages > 0", "messages:Q", alt.value("")))
    return title, style(bars + text).properties(height=230)


# ---------- page ----------
st.markdown(DASH_CSS, unsafe_allow_html=True)
hero("Support Dashboard", "Tickets, customer questions and answer quality at a glance")

tickets = pd.DataFrame(ticket_manager.all_tickets(), columns=ticket_manager.TICKET_FIELDS).fillna("")
chats = load(config.CHAT_LOG_FILE, ["time", "message", "reply", "source"])
qa = load(config.QA_LOG_FILE, ["time", "message", "draft", "result", "reason"])

empty = tickets.empty and chats.empty
use_sample = st.sidebar.toggle("Show sample data", value=False,
                               help="Preview the charts with made-up data. Never mixed with real data.")
if use_sample:
    tickets, chats, qa = sample_data()
    st.markdown('<div class="ps-sample">⚠️ Showing <b>SAMPLE data</b> for preview, not real tickets or chats. '
                'Turn off "Show sample data" in the sidebar to see live data.</div>', unsafe_allow_html=True)
elif empty:
    st.info("No chats or tickets on this server yet. Chat with Setu to fill the dashboard, "
            "or turn on **Show sample data** in the sidebar to preview the charts.")

open_t = tickets[tickets["status"] == "open"]
high = int((open_t["priority"] == "high").sum())
pass_rate = (qa["result"] == "PASS").mean() if len(qa) else None
answered = 0
if len(chats):
    guessed = chats.apply(outcome, axis=1)  # older rows have no logged outcome
    logged = chats["outcome"] if "outcome" in chats.columns else pd.Series("", index=chats.index)
    chats = chats.assign(outcome=logged.where(logged.isin(OUTCOME_ORDER), guessed))
    answered = int((chats["outcome"] == "Answered from help docs").sum())

meter = f'<div class="ps-meter"><span style="width:{pass_rate * 100:.0f}%"></span></div>' if pass_rate is not None else ""
st.markdown(f"""
<div class="ps-kpis">
  <div class="ps-kpi" style="--accent:{C_BLUE}"><div class="lbl">🎫 Open tickets</div>
    <div class="val">{len(open_t)}</div><div class="sub">waiting for a person</div></div>
  <div class="ps-kpi" style="--accent:{C_ORANGE}"><div class="lbl">🚨 High priority</div>
    <div class="val">{high}</div><div class="sub">fraud / unknown payments</div></div>
  <div class="ps-kpi" style="--accent:{C_AQUA}"><div class="lbl">💬 Chat messages</div>
    <div class="val">{len(chats)}</div><div class="sub">{answered} answered from help docs</div></div>
  <div class="ps-kpi" style="--accent:{C_YELLOW}"><div class="lbl">✅ QA first-pass rate</div>
    <div class="val">{f"{pass_rate:.0%}" if pass_rate is not None else "—"}</div>
    <div class="sub">replies approved without rewrite</div>{meter}</div>
</div>""", unsafe_allow_html=True)

left, right = st.columns([1.05, 1], gap="medium")
with left:
    box = card("How chats were handled", "Share of chat messages by outcome")
    if len(chats):
        d = chats["outcome"].value_counts().reindex(OUTCOME_ORDER).dropna().astype(int).rename_axis("outcome").reset_index(name="count")
        d["share"] = d["count"] / d["count"].sum()
        d["order"] = d["outcome"].map({o: i for i, o in enumerate(OUTCOME_ORDER)})
        box.altair_chart(donut(d), use_container_width=True)
    else:
        box.markdown('<div class="ps-empty">No chats yet.</div>', unsafe_allow_html=True)
with right:
    box = card("Open tickets by priority", "High = fraud, hacked account or unknown payment")
    if len(open_t):
        box.altair_chart(priority_bar(open_t), use_container_width=True)
    else:
        box.markdown('<div class="ps-empty">No open tickets.</div>', unsafe_allow_html=True)
    box = card("Chat activity")
    act = activity(chats) if len(chats) else None
    if act:
        box.caption(act[0])
        box.altair_chart(act[1], use_container_width=True)
    else:
        box.markdown('<div class="ps-empty">No chats yet.</div>', unsafe_allow_html=True)

box = card("Tickets by reason", "Why customers were handed to a person")
if len(tickets):
    d = tickets["reason"].value_counts().rename_axis("reason").reset_index(name="tickets")
    box.altair_chart(hbar(d, "reason", "tickets", C_BLUE), use_container_width=True)
else:
    box.markdown('<div class="ps-empty">No tickets yet.</div>', unsafe_allow_html=True)

left, right = st.columns(2, gap="medium")
with left:
    box = card("Top 5 customer questions", "Most asked, by exact wording")
    if len(chats):
        q = chats["message"].str.strip()
        top = q.str.lower().value_counts().head(5)
        first_seen = {s.lower(): s for s in q[::-1]}
        mx = int(top.max())
        rows = "".join(
            f'<div class="ps-q"><div class="rank">{i}</div><div><div class="txt">{html.escape(first_seen[k])}</div>'
            f'<div class="bar"><span style="width:{v / mx * 100:.0f}%"></span></div></div><div class="n">{v}</div></div>'
            for i, (k, v) in enumerate(top.items(), 1))
        box.markdown(rows, unsafe_allow_html=True)
    else:
        box.markdown('<div class="ps-empty">No chats yet.</div>', unsafe_allow_html=True)
with right:
    box = card("Most used help-doc sections", "Sources cited in Setu's answers")
    src = chats["source"][chats["source"].ne("none") & chats["source"].ne("")] if len(chats) else pd.Series(dtype=str)
    if len(src):
        src = src.str.split("; ").explode().str.replace(r"^FAQ:\s*", "", regex=True)
        d = src.value_counts().head(6).rename_axis("section").reset_index(name="answers")
        box.altair_chart(hbar(d, "section", "answers", C_AQUA), use_container_width=True)
    else:
        box.markdown('<div class="ps-empty">No help-doc answers yet.</div>', unsafe_allow_html=True)

box = card("Recent tickets")
if len(tickets):
    if "category" not in tickets.columns:
        tickets["category"] = ""
    show = tickets.iloc[::-1].head(20)[["ticket_id", "time", "priority", "category", "reason", "customer_message",
                                        "status"]]
    box.dataframe(show, hide_index=True, use_container_width=True, column_config={
        "ticket_id": "Ticket", "time": "Time", "priority": "Priority", "category": "Category", "reason": "Reason",
        "customer_message": st.column_config.TextColumn("Summary", width="large"), "status": "Status"})
else:
    box.markdown('<div class="ps-empty">No tickets yet.</div>', unsafe_allow_html=True)
