"""Code-level guardrail: remove secrets from customer messages BEFORE the AI or any log sees them.

This guarantees Setu can never repeat a PIN/OTP/CVV/card/account number, even if the
prompt is tricked. Setu sees a placeholder like "[UPI PIN removed]" and warns the customer.
"""
import re

# Keyword (English / Hindi / Hinglish) followed by digits, e.g. "UPI PIN is 4821", "otp: 552311", "पिन 1234"
_KEYWORD_THEN_DIGITS = [
    ("UPI PIN", r"(?:upi\s*)?(?:m-?)?pin|पिन"),
    ("OTP", r"otp|ओटीपी"),
    ("CVV", r"cvv|cvc"),
]
_DIGITS_THEN_KEYWORD = [
    ("UPI PIN", r"(?:upi\s*)?pin|पिन"),
    ("OTP", r"otp|ओटीपी"),
    ("CVV", r"cvv"),
]

_CARD = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")  # 13-19 digit card numbers
_ACCOUNT = re.compile(
    r"((?:a/?c|acc(?:ount)?|bank\s*account|खाता)\s*(?:no\.?|number|num)?\s*(?:is|:|=|hai|है)?\s*)(\d{9,18})",
    re.IGNORECASE,
)
_LONG_NUMBER = re.compile(r"(?<![\w-])\d{11,18}(?![\w-])")  # 11-18 digits: likely an account number


def redact(text: str) -> tuple[str, list[str]]:
    """Return (safe_text, list_of_what_was_removed)."""
    found: list[str] = []
    safe = text or ""

    # Long numbers first, so the short-code rules below can't split a card number.
    if _CARD.search(safe):
        found.append("card number")
        safe = _CARD.sub("[card number removed]", safe)

    if _ACCOUNT.search(safe):
        found.append("bank account number")
        safe = _ACCOUNT.sub(lambda m: f"{m.group(1)}[bank account number removed]", safe)

    if _LONG_NUMBER.search(safe):
        found.append("bank account number")
        safe = _LONG_NUMBER.sub("[bank account number removed]", safe)

    for label, kw in _KEYWORD_THEN_DIGITS:
        pattern = re.compile(rf"(\b|^)({kw})(\W{{0,12}}?(?:is|:|=|hai|है|was)?\W{{0,6}})(\d{{3,8}})\b",
                             re.IGNORECASE)
        if pattern.search(safe):
            found.append(label)
            safe = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[{label} removed]", safe)

    for label, kw in _DIGITS_THEN_KEYWORD:
        pattern = re.compile(rf"\b(\d{{3,8}})(\s*(?:is\s+)?(?:my\s+)?(?:{kw}))", re.IGNORECASE)
        if pattern.search(safe):
            found.append(label)
            safe = pattern.sub(lambda m: f"[{label} removed]{m.group(2)}", safe)

    return safe, sorted(set(found))
