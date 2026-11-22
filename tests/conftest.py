"""Shared test setup. These tests need NO API key and never touch the real CSV files."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paysetu_agent import config  # noqa: E402


@pytest.fixture
def tmp_logs(tmp_path, monkeypatch):
    """Point tickets / chat log / QA log at a temporary folder for one test."""
    monkeypatch.setattr(config, "TICKETS_FILE", tmp_path / "tickets.csv")
    monkeypatch.setattr(config, "CHAT_LOG_FILE", tmp_path / "chat_log.csv")
    monkeypatch.setattr(config, "QA_LOG_FILE", tmp_path / "qa_log.csv")
    monkeypatch.setattr(config, "FRAUD_ALERTS_FILE", tmp_path / "fraud_alerts.csv")
    return tmp_path


@pytest.fixture
def fake_setu(tmp_logs, monkeypatch):
    """A SetuChat whose Gemini call is replaced by a scripted reply (no API, no quota).

    Usage: chat, calls = fake_setu(draft, tool_results)
    `calls` records exactly what text was sent to the agent.
    """
    from paysetu_agent import chat as chat_mod

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")

    def make(draft="", tool_results=None, fail=False, quota_on_main=False):
        calls = []
        holder = {}

        def fake_run(runner, session_id, text):
            calls.append(text)
            if fail:
                raise RuntimeError("503 UNAVAILABLE (simulated)")
            if quota_on_main and runner is holder["chat"].runner:
                try:
                    raise RuntimeError("429 RESOURCE_EXHAUSTED: You exceeded your current quota")
                except RuntimeError as inner:  # wrapped like ADK does
                    raise RuntimeError("Dynamic node setu failed") from inner
            return draft, list(tool_results or [])

        monkeypatch.setattr(chat_mod, "_run", fake_run)
        holder["chat"] = chat_mod.SetuChat(qa=False)
        return holder["chat"], calls

    return make


@pytest.fixture
def tool_ctx():
    """A stand-in for ADK's ToolContext: per-chat state and a session id."""
    return SimpleNamespace(state={}, session=SimpleNamespace(id="session-test-1"))


@pytest.fixture(autouse=True)
def reset_model_breaker(monkeypatch):
    """Every test starts with the main model available."""
    monkeypatch.setattr(config, "_main_paused_until", 0.0)
