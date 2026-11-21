"""CSV storage for tickets, chat log and QA log. Ticket IDs are made here, never by the AI."""
import csv
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

TICKET_FIELDS = ["ticket_id", "time", "customer_message", "reason", "priority", "status"]
CHAT_FIELDS = ["time", "message", "reply", "source"]
QA_FIELDS = ["time", "message", "draft", "result", "reason"]

# Fixed reasons keep the dashboard chart tidy.
TICKET_REASONS = [
    "Fraud or hacked account",
    "Unknown transaction",
    "Disputed amount above ₹5,000",
    "Failed payment not reversed after 3 working days",
    "KYC rejected",
    "Angry or upset customer",
    "Answer not in help docs",
    "Customer asked for a person",
    "Transaction needs action",
]
HIGH_PRIORITY_REASONS = {"Fraud or hacked account", "Unknown transaction"}

_lock = threading.Lock()


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")


def _ensure(path: Path, fields: list[str]) -> None:
    if not path.exists() or path.stat().st_size == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(fields)


def _append(path: Path, fields: list[str], row: dict) -> None:
    _ensure(path, fields)
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(row)


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------- Tickets ----------
def _normalise_reason(reason: str) -> str:
    text = (reason or "").strip().lower()
    for r in TICKET_REASONS:
        if text == r.lower():
            return r
    keywords = [
        (("fraud", "hack", "scam", "stolen"), "Fraud or hacked account"),
        (("unknown", "unauthori", "didn't do", "did not do"), "Unknown transaction"),
        (("5,000", "5000", "dispute"), "Disputed amount above ₹5,000"),
        (("not reversed", "failed"), "Failed payment not reversed after 3 working days"),
        (("kyc",), "KYC rejected"),
        (("angry", "upset", "frustrat", "complain"), "Angry or upset customer"),
        (("person", "human", "agent", "representative"), "Customer asked for a person"),
        (("not in help", "no information", "not available", "don't have"), "Answer not in help docs"),
        (("transaction", "pending", "action"), "Transaction needs action"),
    ]
    for words, label in keywords:
        if any(w in text for w in words):
            return label
    return "Answer not in help docs"


def create_ticket(message: str, reason: str, priority: str) -> dict:
    """Save a ticket and return it. The ID (TKT-1001, TKT-1002, ...) is generated here."""
    reason = _normalise_reason(reason)
    priority = (priority or "").strip().lower()
    if reason in HIGH_PRIORITY_REASONS:
        priority = "high"  # fraud is always high priority
    if priority not in ("normal", "high"):
        priority = "normal"

    with _lock:
        rows = read_rows(config.TICKETS_FILE)
        numbers = [int(r["ticket_id"].split("-")[1]) for r in rows
                   if r.get("ticket_id", "").startswith("TKT-") and r["ticket_id"].split("-")[1].isdigit()]
        ticket = {
            "ticket_id": f"TKT-{max(numbers, default=1000) + 1}",
            "time": now(),
            "customer_message": (message or "").strip()[:500],
            "reason": reason,
            "priority": priority,
            "status": "open",
        }
        _append(config.TICKETS_FILE, TICKET_FIELDS, ticket)
    return ticket


def open_tickets() -> list[dict]:
    return [r for r in read_rows(config.TICKETS_FILE) if r.get("status") == "open"]


# ---------- Logs ----------
def log_chat(message: str, reply: str, source: str) -> None:
    with _lock:
        _append(config.CHAT_LOG_FILE, CHAT_FIELDS,
                {"time": now(), "message": message, "reply": reply, "source": source})


def log_qa(message: str, draft: str, result: str, reason: str) -> None:
    with _lock:
        _append(config.QA_LOG_FILE, QA_FIELDS,
                {"time": now(), "message": message, "draft": draft, "result": result, "reason": reason})
