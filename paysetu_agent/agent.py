"""Setu: the PaySetu Wallet support agent (Google ADK).

`adk web` (run from the project folder) finds `root_agent` here.
"""
from google.adk.agents import Agent
from google.genai import types

from .config import CHAT_MODEL, retry_options
from .prompts import SETU_INSTRUCTION

root_agent = Agent(
    name="setu",
    model=CHAT_MODEL,
    description="PaySetu Wallet customer support agent.",
    instruction=SETU_INSTRUCTION,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,  # low = more consistent, factual replies
        http_options=retry_options(),
    ),
)
