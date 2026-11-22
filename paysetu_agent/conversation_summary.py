"""Hand-off summary for a human agent, saved on the ticket whenever one is created.

Facts (verified transaction, sentiment, fraud risk, escalation reason, next action) are filled in
by code from verified data. Only "issue" and "steps already taken" are written by Gemini, always
in English, from the already-redacted chat. Everything is redacted again before saving, and a
plain template is used if Gemini is unavailable. PINs, OTPs, CVVs, card/account numbers and full
phone numbers never appear in a summary.
"""
import json
import logging
import re

from google.genai import types

from . import config
from .safety import redact

MAX_TURNS = 8  # last few exchanges are enough for a hand-off

SUMMARY_PROMPT = """You write hand-off notes for a human support agent at PaySetu Wallet (a UPI payments app).
Read the chat between the customer and Setu (PaySetu's AI assistant). Secrets were already removed.
Reply ONLY with JSON in ENGLISH, even if the chat is in Hindi or Hinglish:
{"issue": "<one sentence: the customer's main problem>",
 "steps": ["<up to 3 short items: what Setu already explained or did>"]}
Rules: use only facts from the chat; never invent amounts, dates or IDs; never include PINs, OTPs,
CVVs, card numbers, bank account numbers or full phone numbers.

CHAT:
"""

NEXT_ACTION = {
    "Fraud": "Call the customer urgently. Confirm Block account is done and a 1930 complaint is filed; "
             "review recent transactions and start a dispute with the bank.",
    "Payment Failure": "Check the reversal with the bank. Failed payments reverse within 3 working days; "
                       "if not reversed, raise a dispute (reviewed within 7 working days).",
    "Pending Payment": "Check the payment status. Pending payments complete or reverse within 48 hours; "
                       "follow up if it is older than that.",
    "KYC": "Review why KYC was rejected and guide the customer to redo PAN and Aadhaar OTP verification.",
    "Wallet": "Review the wallet limit and KYC status (₹10,000 without full KYC, ₹2,00,000 with it) "
              "and explain the options.",
    "Cashback": "Check whether the payment was eligible; cashback is added within 24 hours of an eligible payment.",
    "Bills": "Check the bill status with the provider (updates can take up to 48 hours) using the app receipt.",
    "Other": "Contact the customer and answer the question; consider adding it to the help docs.",
}

# A standalone Indian mobile number (not digits inside an ID such as PS9995683007).
_PHONE = re.compile(r"(?<![A-Za-z0-9])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d(\d{4})(?![A-Za-z0-9])")


def sanitize(text: str) -> str:
    """Remove secrets and mask full phone numbers (keep only the last 4 digits)."""
    from .emailer import mask_email

    safe, _ = redact(text or "")
    return mask_email(_PHONE.sub(lambda m: "XXXXXX" + m.group(1), safe))


def _transcript(turns: list[tuple[str, str]]) -> str:
    lines = []
    for customer, setu in turns[-MAX_TURNS:]:
        lines.append(f"Customer: {sanitize(customer)[:600]}")
        lines.append(f"Setu: {sanitize(setu)[:600]}")
    return "\n".join(lines)


def _ai_part(turns: list[tuple[str, str]]) -> tuple[dict | None, str]:
    """Ask Gemini (with backup model) for issue + steps. Returns (data or None, model_used)."""
    from . import rag

    prompt = SUMMARY_PROMPT + _transcript(turns)
    try:
        resp, model = config.with_model_fallback(lambda m: rag._client().models.generate_content(
            model=m, contents=prompt,
            config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json")))
        data = json.loads(re.search(r"\{.*\}", resp.text or "", re.S).group(0))
        issue = str(data.get("issue", "")).strip()
        steps = [str(x).strip() for x in data.get("steps", []) if str(x).strip()][:3]
        return ({"issue": issue, "steps": steps} if issue else None), model
    except Exception as exc:
        logging.warning("AI summary unavailable, using template: %s", exc)
        return None, ""


def _template_steps(turns: list[tuple[str, str]], transaction: dict | None) -> list[str]:
    steps = []
    replies = " ".join(s for _, s in turns)
    sources = re.findall(r"\(Source:\s*([^)]+)\)", replies)
    if sources:
        steps.append("Explained the help-doc answer (" + "; ".join(dict.fromkeys(sources))[:150] + ")")
    if transaction:
        steps.append(f"Verified transaction {transaction.get('txn_id')} with ID and phone digits")
    if "1930" in replies:
        steps.append("Told the customer to tap Block account and call 1930")
    if "never share" in replies.lower():
        steps.append("Warned the customer never to share PIN/OTP/CVV")
    return steps[:3] or ["No troubleshooting steps recorded"]


def build_summary(turns: list[tuple[str, str]], ticket: dict, mood: dict, sentiment: dict,
                  risk: dict, transaction: dict | None = None, use_ai: bool = True) -> str:
    """turns: [(customer message, Setu reply), ...] - already redacted."""
    ai, model = _ai_part(turns) if use_ai else (None, "")
    issue = ai["issue"] if ai else (ticket.get("customer_message") or "See chat")
    steps = ai["steps"] if ai and ai["steps"] else _template_steps(turns, transaction)

    if transaction:
        txn = (f"{transaction.get('txn_id')} | {transaction.get('type')} | ₹{transaction.get('amount_inr')} | "
               f"{transaction.get('date')} | status {transaction.get('status')} (verified: ID + phone last 4)")
    else:
        txn = "None verified in this chat"
    feeling = f"{sentiment.get('label', 'Neutral')} (score {sentiment.get('score', 0)})"
    if mood.get("frustrated"):
        feeling += f"; frustrated - {mood.get('why')}"
    fraud = risk.get("level", "Low")
    if fraud != "Low":
        fraud += " - " + "; ".join(r.split(" (\"")[0] for r in risk.get("reasons", [])[:3])
    category = ticket.get("category") or "Other"
    action = NEXT_ACTION.get(category, NEXT_ACTION["Other"])
    if mood.get("frustrated") or sentiment.get("label") == "Angry":
        action = "Customer is upset: call back promptly and apologise. " + action

    lines = [
        f"Issue: {issue}",
        f"Verified transaction: {txn}",
        "Steps already taken: " + "; ".join(steps),
        f"Customer sentiment: {feeling}",
        f"Fraud risk: {fraud}",
        f"Escalation reason: {ticket.get('reason', '')} (priority {ticket.get('priority', 'normal')}, "
        f"category {category})",
        f"Recommended next action: {action}",
        f"Written by: {'AI (' + model + ') + verified facts' if ai else 'template + verified facts'}",
    ]
    return sanitize("\n".join(lines))
