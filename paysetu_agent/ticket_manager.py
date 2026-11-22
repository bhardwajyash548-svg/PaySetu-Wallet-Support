"""Tickets: creation, smart classification, status workflow, history and audit log.

Ticket IDs (TKT-1001, TKT-1002, ...) are generated here by code, never by the AI.
The brief's six original columns stay first; enterprise columns are appended.
"""
import re

from . import config, storage

ORIGINAL_FIELDS = ["ticket_id", "time", "customer_message", "reason", "priority", "status"]
TICKET_FIELDS = ORIGINAL_FIELDS + [
    "category", "sentiment", "fraud_risk", "summary", "session_id", "updated_at",
]

STATUSES = ["open", "in_progress", "resolved", "closed"]
# Allowed status changes (admins can also re-open a ticket).
TRANSITIONS = {
    "open": {"in_progress", "resolved", "closed"},
    "in_progress": {"open", "resolved", "closed"},
    "resolved": {"closed", "open"},
    "closed": {"open"},
}
HISTORY_FIELDS = ["ticket_id", "time", "from_status", "to_status", "changed_by", "note"]
AUDIT_FIELDS = ["time", "actor", "action", "target", "details"]

CATEGORIES = ["Fraud", "Payment Failure", "Pending Payment", "KYC", "Wallet", "Cashback", "Bills", "Other"]
# Checked in this order; the first match wins. Words in English, Hinglish and Hindi.
_CATEGORY_WORDS = [
    ("KYC", ["kyc", "pan", "aadhaar", "aadhar", "verification rejected", "केवाईसी"]),
    ("Pending Payment", ["pending", "processing", "stuck", "atka", "अटका", "पेंडिंग"]),
    ("Payment Failure", ["failed", "fail ho", "deducted", "not reversed", "reversal", "refund", "wrong upi",
                         "wrong person", "by mistake", "dispute", "kat gaye", "money gone", "फेल", "कट गए"]),
    ("Bills", ["bill", "electricity", "fastag", "dth", "broadband", "postpaid", "recharge", "gas", "water",
               "बिल", "बिजली"]),
    ("Cashback", ["cashback", "cash back", "कैशबैक"]),
    ("Wallet", ["wallet", "add money", "limit", "balance", "वॉलेट"]),
]
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


def _clean_text(text: str) -> str:
    """Remove PINs/OTPs/card/account numbers and mask phone numbers (defence in depth: the AI
    only ever sees redacted text, but its ticket message is cleaned again here)."""
    from .conversation_summary import sanitize

    return sanitize((text or "").strip())


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


def _has_word(text: str, word: str) -> bool:
    """Whole-word match for English words ("pan" must not match "company"); substring for Hindi."""
    if word.isascii():
        return re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text) is not None
    return word in text


def classify(message: str, reason: str = "", transaction: dict | None = None,
             fraud_level: str = "Low") -> str:
    """Pick one category: Fraud, Payment Failure, Pending Payment, KYC, Wallet, Cashback, Bills, Other."""
    reason = normalise_reason(reason) if reason else ""
    if reason in HIGH_PRIORITY_REASONS or fraud_level == "High":
        return "Fraud"
    if reason == "KYC rejected":
        return "KYC"
    status = (transaction or {}).get("status", "")
    if status == "Failed" or reason == "Failed payment not reversed after 3 working days":
        return "Payment Failure"
    if status == "Pending":
        return "Pending Payment"
    text = f"{message} {reason}".lower()
    for category, words in _CATEGORY_WORDS:
        if any(_has_word(text, w) for w in words):
            return category
    if reason == "Disputed amount above ₹5,000":
        return "Payment Failure"
    return "Other"


def all_tickets() -> list[dict]:
    if config.TICKETS_FILE.exists():
        storage.ensure_schema(config.TICKETS_FILE, TICKET_FIELDS)  # upgrade old files
    rows = storage.read_rows(config.TICKETS_FILE)
    for r in rows:
        for c in TICKET_FIELDS:
            r.setdefault(c, "")
        if r["category"] not in CATEGORIES:  # tickets created before classification existed
            r["category"] = classify(r["customer_message"], r["reason"], fraud_level=r["fraud_risk"] or "Low")
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
            "customer_message": _clean_text(message)[:500],
            "reason": reason,
            "priority": priority,
            "status": "open",
            "session_id": session_id or "",
            "updated_at": ts,
            **{k: v for k, v in extra.items() if k in TICKET_FIELDS},
        }
        if ticket.get("category") not in CATEGORIES:
            ticket["category"] = classify(message, reason, fraud_level=extra.get("fraud_risk", "Low"))
        storage.append_row(config.TICKETS_FILE, TICKET_FIELDS, ticket)
        _history(ticket["ticket_id"], "", "open", "system", f"Created: {reason}")
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


# ---------- status workflow ----------
class TicketError(ValueError):
    """A ticket change that is not allowed (unknown ticket, bad status, no admin)."""


def _history(ticket_id: str, from_status: str, to_status: str, changed_by: str, note: str = "") -> None:
    storage.append_row(config.TICKET_HISTORY_FILE, HISTORY_FIELDS, {
        "ticket_id": ticket_id, "time": storage.now(), "from_status": from_status,
        "to_status": to_status, "changed_by": changed_by, "note": note[:300]})


def audit(actor: str, action: str, target: str, details: str = "") -> None:
    """Record an administrative action (who did what, to which ticket, when)."""
    storage.append_row(config.AUDIT_LOG_FILE, AUDIT_FIELDS, {
        "time": storage.now(), "actor": actor, "action": action, "target": target, "details": details[:300]})


def history(ticket_id: str) -> list[dict]:
    return [h for h in storage.read_rows(config.TICKET_HISTORY_FILE) if h["ticket_id"] == ticket_id]


def change_status(ticket_id: str, new_status: str, changed_by: str, note: str = "") -> dict:
    """Move a ticket to a new status. Only for authenticated admins (changed_by = admin name).

    Raises TicketError if the ticket does not exist, the status is unknown or the move is not allowed.
    Every change is written to ticket_history.csv and audit_log.csv.
    """
    actor = (changed_by or "").strip()
    if not actor:
        raise TicketError("Only an authenticated admin can change a ticket.")
    new_status = (new_status or "").strip().lower().replace(" ", "_")
    if new_status not in STATUSES:
        raise TicketError(f"Unknown status '{new_status}'. Use one of: {', '.join(STATUS_LABELS.values())}.")
    with storage.lock:
        rows = all_tickets()
        ticket = next((r for r in rows if r["ticket_id"] == (ticket_id or "").strip().upper()), None)
        if ticket is None:
            raise TicketError(f"Ticket {ticket_id} not found.")
        old = ticket["status"] or "open"
        if new_status == old:
            raise TicketError(f"{ticket['ticket_id']} is already {STATUS_LABELS[old]}.")
        if new_status not in TRANSITIONS.get(old, set()):
            raise TicketError(f"Cannot move {ticket['ticket_id']} from {STATUS_LABELS.get(old, old)} "
                              f"to {STATUS_LABELS[new_status]}.")
        ticket["status"] = new_status
        ticket["updated_at"] = storage.now()
        storage.write_rows(config.TICKETS_FILE, TICKET_FIELDS, rows)
        _history(ticket["ticket_id"], old, new_status, actor, note)
        audit(actor, "change_status", ticket["ticket_id"],
              f"{STATUS_LABELS.get(old, old)} -> {STATUS_LABELS[new_status]}" + (f" | {note}" if note else ""))
    return ticket
