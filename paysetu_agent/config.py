"""Shared settings: model names, file paths and API key loading."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Local laptop: read GOOGLE_API_KEY from .env.
# (On Streamlit Cloud, app.py copies it from st.secrets into the environment.)
load_dotenv(PROJECT_ROOT / ".env")

# Gemini models (checked against this API key with check_setup.py).
CHAT_MODEL = os.getenv("PAYSETU_MODEL", "gemini-3.5-flash-lite")
# Used automatically when the main model's quota is used up (HTTP 429), so Setu keeps working.
FALLBACK_MODEL = os.getenv("PAYSETU_FALLBACK_MODEL", "gemini-3.1-flash-lite")
EMBEDDING_MODEL = "gemini-embedding-001"

# Where tickets and logs are written. Test scripts can point this elsewhere
# (PAYSETU_LOG_DIR) so test runs don't fill the real sidebar.
LOG_DIR = Path(os.getenv("PAYSETU_LOG_DIR", PROJECT_ROOT))
TICKETS_FILE = LOG_DIR / "tickets.csv"
CHAT_LOG_FILE = LOG_DIR / "chat_log.csv"
QA_LOG_FILE = LOG_DIR / "qa_log.csv"
FRAUD_ALERTS_FILE = LOG_DIR / "fraud_alerts.csv"
TRANSACTIONS_FILE = DATA_DIR / "transactions.csv"

# QA reviewer on/off (on by default).
QA_ENABLED = os.getenv("PAYSETU_QA", "on").lower() != "off"

GREETING = "Hello, I'm Setu from PaySetu. How can I help with your payments today?"


def retry_options():
    """Retry busy/overloaded Gemini calls (429 quota, 500/503 server busy) with backoff."""
    from google.genai import types

    return types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            attempts=3, initial_delay=2.0, max_delay=20.0,
            http_status_codes=[429, 500, 503, 504],
        )
    )


def require_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "GOOGLE_API_KEY is missing. Add it to .env (laptop) or Streamlit secrets (cloud)."
        )
    return key


def is_quota_error(exc: BaseException | None) -> bool:
    """True if this error (or any error it wraps) is a Gemini quota error (HTTP 429)."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        text = str(exc)
        if "429" in text or "RESOURCE_EXHAUSTED" in text or "exceeded your current quota" in text:
            return True
        exc = exc.__cause__ or exc.__context__
    return False


# Circuit breaker: after a quota error, skip the main model for a while (no wasted retries).
MAIN_MODEL_PAUSE_SECONDS = 600
_main_paused_until = 0.0


def main_model_paused() -> bool:
    import time
    return bool(FALLBACK_MODEL) and time.time() < _main_paused_until


def pause_main_model() -> None:
    import time
    global _main_paused_until
    _main_paused_until = time.time() + MAIN_MODEL_PAUSE_SECONDS


def with_model_fallback(call):
    """Run call(model); if the main model's quota is exhausted, retry once with FALLBACK_MODEL.
    Returns (result, model_used)."""
    if main_model_paused():
        return call(FALLBACK_MODEL), FALLBACK_MODEL
    try:
        return call(CHAT_MODEL), CHAT_MODEL
    except Exception as exc:
        if FALLBACK_MODEL and FALLBACK_MODEL != CHAT_MODEL and is_quota_error(exc):
            pause_main_model()
            return call(FALLBACK_MODEL), FALLBACK_MODEL
        raise
