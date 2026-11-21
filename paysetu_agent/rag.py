"""RAG for Setu: split the help docs into chunks, embed them with Gemini, store and search them in ChromaDB.

- One chunk per FAQ (starts with "Q:") and one per policy section (starts with "Policy:").
- Embeddings: a list of numbers capturing each chunk's meaning, from the Gemini embedding model.
- Search: embed the customer's question the same way and return the 3 closest chunks.
"""
import hashlib
import logging
import re
import sqlite3

# Chroma needs SQLite >= 3.35. Some hosts ship an older one; use pysqlite3 there if installed.
if sqlite3.sqlite_version_info < (3, 35, 0):
    try:
        import sys

        __import__("pysqlite3")
        sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
    except ImportError:
        pass

import chromadb
from chromadb.config import Settings
from google import genai
from google.genai import types

from .config import DATA_DIR, EMBEDDING_MODEL, PROJECT_ROOT, require_api_key, retry_options

HELP_FILE = DATA_DIR / "paysetu_help.txt"
INDEX_DIR = PROJECT_ROOT / "index"
COLLECTION = "paysetu_help"
TOP_K = 3

_collection = None  # cached after first load


# ---------- 1. Chunking ----------
def load_chunks() -> list[dict]:
    """Return one dict per FAQ / policy: {id, kind, title, source, text}."""
    if not HELP_FILE.exists():
        raise FileNotFoundError(f"Help docs not found at {HELP_FILE}")
    lines = HELP_FILE.read_text(encoding="utf-8").splitlines()

    chunks, current = [], None
    for line in lines:
        line = line.rstrip()
        start = re.match(r"^(Q|Policy):\s*(.+)$", line)
        if start:
            if current:
                chunks.append(current)
            kind = "faq" if start.group(1) == "Q" else "policy"
            current = {"kind": kind, "title": start.group(2).strip(), "lines": [line]}
        elif current and line and line not in ("Policies", "Frequently asked questions"):
            current["lines"].append(line)
    if current:
        chunks.append(current)

    result = []
    for i, c in enumerate(chunks, start=1):
        source = c["title"] if c["kind"] == "policy" else f"FAQ: {c['title']}"
        result.append({
            "id": f"{c['kind']}-{i:02d}",
            "kind": c["kind"],
            "title": c["title"],
            "source": source,
            "text": "\n".join(c["lines"]),
        })
    return result


def _file_hash() -> str:
    return hashlib.sha256(HELP_FILE.read_bytes()).hexdigest()[:16]


# ---------- 2. Embeddings ----------
_genai_client = None


def _client() -> genai.Client:
    # Keep one client alive; a throwaway client gets closed mid-request.
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=require_api_key(), http_options=retry_options())
    return _genai_client


def embed(texts: list[str], task_type: str) -> list[list[float]]:
    resp = _client().models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return [e.values for e in resp.embeddings]


# ---------- 3. Index (ChromaDB on disk in index/) ----------
_chroma_client = None


def _chroma() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        INDEX_DIR.mkdir(exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(INDEX_DIR), settings=Settings(anonymized_telemetry=False)
        )
    return _chroma_client


def build_index() -> int:
    """Delete and rebuild the index from data/paysetu_help.txt. Returns the number of chunks."""
    global _collection
    chunks = load_chunks()
    vectors = embed([c["text"] for c in chunks], task_type="RETRIEVAL_DOCUMENT")

    client = _chroma()
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass  # nothing to delete yet
    col = client.create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine", "help_hash": _file_hash()}
    )
    col.add(
        ids=[c["id"] for c in chunks],
        embeddings=vectors,
        documents=[c["text"] for c in chunks],
        metadatas=[{"kind": c["kind"], "title": c["title"], "source": c["source"]} for c in chunks],
    )
    _collection = col
    return len(chunks)


def get_collection():
    """Load the index, building it automatically if it is missing or the help docs changed."""
    global _collection
    if _collection is not None:
        return _collection
    try:
        col = _chroma().get_collection(COLLECTION)
        if col.metadata.get("help_hash") == _file_hash() and col.count() == len(load_chunks()):
            _collection = col
            return col
        logging.info("Help docs changed; rebuilding index.")
    except Exception:
        logging.info("No index found; building it now.")
    build_index()
    return _collection


# ---------- 4. Search ----------
def search(question: str, k: int = TOP_K) -> list[dict]:
    col = get_collection()
    qvec = embed([question], task_type="RETRIEVAL_QUERY")[0]
    res = col.query(query_embeddings=[qvec], n_results=k)
    return [
        {"source": meta["source"], "text": doc, "score": round(1 - dist, 3)}
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]
