"""Tools Setu can call. Each tool is a plain Python function; ADK reads its docstring."""
import csv
import logging
import re

from google.adk.tools import ToolContext

from . import config, rag, storage

MAX_LOOKUPS_PER_CHAT = 5  # stops someone guessing many ID/phone combinations


def search_help_docs(question: str, tool_context: ToolContext) -> dict:
    """Search PaySetu's official help docs and return the 3 most relevant sections.

    Use this for every question about PaySetu payments, UPI, wallet, KYC, bills,
    cashback, fees, limits, timelines, disputes or account security.

    Args:
        question: The customer's question, in English, in your own words.

    Returns:
        A dict with "results": a list of {"source", "text"} sections.
    """
    try:
        results = rag.search(question)
    except Exception as exc:
        logging.warning("search_help_docs failed: %s", exc)
        return {"status": "error", "results": [], "message": "Help docs search is unavailable right now."}

    chunks = [{"source": r["source"], "text": r["text"]} for r in results]
    # Remember what was retrieved (the QA reviewer checks the reply against these).
    tool_context.state["last_chunks"] = chunks
    return {"status": "ok", "results": chunks}


def create_ticket(message: str, reason: str, priority: str) -> dict:
    """Create a support ticket so a human representative follows up within 24 hours.

    Args:
        message: A short ENGLISH summary of the customer's issue (translate if needed).
            Never include PINs, OTPs, CVVs, card or bank account numbers.
        reason: One of: "Fraud or hacked account", "Unknown transaction",
            "Disputed amount above ₹5,000", "Failed payment not reversed after 3 working days",
            "KYC rejected", "Angry or upset customer", "Answer not in help docs",
            "Customer asked for a person", "Transaction needs action".
        priority: "high" for fraud, hacked accounts or unknown transactions; otherwise "normal".

    Returns:
        A dict with the real "ticket_id" to share with the customer.
    """
    try:
        ticket = storage.create_ticket(message, reason, priority)
    except Exception as exc:
        logging.error("create_ticket failed: %s", exc)
        return {"status": "error", "message": "Ticket could not be saved."}
    return {
        "status": "created",
        "ticket_id": ticket["ticket_id"],
        "priority": ticket["priority"],
        "reason": ticket["reason"],
        "follow_up": "A human representative will reply within 24 hours.",
    }


def get_transaction_status(txn_id: str, phone_last4: str, tool_context: ToolContext) -> dict:
    """Look up ONE transaction for the customer. Both values must come from the customer.

    Args:
        txn_id: The transaction ID the customer gave, e.g. "PS9995683007".
        phone_last4: The last 4 digits of the customer's registered phone number.

    Returns:
        {"status": "found", "transaction": {...}} only if BOTH values match the same
        transaction; otherwise {"status": "not found"}.
    """
    count = tool_context.state.get("lookup_count", 0) + 1
    tool_context.state["lookup_count"] = count
    if count > MAX_LOOKUPS_PER_CHAT:
        return {"status": "limit reached",
                "message": "Too many lookups in this chat. Offer to connect the customer to a person."}

    txn = re.sub(r"\s", "", str(txn_id or "")).upper()
    last4 = re.sub(r"\D", "", str(phone_last4 or ""))
    if not re.fullmatch(r"PS\d{10}", txn) or len(last4) != 4:
        return {"status": "not found"}

    try:
        with config.TRANSACTIONS_FILE.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["txn_id"].strip().upper() == txn and row["phone_last4"].strip() == last4:
                    status = row["status"].strip()
                    return {
                        "status": "found",
                        "transaction": {
                            "txn_id": row["txn_id"],
                            "type": row["type"],
                            "amount_inr": row["amount_inr"],
                            "date": row["date"],
                            "status": status,
                        },
                        "needs_action": status in ("Failed", "Pending"),
                    }
    except Exception as exc:
        logging.error("Transaction lookup failed: %s", exc)
        return {"status": "error", "message": "Transaction lookup is unavailable right now."}
    return {"status": "not found"}
