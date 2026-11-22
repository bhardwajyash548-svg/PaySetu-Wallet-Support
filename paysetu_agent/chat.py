"""The full reply pipeline used by the web app and test scripts.

customer message
  -> 1. safety.redact()   remove PINs/OTPs/card numbers before the AI or logs see them
  -> 2. Setu (ADK agent)  draft reply, using tools (help docs search, tickets, lookup)
  -> 3. QA reviewer       PASS / FAIL with a reason (logged to qa_log.csv)
  -> 4. rewrite once      only if FAIL, using the reviewer's reason
  -> 5. safety net        make sure a created ticket's ID is in the reply
  -> 6. chat_log.csv      log message, reply and source
"""
import asyncio
import json
import logging
import re
import uuid

from google.adk.runners import InMemoryRunner
from google.genai import types

from . import config, rag, storage
from .agent import qa_agent, root_agent
from .prompts import REWRITE_INSTRUCTION, SETU_INSTRUCTION
from .safety import redact

APP_NAME = "paysetu_support"
USER_ID = "customer"
BUSY_REPLY = (
    "Sorry, I'm having trouble responding right now because our service is busy. "
    "Please try again in a minute."
)

_qa_runner = None


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


def _script_mismatch(message: str, reply: str) -> str:
    """Hinglish/English in Roman letters must never get a Devanagari reply."""
    if not _DEVANAGARI.search(message) and _DEVANAGARI.search(reply):
        return ("The customer wrote in Roman letters (Hinglish/English) but the draft uses Devanagari. "
                "Rewrite in Roman letters only: simple Hinglish if the customer used Hindi words, else English.")
    return ""


# ---------- QA reviewer ----------
def _review(message: str, draft: str, chunks: list[dict], tools: list[dict]) -> tuple[str, str]:
    global _qa_runner
    if _qa_runner is None:
        _qa_runner = InMemoryRunner(agent=qa_agent, app_name="paysetu_qa")
    session_id = _new_session(_qa_runner, "paysetu_qa")
    packet = json.dumps({
        "customer_message": message,
        "help_doc_sections": chunks,
        "tool_results": tools,
        "draft_reply": draft,
    }, ensure_ascii=False, indent=1)
    text, _ = _run(_qa_runner, session_id, packet)
    try:
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        result = "FAIL" if str(data.get("result", "")).upper() == "FAIL" else "PASS"
        return result, str(data.get("reason", "")).strip()
    except Exception:
        return "PASS", "Reviewer output unreadable; draft kept."


def _rewrite(message: str, draft: str, chunks: list[dict], tools: list[dict], reason: str) -> str:
    prompt = json.dumps({
        "customer_message": message,
        "help_doc_sections": chunks,
        "tool_results": tools,
        "your_draft": draft,
        "reviewer_feedback": reason,
    }, ensure_ascii=False, indent=1)
    resp = rag._client().models.generate_content(
        model=config.CHAT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SETU_INSTRUCTION + "\n\n## Rewrite task\n" + REWRITE_INSTRUCTION,
            temperature=0.2,
        ),
    )
    return (resp.text or "").strip()


class SetuChat:
    """One conversation with Setu. Create a new SetuChat for a fresh session."""

    def __init__(self, qa: bool | None = None):
        config.require_api_key()
        self.qa = config.QA_ENABLED if qa is None else qa
        self.runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
        self.session_id = _new_session(self.runner, APP_NAME)

    def respond(self, message: str) -> dict:
        """Full pipeline. Returns {reply, source, tickets, qa_result, qa_reason, draft}."""
        safe_message, removed = redact(message)
        out = {"reply": BUSY_REPLY, "source": "none", "tickets": [], "qa_result": "", "qa_reason": "",
               "draft": "", "redacted": removed}
        try:
            draft, tool_results = _run(self.runner, self.session_id, safe_message)
        except Exception as exc:  # Gemini busy/quota errors after all retries
            logging.warning("Setu could not reply: %s", exc)
            return out
        draft = draft or BUSY_REPLY
        out["draft"] = draft

        chunks = [c for name, r in tool_results if name == "search_help_docs" for c in r.get("results", [])]
        tools = [{"tool": name, "result": r} for name, r in tool_results if name != "search_help_docs"]
        tickets = [r["ticket_id"] for name, r in tool_results
                   if name == "create_ticket" and r.get("ticket_id")]
        out["tickets"] = tickets

        reply = draft
        if self.qa and draft != BUSY_REPLY:
            script_problem = _script_mismatch(safe_message, draft)
            if script_problem:  # deterministic check, no AI call needed
                result, reason = "FAIL", script_problem
            else:
                try:
                    result, reason = _review(safe_message, draft, chunks, tools)
                except Exception as exc:
                    result, reason = "SKIPPED", f"Reviewer unavailable: {exc}"[:200]
            storage.log_qa(safe_message, draft, result, reason)
            out["qa_result"], out["qa_reason"] = result, reason
            if result == "FAIL":
                try:
                    reply = _rewrite(safe_message, draft, chunks, tools, reason) or draft
                except Exception as exc:
                    logging.warning("Rewrite failed, keeping draft: %s", exc)

        # Safety net: a created ticket's real ID must always reach the customer.
        for tid in tickets:
            if tid not in reply:
                reply += f"\n\nYour ticket ID is {tid}. A person from our team will reply within 24 hours."

        out["reply"] = reply
        out["source"] = _source_of(reply)
        try:
            storage.log_chat(safe_message, reply, out["source"])
        except Exception as exc:
            logging.warning("Could not write chat log: %s", exc)
        return out

    def ask(self, message: str) -> str:
        return self.respond(message)["reply"]
