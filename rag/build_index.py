"""
rag/build_index.py
Run this once to build the ChromaDB index, or whenever PDFs are updated.

Usage:
    python rag/build_index.py
    python rag/build_index.py --reset   # force rebuild even if index exists
"""

import argparse
import logging
import sys
from pathlib import Path
from rag.chromadb_retriever import ChromaDBRetriever
# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

def main():
    parser = argparse.ArgumentParser(description="Build ChromaDB index for SAMARTH")
    parser.add_argument("--reset", action="store_true",
                        help="Delete existing index and rebuild from scratch")
    parser.add_argument("--docs", default="./rag/documents",
                        help="Path to folder containing PDF documents")
    parser.add_argument("--test", action="store_true",
                        help="Run a test query after building")
    args = parser.parse_args()

    retriever = ChromaDBRetriever()

    if args.reset:
        print("⚠️  Resetting existing index…")
        retriever.reset_index()

    print(f"📂 Loading documents from: {args.docs}")
    retriever.initialize(docs_dir=args.docs)

    stats = retriever.get_stats()
    print(f"\n✅ Index ready:")
    print(f"   Chunks:   {stats['total_chunks']}")
    print(f"   Location: {stats['db_path']}")

    if args.test:
        print("\n🔍 Running test queries…\n")
        test_queries = [
            "mandatory accommodations for students with dyslexia under RPwD Act",
            "IEP requirements for children with multiple disabilities",
            "extended time during examinations for students with learning disabilities",
            "responsibilities of schools under inclusive education guidelines",
        ]
        for q in test_queries:
            results = retriever.retrieve(q, n_results=2)
            print(f"Query: {q}")
            for r in results:
                print(f"  [{r['relevance_score']:.3f}] {r['doc_type']} p.{r['page']}: "
                      f"{r['text'][:120]}…")
            print()

if __name__ == "__main__":
    main()