"""Analytics: every metric checked against hand-made logs with known answers."""
from pathlib import Path

import pandas as pd
import pytest

from paysetu_agent import analytics
from paysetu_agent.outcomes import BUSY_REPLY
from paysetu_agent.prompts import NO_INFO_REPLY

ROOT = Path(__file__).resolve().parent.parent


def chat(sid, msg, reply, source="none", outcome="", ms="", sent="", score="", risk="", time="2026-11-22 10:00:00",
         model=""):
    return {"time": time, "message": msg, "reply": reply, "source": source, "session_id": sid, "outcome": outcome,
            "response_ms": ms, "sentiment": sent, "sentiment_score": score, "fraud_risk": risk, "model": model}


@pytest.fixture
def data():
    chats = pd.DataFrame([
        # A: answered from the docs -> resolved
        chat("A", "What is the daily UPI limit?", "₹1,00,000. (Source: FAQ: x)", "FAQ: x", "Answered from help docs",
             "1000", "Neutral", "0", "Low", "2026-11-22 10:05:00", "gemini-3.5-flash-lite"),
        # B: ticket created -> not resolved
        chat("B", "my account is hacked", "Block account, 1930. Ticket TKT-1001.", "none", "Ticket created", "2000",
             "Negative", "-0.67", "High", "2026-11-22 10:10:00", "gemini-3.1-flash-lite"),
        # C: last reply was "I don't have that information" -> not resolved
        chat("C", "what is the daily upi limit?", "ok", "FAQ: x", "Answered from help docs", "3000",
             "Neutral", "0", "Low", "2026-11-22 11:00:00"),
        chat("C", "loyalty points?", NO_INFO_REPLY, "none", "Not in help docs", "4000", "Neutral", "0", "Low",
             "2026-11-22 11:01:00"),
        # D: service busy -> not resolved
        chat("D", "hi", BUSY_REPLY, "none", "Service busy", "10000", "Positive", "0.5", "Low", "2026-11-22 11:30:00"),
        # E: answered, but a ticket exists for this session in tickets.csv -> not resolved
        chat("E", "THIS IS USELESS!!!", "Sorry.", "none", "Other", "", "Angry", "-1", "Medium", "2026-11-22 12:00:00"),
        # legacy row (no session, no outcome): outcome derived from the reply -> answered -> resolved
        chat("", "Which bills can I pay?", "Electricity... (Source: FAQ: Which bills can I pay?)",
             "FAQ: Which bills can I pay?"),
    ])
    tickets = pd.DataFrame([
        {"ticket_id": "TKT-1001", "time": "2026-11-22 10:00:00", "status": "resolved", "category": "Fraud",
         "priority": "high", "session_id": "B"},
        {"ticket_id": "TKT-1002", "time": "2026-11-22 12:00:00", "status": "open", "category": "Other",
         "priority": "normal", "session_id": "E"},
    ])
    history = pd.DataFrame([
        {"ticket_id": "TKT-1001", "time": "2026-11-22 10:00:00", "from_status": "", "to_status": "open"},
        {"ticket_id": "TKT-1001", "time": "2026-11-22 12:30:00", "from_status": "open", "to_status": "resolved"},
    ])
    qa = pd.DataFrame([{"result": r} for r in ("PASS", "PASS", "FAIL", "SKIPPED")])
    fraud = pd.DataFrame([{"level": "High", "time": "t1"}, {"level": "Medium", "time": "t2"}])
    results = pd.DataFrame([{"#": "1", "type": "FAQ", "score": "5"}, {"#": "2", "type": "FAQ", "score": "4"},
                            {"#": "3", "type": "Guardrail", "score": "3"}, {"#": "4", "type": "Lookup", "score": "0"}])
    return {"chats": chats, "tickets": tickets, "history": history, "qa": qa, "fraud": fraud, "results": results}


def test_ai_resolution_rate(data):
    s = analytics.summary(data)
    assert s["resolution"] == {"conversations": 6, "resolved": 2, "rate": 2 / 6}   # A and the legacy row


def test_response_times(data):
    assert analytics.summary(data)["response"] == {"count": 5, "avg_s": 4.0, "median_s": 3.0, "p90_s": 7.6}


def test_ticket_counts_and_time_to_resolve(data):
    s = analytics.summary(data)
    assert s["tickets_total"] == 2
    assert s["tickets_by_status"] == {"open": 1, "in_progress": 0, "resolved": 1, "closed": 0}
    assert s["tickets_by_category"] == {"Fraud": 1, "Other": 1}
    assert s["tickets_by_priority"] == {"high": 1, "normal": 1}
    assert s["resolution_hours"] == 2.5


def test_sentiment_risk_and_fraud_alerts(data):
    s = analytics.summary(data)
    assert s["sentiment"] == {"Positive": 1, "Neutral": 3, "Negative": 1, "Angry": 1}
    assert s["risk"] == {"Low": 4, "Medium": 1, "High": 1}
    assert s["fraud_alerts"] == {"Medium": 1, "High": 1}


def test_top_questions_merge_case(data):
    top = analytics.summary(data)["top_questions"]
    assert top[0] == ("What is the daily UPI limit?", 2)   # two wordings differing only in case


def test_quality_metrics(data):
    s = analytics.summary(data)
    assert s["qa_reviewed"] == 3 and s["qa_pass_rate"] == 2 / 3      # SKIPPED is not counted
    assert s["source_rate"] == 3 / 7                                  # A, C(1st), legacy
    assert s["busy_rate"] == 1 / 7
    assert s["test_avg"] == 4.0 and s["test_by_type"] == {"FAQ": 4.5, "Guardrail": 3.0}   # score 0 ignored


def test_backup_model_share(data):
    assert analytics.summary(data)["backup_rate"] == 1 / 7


def test_sentiment_trend_by_hour(data):
    t = analytics.summary(data)["sentiment_trend"]
    assert list(t["messages"]) == [2, 3, 1]                      # 10:00, 11:00, 12:00 (legacy row has no score)
    assert list(t["avg_score"]) == [-0.34, 0.17, -1.0]


def test_empty_logs_do_not_crash():
    empty = {k: pd.DataFrame() for k in ("chats", "tickets", "history", "qa", "fraud", "results")}
    s = analytics.summary(empty)
    assert s["resolution"]["rate"] is None and s["response"]["avg_s"] is None and s["qa_pass_rate"] is None
    assert s["tickets_total"] == 0 and s["top_questions"] == []


def test_analytics_page_is_admin_only():
    src = (ROOT / "views" / "admin_analytics.py").read_text()
    assert src.index("admin = require_admin()") < src.index("analytics.summary()")
    assert 'st.Page("views/admin_analytics.py"' in (ROOT / "app.py").read_text()
