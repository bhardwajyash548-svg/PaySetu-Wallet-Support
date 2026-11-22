"""Admin analytics: every number is calculated from the app's own log files. Nothing is invented.

Sources: chat_log.csv (messages), tickets.csv + ticket_history.csv (tickets), qa_log.csv (QA reviewer),
fraud_alerts.csv (Medium/High fraud checks), results.csv (latest scored test run).

AI resolution rate (shown with its definition on the page):
    a conversation counts as "resolved by Setu" when NO ticket was created for it AND Setu's last reply
    was not "I don't have that information..." and not the "service busy" message.
    rate = resolved conversations / all conversations.
    Messages logged before conversations were tracked (no session id) count as one conversation each.
"""
from collections import Counter
from datetime import datetime

import pandas as pd

from . import config, storage, ticket_manager
from .outcomes import outcome_from_log

UNRESOLVED_OUTCOMES = {"Not in help docs", "Service busy", "Ticket created"}
RESOLUTION_DEFINITION = (
    "A conversation is resolved by Setu when no ticket was created for it and Setu's last reply was not "
    "\"I don't have that information\" or \"service busy\". Rate = resolved conversations / all conversations."
)


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).fillna("") if rows else pd.DataFrame()


def load() -> dict:
    """Read every log once. Returns DataFrames keyed by name."""
    return {
        "chats": _df(storage.read_rows(config.CHAT_LOG_FILE)),
        "tickets": _df(ticket_manager.all_tickets()),
        "history": _df(storage.read_rows(config.TICKET_HISTORY_FILE)),
        "qa": _df(storage.read_rows(config.QA_LOG_FILE)),
        "fraud": _df(storage.read_rows(config.FRAUD_ALERTS_FILE)),
        "results": _df(storage.read_rows(config.PROJECT_ROOT / "results.csv")),
    }


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return df[name] if name in df.columns else pd.Series([""] * len(df), index=df.index, dtype=object)


def conversation_ids(chats: pd.DataFrame) -> pd.Series:
    """Session id per message; old rows without one get a unique id each."""
    sid = _col(chats, "session_id").astype(str)
    return sid.where(sid != "", "legacy-" + chats.index.astype(str))


def resolution(chats: pd.DataFrame, tickets: pd.DataFrame) -> dict:
    if chats.empty:
        return {"conversations": 0, "resolved": 0, "rate": None}
    chats = chats.assign(conv=conversation_ids(chats))
    ticketed = set(_col(tickets, "session_id")) - {""}
    total = resolved = 0
    for conv, group in chats.groupby("conv", sort=False):
        total += 1
        outcomes = set(_col(group, "outcome"))
        last = _col(group, "outcome").iloc[-1]
        if conv in ticketed or "Ticket created" in outcomes or last in UNRESOLVED_OUTCOMES:
            continue
        resolved += 1
    return {"conversations": total, "resolved": resolved, "rate": resolved / total if total else None}


def response_times(chats: pd.DataFrame) -> dict:
    ms = pd.to_numeric(_col(chats, "response_ms"), errors="coerce")
    ms = ms[ms > 0]
    if ms.empty:
        return {"count": 0, "avg_s": None, "median_s": None, "p90_s": None}
    return {"count": int(len(ms)), "avg_s": round(float(ms.mean()) / 1000, 1),
            "median_s": round(float(ms.median()) / 1000, 1), "p90_s": round(float(ms.quantile(0.9)) / 1000, 1)}


def counts(series: pd.Series, order: list[str] | None = None) -> dict:
    c = Counter(v for v in series if v)
    if order:
        return {k: c.get(k, 0) for k in order}
    return dict(c.most_common())


def top_questions(chats: pd.DataFrame, n: int = 5) -> list[tuple[str, int]]:
    if chats.empty:
        return []
    msgs = _col(chats, "message").astype(str).str.strip()
    msgs = msgs[msgs != ""]
    first = {}
    for m in msgs:
        first.setdefault(m.lower(), m)  # keep the first wording seen
    return [(first[k], v) for k, v in Counter(m.lower() for m in msgs).most_common(n)]


