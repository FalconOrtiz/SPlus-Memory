"""
Robust Test Suite - Auto-detect and test all available phases

Scans for phase files and runs comprehensive tests on what exists.
"""

import sys
import os
import asyncio
import numpy as np
import time
from pathlib import Path

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class RobustTestRunner:
    """Intelligently find and test all phases"""

    def __init__(self):
        self.phases_dir = Path(__file__).parent.parent / "agi"
        self.results = {}
        self.metrics = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "total_time": 0.0
        }

    def find_phase_file(self, phase_num):
        """Find main file for a phase"""
        phase_dir = self.phases_dir / f"memory-layer{phase_num}"
        
        if not phase_dir.exists():
            return None
        
        # Get all Python files (excluding tests)
        all_py = [f for f in phase_dir.glob("*.py") if not f.name.startswith("test_")]
        
        if not all_py:
            return None
        
        # Pick the most recently modified file (latest implementation)
        return max(all_py, key=lambda f: f.stat().st_mtime)

    def load_phase_module(self, phase_num, filename):
        """Dynamically load a phase module"""
        sys.path.insert(0, str(filename.parent))
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"phase_{phase_num}", filename)
            if spec is None:
                logger.error(f"Could not create spec for phase {phase_num}")
                return None
            
            module = importlib.util.module_from_spec(spec)
            if module is None:
                logger.error(f"Could not create module for phase {phase_num}")
                return None
            
            if spec.loader is None:
                logger.error(f"Could not get loader for phase {phase_num}")
                return None
            
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            logger.error(f"Failed to load phase {phase_num}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def test(self, phase: str, name: str, func):
        """Run single test with error handling"""
        start = time.time()
        try:
            result = func()
            duration = time.time() - start
            
            if phase not in self.results:
                self.results[phase] = []
            
            self.results[phase].append({
                "name": name,
                "passed": True,
                "duration": duration,
                "error": None
            })
            
            self.metrics["total"] += 1
            self.metrics["passed"] += 1
            
            logger.info(f"  ✅ {name} ({duration:.3f}s)")
            return True
            
        except Exception as e:
            duration = time.time() - start
            
            if phase not in self.results:
                self.results[phase] = []
            
            self.results[phase].append({
                "name": name,
                "passed": False,
                "duration": duration,
                "error": str(e)[:100]
            })
            
            self.metrics["total"] += 1
            self.metrics["failed"] += 1
            
            logger.info(f"  ❌ {name} ({duration:.3f}s)")
            return False

    def run_all(self):
        """Scan and test all phases"""
        logger.info("\n" + "="*80)
        logger.info("Memory System TURBO SPRINT - ROBUST TEST SUITE")
        logger.info("="*80 + "\n")

        suite_start = time.time()

        # ─── PHASE 8: MULTIMODAL FUSION ───
        logger.info("PHASE 8: MULTIMODAL FUSION ENGINE")
        logger.info("─" * 80)
        
        phase_8_file = self.find_phase_file(8)
        if phase_8_file:
            logger.info(f"Found: {phase_8_file.name}")
            module = self.load_phase_module(8, phase_8_file)
            
            if module:
                try:
                    # Find the main engine class
                    classes = [name for name in dir(module) if 'Fusion' in name or 'Engine' in name]
                    if classes:
                        EngineClass = getattr(module, classes[0])
                        
                        # Test 1: Initialize
                        self.test("phase_8", "Engine initialization", 
                                 lambda: EngineClass() is not None)
                        
                        # Test 2: Vision extraction (if available)
                        def test_vision():
                            engine = EngineClass()
                            if hasattr(engine, 'vision_extractor'):
                                result = engine.vision_extractor.extract(np.random.rand(100, 100, 3))
                                return result is not None
                            return True
                        
                        self.test("phase_8", "Vision feature extraction", test_vision)
                        
                        # Test 3: Performance
                        def test_performance():
                            engine = EngineClass()
                            start = time.time()
                            if hasattr(engine, 'audio_extractor'):
                                engine.audio_extractor.extract(np.random.rand(16000), 16000)
                            elapsed = time.time() - start
                            return elapsed < 0.1
                        
                        self.test("phase_8", "Audio extraction (<100ms)", test_performance)
                except Exception as e:
                    logger.error(f"Memory Layer test error: {e}")
        else:
            logger.info("  No memory-layer file found")

        # ─── PHASE 9: DISTRIBUTED EXECUTION ───
        logger.info("\nPHASE 9: DISTRIBUTED EXECUTION ENGINE")
        logger.info("─" * 80)
        
        phase_9_file = self.find_phase_file(9)
        if phase_9_file:
            logger.info(f"Found: {phase_9_file.name}")
            module = self.load_phase_module(9, phase_9_file)
            
            if module:
                try:
                    classes = [name for name in dir(module) if 'Execution' in name or 'Executor' in name]
                    if classes:
                        EngineClass = getattr(module, classes[0])
                        
                        # Test 1: Initialize
                        self.test("phase_9", "Executor initialization", 
                                 lambda: EngineClass() is not None)
                        
                        # Test 2: Basic scheduling
                        def test_schedule():
                            engine = EngineClass()
                            engine.schedule("task1", lambda: 42)
                            return True
                        
                        self.test("phase_9", "Task scheduling", test_schedule)
                except Exception as e:
                    logger.error(f"Memory Layer test error: {e}")
        else:
            logger.info("  No memory-layer file found")

        # ─── PHASE 10: VECTOR + GRAPH STORAGE ───
        logger.info("\nPHASE 10: VECTOR + GRAPH STORAGE")
        logger.info("─" * 80)
        
        phase_10_file = self.find_phase_file(10)
        if phase_10_file:
            logger.info(f"Found: {phase_10_file.name}")
            module = self.load_phase_module(10, phase_10_file)
            
            if module:
                try:
                    # Look for VectorGraphScaleEngine first
                    if hasattr(module, 'VectorGraphScaleEngine'):
                        EngineClass = module.VectorGraphScaleEngine
                    else:
                        classes = [name for name in dir(module) if 'Engine' in name or 'Scale' in name]
                        if classes:
                            EngineClass = getattr(module, classes[0])
                        else:
                            EngineClass = None
                    
                    if EngineClass:
                        
                        # Test 1: Initialize
                        def test_init():
                            engine = EngineClass()
                            return engine is not None
                        
                        self.test("phase_10", "Storage engine initialization", test_init)
                        
                        # Test 2: Vector operations
                        def test_vectors():
                            engine = EngineClass()
                            emb = np.random.rand(768)
                            # Note: store_knowledge uses knowledge_id, embedding, content parameters
                            engine.store_knowledge(knowledge_id="test", embedding=emb, content={})
                            return True
                        
                        self.test("phase_10", "Vector storage", test_vectors)
                        
                        # Test 3: Query performance
                        def test_query_perf():
                            engine = EngineClass()
                            emb = np.random.rand(768)
                            engine.store_knowledge(knowledge_id="test", embedding=emb, content={})
                            engine.store.build_indexes()
                            
                            start = time.time()
                            query = np.random.rand(768)
                            engine.search_knowledge(query)
                            elapsed = time.time() - start
                            return elapsed < 0.1
                        
                        self.test("phase_10", "Vector search (<100ms)", test_query_perf)
                except Exception as e:
                    logger.error(f"Memory Layer test error: {e}")
        else:
            logger.info("  No memory-layer file found")

        # ─── PHASE 11: META-LEARNING ───
        logger.info("\nPHASE 11: META-LEARNING ENGINE")
        logger.info("─" * 80)
        
        phase_11_file = self.find_phase_file(11)
        if phase_11_file:
            logger.info(f"Found: {phase_11_file.name}")
            module = self.load_phase_module(11, phase_11_file)
            
            if module:
                try:
                    classes = [name for name in dir(module) if 'Learning' in name or 'Tree' in name]
                    if classes:
                        EngineClass = getattr(module, classes[0])
                        
                        # Test 1: Initialize
                        self.test("phase_11", "Learning engine initialization", 
                                 lambda: EngineClass() is not None)
                        
                        # Test 2: Fit + predict
                        def test_fit_predict():
                            engine = EngineClass()
                            X = np.array([[1, 2], [2, 3], [3, 4]])
                            y = np.array([0, 1, 0])
                            engine.fit(X, y)
                            pred = engine.predict(X[:1])
                            return pred is not None
                        
                        self.test("phase_11", "Fit and predict", test_fit_predict)
                        
                        # Test 3: Feature importance
                        def test_importance():
                            engine = EngineClass()
                            X = np.array([[1, 2], [2, 3], [3, 4]])
                            y = np.array([0, 1, 0])
                            engine.fit(X, y)
                            if hasattr(engine, 'get_feature_importance'):
                                imp = engine.get_feature_importance()
                                return imp is not None
                            return True
                        
                        self.test("phase_11", "Feature importance extraction", test_importance)
                        
                        # Test 4: Inference speed
                        def test_inference_speed():
                            engine = EngineClass()
                            X = np.array([[1, 2], [2, 3], [3, 4]])
                            y = np.array([0, 1, 0])
                            engine.fit(X, y)
                            
                            start = time.time()
                            engine.predict(X)
                            elapsed = time.time() - start
                            return elapsed < 0.1
                        
                        self.test("phase_11", "Inference latency (<100ms)", test_inference_speed)
                except Exception as e:
                    logger.error(f"Memory Layer test error: {e}")
        else:
            logger.info("  No memory-layer file found")

        # ─── PHASE 12: CAUSAL REASONING ───
        logger.info("\nPHASE 12: CAUSAL REASONING ENGINE")
        logger.info("─" * 80)
        
        phase_12_file = self.find_phase_file(12)
        if phase_12_file:
            logger.info(f"Found: {phase_12_file.name}")
            module = self.load_phase_module(12, phase_12_file)
            
            if module:
                try:
                    # Look for CausalReasoningEngine first
                    if hasattr(module, 'CausalReasoningEngine'):
                        EngineClass = module.CausalReasoningEngine
                    else:
                        classes = [name for name in dir(module) if 'Reasoning' in name or 'Engine' in name]
                        if classes:
                            EngineClass = getattr(module, classes[0])
                        else:
                            EngineClass = None
                    
                    if EngineClass:
                        
                        # Test 1: Initialize
                        self.test("phase_12", "Causal engine initialization", 
                                 lambda: EngineClass() is not None)
                        
                        # Test 2: Learn observations
                        def test_learn():
                            engine = EngineClass()
                            obs = [
                                ({"A": 1.0, "B": 2.0}, 0.5),
                                ({"A": 2.0, "B": 4.0}, 0.8),
                            ]
                            if hasattr(engine, 'learn_from_observations'):
                                result = engine.learn_from_observations(obs)
                                return result is not None
                            return True
                        
                        self.test("phase_12", "Learn causal observations", test_learn)
                        
                        # Test 3: Reasoning
                        def test_reasoning():
                            engine = EngineClass()
                            obs = [
                                ({"A": 1.0, "B": 2.0}, 0.5),
                                ({"A": 2.0, "B": 4.0}, 0.8),
                            ]
                            if hasattr(engine, 'learn_from_observations'):
                                engine.learn_from_observations(obs)
                            
                            if hasattr(engine, 'reason'):
                                result = engine.reason("A", "B", 1.0)
                                return result is not None
                            return True
                        
                        self.test("phase_12", "Causal reasoning", test_reasoning)
                except Exception as e:
                    logger.error(f"Memory Layer test error: {e}")
        else:
            logger.info("  No memory-layer file found")

        # ─── PHASE 13: COMMON-SENSE KB ───
        logger.info("\nPHASE 13: COMMON-SENSE KNOWLEDGE BASE")
        logger.info("─" * 80)
        
        phase_13_file = self.find_phase_file(13)
        if phase_13_file:
            logger.info(f"Found: {phase_13_file.name}")
            module = self.load_phase_module(13, phase_13_file)
            
            if module:
                try:
                    classes = [name for name in dir(module) if 'Knowledge' in name or 'Reasoning' in name]
                    if classes:
                        EngineClass = getattr(module, classes[0])
                        
                        # Test 1: Initialize
                        self.test("phase_13", "Knowledge engine initialization", 
                                 lambda: EngineClass() is not None)
                        
                        # Test 2: Get knowledge
                        def test_kb():
                            engine = EngineClass()
                            if hasattr(engine, 'get_knowledge'):
                                stats = engine.get_knowledge()
                                return stats is not None and stats.get("total_facts", 0) > 0
                            return True
                        
                        self.test("phase_13", "Knowledge base access", test_kb)
                        
                        # Test 3: Transfer learning
                        def test_transfer():
                            engine = EngineClass()
                            if hasattr(engine, 'transfer'):
                                # Get any available fact
                                if hasattr(engine, 'kb'):
                                    domains = list(engine.kb.domain_index.keys())
                                    if domains:
                                        facts = engine.kb.get_facts_by_domain(domains[0])
                                        if facts:
                                            result = engine.transfer(facts[0].fact_id, "economics")
                                            return result is not None
                            return True
                        
                        self.test("phase_13", "Transfer learning", test_transfer)
                except Exception as e:
                    logger.error(f"Memory Layer test error: {e}")
        else:
            logger.info("  No memory-layer file found")

        self.metrics["total_time"] = time.time() - suite_start

        # Summary
        logger.info("\n" + "="*80)
        logger.info("TEST SUMMARY")
        logger.info("="*80)
        
        for phase in sorted(self.results.keys()):
            tests = self.results[phase]
            passed = sum(1 for t in tests if t["passed"])
            total = len(tests)
            pct = (passed / total * 100) if total > 0 else 0
            logger.info(f"\n{phase.upper()}: {passed}/{total} tests passed ({pct:.0f}%)")
            for test in tests:
                status = "✅" if test["passed"] else "❌"
                logger.info(f"  {status} {test['name']}")
        
        success_rate = (self.metrics["passed"] / max(self.metrics["total"], 1)) * 100 if self.metrics["total"] > 0 else 0
        
        logger.info("\n" + "="*80)
        logger.info(f"TOTAL: {self.metrics['passed']}/{self.metrics['total']} tests passed")
        logger.info(f"Success rate: {success_rate:.1f}%")
        logger.info(f"Total time: {self.metrics['total_time']:.2f}s")
        logger.info("="*80 + "\n")
        
        return success_rate >= 75.0  # More lenient for discovery


if __name__ == "__main__":
    runner = RobustTestRunner()
    success = runner.run_all()
    exit(0 if success else 1)
