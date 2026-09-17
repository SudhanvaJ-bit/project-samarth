"""
rag/chromadb_retriever.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ChromaDB vector store for SAMARTH legal document retrieval.

Architecture:
  - Documents chunked at ~400 words with 50-word overlap
  - Embedded with gemini-embedding-2 (retrieval_document task)
  - Queries embedded with retrieval_query task for asymmetric search
  - Persistent store at rag/chroma_db/ — built once, loaded forever
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import hashlib
import logging
import time
from pathlib import Path
from typing import Any
import os
from dotenv import load_dotenv
from google import genai
import chromadb
from google.genai import types
import pdfplumber

from dataclasses import dataclass

@dataclass
class RetrievalResult:
    """Structured result returned by retrieve(). Supports dot-notation access."""
    text:            str
    source:          str
    page:            int
    doc_type:        str
    relevance_score: float

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
CHROMA_PATH      = Path("./rag/chroma_db")
COLLECTION_NAME  = "samarth_legal_docs"
EMBEDDING_MODEL  = "models/gemini-embedding-2"
CHUNK_SIZE       = 400   # words per chunk
CHUNK_OVERLAP    = 50    # words overlap between consecutive chunks
EMBED_BATCH_SIZE = 20    # chunks per Gemini embedding call batch
EMBED_DELAY_SEC  = 0.5   # delay between batches (rate limit safety)


# ── Gemini embedding helpers ────────────────────────────────────────────────

# At module level — create client once


load_dotenv()

_genai_client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY")
)

def _embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts as retrieval DOCUMENTS (for indexing)."""
    embeddings = []
    for text in texts:
        result = _genai_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        embeddings.append(result.embeddings[0].values)
    return embeddings


def _embed_query(text: str) -> list[float]:
    """Embed a single text as a retrieval QUERY (for searching)."""
    result = _genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return result.embeddings[0].values


# ── PDF chunking ─────────────────────────────────────────────────────────────

def _doc_type(filename: str) -> str:
    name = filename.lower()
    if "rpwd" in name or "rights" in name:
        return "RPwD Act 2016"
    if "ncte" in name or "ncert" in name or "guideline" in name:
        return "NCTE/NCERT Guidelines"
    return "Legal Document"


def _chunk_text(text: str, source: str, page: int) -> list[dict]:
    """
    Split text into overlapping word-count chunks.
    Returns list of dicts: {text, source, page, doc_type, chunk_index}
    """
    words    = text.split()
    chunks   = []
    start    = 0
    idx      = 0

    while start < len(words):
        end        = min(start + CHUNK_SIZE, len(words))
        chunk_text = " ".join(words[start:end]).strip()

        if len(chunk_text) > 50:   # skip trivially short chunks
            chunks.append({
                "text":        chunk_text,
                "source":      source,
                "page":        page,
                "doc_type":    _doc_type(source),
                "chunk_index": idx,
            })
            idx += 1

        if end >= len(words):
            break
        start = end - CHUNK_OVERLAP   # overlap for context continuity

    return chunks


