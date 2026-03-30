#!/usr/bin/env python3
"""
Test Suite for Memory Engine Phase 1-2
Validates: BM25, temporal decay, database operations, hybrid search

Run: python3 test_memory_engine.py
"""

import sys
import sqlite3
import math
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from memory_engine import MemoryEngine


class TestMemoryEngine:
    """Test suite for Memory Engine"""
    
    def __init__(self):
        self.engine = MemoryEngine()
        self.passed = 0
        self.failed = 0
        self.test_db_path = Path("/tmp/test_memory.db")
    
    def setup(self):
        """Setup test database"""
        # Remove old test DB if exists
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        
        # Use test database
        self.engine.db_path = self.test_db_path
        self.engine.connect()
        self.engine.init_db()
    
    def teardown(self):
        """Cleanup"""
        if self.engine.conn:
            self.engine.close()
        if self.test_db_path.exists():
            self.test_db_path.unlink()
    
    def assert_true(self, condition, test_name):
        """Assert condition is true"""
        if condition:
            self.passed += 1
            print(f"  ✓ {test_name}")
        else:
            self.failed += 1
            print(f"  ✗ {test_name}")
    
    def assert_equal(self, actual, expected, test_name):
        """Assert values are equal"""
        if actual == expected:
            self.passed += 1
            print(f"  ✓ {test_name}")
        else:
            self.failed += 1
            print(f"  ✗ {test_name} (expected {expected}, got {actual})")
    
    def assert_in_range(self, value, min_val, max_val, test_name):
        """Assert value is in range"""
        if min_val <= value <= max_val:
            self.passed += 1
            print(f"  ✓ {test_name} ({value:.2f})")
        else:
            self.failed += 1
            print(f"  ✗ {test_name} ({value:.2f} not in [{min_val}, {max_val}])")
    
    # ─────────────────────────────────────────────────────────────────
    # BM25 SCORING TESTS
    # ─────────────────────────────────────────────────────────────────
    
    def test_bm25_exact_match(self):
        """BM25: Exact match should score high"""
        score = self.engine.bm25_score("authentication", "OAuth authentication")
        self.assert_in_range(score, 0.7, 1.0, "BM25 exact match")
    
    def test_bm25_partial_match(self):
        """BM25: Partial match should score medium"""
        score = self.engine.bm25_score("auth", "authenticate users")
        self.assert_in_range(score, 0.5, 0.9, "BM25 partial match")
    
    def test_bm25_no_match(self):
        """BM25: No match should score low"""
        score = self.engine.bm25_score("xyz", "OAuth authentication")
        self.assert_in_range(score, 0.0, 0.3, "BM25 no match")
    
    def test_bm25_multiple_terms(self):
        """BM25: Multiple matching terms score higher"""
        score1 = self.engine.bm25_score("auth user", "OAuth authentication users")
        score2 = self.engine.bm25_score("auth xyz", "OAuth authentication")
        self.assert_true(score1 > score2, "BM25 multiple terms boost")
    
    # ─────────────────────────────────────────────────────────────────
    # TEMPORAL DECAY TESTS
    # ─────────────────────────────────────────────────────────────────
    
    def test_decay_fresh(self):
        """Decay: Fresh facts (0 days) should have weight ~1.0"""
        now = datetime.now()
        weight = self.engine.calculate_decay_weight(now)
        self.assert_in_range(weight, 0.9, 1.0, "Decay fresh (0 days)")
    
    def test_decay_recent(self):
        """Decay: Recent facts (7 days) should have weight ~0.7"""
        created = datetime.now() - timedelta(days=7)
        weight = self.engine.calculate_decay_weight(created)
        self.assert_in_range(weight, 0.65, 0.75, "Decay recent (7 days)")
    
    def test_decay_medium(self):
        """Decay: Medium facts (30 days) should have weight ~0.2"""
        created = datetime.now() - timedelta(days=30)
        weight = self.engine.calculate_decay_weight(created)
        self.assert_in_range(weight, 0.15, 0.25, "Decay medium (30 days)")
    
    def test_decay_old(self):
        """Decay: Old facts (60 days) should have weight ~0.05"""
        created = datetime.now() - timedelta(days=60)
        weight = self.engine.calculate_decay_weight(created)
        self.assert_in_range(weight, 0.01, 0.1, "Decay old (60 days)")
    
    def test_decay_always_positive(self):
        """Decay: Weight should never go below 0.01"""
        created = datetime.now() - timedelta(days=365)  # 1 year
        weight = self.engine.calculate_decay_weight(created)
        self.assert_true(weight >= 0.01, "Decay always positive")
    
    # ─────────────────────────────────────────────────────────────────
    # FRESHNESS TIER TESTS
    # ─────────────────────────────────────────────────────────────────
    
    def test_freshness_recent(self):
        """Freshness: 2 days old should be "recent" """
        created = datetime.now() - timedelta(days=2)
        tier = self.engine.get_freshness_tier(created)
        self.assert_equal(tier, "recent", "Freshness recent (2 days)")
    
    def test_freshness_medium(self):
        """Freshness: 20 days old should be "medium" """
        created = datetime.now() - timedelta(days=20)
        tier = self.engine.get_freshness_tier(created)
        self.assert_equal(tier, "medium", "Freshness medium (20 days)")
    
    def test_freshness_old(self):
        """Freshness: 60 days old should be "old" """
        created = datetime.now() - timedelta(days=60)
        tier = self.engine.get_freshness_tier(created)
        self.assert_equal(tier, "old", "Freshness old (60 days)")
    
    def test_freshness_archive(self):
        """Freshness: 120 days old should be "archive" """
        created = datetime.now() - timedelta(days=120)
        tier = self.engine.get_freshness_tier(created)
        self.assert_equal(tier, "archive", "Freshness archive (120 days)")
    
    # ─────────────────────────────────────────────────────────────────
    # DATABASE OPERATIONS TESTS
    # ─────────────────────────────────────────────────────────────────
    
    def test_add_fact(self):
        """DB: Add fact should succeed"""
        fact_id = self.engine.add_fact(
            "Test fact content",
            "test",
            fact_type="TEST"
        )
        self.assert_true(fact_id.startswith("fact_"), "Add fact returns ID")
    
    def test_duplicate_detection(self):
        """DB: Duplicate fact should not be added twice"""
        content = "Unique test fact 12345"
        id1 = self.engine.add_fact(content, "test")
        id2 = self.engine.add_fact(content, "test")
        self.assert_equal(id1, id2, "Duplicate detection")
    
    def test_fact_content_hash(self):
        """DB: Content hash should be consistent"""
        content = "Test content 12345"
        hash1 = self.engine.get_content_hash(content)
        hash2 = self.engine.get_content_hash(content)
        self.assert_equal(hash1, hash2, "Content hash consistency")
    
    def test_fact_id_generation(self):
        """DB: Fact ID generation should be deterministic"""
        content = "Test content XYZ"
        id1 = self.engine.generate_fact_id(content)
        id2 = self.engine.generate_fact_id(content)
        self.assert_equal(id1, id2, "Fact ID deterministic")
    
    # ─────────────────────────────────────────────────────────────────
    # INTEGRATION TESTS
    # ─────────────────────────────────────────────────────────────────
    
    def test_add_and_retrieve(self):
        """Integration: Add fact and retrieve it"""
        content = "OAuth is authentication"
        fact_id = self.engine.add_fact(content, "test", fact_type="TECH")
        
        # Query
        results = self.engine.hybrid_search("OAuth", top_k=1)
        
        self.assert_true(len(results) > 0, "Retrieve fact after add")
        if len(results) > 0:
            self.assert_equal(results[0].fact_id, fact_id, "Retrieved correct fact")
    
    def test_ranking_by_relevance(self):
        """Integration: Hybrid search ranks by relevance"""
        # Add facts
        self.engine.add_fact("OAuth authentication", "test", fact_type="TECH")
        self.engine.add_fact("Password reset", "test", fact_type="TECH")
        self.engine.add_fact("Session management", "test", fact_type="TECH")
        
        # Search
        results = self.engine.hybrid_search("authentication", top_k=3)
        
        self.assert_true(len(results) >= 1, "Search returns results")
        if len(results) >= 1:
            # First result should have "authentication" in it
            has_auth = "authentication" in results[0].content.lower()
            self.assert_true(has_auth, "Top result contains query term")
    
    def test_decay_affects_ranking(self):
        """Integration: Older facts rank lower"""
        # Add old fact
        old_content = "Old authentication method"
        old_id = self.engine.add_fact(old_content, "test", fact_type="TECH")
        
        # Manually age it
        cursor = self.engine.conn.cursor()
        old_date = (datetime.now() - timedelta(days=100)).isoformat()
        cursor.execute(
            "UPDATE memory_facts SET created_at = ? WHERE id = ?",
            (old_date, old_id)
        )
        self.engine.conn.commit()
        
        # Recalculate decay
        self.engine.update_decay_weights()
        
        # Verify weight is low
        cursor.execute("SELECT decay_weight FROM memory_facts WHERE id = ?", (old_id,))
        weight = cursor.fetchone()[0]
        
        self.assert_true(weight < 0.1, "Old fact has low decay weight")
    
    # ─────────────────────────────────────────────────────────────────
    # STATUS TESTS
    # ─────────────────────────────────────────────────────────────────
    
    def test_status_format(self):
        """Status: Status report has required fields"""
        status = self.engine.get_status()
        
        self.assert_true("status" in status, "Status has 'status' field")
        self.assert_true("total_facts" in status, "Status has 'total_facts' field")
        self.assert_true("timestamp" in status, "Status has 'timestamp' field")
    
    def test_status_counts(self):
        """Status: Status counts are accurate (incremental)"""
        # Get current count
        before = self.engine.get_status()["total_facts"]
        
        # Add 2 new unique facts
        self.engine.add_fact("Status test fact AAA unique", "test")
        self.engine.add_fact("Status test fact BBB unique", "test")
        
        after = self.engine.get_status()["total_facts"]
        self.assert_equal(after - before, 2, "Status counts new facts correctly")
    
    # ─────────────────────────────────────────────────────────────────
    # TEST RUNNER
    # ─────────────────────────────────────────────────────────────────
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*60)
        print("MEMORY ENGINE TEST SUITE - PHASE 1-2")
        print("="*60 + "\n")
        
        self.setup()
        
        try:
            print("BM25 SCORING TESTS:")
            self.test_bm25_exact_match()
            self.test_bm25_partial_match()
            self.test_bm25_no_match()
            self.test_bm25_multiple_terms()
            
            print("\nTEMPORAL DECAY TESTS:")
            self.test_decay_fresh()
            self.test_decay_recent()
            self.test_decay_medium()
            self.test_decay_old()
            self.test_decay_always_positive()
            
            print("\nFRESHNESS TIER TESTS:")
            self.test_freshness_recent()
            self.test_freshness_medium()
            self.test_freshness_old()
            self.test_freshness_archive()
            
            print("\nDATABASE OPERATIONS TESTS:")
            self.test_add_fact()
            self.test_duplicate_detection()
            self.test_fact_content_hash()
            self.test_fact_id_generation()
            
            print("\nINTEGRATION TESTS:")
            self.test_add_and_retrieve()
            self.test_ranking_by_relevance()
            self.test_decay_affects_ranking()
            
            print("\nSTATUS TESTS:")
            self.test_status_format()
            self.test_status_counts()
            
        finally:
            self.teardown()
        
        # Summary
        total = self.passed + self.failed
        print("\n" + "="*60)
        print(f"RESULTS: {self.passed}/{total} tests passed")
        
        if self.failed == 0:
            print("✓ ALL TESTS PASSED")
        else:
            print(f"✗ {self.failed} tests failed")
        
        print("="*60 + "\n")
        
        return self.failed == 0


if __name__ == "__main__":
    tester = TestMemoryEngine()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
