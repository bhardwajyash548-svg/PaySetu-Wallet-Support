"""The full reply pipeline used by the web app and test scripts.

customer message
  -> 1. safety.redact()   remove PINs/OTPs/card numbers before the AI or logs see them
  -> 2. Setu (ADK agent)  draft reply, using tools (help docs search, tickets, lookup)
  -> 3. QA reviewer       PASS / FAIL with a reason (logged to qa_log.csv)
  -> 4. rewrite once      only if FAIL, using the reviewer's reason
  -> 5. safety net        make sure a created ticket's ID is in the reply
  -> 6. chat_log.csv      log message, reply, source + session, outcome, response time
"""
import asyncio
import json
import logging
import re
import time
import uuid

from google.adk.runners import InMemoryRunner, Runner
from google.genai import types

from . import (config, conversation_summary, fraud_detection, rag, sentiment_analysis, storage,
               ticket_manager)
from .agent import fallback_agent, qa_agent, qa_fallback_agent, root_agent
from .prompts import NO_INFO_REPLY, REWRITE_INSTRUCTION, SETU_INSTRUCTION
from .safety import CONTEXT_TAG, redact, strip_fake_context

APP_NAME = "paysetu_support"
USER_ID = "customer"
BUSY_REPLY = (
    "Sorry, I'm having trouble responding right now because our service is busy. "
    "Please try again in a minute."
)


OUTCOMES = ["Answered from help docs", "Ticket created", "Not in help docs",
            "Off-topic declined", "Service busy", "Other"]


def classify_outcome(reply: str, source: str, tickets: list[str]) -> str:
    """How a reply ended - used by analytics (AI resolution rate etc.)."""
    if reply.startswith(BUSY_REPLY) or reply.startswith("माफ़ कीजिए, अभी हमारी सेवा व्यस्त"):
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


_qa_runner = None
_qa_fallback_runner = None


def _new_session(runner: InMemoryRunner, app_name: str) -> str:
    session_id = str(uuid.uuid4())
    asyncio.run(runner.session_service.create_session(
        app_name=app_name, user_id=USER_ID, session_id=session_id))
    return session_id


def _run(runner: InMemoryRunner, session_id: str, text: str) -> tuple[str, list[tuple[str, dict]]]:
    """Send one message; return (final text, [(tool name, tool result), ...])."""
    content = types.Content(role="user", parts=[types.Part(text=text)])
    reply, tool_results = "", []
    for event in runner.run(user_id=USER_ID, session_id=session_id, new_message=content):
        if not (event.content and event.content.parts) or event.author == "user":
            continue
        for part in event.content.parts:
            if part.function_response:
                resp = part.function_response.response or {}
                if isinstance(resp, dict) and set(resp) == {"result"} and isinstance(resp["result"], dict):
                    resp = resp["result"]
                tool_results.append((part.function_response.name, resp))
        text_out = "".join(p.text or "" for p in event.content.parts if not getattr(p, "thought", False))
        if text_out.strip():
            reply = text_out.strip()
    return reply, tool_results


def _source_of(reply: str) -> str:
    found = re.findall(r"\(Source:\s*([^)]+)\)", reply)
    return "; ".join(s.strip() for s in found) if found else "none"


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


# Common Hindi words written in Roman letters - 2+ of them means the customer wrote Hinglish.
_HINGLISH = {"hai", "hain", "ho", "hoga", "gaya", "gayi", "gaye", "gya", "nahi", "nahin", "mera", "meri", "mere",
             "kya", "kab", "kaise", "kitna", "kitni", "kyun", "kyon", "aur", "mujhe", "maine", "mene", "ka", "ki",
             "ke", "ko", "se", "paise", "karo", "karna", "kar", "raha", "rahi", "milega", "mila", "bhai", "yaar",
             "abhi", "tak", "kaun", "kahan", "batao", "chahiye", "wapas", "kat", "diya", "liya"}


