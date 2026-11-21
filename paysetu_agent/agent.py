"""Setu: the PaySetu Wallet support agent (Google ADK).

`adk web` (run from the project folder) finds `root_agent` here.
"""
from google.adk.agents import Agent
from google.genai import types

from .config import CHAT_MODEL, retry_options
from .prompts import SETU_INSTRUCTION
from .tools import search_help_docs

import logging

from . import rag

# Build the help-docs index at startup if index/ is missing (e.g. a fresh Streamlit Cloud deploy).
try:
    rag.get_collection()
except Exception as exc:  # don't crash startup; search_help_docs will report the problem
    logging.warning("Could not prepare help docs index: %s", exc)

root_agent = Agent(
    name="setu",
    model=CHAT_MODEL,
    description="PaySetu Wallet customer support agent.",
    instruction=SETU_INSTRUCTION,
    tools=[search_help_docs],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,  # low = more consistent, factual replies
        http_options=retry_options(),
    ),
)