def _extract_chunks_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Extract and chunk all text from a PDF.
    Groups text by page, then chunks each page's content.
    """
    all_chunks = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text or not text.strip():
                continue
            page_chunks = _chunk_text(
                text.strip(), pdf_path.name, page_num)
            all_chunks.extend(page_chunks)

    logger.info(
        f"  {pdf_path.name}: {len(pdf.pages)} pages → {len(all_chunks)} chunks")
    return all_chunks


# ── ChromaDB Retriever ────────────────────────────────────────────────────────

class ChromaDBRetriever:
    """
    Persistent vector retriever backed by ChromaDB + Gemini embeddings.

    Usage:
        retriever = ChromaDBRetriever()
        retriever.initialize("./rag/documents")
        results = retriever.retrieve("mandatory accommodations for dyslexia")
    """

    def __init__(self):
        self._client:     chromadb.PersistentClient | None = None
        self._collection: Any                              = None
        self._ready:      bool                             = False

    # ── Public API ────────────────────────────────────────────────────────

    def initialize(self, docs_dir: str = "./rag/documents") -> None:
        """
        Load or build the ChromaDB index.
        If the index already exists and has documents, just loads it.
        Call once at application startup.
        """
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(CHROMA_PATH))

        # Collection with cosine similarity (best for semantic search)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        existing = self._collection.count()
        if existing > 0:
            logger.info(
                f"ChromaDB: loaded existing index — {existing} chunks ready")
            self._ready = True
            return

        # First run — build the index
        logger.info("ChromaDB: no index found — building from documents…")
        self._build_index(docs_dir)
        self._ready = True

    def retrieve(
        self,
        query: str,
        n_results: int = 4,
    ) -> list[dict]:
        """
        Semantic search over the legal document corpus.

        Returns list of dicts:
            text, source, page, doc_type, relevance_score
        """
        if not self._ready:
            raise RuntimeError(
                "ChromaDBRetriever not initialised. Call initialize() first.")

        # Embed query with retrieval_query task (asymmetric search)
        query_embedding = _embed_query(query)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append(RetrievalResult(
                text=            doc,
                source=          meta.get("source", ""),
                page=            meta.get("page", 0),
                doc_type=        meta.get("doc_type", ""),
                relevance_score= round(1.0 - float(dist), 4),
            ))

        return chunks
    
    def query_for_disability(self, disability: str, top_k: int = 5) -> list[dict]:
        """
        Retrieve legal/guideline chunks related to a specific disability.
        Used by compliance_agent.py.
        """
        query = (
            f"RPwD Act 2016 NCTE NCERT inclusive education "
            f"reasonable accommodations support services examination modifications "
            f"for {disability}"
        )

        return self.retrieve(query=query, n_results=top_k)
    
    def query_mandatory_iep_components(self, top_k: int = 5) -> list[dict]:
        """
        Retrieve chunks about mandatory IEP components, review, goals,
        accommodations, services, assessment modifications, and parent reporting.
        Used by compliance_agent.py.
        """
        query = (
            "mandatory IEP components individualized education program "
            "present levels annual goals short term objectives "
            "special education services accommodations assessment modifications "
            "parent participation progress reporting review schedule "
            "RPwD Act 2016 NCTE NCERT inclusive education"
        )

        return self.retrieve(
            query=query,
            n_results=top_k
        )
        
    def query_assessment_accommodations(self, disability: str = "", top_k: int = 5) -> list[dict]:
        """
        Retrieve chunks about exam/testing accommodations.
        Used by compliance_agent.py.
        """
        query = (
            f"assessment accommodations examination concessions extra time "
            f"scribe reader separate room assistive technology modified tests "
            f"inclusive education RPwD Act 2016 NCTE NCERT {disability}"
        )

        return self.retrieve(
            query=query,
            n_results=top_k
        )
        
    def query_accommodations(self, disability: str = "", top_k: int = 5) -> list[dict]:
        query = (
            f"reasonable accommodations classroom support examination modifications "
            f"assistive technology inclusive education {disability} "
            f"RPwD Act 2016 NCTE NCERT"
        )

        return self.retrieve(
            query=query,
            n_results=top_k
        )

    def query_assessment_modifications(self, disability: str = "", top_k: int = 5) -> list[dict]:
        query = (
            f"assessment modifications exam accommodations extra time scribe reader "
            f"separate room assistive technology inclusive education {disability} "
            f"RPwD Act 2016"
        )

        return self.retrieve(
            query=query,
            n_results=top_k
        )

    def get_stats(self) -> dict:
        return {
            "total_chunks": self._collection.count() if self._collection else 0,
            "ready":        self._ready,
            "db_path":      str(CHROMA_PATH),
            "collection":   COLLECTION_NAME,
        }

    def reset_index(self) -> None:
        """Delete and rebuild the index. Use when documents change."""
        if self._client and self._collection:
            self._client.delete_collection(COLLECTION_NAME)
            logger.info("ChromaDB: index deleted")
        self._ready = False

    # ── Index builder ─────────────────────────────────────────────────────

    def _build_index(self, docs_dir: str) -> None:
        docs_path = Path(docs_dir)
        pdf_files = sorted(docs_path.glob("*.pdf"))

        if not pdf_files:
            logger.error(f"ChromaDB: no PDFs found in {docs_dir}")
            return

        # ── Step 1: Extract all chunks from all PDFs ──────────────────────
        logger.info(f"ChromaDB: extracting text from {len(pdf_files)} PDFs…")
        all_chunks: list[dict] = []
        for pdf_path in pdf_files:
            all_chunks.extend(_extract_chunks_from_pdf(pdf_path))

        logger.info(f"ChromaDB: {len(all_chunks)} total chunks extracted")

        # ── Step 2: Embed in batches ──────────────────────────────────────
        all_ids        = []
        all_texts      = []
        all_embeddings = []
        all_metadatas  = []

        for i in range(0, len(all_chunks), EMBED_BATCH_SIZE):
            batch     = all_chunks[i : i + EMBED_BATCH_SIZE]
            batch_num = i // EMBED_BATCH_SIZE + 1
            total_bat = (len(all_chunks) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE

            logger.info(
                f"ChromaDB: embedding batch {batch_num}/{total_bat} "
                f"({len(batch)} chunks)…")

            texts = [c["text"] for c in batch]

            try:
                embeddings = _embed_documents(texts)
            except Exception as e:
                logger.error(f"Embedding failed for batch {batch_num}: {e}")
                raise

            for chunk, emb in zip(batch, embeddings):
                uid = hashlib.md5(
                    f"{chunk['source']}_{chunk['page']}_{chunk['chunk_index']}"
                    .encode()
                ).hexdigest()
                all_ids.append(uid)
                all_texts.append(chunk["text"])
                all_embeddings.append(emb)
                all_metadatas.append({
                    "source":      chunk["source"],
                    "page":        chunk["page"],
                    "doc_type":    chunk["doc_type"],
                    "chunk_index": chunk["chunk_index"],
                })

            # Rate-limit safety between batches
            if i + EMBED_BATCH_SIZE < len(all_chunks):
                time.sleep(EMBED_DELAY_SEC)

        # ── Step 3: Add to ChromaDB ───────────────────────────────────────
        STORE_BATCH = 100
        for i in range(0, len(all_ids), STORE_BATCH):
            self._collection.add(
                ids=        all_ids[i : i + STORE_BATCH],
                documents=  all_texts[i : i + STORE_BATCH],
                embeddings= all_embeddings[i : i + STORE_BATCH],
                metadatas=  all_metadatas[i : i + STORE_BATCH],
            )

        logger.info(
            f"ChromaDB: index built — {self._collection.count()} chunks stored "
            f"at {CHROMA_PATH}")
    
    def query_transition_planning(self, top_k: int = 4) -> list:
        """Retrieve chunks about transition planning for students aged 14+."""
        query = (
            "transition planning post-school outcomes vocational assessment "
            "employment community living post-secondary education "
            "RPwD Act 2016 Section 17 NCTE NCERT age 14 transition services"
        )
        return self.retrieve(query=query, n_results=top_k)


    def format_for_prompt(self, results: list) -> str:
        """
        Format a list of RetrievalResult objects into a clean string
        for injection into the Gemini compliance prompt.
        """
        if not results:
            return "No relevant legal context retrieved."

        sections = []
        for i, r in enumerate(results, 1):
            sections.append(
                f"[{i}] Source: {r.doc_type} (p.{r.page})\n"
                f"Relevance: {r.relevance_score:.3f}\n"
                f"Content: {r.text.strip()}"
            )

        return "\n\n---\n\n".join(sections)
    
        
    