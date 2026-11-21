"""Shared settings: model names, file paths and API key loading."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Gemini models (checked against this API key with check_setup.py).
CHAT_MODEL = "gemini-3.5-flash-lite"
EMBEDDING_MODEL = "gemini-embedding-001"


def retry_options():
    """Retry busy/overloaded Gemini calls (429 quota, 500/503 server busy) with backoff."""
    from google.genai import types

    return types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            attempts=5, initial_delay=2.0, max_delay=30.0,
            http_status_codes=[429, 500, 503, 504],
        )
    )


GREETING ="Hello, I'm Setu from PaySetu. How can I help with your payments today?"

# Local laptop: read GOOGLE_API_KEY from .env.
# (On Streamlit Cloud, app.py copies it from st.secrets into the environment.)
load_dotenv(PROJECT_ROOT / ".env")


def require_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "GOOGLE_API_KEY is missing. Add it to .env (laptop) or Streamlit secrets (cloud)."
        )
    return key
