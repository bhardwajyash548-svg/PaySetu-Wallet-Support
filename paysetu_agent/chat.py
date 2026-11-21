"""A simple way to talk to Setu from Python (used by scripts, tests and the web app)."""
import logging
import uuid

from google.adk.runners import InMemoryRunner
from google.genai import types

from .agent import root_agent
from .config import require_api_key

APP_NAME = "paysetu_support"
USER_ID = "customer"
BUSY_REPLY = (
    "Sorry, I'm having trouble responding right now because our service is busy. "
    "Please try again in a minute."
)


class SetuChat:
    """One conversation with Setu. Create a new SetuChat for a fresh session."""

    def __init__(self):
        require_api_key()
        self.runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
        self.session_id = str(uuid.uuid4())
        self.runner.session_service.create_session_sync(
            app_name=APP_NAME, user_id=USER_ID, session_id=self.session_id
        )

    def ask(self, message: str) -> str:
        content = types.Content(role="user", parts=[types.Part(text=message)])
        reply = ""
        try:
            for event in self.runner.run(
                user_id=USER_ID, session_id=self.session_id, new_message=content
            ):
                if event.content and event.content.parts and event.author != "user":
                    text = "".join(p.text or "" for p in event.content.parts)
                    if text.strip():
                        reply = text.strip()  # keep the final text reply
        except Exception as exc:  # Gemini busy/quota errors after all retries
            logging.warning("Setu could not reply: %s", exc)
            return BUSY_REPLY
        return reply or BUSY_REPLY
