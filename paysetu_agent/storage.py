"""CSV storage helpers and the chat / QA logs.

Every CSV keeps the brief's original columns first; newer columns are appended.
Old files are upgraded in place (ensure_schema) without losing rows.
Tickets live in ticket_manager.py.
"""
import csv
import os
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

# Original brief columns first, enterprise columns after.
CHAT_FIELDS = ["time", "message", "reply", "source",
               "session_id", "outcome", "response_ms", "sentiment", "sentiment_score", "fraud_risk", "model"]
QA_FIELDS = ["time", "message", "draft", "result", "reason"]
FRAUD_FIELDS = ["time", "session_id", "level", "points", "reasons", "message", "ticket_ids"]

lock = threading.RLock()  # one lock for all CSV writes in this process


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ensure_schema(path: Path, fields: list[str]) -> list[str]:
    """Create the file with `fields`, or add any missing columns to an older file.

    Returns the file's final column order (existing extra columns are kept at the end).
    """
    with lock:
        if not path.exists() or path.stat().st_size == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(fields)
            return list(fields)
        with path.open(newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        missing = [c for c in fields if c not in header]
        if not missing:
            return header
        final = fields + [c for c in header if c not in fields]
        rows = read_rows(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=final, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in final})
        os.replace(tmp, path)
        return final


def append_row(path: Path, fields: list[str], row: dict) -> None:
    with lock:
        header = ensure_schema(path, fields)
        with path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=header, extrasaction="ignore").writerow(
                {c: row.get(c, "") for c in header})


def write_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    """Atomically rewrite a whole CSV (used for ticket updates)."""
    with lock:
        header = ensure_schema(path, fields)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in header})
        os.replace(tmp, path)


# ---------- Logs ----------
def log_chat(message: str, reply: str, source: str, **extra) -> None:
    """extra: session_id, outcome, response_ms, sentiment, sentiment_score, fraud_risk."""
    append_row(config.CHAT_LOG_FILE, CHAT_FIELDS,
               {"time": now(), "message": message, "reply": reply, "source": source, **extra})


def log_qa(message: str, draft: str, result: str, reason: str) -> None:
    append_row(config.QA_LOG_FILE, QA_FIELDS,
               {"time": now(), "message": message, "draft": draft, "result": result, "reason": reason})


def log_fraud(session_id: str, risk: dict, message: str, ticket_ids: list[str]) -> None:
    """Medium/High fraud assessments, for the admin fraud-alert view."""
    append_row(config.FRAUD_ALERTS_FILE, FRAUD_FIELDS, {
        "time": now(), "session_id": session_id, "level": risk["level"], "points": risk["points"],
        "reasons": " | ".join(risk["reasons"]), "message": message, "ticket_ids": " ".join(ticket_ids)})
