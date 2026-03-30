#!/usr/bin/env python3
"""
Phase 5 Test Suite — Multi-Agent Coherence

Tests all Phase 5 components:
- Agent synchronization
- Consensus voting
- Cross-agent inference
- Coherence validation
- Multi-agent orchestration

Run with: python test_phase5.py

Expected results:
- All tests pass
- <200ms per multi-agent query
- <500ms synchronization
- >90% coherence health

Usage:
    python test_phase5.py --verbose
    python test_phase5.py --specific agent_sync
    python test_phase5.py --benchmark
"""

import unittest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime
import time
import sys

# Add scripts to path
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from agent_sync import AgentSynchronizer
from consensus_engine import ConsensusEngine
from cross_agent_inference import CrossAgentInferencer
from coherence_validator import CoherenceValidator
from multi_agent_orchestrator import MultiAgentOrchestrator


class Phase5TestCase(unittest.TestCase):
    """Base test case with temporary database."""
    
    @classmethod
    def setUpClass(cls):
        """Set up temporary database."""
        cls.db_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.db_dir.name) / 'test.db'
        
        # Initialize test database with schema
        cls._init_test_db()
    
    @classmethod
    def _init_test_db(cls):
        """Initialize test database schema."""
        conn = sqlite3.connect(str(cls.db_path))
        cursor = conn.cursor()
        
        # Create essential tables
        cursor.execute("""
            CREATE TABLE memory_facts (
                id TEXT PRIMARY KEY,
                content TEXT,
                confidence REAL,
                agent_id TEXT,
                created_at TEXT,
                updated_at TEXT,
                metadata TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE agent_votes (
                id INTEGER PRIMARY KEY,
                fact_id TEXT,
                agent_id TEXT,
                confidence REAL,
                reason TEXT,
                timestamp TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE agent_state (
                agent_id TEXT PRIMARY KEY,
                last_sync TEXT,
                fact_count INTEGER,
                sync_status TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE agent_sync_log (
                id INTEGER PRIMARY KEY,
                agent_id_from TEXT,
                agent_id_to TEXT,
                facts_synced INTEGER,
                timestamp TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE consensus_log (
                id INTEGER PRIMARY KEY,
                fact_id TEXT,
                consensus_score REAL,
                approver TEXT,
                timestamp TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE fact_references (
                id INTEGER PRIMARY KEY,
                fact_id TEXT,
                ref_fact_id TEXT,
                dependency_strength REAL,
                created_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE agent_performance_log (
                id INTEGER PRIMARY KEY,
                agent_id TEXT,
                search_time_ms REAL,
                timestamp TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up temporary database."""
        cls.db_dir.cleanup()


class TestAgentSync(Phase5TestCase):
    """Tests for AgentSynchronizer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sync = AgentSynchronizer(self.db_path)
        self._populate_test_data()
    
    def tearDown(self):
        """Clean up."""
        self.sync.close()
    
    def _populate_test_data(self):
        """Add test data."""
        cursor = self.sync.conn.cursor()
        
        facts = [
            ('fact1', 'Test fact 1', 0.95, 'falcon', datetime.now().isoformat()),
            ('fact2', 'Test fact 2', 0.90, 'katsumi', datetime.now().isoformat()),
            ('fact3', 'Test fact 3', 0.85, 'leo', datetime.now().isoformat()),
        ]
        
        for fact_id, content, conf, agent, ts in facts:
            cursor.execute("""
                INSERT INTO memory_facts (id, content, confidence, agent_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (fact_id, content, conf, agent, ts, ts))
        
        self.sync.conn.commit()
    
    def test_pull_updates(self):
        """Test pulling updates from agent."""
        updates = self.sync.pull_updates('falcon')
        self.assertGreater(len(updates), 0)
        self.assertEqual(updates[0]['agent_id'], 'falcon')
    
    def test_sync_agents(self):
        """Test synchronizing agents."""
        report = self.sync.sync_agents(['falcon', 'katsumi', 'leo'])
        self.assertEqual(report['status'], 'complete')
        self.assertGreater(report['facts_pulled'], 0)


class TestConsensusEngine(Phase5TestCase):
    """Tests for ConsensusEngine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.voter = ConsensusEngine(self.db_path)
        self._populate_votes()
    
    def tearDown(self):
        """Clean up."""
        self.voter.close()
    
    def _populate_votes(self):
        """Add test votes."""
        # Unanimous vote
        self.voter.vote('fact1', 'falcon', 0.95)
        self.voter.vote('fact1', 'katsumi', 0.92)
        self.voter.vote('fact1', 'leo', 0.88)
        
        # Disputed vote
        self.voter.vote('fact2', 'falcon', 0.90)
        self.voter.vote('fact2', 'leo', 0.50)
    
    def test_vote_recording(self):
        """Test recording votes."""
        result = self.voter.vote('fact3', 'falcon', 0.85)
        self.assertTrue(result)
    
    def test_get_votes(self):
        """Test retrieving votes."""
        votes = self.voter.get_votes('fact1')
        self.assertEqual(len(votes), 3)
    
    def test_consensus_calculation(self):
        """Test consensus calculation."""
        consensus = self.voter.calculate_consensus('fact1')
        self.assertEqual(consensus.agreement_count, 3)
        self.assertGreater(consensus.consensus_score, 0.5)
    
    def test_consensus_status(self):
        """Test consensus status determination."""
        consensus = self.voter.calculate_consensus('fact1')
        self.assertEqual(consensus.status, 'approved')
        
        consensus = self.voter.calculate_consensus('fact2')
        self.assertEqual(consensus.status, 'disputed')


class TestCrossAgentInference(Phase5TestCase):
    """Tests for CrossAgentInferencer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.inferencer = CrossAgentInferencer(self.db_path)
        self._populate_memory()
    
    def tearDown(self):
        """Clean up."""
        self.inferencer.close()
    
    def _populate_memory(self):
        """Add test memory facts."""
        cursor = self.inferencer.conn.cursor()
        
        facts = [
            ('mem1', 'System architecture hybrid ranking', 0.95, 'falcon'),
            ('mem2', 'Pattern recognition with windowing', 0.90, 'katsumi'),
            ('mem3', 'External validation complete', 0.85, 'leo'),
        ]
        
        for fact_id, content, conf, agent in facts:
            cursor.execute("""
                INSERT INTO memory_facts (id, content, confidence, agent_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (fact_id, content, conf, agent, datetime.now().isoformat(), datetime.now().isoformat()))
        
        self.inferencer.conn.commit()
    
    def test_single_agent_query(self):
        """Test querying single agent."""
        result = self.inferencer._query_agent('falcon', 'system')
        self.assertIsNotNone(result)
        self.assertEqual(result.agent_id, 'falcon')
    
    def test_cross_agent_query(self):
        """Test cross-agent query."""
        result = self.inferencer.query('architecture')
        self.assertIsNotNone(result.unified_answer)
        self.assertGreater(result.confidence, 0.0)
    
    def test_merge_and_rank(self):
        """Test merging and ranking results."""
        # Create mock agent results
        from cross_agent_inference import AgentResult
        
        agent_results = {
            'falcon': AgentResult(
                agent_id='falcon',
                query='test',
                results=[{'id': '1', 'confidence': 0.95}],
                confidence=0.95,
                relevance=0.95,
                summary='Test',
                search_time_ms=50
            ),
            'katsumi': AgentResult(
                agent_id='katsumi',
                query='test',
                results=[{'id': '2', 'confidence': 0.90}],
                confidence=0.90,
                relevance=0.90,
                summary='Test',
                search_time_ms=60
            )
        }
        
        merged, contrib = self.inferencer._merge_and_rank(agent_results)
        self.assertGreater(len(merged), 0)


class TestCoherenceValidator(Phase5TestCase):
    """Tests for CoherenceValidator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.validator = CoherenceValidator(self.db_path)
        self._populate_test_data()
    
    def tearDown(self):
        """Clean up."""
        self.validator.close()
    
    def _populate_test_data(self):
        """Add test data."""
        cursor = self.validator.conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO memory_facts (id, content, confidence, agent_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('fact1', 'Coherent fact', 0.95, 'falcon', now, now))
        
        self.validator.conn.commit()
    
    def test_temporal_coherence(self):
        """Test temporal coherence check."""
        violations = self.validator.check_temporal_coherence()
        # Should have no violations in test data
        self.assertIsInstance(violations, list)
    
    def test_logical_coherence(self):
        """Test logical coherence check."""
        violations = self.validator.check_logical_coherence()
        self.assertIsInstance(violations, list)
    
    def test_source_coherence(self):
        """Test source coherence check."""
        violations = self.validator.check_source_coherence()
        self.assertIsInstance(violations, list)
    
    def test_full_validation(self):
        """Test full validation."""
        report = self.validator.validate_all()
        self.assertIn('health_score', report)
        self.assertIn('total_violations', report)


class TestMultiAgentOrchestrator(Phase5TestCase):
    """Tests for MultiAgentOrchestrator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.orchestrator = MultiAgentOrchestrator(self.db_path)
        self._populate_memory()
    
    def tearDown(self):
        """Clean up."""
        self.orchestrator.close()
    
    def _populate_memory(self):
        """Add test memory."""
        cursor = self.orchestrator.conn.cursor()
        
        facts = [
            ('f1', 'Phase 5 test fact', 0.95, 'falcon'),
            ('f2', 'Multi-agent system', 0.90, 'katsumi'),
            ('f3', 'Coherence validation', 0.85, 'leo'),
        ]
        
        for fact_id, content, conf, agent in facts:
            cursor.execute("""
                INSERT INTO memory_facts (id, content, confidence, agent_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (fact_id, content, conf, agent, datetime.now().isoformat(), datetime.now().isoformat()))
        
        self.orchestrator.conn.commit()
    
    def test_process_query(self):
        """Test processing query through full pipeline."""
        result = self.orchestrator.process_query('multi-agent')
        self.assertEqual(result['status'], 'complete')
        self.assertIn('pipeline', result)
    
    def test_health_check(self):
        """Test health check."""
        health = self.orchestrator.get_health()
        self.assertIn('overall', health)
        self.assertGreaterEqual(health['overall'], 0)
    
    def test_status(self):
        """Test getting status."""
        status = self.orchestrator.get_status()
        self.assertEqual(status['phase'], 5)
        self.assertEqual(status['status'], 'operational')


class BenchmarkTests(Phase5TestCase):
    """Performance benchmarks for Phase 5."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.orchestrator = MultiAgentOrchestrator(self.db_path)
        self._populate_large_dataset()
    
    def tearDown(self):
        """Clean up."""
        self.orchestrator.close()
    
    def _populate_large_dataset(self):
        """Add larger test dataset."""
        cursor = self.orchestrator.conn.cursor()
        
        agents = ['falcon', 'katsumi', 'leo']
        for i in range(30):
            agent = agents[i % 3]
            cursor.execute("""
                INSERT INTO memory_facts (id, content, confidence, agent_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f'fact{i}', f'Test fact {i}', 0.80 + (i % 10) * 0.01, agent,
                  datetime.now().isoformat(), datetime.now().isoformat()))
        
        self.orchestrator.conn.commit()
    
    def test_query_latency(self):
        """Test multi-agent query latency (<200ms)."""
        start = time.time()
        result = self.orchestrator.process_query('test query')
        elapsed = (time.time() - start) * 1000
        
        self.assertLess(elapsed, 200, f"Query took {elapsed}ms (target: <200ms)")
    
    def test_sync_latency(self):
        """Test synchronization latency (<500ms)."""
        start = time.time()
        report = self.orchestrator.synchronizer.sync_agents()
        elapsed = (time.time() - start) * 1000
        
        self.assertLess(elapsed, 500, f"Sync took {elapsed}ms (target: <500ms)")


def run_tests(verbose=False, specific=None, benchmark=False):
    """Run test suite."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    if specific:
        # Run specific test
        test_class = globals().get(f'Test{specific.title()}')
        if test_class:
            suite.addTests(loader.loadTestsFromTestCase(test_class))
    elif benchmark:
        # Run benchmarks only
        suite.addTests(loader.loadTestsFromTestCase(BenchmarkTests))
    else:
        # Run all tests
        suite.addTests(loader.loadTestsFromTestCase(TestAgentSync))
        suite.addTests(loader.loadTestsFromTestCase(TestConsensusEngine))
        suite.addTests(loader.loadTestsFromTestCase(TestCrossAgentInference))
        suite.addTests(loader.loadTestsFromTestCase(TestCoherenceValidator))
        suite.addTests(loader.loadTestsFromTestCase(TestMultiAgentOrchestrator))
    
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Phase 5 Test Suite')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--specific', help='Run specific test class')
    parser.add_argument('--benchmark', action='store_true', help='Run benchmarks only')
    
    args = parser.parse_args()
    exit(run_tests(verbose=args.verbose, specific=args.specific, benchmark=args.benchmark))