def sentiment_trend(chats: pd.DataFrame) -> pd.DataFrame:
    """Average sentiment score per hour (or per day if the logs span more than 2 days)."""
    if chats.empty:
        return pd.DataFrame(columns=["time", "avg_score", "messages"])
    t = pd.to_datetime(_col(chats, "time"), errors="coerce")
    s = pd.to_numeric(_col(chats, "sentiment_score"), errors="coerce")
    df = pd.DataFrame({"t": t, "s": s}).dropna()
    if df.empty:
        return pd.DataFrame(columns=["time", "avg_score", "messages"])
    freq = "h" if df["t"].max() - df["t"].min() <= pd.Timedelta(days=2) else "D"
    g = df.groupby(df["t"].dt.floor(freq))["s"]
    return pd.DataFrame({"time": g.mean().index, "avg_score": g.mean().round(2).values, "messages": g.size().values})


def resolution_hours(history: pd.DataFrame, tickets: pd.DataFrame) -> float | None:
    """Average hours from ticket creation to first Resolved/Closed, for tickets that got there."""
    if history.empty or tickets.empty:
        return None
    created = {t["ticket_id"]: t["time"] for _, t in tickets.iterrows()}
    hours = []
    done = history[_col(history, "to_status").isin(["resolved", "closed"])]
    for tid, group in done.groupby("ticket_id"):
        try:
            start = datetime.strptime(created[tid], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(group["time"].min(), "%Y-%m-%d %H:%M:%S")
            hours.append((end - start).total_seconds() / 3600)
        except (KeyError, ValueError):
            continue
    return round(sum(hours) / len(hours), 1) if hours else None


def with_outcomes(chats: pd.DataFrame) -> pd.DataFrame:
    """Fill in the outcome for old rows logged before outcomes were recorded (same rule as the chat)."""
    if chats.empty:
        return chats
    logged = _col(chats, "outcome")
    derived = [outcome_from_log(r, s) for r, s in zip(_col(chats, "reply"), _col(chats, "source"))]
    return chats.assign(outcome=[l or d for l, d in zip(logged, derived)])


def summary(data: dict | None = None) -> dict:
    """Everything the Admin Analytics page shows, in one dict."""
    d = data or load()
    chats, tickets, qa, fraud, results = with_outcomes(d["chats"]), d["tickets"], d["qa"], d["fraud"], d["results"]

    replies = len(chats)
    with_source = int((_col(chats, "outcome") == "Answered from help docs").sum()) if replies else 0
    busy = int((_col(chats, "outcome") == "Service busy").sum()) if replies else 0
    backup = int((_col(chats, "model").astype(str).isin([config.FALLBACK_MODEL]) &
                  (config.FALLBACK_MODEL != config.CHAT_MODEL)).sum()) if replies else 0

    reviewed = qa[_col(qa, "result").isin(["PASS", "FAIL"])] if not qa.empty else qa
    passes = int((_col(reviewed, "result") == "PASS").sum()) if not reviewed.empty else 0
    test_avg, test_by_type = None, {}
    if not results.empty and "score" in results.columns:
        scores = pd.to_numeric(results["score"], errors="coerce")
        scored = results.assign(score=scores)[scores > 0]
        if not scored.empty:
            test_avg = round(float(scored["score"].mean()), 2)
            test_by_type = {k: round(float(v), 2) for k, v in scored.groupby("type")["score"].mean().items()}

    return {
        "messages": replies,
        "resolution": resolution(chats, tickets),
        "response": response_times(chats),
        "tickets_total": len(tickets),
        "tickets_by_status": counts(_col(tickets, "status"), ticket_manager.STATUSES),
        "tickets_by_category": {k: v for k, v in counts(_col(tickets, "category"),
                                                       ticket_manager.CATEGORIES).items() if v},
        "tickets_by_priority": counts(_col(tickets, "priority"), ["high", "normal"]),
        "resolution_hours": resolution_hours(d["history"], tickets),
        "sentiment": counts(_col(chats, "sentiment"), ["Positive", "Neutral", "Negative", "Angry"]),
        "risk": counts(_col(chats, "fraud_risk"), ["Low", "Medium", "High"]),
        "fraud_alerts": counts(_col(fraud, "level"), ["Medium", "High"]),
        "fraud_latest": fraud.tail(10).iloc[::-1].to_dict("records") if not fraud.empty else [],
        "top_questions": top_questions(chats),
        "sentiment_trend": sentiment_trend(chats),
        "qa_reviewed": len(reviewed),
        "qa_pass_rate": passes / len(reviewed) if len(reviewed) else None,
        "source_rate": with_source / replies if replies else None,
        "busy_rate": busy / replies if replies else None,
        "backup_rate": backup / replies if replies else None,
        "test_avg": test_avg,
        "test_by_type": test_by_type,
    }
