"""Tools Setu can call. Each tool is a plain Python function; ADK reads its docstring."""
import logging

from google.adk.tools import ToolContext

from . import rag


def search_help_docs(question: str, tool_context: ToolContext) -> dict:
    """Search PaySetu's official help docs and return the 3 most relevant sections.

    Use this for every question about PaySetu payments, UPI, wallet, KYC, bills,
    cashback, fees, limits, timelines, disputes or account security.

    Args:
        question: The customer's question, in English, in your own words.

    Returns:
        A dict with "results": a list of {"source", "text"} sections.
    """
    try:
        results = rag.search(question)
    except Exception as exc:
        logging.warning("search_help_docs failed: %s", exc)
        return {"status": "error", "results": [], "message": "Help docs search is unavailable right now."}

    chunks = [{"source": r["source"], "text": r["text"]} for r in results]
    # Remember what was retrieved this turn (used later by the QA reviewer).
    tool_context.state["last_chunks"] = chunks
    return {"status": "ok", "results": chunks}
