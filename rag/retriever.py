"""
rag/retriever.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Single retriever interface used by all agents.
Swap the backend here — agents never change.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
from rag.chromadb_retriever import ChromaDBRetriever
from rag.chromadb_retriever import RetrievalResult

__all__ = ["initialize_retriever", "retrieve", "get_retriever_stats", 
           "reset_index", "RetrievalResult"]
logger = logging.getLogger(__name__)

# ── Singleton instance ────────────────────────────────────────────────────────
_retriever = ChromaDBRetriever()


def initialize_retriever(docs_dir: str = "./rag/documents") -> None:
    """
    Call once at application startup (in FastAPI lifespan).
    Loads existing index or builds a new one from PDFs.
    """
    _retriever.initialize(docs_dir)


def retrieve(query: str, n_results: int = 4) -> list[RetrievalResult]:
    """
    Retrieve the n most semantically relevant legal document chunks.

    Returns:
        list of RetrievalResult objects
    """
    return _retriever.retrieve(query, n_results)


def get_retriever_stats() -> dict:
    """Stats for health check and logging."""
    return _retriever.get_stats()


def reset_index() -> None:
    """Force rebuild the vector index. Use when PDFs are updated."""
    _retriever.reset_index()
    _retriever.initialize()
    
retriever = _retriever