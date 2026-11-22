"""Fraud risk: Low / Medium / High with plain-English reasons.

Explainable RULES for this fictional demo dataset - not a trained prediction model.
Each rule adds points; the total decides the level:
    0-2 points = Low,  3-4 = Medium,  5+ = High.
High needs real harm (an unrecognised debit, account takeover or a shared secret);
without one, the level is capped at Medium (e.g. "I got a lottery SMS, is it a scam?").
High risk is escalated immediately (high-priority ticket + Block account + 1930).
"""
import re

HIGH_AT, MEDIUM_AT = 5, 3
HARM_REASONS = ("did not make", "hacked", "shared a PIN")  # rules that show real harm

# (points, reason, phrases) - English, Hinglish and Hindi.
RULES = [
    (5, "Customer reports a payment or debit they did not make", [
        "didn't do", "did not do", "didn't make", "did not make", "not done by me", "i didn't authori",
        "without my permission", "without my knowledge", "unauthori", "unknown transaction", "unknown debit",
        "unknown payment", "not me", "taken from my account", "money was taken", "deducted without",
        "maine nahi kiya", "mene nahi kiya", "maine nahi bheja", "bina bataye", "mere bina",
        "मैंने नहीं किया", "मेरे बिना", "बिना बताए",
    ]),
    (5, "Customer says the account may be hacked or taken over", [
        "hacked", "hack ho", "someone logged", "someone else logged", "account compromised",
        "someone is using my account", "lost my phone", "phone stolen", "sim swap", "kisi ne mera account",
        "हैक", "किसी ने मेरा अकाउंट",
    ]),
    (4, "Customer shared a PIN/OTP/CVV with someone else", [
        "shared my otp", "shared otp", "gave my otp", "gave otp", "told my otp", "gave my pin", "shared my pin",
        "told him the otp", "told her the otp", "otp bata diya", "otp de diya", "pin bata diya", "pin de diya",
        "ओटीपी बता दिया", "ओटीपी दे दिया", "पिन बता दिया",
    ]),
    (3, "Signs of a scam call, link or remote-access app", [
        "screen share", "screenshare", "anydesk", "teamviewer", "quicksupport", "remote access",
        "kyc update call", "called me for kyc", "asked for my otp", "asked for otp", "asking for otp",
        "asked for my pin", "lottery", "won a prize", "you have won", "refund agent", "customer care called",
        "click the link", "clicked a link", "scan to receive", "qr to receive", "collect request",
        "otp maang", "otp mang", "pin maang",
        "लॉटरी", "ओटीपी मांग",
    ]),
    (2, "Customer uses fraud or scam words", [
        "fraud", "scam", "scammer", "cheated", "cheat", "dhoka", "thagi", "धोखा", "ठगी", "फ्रॉड",
    ]),
]

AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+)|([\d,]{4,})\s*(?:rupees|rs|रुपये)", re.IGNORECASE)


def _amounts(text: str) -> list[int]:
    out = []
    for a, b in AMOUNT_RE.findall(text or ""):
        digits = (a or b).replace(",", "")
        if digits.isdigit():
            out.append(int(digits))
    return out


def level_for(points: int) -> str:
    return "High" if points >= HIGH_AT else "Medium" if points >= MEDIUM_AT else "Low"


def assess(message: str, removed_secrets: list[str] | None = None, transaction: dict | None = None) -> dict:
    """Score one customer message (plus an optional VERIFIED transaction).

    Returns {"level", "points", "reasons": [...]}.
    """
    low = (message or "").lower()
    points, reasons = 0, []
    for pts, reason, phrases in RULES:
        hit = next((p for p in phrases if p in low), None)
        if hit:
            points += pts
            reasons.append(f"{reason} (\"{hit}\")")

    if removed_secrets and any(s in ("UPI PIN", "OTP", "CVV", "card number") for s in removed_secrets):
        points += 1
        reasons.append("Customer typed a secret (" + ", ".join(removed_secrets) + ") into chat - possible phishing risk")

    big = [a for a in _amounts(message) if a > 5000]
    if big and points > 0:
        points += 2
        reasons.append(f"Suspicious report involves more than ₹5,000 (₹{max(big):,})")

    if transaction and points > 0:
        status = transaction.get("status", "")
        if status in ("Success", "Pending"):
            points += 1
            reasons.append(f"Verified transaction {transaction.get('txn_id')} shows money moved or moving ({status})")
        try:
            if int(str(transaction.get("amount_inr", "0")).replace(",", "")) > 5000:
                points += 1
                reasons.append("Verified transaction amount is above ₹5,000")
        except ValueError:
            pass

    harm = any(any(h in r for h in HARM_REASONS) for r in reasons)
    if not harm and points >= HIGH_AT:
        points = HIGH_AT - 1
        reasons.append("No loss, takeover or shared secret reported, so risk is capped at Medium")
    level = level_for(points)
    if not reasons:
        reasons = ["No fraud signals found"]
    return {"level": level, "points": points, "reasons": reasons}


def combine(*results: dict) -> dict:
    """Keep the highest-risk assessment (e.g. message-only vs message + verified transaction)."""
    best = max(results, key=lambda r: r["points"])
    return best
