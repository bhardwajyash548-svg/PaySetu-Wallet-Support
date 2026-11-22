"""How a Setu reply ended. Shared by the chat pipeline (when logging) and analytics
(to label old log rows that were written before outcomes were recorded)."""
import re

from .prompts import NO_INFO_REPLY

BUSY_REPLY = (
    "Sorry, I'm having trouble responding right now because our service is busy. "
    "Please try again in a minute."
)
BUSY_REPLY_HI = "माफ़ कीजिए, अभी हमारी सेवा व्यस्त है इसलिए मैं जवाब नहीं दे पा रहा हूँ। कृपया एक मिनट बाद फिर कोशिश करें।"

OUTCOMES = ["Answered from help docs", "Ticket created", "Not in help docs",
            "Off-topic declined", "Service busy", "Other"]


def classify_outcome(reply: str, source: str, tickets: list[str]) -> str:
    reply = reply or ""
    if reply.startswith(BUSY_REPLY) or reply.startswith(BUSY_REPLY_HI[:30]):
        return "Ticket created" if tickets else "Service busy"
    if tickets:
        return "Ticket created"
    if source and source != "none":
        return "Answered from help docs"
    if NO_INFO_REPLY.split(".")[0] in reply:
        return "Not in help docs"
    if "only help with PaySetu" in reply:
        return "Off-topic declined"
    return "Other"


def outcome_from_log(reply: str, source: str) -> str:
    """For old log rows: tickets are recognised from a TKT-#### ID in the reply."""
    return classify_outcome(reply, source, re.findall(r"TKT-\d+", reply or ""))