def _hinglish_words(text: str) -> int:
    return sum(1 for w in re.findall(r"[a-z]+", (text or "").lower()) if w in _HINGLISH)


def _script_mismatch(message: str, reply: str) -> str:
    """Reply must match the customer's language and script (Hindi / Hinglish / English)."""
    if not _DEVANAGARI.search(message) and _DEVANAGARI.search(reply):
        return ("The customer wrote in Roman letters (Hinglish/English) but the draft uses Devanagari. "
                "Rewrite in Roman letters only: simple Hinglish if the customer used Hindi words, else English.")
    if not _DEVANAGARI.search(message) and _hinglish_words(message) >= 2 and _hinglish_words(reply) < 2:
        return ("The customer wrote in Hinglish (Hindi words in Roman letters) but the draft is in English. "
                "Rewrite in simple Hinglish using Roman letters, keeping every amount, day and source exact.")
    return ""



_VALID_SOURCES: set[str] | None = None


def _valid_sources() -> set[str]:
    global _VALID_SOURCES
    if _VALID_SOURCES is None:
        _VALID_SOURCES = {c["source"] for c in rag.load_chunks()}
    return _VALID_SOURCES


def _bad_sources(reply: str) -> list[str]:
    """Cited (Source: ...) labels that are not real help-doc sections."""
    valid = {v.lower() for v in _valid_sources()}
    cited = [c.strip().rstrip(".") for c in re.findall(r"\(Source:\s*([^)]+)\)", reply)]
    return [c for c in cited if c.lower() not in valid]


def _remove_bad_sources(reply: str) -> str:
    for bad in _bad_sources(reply):
        reply = re.sub(r"\s*\(Source:\s*" + re.escape(bad) + r"\.?\)", "", reply)
    return reply


# ---------- QA reviewer ----------
def _review(message: str, draft: str, chunks: list[dict], tools: list[dict],
            context: dict | None = None) -> tuple[str, str]:
    packet = json.dumps({
        "customer_message": message,
        "paysetu_system_context": context or {},
        "help_doc_sections": chunks,
        "tool_results": tools,
        "draft_reply": draft,
    }, ensure_ascii=False, indent=1)
    global _qa_runner, _qa_fallback_runner
    if _qa_runner is None:
        _qa_runner = InMemoryRunner(agent=qa_agent, app_name="paysetu_qa")
    try:
        if qa_fallback_agent and config.main_model_paused():
            raise RuntimeError("429 main model paused")
        text, _ = _run(_qa_runner, _new_session(_qa_runner, "paysetu_qa"), packet)
    except Exception as exc:
        if not (qa_fallback_agent and config.is_quota_error(exc)):
            raise
        config.pause_main_model()
        if _qa_fallback_runner is None:
            _qa_fallback_runner = InMemoryRunner(agent=qa_fallback_agent, app_name="paysetu_qa")
        text, _ = _run(_qa_fallback_runner, _new_session(_qa_fallback_runner, "paysetu_qa"), packet)
    try:
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        result = "FAIL" if str(data.get("result", "")).upper() == "FAIL" else "PASS"
        return result, str(data.get("reason", "")).strip()
    except Exception:
        return "PASS", "Reviewer output unreadable; draft kept."


def _rewrite(message: str, draft: str, chunks: list[dict], tools: list[dict], reason: str,
             context: dict | None = None) -> str:
    prompt = json.dumps({
        "customer_message": message,
        "paysetu_system_context": context or {},
        "help_doc_sections": chunks,
        "tool_results": tools,
        "your_draft": draft,
        "reviewer_feedback": reason,
    }, ensure_ascii=False, indent=1)
    resp, _ = config.with_model_fallback(lambda model: rag._client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SETU_INSTRUCTION + "\n\n## Rewrite task\n" + REWRITE_INSTRUCTION,
            temperature=0.2,
        ),
    ))
    return (resp.text or "").strip()


