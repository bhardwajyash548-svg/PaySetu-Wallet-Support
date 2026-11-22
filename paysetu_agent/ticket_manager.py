"""Tickets: creation, reading and (later phases) classification and status tracking.

Ticket IDs (TKT-1001, TKT-1002, ...) are generated here by code, never by the AI.
The brief's six original columns stay first; enterprise columns are appended.
"""
from . import config, storage

ORIGINAL_FIELDS = ["ticket_id", "time", "customer_message", "reason", "priority", "status"]
TICKET_FIELDS = ORIGINAL_FIELDS + [
    "category", "sentiment", "fraud_risk", "summary", "session_id", "updated_at",
]

STATUSES = ["open", "in_progress", "resolved", "closed"]
STATUS_LABELS = {"open": "Open", "in_progress": "In Progress", "resolved": "Resolved", "closed": "Closed"}

# Fixed reasons keep the dashboard tidy (original hand-off rules + lookup follow-up).
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


def normalise_reason(reason: str) -> str:
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


def all_tickets() -> list[dict]:
    if config.TICKETS_FILE.exists():
        storage.ensure_schema(config.TICKETS_FILE, TICKET_FIELDS)  # upgrade old files
    rows = storage.read_rows(config.TICKETS_FILE)
    for r in rows:
        for c in TICKET_FIELDS:
            r.setdefault(c, "")
    return rows


def get_ticket(ticket_id: str) -> dict | None:
    tid = (ticket_id or "").strip().upper()
    return next((t for t in all_tickets() if t["ticket_id"] == tid), None)


def open_tickets(session_id: str | None = None) -> list[dict]:
    """Open tickets; with session_id, only that chat's tickets (customers never see others')."""
    rows = [t for t in all_tickets() if t.get("status") == "open"]
    if session_id is not None:
        rows = [t for t in rows if t.get("session_id") == session_id]
    return rows


def create_ticket(message: str, reason: str, priority: str, session_id: str = "", **extra) -> dict:
    """Save a ticket and return it. extra: category, sentiment, fraud_risk, summary."""
    reason = normalise_reason(reason)
    priority = (priority or "").strip().lower()
    if reason in HIGH_PRIORITY_REASONS:
        priority = "high"  # fraud is always high priority
    if priority not in ("normal", "high"):
        priority = "normal"

    with storage.lock:
        rows = all_tickets()
        numbers = [int(r["ticket_id"].split("-")[1]) for r in rows
                   if r.get("ticket_id", "").startswith("TKT-") and r["ticket_id"].split("-")[1].isdigit()]
        ts = storage.now()
        ticket = {
            "ticket_id": f"TKT-{max(numbers, default=1000) + 1}",
            "time": ts,
            "customer_message": (message or "").strip()[:500],
            "reason": reason,
            "priority": priority,
            "status": "open",
            "session_id": session_id or "",
            "updated_at": ts,
            **{k: v for k, v in extra.items() if k in TICKET_FIELDS},
        }
        storage.append_row(config.TICKETS_FILE, TICKET_FIELDS, ticket)
    return ticket


def update_fields(ticket_id: str, **fields) -> dict | None:
    """Set extra fields on a ticket (e.g. summary, session_id). Returns the updated ticket."""
    allowed = {k: v for k, v in fields.items() if k in TICKET_FIELDS and k not in ("ticket_id", "time")}
    with storage.lock:
        rows = all_tickets()
        hit = None
        for r in rows:
            if r["ticket_id"] == ticket_id:
                r.update(allowed)
                r["updated_at"] = storage.now()
                hit = r
        if hit:
            storage.write_rows(config.TICKETS_FILE, TICKET_FIELDS, rows)
    return hit
