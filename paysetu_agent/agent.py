"""The two ADK agents: Setu (support) and the QA reviewer.

`adk web` (run from the project folder) finds `root_agent` here. (adk web shows Setu's
raw replies; the QA review step runs in chat.py, used by the Streamlit app and test scripts.)
"""
import logging
from typing import Literal

from google.adk.agents import Agent
from google.genai import types
from pydantic import BaseModel, Field

from . import rag
from .config import CHAT_MODEL, FALLBACK_MODEL, retry_options
from .prompts import QA_INSTRUCTION, SETU_INSTRUCTION
from .tools import create_ticket, get_transaction_status, search_help_docs, send_receipt_email

# Build the help-docs index at startup if index/ is missing (e.g. a fresh Streamlit Cloud deploy).
try:
    rag.get_collection()
except Exception as exc:  # don't crash startup; search_help_docs will report the problem
    logging.warning("Could not prepare help docs index: %s", exc)


def _config(temperature: float) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(temperature=temperature, http_options=retry_options())


def make_setu(model: str, name: str = "setu") -> Agent:
    return Agent(
        name=name,
        model=model,
        description="PaySetu Wallet customer support agent.",
        instruction=SETU_INSTRUCTION,
        tools=[search_help_docs, create_ticket, get_transaction_status, send_receipt_email],
        generate_content_config=_config(0.2),  # low = consistent, factual replies
    )


root_agent = make_setu(CHAT_MODEL)
# Same Setu on the backup model (used only when the main model's quota is exhausted).
fallback_agent = make_setu(FALLBACK_MODEL) if FALLBACK_MODEL else None


class QAResult(BaseModel):
    result: Literal["PASS", "FAIL"] = Field(description="PASS or FAIL")
    reason: str = Field(description="One short sentence")


def make_qa(model: str) -> Agent:
    return Agent(
        name="qa_reviewer",
        model=model,
        description="Reviews Setu's draft replies before the customer sees them.",
        instruction=QA_INSTRUCTION,
        output_schema=QAResult,
        generate_content_config=_config(0.0),
    )


qa_agent = make_qa(CHAT_MODEL)
qa_fallback_agent = make_qa(FALLBACK_MODEL) if FALLBACK_MODEL else None