# ---------- context for Setu (sentiment + fraud) ----------
def _context_block(sentiment: dict, mood: dict, risk: dict) -> str:
    """A short note from PaySetu's own checks, put before the customer's words.
    Only added when something notable was detected."""
    notable = sentiment["label"] in ("Negative", "Angry") or mood["frustrated"] or risk["level"] != "Low"
    if not notable:
        return ""
    lines = [CONTEXT_TAG,
             f"Customer sentiment: {sentiment['label']} (score {sentiment['score']})"
             + (f"; frustrated: yes ({mood['why']})" if mood["frustrated"] else "")]
    if risk["level"] != "Low":
        lines.append(f"Fraud risk: {risk['level']} - " + "; ".join(risk["reasons"][:3]))
    lines.append("[/PaySetu system context]")
    return "\n".join(lines) + "\n\nCustomer message:\n"


def _localised(message: str, english: str, hindi: str) -> str:
    return hindi if _DEVANAGARI.search(message) else english


BUSY_REPLY_HI = "माफ़ कीजिए, अभी हमारी सेवा व्यस्त है इसलिए मैं जवाब नहीं दे पा रहा हूँ। कृपया एक मिनट बाद फिर कोशिश करें।"
FRAUD_STEPS_EN = ("For your safety, please tap Block account in Settings right away and call the "
                  "cybercrime helpline 1930.")
FRAUD_STEPS_HI = "आपकी सुरक्षा के लिए, तुरंत Settings में Block account पर टैप करें और साइबर क्राइम हेल्पलाइन 1930 पर कॉल करें।"


