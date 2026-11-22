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
    return tmp_path


@pytest.fixture
def tool_ctx():
    """A stand-in for ADK's ToolContext: per-chat state and a session id."""
    return SimpleNamespace(state={}, session=SimpleNamespace(id="session-test-1"))
