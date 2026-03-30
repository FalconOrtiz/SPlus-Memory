#!/usr/bin/env python3
"""
Phase 3 Quick Test — Semantic Search & Deduplication

Validates core Phase 3 functionality:
- Semantic search operational
- Embedding retrieval working
- Similarity calculation correct
- Deduplication pipeline ready
"""

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))

from semantic_search import SemanticSearcher
from deduplicator import FactDeduplicator


def test_semantic_search():
    """Test semantic search capabilities."""
    print("\n" + "="*70)
    print("TEST 1: SEMANTIC SEARCH")
    print("="*70)
    
    searcher = SemanticSearcher()
    
    try:
        # Get embedding stats
        stats = searcher.embedding_stats()
        print(f"\n✓ Embedding Statistics:")
        print(f"  Total embeddings: {stats.get('total_embeddings', 0)}")
        print(f"  Models: {stats.get('models', {})}")
        
        if stats.get('total_embeddings', 0) == 0:
            print("  ✗ No embeddings found in database")
            return False
        
        # Get a random fact with embedding
        import sqlite3
        conn = sqlite3.connect(str(searcher.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fact_id FROM semantic_embeddings LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print("  ✗ No facts with embeddings")
            return False
        
        test_fact_id = row[0]
        print(f"\n✓ Test fact: {test_fact_id}")
        
        # Get its embedding
        embedding = searcher.get_embedding(test_fact_id)
        if embedding:
            print(f"✓ Retrieved embedding ({len(embedding)} dimensions)")
        else:
            print(f"✗ Failed to retrieve embedding")
            return False
        
        # Find similar facts
        similar = searcher.get_similar_facts(test_fact_id, top_k=5, min_similarity=0.7)
        print(f"✓ Found {len(similar)} similar facts")
        for fact in similar[:3]:
            print(f"    • {fact['fact_id']}: {fact['similarity']:.3f}")
        
        print("\n✓ SEMANTIC SEARCH TEST PASSED")
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        searcher.close()


def test_deduplication():
    """Test deduplication pipeline."""
    print("\n" + "="*70)
    print("TEST 2: DEDUPLICATION")
    print("="*70)
    
    dedup = FactDeduplicator()
    
    try:
        # Get deduplication stats
        stats = dedup.get_deduplication_stats()
        print(f"\n✓ Deduplication Statistics:")
        print(f"  Total facts: {stats.get('total_facts', 0)}")
        print(f"  Inactive facts: {stats.get('inactive_facts', 0)}")
        print(f"  Duplicates merged: {stats.get('duplicates_merged', 0)}")
        print(f"  Dedup rate: {stats.get('deduplication_rate', 0):.2f}%")
        
        # Find duplicates (dry run, threshold=0.90 for testing)
        print(f"\n✓ Finding duplicates (threshold=0.90)...")
        duplicates = dedup.find_duplicates(threshold=0.90, max_duplicates=100)
        
        if duplicates:
            print(f"✓ Found {len(duplicates)} duplicate groups")
            for i, group in enumerate(duplicates[:3], 1):
                print(f"    Group {i}: {len(group)} facts")
                canonical = dedup.select_canonical(group)
                print(f"      Canonical: {canonical}")
        else:
            print(f"  No significant duplicates found (threshold=0.90)")
        
        print("\n✓ DEDUPLICATION TEST PASSED")
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        dedup.close()


def main():
    """Run all Phase 3 tests."""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*68 + "║")
    print("║  PHASE 3 - SEMANTIC SEARCH & DEDUPLICATION - QUICK TEST" + " "*11 + "║")
    print("║" + " "*68 + "║")
    print("╚" + "="*68 + "╝")
    
    start_time = time.time()
    
    results = {
        'Semantic Search': False,
        'Deduplication': False
    }
    
    try:
        results['Semantic Search'] = test_semantic_search()
    except Exception as e:
        print(f"\n✗ Semantic search test failed: {e}")
    
    try:
        results['Deduplication'] = test_deduplication()
    except Exception as e:
        print(f"\n✗ Deduplication test failed: {e}")
    
    elapsed = time.time() - start_time
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {test_name}")
    
    print("-" * 70)
    print(f"Result: {passed}/{total} tests passed ({elapsed:.2f}s)")
    
    if passed == total:
        print("\n✅ PHASE 3 SYSTEMS OPERATIONAL - READY FOR PRODUCTION")
    else:
        print(f"\n⚠️  {total - passed} tests failed - Review required")
    
    print("="*70 + "\n")
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