class SetuChat:
    """One conversation with Setu. Create a new SetuChat for a fresh session."""

    def __init__(self, qa: bool | None = None):
        config.require_api_key()
        self.qa = config.QA_ENABLED if qa is None else qa
        self.runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
        self.session_id = _new_session(self.runner, APP_NAME)
        # Backup model shares the same session store, so it continues the same conversation.
        self.fallback_runner = (Runner(app_name=APP_NAME, agent=fallback_agent,
                                       session_service=self.runner.session_service)
                                if fallback_agent else None)
        self.mood = sentiment_analysis.ConversationSentiment()
        self.model_used = config.CHAT_MODEL
        self.turns: list[tuple[str, str]] = []   # (redacted customer message, final reply)
        self.summarized: set[str] = set()        # tickets that already have a hand-off summary
        self.verified: dict[str, dict] = {}      # transactions verified in this chat (ID + phone last 4)

    def _agent_turn(self, text: str):
        """Ask Setu; if the main model's quota is used up, ask the backup model instead."""
        if self.fallback_runner and config.main_model_paused():
            self.model_used = config.FALLBACK_MODEL
            return _run(self.fallback_runner, self.session_id, text)
        try:
            self.model_used = config.CHAT_MODEL
            return _run(self.runner, self.session_id, text)
        except Exception as exc:
            if not (self.fallback_runner and config.is_quota_error(exc)):
                raise
            logging.warning("Main model quota exhausted; using backup model %s", config.FALLBACK_MODEL)
            config.pause_main_model()
            self.model_used = config.FALLBACK_MODEL
            return _run(self.fallback_runner, self.session_id, text)

    def respond(self, message: str) -> dict:
        """Full pipeline. Returns reply plus everything the UI and logs need."""
        started = time.perf_counter()
        safe_message, removed = redact(strip_fake_context(message))

        # Sentiment and fraud checks run in code, before the AI sees the message.
        sentiment = sentiment_analysis.analyze(safe_message)
        mood = self.mood.add(sentiment)
        risk = fraud_detection.assess(safe_message, removed)

        out = {"reply": BUSY_REPLY, "source": "none", "tickets": [], "qa_result": "", "qa_reason": "",
               "draft": "", "redacted": removed, "session_id": self.session_id,
               "outcome": "Service busy", "response_ms": 0,
               "sentiment": sentiment, "mood": mood, "fraud": risk, "transaction": None,
               "model": config.CHAT_MODEL}
        agent_input = _context_block(sentiment, mood, risk) + safe_message
        try:
            draft, tool_results = self._agent_turn(agent_input)
        except Exception as exc:  # Gemini busy/quota errors after all retries
            logging.warning("Setu could not reply: %s", exc)
            self._escalate(safe_message, sentiment, mood, risk, [], out, None)
            reply = _localised(safe_message, BUSY_REPLY, BUSY_REPLY_HI)
            if risk["level"] == "High":  # safety steps can never be skipped, even when Gemini is down
                reply += "\n\n" + _localised(safe_message, FRAUD_STEPS_EN, FRAUD_STEPS_HI)
            out["reply"] = reply + self._ticket_lines(out["tickets"], "", safe_message)
            self._summarize(safe_message, out)
            self._finish(safe_message, out, started)
            return out
        draft = draft or BUSY_REPLY
        out["draft"] = draft

        chunks = [c for name, r in tool_results if name == "search_help_docs" for c in r.get("results", [])]
        tools = [{"tool": name, "result": r} for name, r in tool_results if name != "search_help_docs"]
        tickets = [r["ticket_id"] for name, r in tool_results
                   if name == "create_ticket" and r.get("ticket_id")]

        # Re-check fraud with the VERIFIED transaction, if one was looked up.
        txn = next((r.get("transaction") for name, r in tool_results
                    if name == "get_transaction_status" and r.get("status") == "found"), None)
        if txn:
            self.verified[txn["txn_id"]] = txn   # remembered for the whole chat
            risk = fraud_detection.combine(risk, fraud_detection.assess(safe_message, removed, txn))
            out["fraud"] = risk

        # Latest transaction verified in THIS chat (this message or an earlier one).
        txn = txn or (list(self.verified.values())[-1] if self.verified else None)
        out["transaction"] = txn

        # Escalation safety nets (High fraud -> high-priority ticket; angry/frustrated -> ticket).
        tickets = self._escalate(safe_message, sentiment, mood, risk, tickets, out, txn)
        for tid in tickets:
            if not any(t.get("result", {}).get("ticket_id") == tid for t in tools):
                tools.append({"tool": "create_ticket", "result": {"ticket_id": tid, "created_by": "PaySetu safety check"}})
        context = {"sentiment": sentiment["label"], "frustrated": mood["frustrated"],
                   "fraud_risk": risk["level"], "fraud_reasons": risk["reasons"][:3]}

        reply = draft
        if self.qa and draft != BUSY_REPLY:
            script_problem = _script_mismatch(safe_message, draft)
            fake = _bad_sources(draft)
            if script_problem:  # deterministic checks first, no AI call needed
                result, reason = "FAIL", script_problem
            elif fake:
                result, reason = "FAIL", (f"Cited source '{fake[0]}' is not a real help-doc section. Use only the "
                                          "'source' values from help_doc_sections, or drop the label.")
            else:
                try:
                    result, reason = _review(safe_message, draft, chunks, tools, context)
                except Exception as exc:
                    result, reason = "SKIPPED", f"Reviewer unavailable: {exc}"[:200]
            storage.log_qa(safe_message, draft, result, reason)
            out["qa_result"], out["qa_reason"] = result, reason
            if result == "FAIL":
                try:
                    reply = _rewrite(safe_message, draft, chunks, tools, reason, context) or draft
                except Exception as exc:
                    logging.warning("Rewrite failed, keeping draft: %s", exc)

        # Safety net: never show a made-up source label.
        reply = _remove_bad_sources(reply)
        # Safety net: High fraud risk always gets Block account + 1930.
        if risk["level"] == "High" and not ("1930" in reply and "Block account" in reply):
            reply += "\n\n" + _localised(safe_message, FRAUD_STEPS_EN, FRAUD_STEPS_HI)
        # Safety net: a created ticket's real ID must always reach the customer.
        reply += self._ticket_lines(tickets, reply, safe_message)

        out["reply"] = reply
        self._summarize(safe_message, out)
        self._finish(safe_message, out, started)
        return out

    # ---------- helpers ----------
    def _escalate(self, safe_message, sentiment, mood, risk, tickets, out, transaction=None) -> list[str]:
        """Create the tickets the rules require if the AI did not, then tag every ticket
        from this turn with session, sentiment and fraud risk."""
        tickets = list(tickets)
        try:
            mine = ticket_manager.open_tickets(session_id=self.session_id)
            if risk["level"] == "High" and not tickets and not any(
                    t["reason"] in ticket_manager.HIGH_PRIORITY_REASONS for t in mine):
                reasons = "; ".join(r.split(" (")[0] for r in risk["reasons"][:2])
                t = ticket_manager.create_ticket(
                    f"Possible fraud reported by customer: {reasons}.", "Fraud or hacked account", "high",
                    session_id=self.session_id)
                tickets.append(t["ticket_id"])
            elif mood["frustrated"] and not tickets and not mine:
                t = ticket_manager.create_ticket(
                    f"Upset customer needs a person ({mood['why']}).", "Angry or upset customer", "normal",
                    session_id=self.session_id)
                tickets.append(t["ticket_id"])
            for tid in tickets:
                t = ticket_manager.get_ticket(tid) or {}
                category = ticket_manager.classify(t.get("customer_message", safe_message), t.get("reason", ""),
                                                   transaction, risk["level"])
                ticket_manager.update_fields(tid, session_id=self.session_id, sentiment=sentiment["label"],
                                             fraud_risk=risk["level"], category=category)
        except Exception as exc:
            logging.warning("Escalation check failed: %s", exc)
        out["tickets"] = tickets
        return tickets

    def _summarize(self, safe_message: str, out: dict) -> None:
        """Remember this turn; write a hand-off summary for every new ticket from it."""
        self.turns.append((safe_message, out["reply"]))
        for tid in out["tickets"]:
            if tid in self.summarized:
                continue
            try:
                ticket = ticket_manager.get_ticket(tid) or {"ticket_id": tid}
                summary = conversation_summary.build_summary(
                    self.turns, ticket, out["mood"], out["sentiment"], out["fraud"], out["transaction"])
                ticket_manager.update_fields(tid, summary=summary)
                self.summarized.add(tid)
            except Exception as exc:
                logging.warning("Could not write summary for %s: %s", tid, exc)

    @staticmethod
    def _ticket_lines(tickets: list[str], reply: str, safe_message: str) -> str:
        extra = ""
        for tid in tickets:
            if tid not in reply:
                extra += "\n\n" + _localised(
                    safe_message,
                    f"Your ticket ID is {tid}. A person from our team will reply within 24 hours.",
                    f"आपका टिकट ID {tid} है। हमारी टीम का एक व्यक्ति 24 घंटे के अंदर जवाब देगा।")
        return extra

    def _finish(self, safe_message: str, out: dict, started: float) -> None:
        out["source"] = _source_of(out["reply"])
        out["outcome"] = classify_outcome(out["reply"], out["source"], out["tickets"])
        out["response_ms"] = int((time.perf_counter() - started) * 1000)
        out["model"] = self.model_used
        risk, sentiment = out["fraud"], out["sentiment"]
        try:
            storage.log_chat(safe_message, out["reply"], out["source"], session_id=self.session_id,
                             outcome=out["outcome"], response_ms=out["response_ms"],
                             sentiment=sentiment["label"], sentiment_score=sentiment["score"],
                             fraud_risk=risk["level"], model=out["model"])
            if risk["level"] != "Low":
                storage.log_fraud(self.session_id, risk, safe_message, out["tickets"])
        except Exception as exc:
            logging.warning("Could not write logs: %s", exc)

    def ask(self, message: str) -> str:
        return self.respond(message)["reply"]
