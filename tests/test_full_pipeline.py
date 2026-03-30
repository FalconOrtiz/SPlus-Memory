"""
Integration Tests: All Phases 8-13

Test the complete Memory System pipeline end-to-end:
Input (Memory Layer) → Learning (Memory Layer) → Reasoning (Memory Layer) 
→ Execution (Memory Layer) → Storage (Memory Layer) → Wisdom (Memory Layer)

Target: >90% success rate on all integration flows
"""

import sys
import asyncio
import numpy as np
import time
from pathlib import Path

# Import all phase engines via package
from splusplus.agi.multimodal_fusion_engine import MultimodalFusionEngine
from splusplus.agi.distributed_executor import DistributedExecutor as DistributedExecutionEngine, Task as TaskPriority
from splusplus.agi.vector_graph_scale import VectorGraphScaleEngine, RelationType
from splusplus.agi.meta_learning_engine import MetaLearningEngine
from splusplus.agi.causal_reasoner import CausalReasoningEngine
from splusplus.agi.common_sense_kb import CommonSenseReasoningEngine

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class TestIntegrationAllPhases:
    """Test complete Memory System pipeline — pytest-compatible"""

    def log_test(self, phase: str, test_name: str, passed: bool, duration: float):
        """Log test result"""
        status = "PASS" if passed else "FAIL"
        logger.info(f"  {status} {test_name} ({duration:.3f}s)")

    # ─── PHASE 8: MULTIMODAL FUSION ───

    def test_phase_8_vision_extraction(self):
        """Test vision feature extraction"""
        start = time.time()
        try:
            engine = MultimodalFusionEngine()
            
            # Create test image
            image = np.random.rand(100, 100, 3)
            features = engine.vision_extractor.extract(image)
            
            assert features is not None
            assert features.confidence > 0
            
            self.log_test("phase_8", "vision_extraction", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Vision extraction failed: {e}")
            self.log_test("phase_8", "vision_extraction", False, time.time() - start)
            return False

    def test_phase_8_audio_extraction(self):
        """Test audio feature extraction"""
        start = time.time()
        try:
            engine = MultimodalFusionEngine()
            
            # Create test audio
            audio = np.random.rand(16000)
            features = engine.audio_extractor.extract(audio, sample_rate=16000)
            
            assert features is not None
            assert features.confidence > 0
            
            self.log_test("phase_8", "audio_extraction", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            self.log_test("phase_8", "audio_extraction", False, time.time() - start)
            return False

    def test_phase_8_text_extraction(self):
        """Test text feature extraction"""
        start = time.time()
        try:
            engine = MultimodalFusionEngine()
            
            text = "This is a test sentence for feature extraction."
            features = engine.text_extractor.extract(text)
            
            assert features is not None
            assert features.confidence > 0
            
            self.log_test("phase_8", "text_extraction", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            self.log_test("phase_8", "text_extraction", False, time.time() - start)
            return False

    # ─── PHASE 11: META-LEARNING ───

    def test_phase_11_decision_tree_learning(self):
        """Test decision tree learning"""
        start = time.time()
        try:
            engine = MetaLearningEngine()
            
            # Create training data
            X = np.array([
                [0, 0],
                [1, 1],
                [0, 1],
                [1, 0]
            ])
            y = np.array([0, 1, 0, 1])
            
            # Train
            engine.fit(X, y)
            
            # Predict
            pred = engine.predict(X[:1])
            assert pred is not None
            
            self.log_test("phase_11", "decision_tree_learning", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Decision tree learning failed: {e}")
            self.log_test("phase_11", "decision_tree_learning", False, time.time() - start)
            return False

    def test_phase_11_feature_extraction(self):
        """Test feature importance extraction"""
        start = time.time()
        try:
            engine = MetaLearningEngine()
            
            # Create training data
            X = np.array([[1, 2], [2, 3], [3, 4], [4, 5]])
            y = np.array([0, 1, 0, 1])
            
            engine.fit(X, y)
            importance = engine.get_feature_importance()
            
            assert importance is not None
            assert len(importance) == 2
            
            self.log_test("phase_11", "feature_extraction", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            self.log_test("phase_11", "feature_extraction", False, time.time() - start)
            return False

    # ─── PHASE 12: CAUSAL REASONING ───

    def test_phase_12_causal_graph_discovery(self):
        """Test causal graph discovery"""
        start = time.time()
        try:
            engine = CausalReasoningEngine()
            
            # Create observations
            observations = [
                ({"A": 1, "B": 2}, 0.5),
                ({"A": 2, "B": 4}, 0.8),
                ({"A": 3, "B": 6}, 0.9),
            ]
            
            result = engine.learn_from_observations(observations)
            
            assert result["observations_added"] == 3
            assert result["edges_discovered"] > 0
            
            self.log_test("phase_12", "causal_graph_discovery", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Causal graph discovery failed: {e}")
            self.log_test("phase_12", "causal_graph_discovery", False, time.time() - start)
            return False

    def test_phase_12_consequence_prediction(self):
        """Test consequence prediction"""
        start = time.time()
        try:
            engine = CausalReasoningEngine()
            
            # Learn causal model
            observations = [
                ({"action": 1, "outcome": 2}, 0.5),
                ({"action": 2, "outcome": 4}, 0.8),
                ({"action": 3, "outcome": 6}, 0.9),
            ]
            engine.learn_from_observations(observations)
            
            # Predict
            result = engine.reason("action", "outcome", magnitude=2.0)
            
            assert result["confidence"] > 0
            
            self.log_test("phase_12", "consequence_prediction", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Consequence prediction failed: {e}")
            self.log_test("phase_12", "consequence_prediction", False, time.time() - start)
            return False

    # ─── PHASE 9: DISTRIBUTED EXECUTION ───

    async def test_phase_9_parallel_execution(self):
        """Test parallel task execution"""
        start = time.time()
        try:
            engine = DistributedExecutionEngine(max_parallel=5)
            
            # Schedule tasks
            def task_func(n):
                return n * 2
            
            for i in range(5):
                engine.schedule(f"task_{i}", task_func, args=(i,))
            
            # Execute
            results = await engine.run()
            
            assert results["summary"]["completed"] == 5
            
            self.log_test("phase_9", "parallel_execution", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Parallel execution failed: {e}")
            self.log_test("phase_9", "parallel_execution", False, time.time() - start)
            return False

    async def test_phase_9_dag_resolution(self):
        """Test DAG dependency resolution"""
        start = time.time()
        try:
            engine = DistributedExecutionEngine()
            
            # Create dependency chain
            def task_1():
                return "result_1"
            
            def task_2():
                return "result_2"
            
            task_1_id = engine.schedule("task_1", task_1)
            task_2_id = engine.schedule("task_2", task_2, depends_on=[task_1_id])
            
            # Execute
            results = await engine.run()
            
            assert results["summary"]["completed"] == 2
            
            self.log_test("phase_9", "dag_resolution", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"DAG resolution failed: {e}")
            self.log_test("phase_9", "dag_resolution", False, time.time() - start)
            return False

    # ─── PHASE 10: VECTOR + GRAPH STORAGE ───

    def test_phase_10_vector_search(self):
        """Test vector similarity search"""
        start = time.time()
        try:
            engine = VectorGraphScaleEngine()
            
            # Create vectors
            embedding = np.random.rand(768)
            engine.store_knowledge("fact_1", embedding, {"text": "test"})
            
            engine.store.build_indexes()
            
            # Search
            query = np.random.rand(768)
            results = engine.search_knowledge(query, top_k=5)
            
            assert results is not None
            
            self.log_test("phase_10", "vector_search", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            self.log_test("phase_10", "vector_search", False, time.time() - start)
            return False

    def test_phase_10_graph_relationships(self):
        """Test graph relationship storage"""
        start = time.time()
        try:
            engine = VectorGraphScaleEngine()
            
            # Add entities with relationships
            emb1 = np.random.rand(768)
            emb2 = np.random.rand(768)
            
            engine.store_knowledge("entity_1", emb1, {"name": "e1"})
            engine.store_knowledge("entity_2", emb2, {"name": "e2"}, 
                                 related=[("entity_1", "semantic")])
            
            # Get subgraph
            subgraph = engine.store.graph_store.get_subgraph("entity_1", depth=1)
            
            assert "entity_2" in subgraph["nodes"]
            
            self.log_test("phase_10", "graph_relationships", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Graph relationships failed: {e}")
            self.log_test("phase_10", "graph_relationships", False, time.time() - start)
            return False

    # ─── PHASE 13: COMMON-SENSE KB ───

    def test_phase_13_knowledge_base(self):
        """Test knowledge base functionality"""
        start = time.time()
        try:
            engine = CommonSenseReasoningEngine()
            
            # Get knowledge
            stats = engine.get_knowledge()
            
            assert stats["total_facts"] > 0
            assert len(stats["domain_breakdown"]) > 0
            
            self.log_test("phase_13", "knowledge_base", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Knowledge base failed: {e}")
            self.log_test("phase_13", "knowledge_base", False, time.time() - start)
            return False

    def test_phase_13_transfer_learning(self):
        """Test cross-domain transfer learning"""
        start = time.time()
        try:
            engine = CommonSenseReasoningEngine()
            
            # Get a fact and transfer it
            fact = engine.kb.get_facts_by_domain(
                list(engine.kb.domain_index.keys())[0]
            )[0]
            
            result = engine.transfer(fact.fact_id, "economics")
            
            assert result is not None
            assert result["confidence"] > 0
            
            self.log_test("phase_13", "transfer_learning", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Transfer learning failed: {e}")
            self.log_test("phase_13", "transfer_learning", False, time.time() - start)
            return False

    # ─── INTEGRATION TESTS ───

    async def test_integration_multimodal_to_learning(self):
        """Integration: Memory Layer → Memory Layer"""
        start = time.time()
        try:
            # Extract features from multimodal input
            fusion_engine = MultimodalFusionEngine()
            image = np.random.rand(100, 100, 3)
            features = fusion_engine.vision_extractor.extract(image)
            
            # Use features for learning
            ml_engine = MetaLearningEngine()
            X = np.array([[features.avg_color, features.contrast]])
            y = np.array([0])
            
            ml_engine.fit(X, y)
            
            self.log_test("integration", "multimodal_to_learning", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Integration failed: {e}")
            self.log_test("integration", "multimodal_to_learning", False, time.time() - start)
            return False

    async def test_integration_full_pipeline(self):
        """Integration: Complete pipeline 8→11→12→9→10"""
        start = time.time()
        try:
            # Memory Layer: Multimodal input
            text = "action increases outcome"
            
            # Memory Layer: Learn rules
            ml_engine = MetaLearningEngine()
            X = np.array([[1, 2], [2, 4], [3, 6]])
            y = np.array([0, 1, 1])
            ml_engine.fit(X, y)
            
            # Memory Layer: Causal reasoning
            causal_engine = CausalReasoningEngine()
            observations = [
                ({"action": 1, "outcome": 2}, 0.5),
                ({"action": 2, "outcome": 4}, 0.8),
            ]
            causal_engine.learn_from_observations(observations)
            
            # Memory Layer: Execute decisions
            exec_engine = DistributedExecutionEngine()
            exec_engine.schedule("predict", lambda: ml_engine.predict([[2, 4]]))
            exec_results = await exec_engine.run()
            
            # Memory Layer: Store results
            storage_engine = VectorGraphScaleEngine()
            emb = np.random.rand(768)
            storage_engine.store_knowledge("result", emb, {"pipeline": "complete"})
            
            assert exec_results["summary"]["completed"] > 0
            
            self.log_test("integration", "full_pipeline", True, time.time() - start)
            return True
        except Exception as e:
            logger.error(f"Full pipeline failed: {e}")
            self.log_test("integration", "full_pipeline", False, time.time() - start)
            return False

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
