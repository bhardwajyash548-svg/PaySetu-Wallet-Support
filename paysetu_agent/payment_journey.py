"""Payment journey for ONE verified transaction.

Shows only facts from data/transactions.csv (date, type, amount, actual status) plus the
official PaySetu policy for that status. It never invents bank events, live updates or
confirmations. Working days count Monday-Friday (public holidays are not in our data).
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

POLICY_SOURCE = "Failed, pending and wrong payments policy"


def parse_date(text: str) -> date | None:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime((text or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def today_ist() -> date:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def working_days_after(start: date, end: date) -> int:
    """Mon-Fri days after `start`, up to and including `end`."""
    days, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def build_journey(txn: dict, today: date | None = None) -> dict:
    """Return {"steps": [...], "headline", "next_action", "needs_ticket", "source", "facts"}.

    Each step: {"kind": "fact" | "policy", "label", "value", "detail", "tone"}.
    tone is one of ok / bad / wait / info (for colouring only).
    """
    today = today or today_ist()
    status = (txn.get("status") or "").strip()
    when = parse_date(txn.get("date", ""))
    try:
        amount = f"₹{int(str(txn.get('amount_inr', '0')).replace(',', '')):,}"
    except ValueError:
        amount = f"₹{txn.get('amount_inr', '')}"

    steps = [
        {"kind": "fact", "label": "Recorded", "value": txn.get("date", "unknown date"),
         "detail": f"{txn.get('type', 'Payment')} of {amount}", "tone": "info"},
        {"kind": "fact", "label": "Actual status", "value": status or "Unknown",
         "detail": "From PaySetu transaction records",
         "tone": {"Success": "ok", "Failed": "bad", "Pending": "wait", "Reversed": "info"}.get(status, "info")},
    ]
    needs_ticket = False
    elapsed = working_days_after(when, today) if when else None

    if status == "Success":
        policy = ("Completed", "No further steps in our records.")
        headline = "This payment completed successfully."
        next_action = "No action needed. You can download the receipt below."
    elif status == "Failed":
        policy = ("Reversal within 3 working days",
                  "Failed payments are reversed to the bank automatically within 3 working days.")
        if elapsed is not None and elapsed > 3:
            needs_ticket = True
            headline = f"This payment failed and {elapsed} working days have passed since {txn.get('date')}."
            next_action = ("The 3-working-day reversal window has passed, so a person should check it. "
                           "We can raise a ticket for you.")
        else:
            left = 3 - (elapsed or 0)
            headline = "This payment failed. The reversal window is still open."
            next_action = (f"Please wait up to {left} more working day{'s' if left != 1 else ''} for the automatic "
                           "reversal. If it does not arrive, we can raise a ticket.")
    elif status == "Pending":
        policy = ("Completes or reverses within 48 hours",
                  "A pending payment either completes or is reversed on its own within 48 hours.")
        days = (today - when).days if when else None
        if days is not None and days > 2:
            needs_ticket = True
            headline = f"This payment has been pending since {txn.get('date')}, which is more than 48 hours."
            next_action = "It is past the 48-hour window, so a person should check it. We can raise a ticket for you."
        else:
            headline = "This payment is still pending."
            next_action = "Please wait up to 48 hours from the payment; it will complete or reverse on its own."
    elif status == "Reversed":
        policy = ("Reversed", "The payment did not go through and the amount was reversed to the source account.")
        headline = "This payment was reversed."
        next_action = ("No action needed in our records. If the money is not in your account, "
                       "we can raise a ticket for a person to check.")
    else:
        policy = ("Status unclear", "Our records do not show a clear status.")
        headline = "We could not read this payment's status."
        next_action = "A person should check this. We can raise a ticket for you."
        needs_ticket = True

    steps.append({"kind": "policy", "label": "What the policy says", "value": policy[0], "detail": policy[1],
                  "tone": "info"})
    if elapsed is not None and status == "Failed":
        steps[-1]["detail"] += f" ({elapsed} working day{'s' if elapsed != 1 else ''} since the payment, Mon-Fri.)"
    elif when and status == "Pending":
        days = (today - when).days
        steps[-1]["detail"] += f" ({days} day{'s' if days != 1 else ''} since the payment date.)"

    return {
        "txn_id": txn.get("txn_id", ""),
        "facts": {"type": txn.get("type", ""), "amount": amount, "date": txn.get("date", ""), "status": status},
        "steps": steps,
        "headline": headline,
        "next_action": next_action,
        "needs_ticket": needs_ticket,
        "receipt_title": "Payment Receipt" if status == "Success" else "Transaction Status Statement",
        "source": POLICY_SOURCE,
    }
