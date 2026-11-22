"""Customer sentiment: Positive / Neutral / Negative / Angry, with a score from -1 to +1.

Rule-based and explainable (word lists in English, Hindi and Hinglish, plus tone signals
such as "!!!" and ALL CAPS). No AI call, so it is fast, free and testable.
A conversation tracker detects frustration across messages.
"""
import re
from dataclasses import dataclass, field

LABELS = ["Positive", "Neutral", "Negative", "Angry"]

POSITIVE = [
    "thank", "thanks", "thx", "great", "awesome", "perfect", "helpful", "resolved", "solved", "works now",
    "appreciate", "good job", "excellent", "nice", "love", "happy", "glad",
    "dhanyavaad", "dhanyawad", "shukriya", "badhiya", "bahut accha", "mast",
    "solve ho gaya", "solve ho gya", "theek ho gaya", "sahi ho gaya", "ho gaya thanks",
    "धन्यवाद", "शुक्रिया", "बढ़िया", "अच्छा", "ठीक हो गया", "हल हो गया",
]
NEGATIVE = [
    "problem", "issue", "not working", "doesn't work", "didn't get", "not received", "failed", "stuck",
    "deducted", "worried", "worry", "waiting", "still not", "again", "disappointed", "confused",
    "unhappy", "delay", "late", "missing", "error", "wrong", "lost", "upset", "not happy",
    "taken from my account", "didn't do", "did not do", "not done by me", "without my permission",
    "hacked", "scared", "help me", "urgent",
    "pareshan", "dikkat", "nahi aaya", "nahi aaye", "nahi mila", "abhi tak", "kat gaye", "kat gya", "fas gaya",
    "fail ho", "maine nahi kiya",
    "परेशान", "दिक्कत", "समस्या", "नहीं आया", "नहीं आए", "नहीं मिला", "कट गए", "अभी तक", "फेल",
]
ANGRY = [
    "angry", "furious", "worst", "useless", "pathetic", "ridiculous", "nonsense", "rubbish",
    "fed up", "sick of", "terrible", "horrible", "hopeless", "disgusting", "shameful", "unacceptable",
    "what the hell", "wtf", "idiot", "stupid", "never using", "never again", "worst app",
    "bakwas", "bekar", "ghatiya", "gussa", "faltu", "bewakoof",
    "बकवास", "बेकार", "घटिया", "गुस्सा", "फालतू",
]
NEGATORS = ["not ", "no ", "never ", "nahi ", "नहीं "]


def _count(text: str, words: list[str]) -> list[str]:
    hits = []
    for w in words:
        if re.search(r"(?<![a-z])" + re.escape(w), text):
            # "not happy", "no problem" flip meaning
            start = text.find(w)
            before = text[max(0, start - 6):start]
            if any(before.endswith(n) for n in NEGATORS):
                continue
            hits.append(w)
    # "thanks" already covers "thank": keep only the longest overlapping words
    return [h for h in hits if not any(h != o and h in o for o in hits)]


def analyze(text: str) -> dict:
    """Return {"label", "score" (-1..1), "signals": [why]}."""
    raw = text or ""
    low = raw.lower()
    pos = _count(low, POSITIVE)
    neg = _count(low, NEGATIVE)
    ang = _count(low, ANGRY)
    fixed = ("no problem", "no issue", "problem solve", "problem solved", "issue resolved", "issue solved",
             "problem fixed", "समस्या हल")
    if any(f in low for f in fixed):
        neg = [w for w in neg if w not in ("problem", "issue")]

    signals = []
    raw_score = 1.0 * len(pos) - 1.0 * len(neg) - 2.0 * len(ang)
    if pos:
        signals.append("positive words: " + ", ".join(pos[:3]))
    if neg:
        signals.append("negative words: " + ", ".join(neg[:3]))
    if ang:
        signals.append("angry words: " + ", ".join(ang[:3]))

    exclaims = raw.count("!")
    caps_words = [w for w in re.findall(r"\b[A-Z]{3,}\b", raw) if w not in {"UPI", "PIN", "OTP", "CVV", "KYC", "PAN", "DTH", "TKT", "SMS", "INR"}]
    shouting = len(caps_words) >= 2 or exclaims >= 3
    if shouting:
        raw_score -= 1.5
        signals.append("shouting (ALL CAPS or !!!)")
    elif exclaims == 2 and (neg or ang):
        raw_score -= 0.5

    score = max(-1.0, min(1.0, raw_score / 3.0))
    if ang and (score <= -0.5 or shouting or len(ang) >= 2):
        label = "Angry"
    elif ang or score <= -0.15:
        label = "Negative"
    elif score >= 0.2:
        label = "Positive"
    else:
        label = "Neutral"
    return {"label": label, "score": round(score, 2), "signals": signals or ["no strong signals"]}


@dataclass
class ConversationSentiment:
    """Tracks sentiment across one chat and spots frustration."""
    history: list = field(default_factory=list)  # list of analyze() results

    def add(self, result: dict) -> dict:
        self.history.append(result)
        return self.status()

    def status(self) -> dict:
        labels = [h["label"] for h in self.history]
        scores = [h["score"] for h in self.history]
        frustrated, why = False, ""
        if labels and labels[-1] == "Angry":
            frustrated, why = True, "customer is angry"
        elif len(labels) >= 2 and all(l in ("Negative", "Angry") for l in labels[-2:]):
            frustrated, why = True, "two negative messages in a row"
        elif len(scores) >= 3 and scores[-1] <= -0.3 and scores[-3] - scores[-1] >= 0.5:
            frustrated, why = True, "mood getting worse during the chat"
        avg = round(sum(scores) / len(scores), 2) if scores else 0.0
        return {"latest": labels[-1] if labels else "Neutral", "average": avg,
                "trend": scores[-5:], "frustrated": frustrated, "why": why}
