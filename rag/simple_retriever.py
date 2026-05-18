"""
rag/simple_retriever.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Zero-dependency retriever — no ChromaDB, no embeddings.
Uses keyword search on pre-extracted PDF text.
Works on any RAM. Upgrade to ChromaDB on deployment.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import math
import re
import logging
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass

import fitz

logger = logging.getLogger(__name__)

DOCS_DIR   = Path(__file__).parent / "documents"
CACHE_FILE = Path(__file__).parent / "chunks_cache.json"

SOURCES = {
    "rpwd_act":        "rpwd_act_2016.pdf",
    "ncte_guidelines": "ncte_guidelines.pdf",
}


@dataclass
class RetrievalResult:
    text:    str
    source:  str
    score:   float
    section: str = ""


# ═══════════════════════════════════════════════════════
# STEP 1 — BUILD CACHE (runs once)
# ═══════════════════════════════════════════════════════

def build_cache():
    """
    Extract text from PDFs and save as JSON chunks.
    Runs once — subsequent calls load from cache file.
    """
    if CACHE_FILE.exists():
        logger.info("Cache already exists — skipping extraction")
        return

    logger.info("Building chunk cache from PDFs...")
    all_chunks = []

    for source_name, filename in SOURCES.items():
        pdf_path = DOCS_DIR / filename
        if not pdf_path.exists():
            logger.error(f"PDF not found: {pdf_path}")
            continue

        doc = fitz.open(str(pdf_path))
        logger.info(f"Processing {filename} — {len(doc)} pages")

        for page_num, page in enumerate(doc):
            text = page.get_text("text").strip()
            if not text or len(text) < 50:
                continue

            # Split page into 400-char chunks
            for i in range(0, len(text), 350):
                chunk = text[i:i + 400].strip()
                if len(chunk) > 50:
                    all_chunks.append({
                        "text":   chunk,
                        "source": source_name,
                        "page":   page_num + 1,
                        "file":   filename,
                    })

        doc.close()
        logger.info(f"  {source_name}: chunks added")

    # Save to JSON
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    logger.info(f"Cache saved: {len(all_chunks)} chunks → {CACHE_FILE}")


# ═══════════════════════════════════════════════════════
# STEP 2 — KEYWORD SEARCH
# ═══════════════════════════════════════════════════════

def _score(text: str, query: str) -> float:
    """
    TF-IDF-style keyword scoring.
    No external dependencies needed.
    """
    text_lower  = text.lower()
    query_words = re.findall(r'\w+', query.lower())

    if not query_words:
        return 0.0

    score = 0.0
    for word in query_words:
        if len(word) < 3:
            continue
        count = text_lower.count(word)
        tf    = count / (len(text_lower.split()) + 1)
        idf   = math.log(10 / (1 + count)) + 1
        score += tf * idf

    # Bonus for exact phrase match
    if query.lower() in text_lower:
        score += 2.0

    return round(score, 4)


def query(
    question: str,
    source:   str = "both",
    top_k:    int = 4,
) -> List[RetrievalResult]:
    """
    Search legal documents for relevant passages.

    Args:
        question : Natural language query
        source   : "rpwd_act" | "ncte_guidelines" | "both"
        top_k    : Number of results to return
    """
    # Build cache if needed
    if not CACHE_FILE.exists():
        build_cache()

    # Load chunks
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    # Filter by source
    if source != "both":
        chunks = [c for c in chunks if c["source"] == source]

    # Score all chunks
    scored = []
    for chunk in chunks:

        # ── Skip URL-heavy chunks (bibliography/reference pages) ──
        url_count = chunk["text"].count("http")
        if url_count > 2:
            continue

        # ── Skip very short chunks ──
        if len(chunk["text"].strip()) < 60:
            continue

        s = _score(chunk["text"], question)
        if s > 0:
            scored.append((s, chunk))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top_k as RetrievalResult objects
    results = []
    for score, chunk in scored[:top_k]:
        results.append(RetrievalResult(
            text    = chunk["text"],
            source  = chunk["source"],
            score   = score,
            section = f"Page {chunk['page']} — {chunk['file']}",
        ))

    return results


def format_for_prompt(results: List[RetrievalResult]) -> str:
    """
    Format retrieval results for LLM prompt injection.
    Each result is numbered with source and score.
    """
    if not results:
        return "No relevant legal provisions found."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"[{i}] Source: {r.source} | {r.section} | Score: {r.score}\n"
            f"{r.text.strip()}"
        )
    return "\n\n---\n\n".join(lines)


def query_for_disability(disability: str, top_k: int = 4) -> List[RetrievalResult]:
    """Disability-specific legal query."""
    return query(
        f"rights accommodations obligations {disability} students education IEP",
        top_k=top_k,
    )


def query_mandatory_iep_components() -> List[RetrievalResult]:
    """Query for mandatory IEP requirements."""
    return query(
        "mandatory IEP components individualized education program requirements",
        top_k=4,
    )


def query_assessment_accommodations(disability: str = "") -> List[RetrievalResult]:
    """Query for exam and assessment accommodations."""
    return query(
        f"examination assessment accommodation extra time scribe {disability}",
        top_k=3,
    )


def query_transition_planning() -> List[RetrievalResult]:
    """Query for transition planning requirements (age 14+)."""
    return query(
        "transition planning post school vocational age 14 IEP",
        top_k=3,
    )


# ═══════════════════════════════════════════════════════
# RETRIEVER INTERFACE
# Agents import this — never call ChromaDB directly
# ═══════════════════════════════════════════════════════

class SimpleRetriever:
    """
    Drop-in replacement for ChromaDB retriever.
    Same interface — swap to ChromaDB on deployment
    by changing the import in retriever.py only.
    """

    def __init__(self):
        build_cache()

    def query(self, question: str, collection: str = "both",
              top_k: int = 4) -> List[RetrievalResult]:
        return query(question, source=collection, top_k=top_k)

    def query_for_disability(self, disability: str,
                             top_k: int = 4) -> List[RetrievalResult]:
        return query_for_disability(disability, top_k=top_k)

    def query_mandatory_iep_components(self) -> List[RetrievalResult]:
        return query_mandatory_iep_components()

    def query_assessment_accommodations(self,
                                        disability: str = "") -> List[RetrievalResult]:
        return query_assessment_accommodations(disability)

    def query_transition_planning(self) -> List[RetrievalResult]:
        return query_transition_planning()

    def format_for_prompt(self, results: List[RetrievalResult]) -> str:
        return format_for_prompt(results)


# ── Singleton instance used by all agents ─────────────
retriever = SimpleRetriever()