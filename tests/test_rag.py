"""
tests/test_rag.py — Test the RAG retriever
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.simple_retriever import build_cache, query, format_for_prompt


def test_build_cache():
    """Build the chunk cache from PDFs."""
    print("\n🔨 Building cache from PDFs...")
    build_cache()
    from rag.simple_retriever import CACHE_FILE
    assert CACHE_FILE.exists(), "Cache file not created!"
    print(f"✅ Cache built: {CACHE_FILE}")


def test_query_rpwd():
    """Query RPwD Act for disability education rights."""
    print("\n🔍 Querying RPwD Act...")
    results = query("IEP education rights disability students", source="rpwd_act", top_k=3)
    assert len(results) > 0, "No results from RPwD Act!"
    print(f"✅ Got {len(results)} results")
    for r in results:
        print(f"   Score: {r.score} | {r.section}")
        print(f"   Text : {r.text[:80]}...")


def test_query_ncte():
    """Query NCTE guidelines for IEP components."""
    print("\n🔍 Querying NCTE Guidelines...")
    results = query("individualized education program inclusive school", source="ncte_guidelines", top_k=3)
    assert len(results) > 0, "No results from NCTE!"
    print(f"✅ Got {len(results)} results")
    for r in results:
        print(f"   Score: {r.score} | {r.section}")
        print(f"   Text : {r.text[:80]}...")


def test_format_for_prompt():
    """Test prompt formatting."""
    print("\n📝 Testing prompt format...")
    results = query("disability accommodation exam", top_k=2)
    formatted = format_for_prompt(results)
    assert "[1]" in formatted
    print("✅ Prompt format correct")
    print(f"\n--- Sample prompt injection ---\n{formatted[:300]}...")


if __name__ == "__main__":
    print("\n🧪 Running RAG Tests...\n")
    test_build_cache()
    test_query_rpwd()
    test_query_ncte()
    test_format_for_prompt()
    print("\n🎉 ALL RAG TESTS PASSED — Step 3 Complete!\n")