"""Tools Setu can call. Each tool is a plain Python function; ADK reads its docstring."""
import csv
import logging
import re

from google.adk.tools import ToolContext

from . import config, emailer, rag, storage, ticket_manager

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


def create_ticket(message: str, reason: str, priority: str, tool_context: ToolContext) -> dict:
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
        session = getattr(tool_context, "session", None)
        session_id = getattr(session, "id", "") or ""
        # One ticket per issue per chat: a repeat request returns the existing ticket.
        same = [t for t in ticket_manager.open_tickets(session_id=session_id)
                if session_id and t["reason"] == ticket_manager.normalise_reason(reason)]
        if same:
            t = same[-1]
            return {"status": "already_open", "ticket_id": t["ticket_id"], "priority": t["priority"],
                    "reason": t["reason"], "follow_up": "A human representative will reply within 24 hours."}
        ticket = ticket_manager.create_ticket(message, reason, priority, session_id=session_id)
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
                    # Remember the verification for this chat only (needed to email the PDF later).
                    verified = dict(tool_context.state.get("verified_txns", {}))
                    verified[txn] = last4
                    tool_context.state["verified_txns"] = verified
                    return {
                        "status": "found",
                        "transaction": {
                            "txn_id": row["txn_id"],
                            "type": row["type"],
                            "amount_inr": row["amount_inr"],
                            "date": row["date"],
                            "status": status,
                            "phone_last4": last4,  # what the customer typed; needed to re-verify for a PDF
                        },
                        "needs_action": status in ("Failed", "Pending"),
                    }
    except Exception as exc:
        logging.error("Transaction lookup failed: %s", exc)
        return {"status": "error", "message": "Transaction lookup is unavailable right now."}
    return {"status": "not found"}


MAX_EMAILS_PER_CHAT = 3


def send_receipt_email(txn_id: str, email: str, tool_context: ToolContext) -> dict:
    """Email the PDF for ONE transaction to the customer.

    Only works for a transaction verified earlier in THIS chat (ID + phone last 4), and only to an
    email address the customer typed in this chat. Success gets a payment receipt; any other status
    gets a transaction status statement.

    Args:
        txn_id: The verified transaction ID, e.g. "PS9995683007".
        email: The email address the customer gave, e.g. "name@gmail.com".

    Returns:
        {"status": "sent", "to": masked address, "document": ...} or another status with a message.
    """
    from .receipt_generator import ReceiptError, make_pdf

    session_id = getattr(getattr(tool_context, "session", None), "id", "") or ""
    txn = re.sub(r"\s", "", str(txn_id or "")).upper()
    phone = tool_context.state.get("verified_txns", {}).get(txn)

    def done(status: str, message: str, address: str = "", **extra) -> dict:
        storage.log_email(session_id, txn, emailer.mask_email(address), status)
        return {"status": status, "message": message, **extra}

    if not phone:
        return done("not_verified", "This transaction has not been verified in this chat. Ask for the "
                    "transaction ID and the last 4 digits of the registered phone number first.")
    to = emailer.clean_email(email)
    if not to:
        return done("invalid_email", "That does not look like a valid email address. Ask the customer to "
                    "type it again.", email or "")
    sent = int(tool_context.state.get("emails_sent", 0))
    if sent >= MAX_EMAILS_PER_CHAT:
        return done("limit_reached", "The email limit for this chat has been reached.", to)
    if not emailer.is_configured():
        return done("email_not_configured", "Email sending is not set up on this server, so the PDF cannot be "
                    "emailed right now. The customer can use the download button instead.", to)
    try:
        pdf, filename = make_pdf(txn, phone)  # re-verifies ID + phone against the records
        row = next(r for r in _rows() if r["txn_id"] == txn)
        title = "Payment Receipt" if row["status"] == "Success" else "Transaction Status Statement"
        emailer.send_document(to, pdf, filename, row, title)
    except ReceiptError:
        return done("not_verified", "This transaction could not be verified.", to)
    except Exception as exc:
        logging.warning("Receipt email failed: %s", type(exc).__name__)
        return done("send_failed", "The email could not be sent right now. Please try again later.", to)
    tool_context.state["emails_sent"] = sent + 1
    return done("sent", f"{title} emailed.", to, to=emailer.mask_email(to), document=title)


def _rows() -> list[dict]:
    with config.TRANSACTIONS_FILE.open(newline="", encoding="utf-8") as f:
        return [{k: v.strip() for k, v in r.items()} for r in csv.DictReader(f)]
