"""
rag/retriever.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE SINGLE SWITCH FILE.

To swap from simple → ChromaDB on deployment:
Change line below from simple_retriever to chromadb_retriever.
Nothing else in the codebase needs to change.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ── Active backend (swap this line on deployment) ─────
from rag.simple_retriever import SimpleRetriever, RetrievalResult
# from rag.chromadb_retriever import ChromaRetriever as SimpleRetriever

# ── Export singleton used by all agents ───────────────
from rag.simple_retriever import retriever

__all__ = ["retriever", "RetrievalResult"]