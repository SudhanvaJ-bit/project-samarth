"""
rag/ingest.py — Ultra Minimal Version (low RAM)
"""
import os
import time
import logging
from pathlib import Path
from typing import List
from dotenv import load_dotenv

import fitz
import chromadb
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DOCS_DIR    = Path(__file__).parent / "documents"
CHROMA_PATH = os.getenv("CHROMA_PERSIST_PATH", "./chroma_db")
API_KEY     = os.getenv("GOOGLE_API_KEY")

# Key pages only — skips irrelevant pages to save RAM
KEY_PAGES = {
    "rpwd_act_2016.pdf":   list(range(0, 20)),   # First 20 pages (core legal sections)
    "ncte_guidelines.pdf": list(range(0, 20)),   # First 20 pages (core guidelines)
}

COLLECTIONS = {
    "rpwd_act":        "rpwd_act_2016.pdf",
    "ncte_guidelines": "ncte_guidelines.pdf",
}


class GeminiEmbeddingFunction(chromadb.EmbeddingFunction):
    def __init__(self):
        self.model = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=API_KEY,
        )

    def __call__(self, input: List[str]) -> List[List[float]]:
        results = []
        for text in input:
            emb = self.model.embed_query(text[:1500])
            results.append(emb)
            time.sleep(0.1)
        return results


def get_chunks_from_pdf(pdf_path: Path, page_indices: list) -> List[str]:
    """
    Opens PDF, reads only specified pages,
    splits into ~300 char chunks on the fly.
    Never holds more than one page in memory.
    """
    chunks = []
    doc    = fitz.open(str(pdf_path))

    for page_num in page_indices:
        if page_num >= len(doc):
            break

        # Get page text and immediately split
        text = doc[page_num].get_text("text").strip()

        if not text or len(text) < 50:
            continue

        # Split page into 300-char chunks
        size = 300
        for i in range(0, len(text), size - 30):
            chunk = text[i:i + size].strip()
            if len(chunk) > 50:
                chunks.append(chunk)

        # Hard cap — stop at 30 chunks per collection
        if len(chunks) >= 30:
            chunks = chunks[:30]
            break

        # Free page text immediately
        del text

    doc.close()
    logger.info(f"  Extracted {len(chunks)} chunks from {len(page_indices)} pages")
    return chunks


def ingest_documents():
    logger.info("=" * 50)
    logger.info("  SAMARTH RAG — Ultra Minimal Mode")
    logger.info("=" * 50)

    if not API_KEY:
        logger.error("❌ GOOGLE_API_KEY not in .env")
        return

    embedding_fn = GeminiEmbeddingFunction()
    client       = chromadb.PersistentClient(path=CHROMA_PATH)

    for collection_name, filename in COLLECTIONS.items():
        pdf_path    = DOCS_DIR / filename
        page_list   = KEY_PAGES.get(filename, list(range(15)))

        logger.info(f"\n📄 {filename} → '{collection_name}'")

        if not pdf_path.exists():
            logger.error(f"  ❌ File not found: {pdf_path}")
            continue

        # Get chunks — minimal RAM usage
        chunks = get_chunks_from_pdf(pdf_path, page_list)
        if not chunks:
            logger.error(f"  ❌ No chunks from {filename}")
            continue

        # Delete old collection
        try:
            client.delete_collection(name=collection_name)
            logger.info(f"  🗑  Cleared old collection")
        except Exception:
            pass

        # Create collection
        col = client.create_collection(
            name               = collection_name,
            embedding_function = embedding_fn,
            metadata           = {"hnsw:space": "cosine"},
        )

        # Insert ONE chunk at a time — minimum RAM
        for i, chunk in enumerate(chunks):
            try:
                col.add(
                    ids       = [f"{collection_name}_{i}"],
                    documents = [chunk],
                    metadatas = [{"source": filename, "chunk_index": i}],
                )
                logger.info(f"  ✅ Chunk {i+1}/{len(chunks)} stored")
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"  ❌ Chunk {i} failed: {e}")

        del chunks
        logger.info(f"  ✅ '{collection_name}' complete!\n")

    logger.info("🎉 Ingestion complete!")


def verify_ingestion():
    logger.info("\n── Verification ───────────────────────")
    embedding_fn = GeminiEmbeddingFunction()
    client       = chromadb.PersistentClient(path=CHROMA_PATH)

    for col_name in COLLECTIONS.keys():
        try:
            col     = client.get_collection(
                name               = col_name,
                embedding_function = embedding_fn,
            )
            count   = col.count()
            results = col.query(
                query_texts = ["disability education rights IEP"],
                n_results   = 1,
            )
            preview = results["documents"][0][0][:80].replace("\n", " ")
            logger.info(f"  ✅ '{col_name}': {count} chunks")
            logger.info(f"     Top result: ...{preview}...")
        except Exception as e:
            logger.error(f"  ❌ '{col_name}': {e}")

    logger.info("───────────────────────────────────────\n")


if __name__ == "__main__":
    ingest_documents()
    verify_ingestion()