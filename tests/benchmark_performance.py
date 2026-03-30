#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  PERFORMANCE BENCHMARK — P50 / P99 / THROUGHPUT / RESOURCES
  Memory Engine × AGI Sprint
═══════════════════════════════════════════════════════════════════

Measures:
  - Latency percentiles: p50, p90, p95, p99, p999
  - Throughput: ops/sec per subsystem
  - Memory usage: RSS delta per operation
  - CPU time: user + system per operation
  - DB I/O: reads/writes per second
"""

import sys
import os
import time
import json
import sqlite3
import math
import resource
import statistics
import tracemalloc
import numpy as np
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

AGI = Path(__file__).parent.parent / "agi"
ME = Path.home() / ".hermes/memory-engine"
DB = ME / "db/memory.db"

sys.path.insert(0, str(AGI / "phase-10"))
sys.path.insert(0, str(AGI / "phase-11"))
sys.path.insert(0, str(AGI / "phase-12"))
sys.path.insert(0, str(AGI / "phase-13"))
sys.path.insert(0, str(ME / "scripts"))

# Suppress noisy logs
import logging
logging.disable(logging.INFO)


# ── Benchmark Harness ──────────────────────────────────────────

@dataclass
class BenchResult:
    name: str
    iterations: int
    latencies_ms: List[float]
    mem_start_kb: float = 0
    mem_end_kb: float = 0
    cpu_user_ms: float = 0
    cpu_sys_ms: float = 0

    @property
    def p50(self): return self._pct(50)
    @property
    def p90(self): return self._pct(90)
    @property
    def p95(self): return self._pct(95)
    @property
    def p99(self): return self._pct(99)
    @property
    def p999(self): return self._pct(99.9)
    @property
    def mean(self): return statistics.mean(self.latencies_ms) if self.latencies_ms else 0
    @property
    def stdev(self): return statistics.stdev(self.latencies_ms) if len(self.latencies_ms) > 1 else 0
    @property
    def min_ms(self): return min(self.latencies_ms) if self.latencies_ms else 0
    @property
    def max_ms(self): return max(self.latencies_ms) if self.latencies_ms else 0
    @property
    def throughput(self):
        total_s = sum(self.latencies_ms) / 1000.0
        return self.iterations / total_s if total_s > 0 else 0
    @property
    def mem_delta_kb(self): return self.mem_end_kb - self.mem_start_kb

    def _pct(self, p):
        if not self.latencies_ms:
            return 0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * p / 100)
        idx = min(idx, len(sorted_l) - 1)
        return sorted_l[idx]


def bench(name, fn, iterations=100, warmup=5):
    """Run a benchmark with warmup, memory tracking, and CPU timing."""
    # Warmup
    for _ in range(warmup):
        try:
            fn()
        except:
            pass

    tracemalloc.start()
    mem_start = tracemalloc.get_traced_memory()[0] / 1024
    ru_start = resource.getrusage(resource.RUSAGE_SELF)

    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

    ru_end = resource.getrusage(resource.RUSAGE_SELF)
    mem_end = tracemalloc.get_traced_memory()[0] / 1024
    tracemalloc.stop()

    cpu_user = (ru_end.ru_utime - ru_start.ru_utime) * 1000
    cpu_sys = (ru_end.ru_stime - ru_start.ru_stime) * 1000

    return BenchResult(
        name=name,
        iterations=iterations,
        latencies_ms=latencies,
        mem_start_kb=mem_start,
        mem_end_kb=mem_end,
        cpu_user_ms=cpu_user,
        cpu_sys_ms=cpu_sys
    )


def print_result(r: BenchResult):
    print(f"\n  ◆ {r.name} ({r.iterations} iterations)")
    print(f"  ┌─────────────────────────────────────────────────┐")
    print(f"  │  p50:  {r.p50:8.3f} ms   p90:  {r.p90:8.3f} ms       │")
    print(f"  │  p95:  {r.p95:8.3f} ms   p99:  {r.p99:8.3f} ms       │")
    print(f"  │  p999: {r.p999:8.3f} ms   mean: {r.mean:8.3f} ms       │")
    print(f"  │  min:  {r.min_ms:8.3f} ms   max:  {r.max_ms:8.3f} ms       │")
    print(f"  │  stdev: {r.stdev:7.3f} ms                           │")
    print(f"  │  throughput: {r.throughput:,.0f} ops/sec                  │")
    print(f"  │  mem delta:  {r.mem_delta_kb:+.1f} KB                     │")
    print(f"  │  cpu (user): {r.cpu_user_ms:.1f} ms  (sys): {r.cpu_sys_ms:.1f} ms     │")
    print(f"  └─────────────────────────────────────────────────┘")

    # Status
    if r.p99 < 10:
        status = "✅ EXCELLENT"
    elif r.p99 < 50:
        status = "✅ GOOD"
    elif r.p99 < 100:
        status = "⚠️  ACCEPTABLE"
    else:
        status = "❌ SLOW"
    print(f"  Status: {status} (p99 < {'10ms' if r.p99 < 10 else '50ms' if r.p99 < 50 else '100ms' if r.p99 < 100 else 'OVER'})")


# ═══════════════════════════════════════════════════════════════
# BENCHMARKS
# ═══════════════════════════════════════════════════════════════

print("=" * 72)
print("  PERFORMANCE BENCHMARK — P50/P99/THROUGHPUT/RESOURCES")
print("  Memory Engine × AGI Sprint")
print("=" * 72)

results = []

# ── 1. DB READ: memory_facts SELECT ───────────────────────────
print("\n" + "─" * 72)
print("  SECTION 1: DATABASE I/O")
print("─" * 72)

conn = sqlite3.connect(str(DB))

def bench_db_read():
    cur = conn.cursor()
    cur.execute("SELECT id, content, confidence, decay_weight, tags FROM memory_facts LIMIT 10")
    cur.fetchall()

r = bench("DB Read: SELECT memory_facts (10 rows)", bench_db_read, iterations=500)
results.append(r)
print_result(r)

def bench_db_search():
    cur = conn.cursor()
    cur.execute("SELECT id, content FROM memory_facts WHERE content LIKE '%memory%' OR content LIKE '%agent%'")
    cur.fetchall()

r = bench("DB Search: LIKE query", bench_db_search, iterations=500)
results.append(r)
print_result(r)

def bench_db_join():
    cur = conn.cursor()
    cur.execute("""
        SELECT f.id, f.content, r.relationship_type, r.confidence
        FROM memory_facts f
        LEFT JOIN fact_relationships r ON f.id = r.source_fact_id
        LIMIT 50
    """)
    cur.fetchall()

r = bench("DB Join: facts + relationships", bench_db_join, iterations=500)
results.append(r)
print_result(r)

def bench_db_write():
    cur = conn.cursor()
    cur.execute("UPDATE memory_facts SET referenced_count = referenced_count WHERE id = 1")

r = bench("DB Write: UPDATE single row", bench_db_write, iterations=500)
results.append(r)
print_result(r)

conn.close()

# ── 2. VECTOR OPERATIONS: Phase 10 ───────────────────────────
print("\n" + "─" * 72)
print("  SECTION 2: VECTOR + GRAPH OPERATIONS (Phase 10)")
print("─" * 72)

from vector_graph_scale import VectorStore, GraphStore, IndexType, RelationType

# Pre-build store with data
vstore = VectorStore(dimension=384, index_type=IndexType.HNSW)
test_embeddings = {}
for i in range(100):
    emb = np.random.randn(384).astype(np.float32)
    emb /= np.linalg.norm(emb)
    vstore.add_vector(f"bench_{i}", emb, metadata={"idx": i})
    test_embeddings[i] = emb
vstore.build_index()

query_emb = np.random.randn(384).astype(np.float32)
query_emb /= np.linalg.norm(query_emb)

def bench_vector_insert():
    emb = np.random.randn(384).astype(np.float32)
    emb /= np.linalg.norm(emb)
    vid = f"tmp_{time.perf_counter_ns()}"
    vstore.add_vector(vid, emb)

r = bench("Vector Insert (384-dim)", bench_vector_insert, iterations=500)
results.append(r)
print_result(r)

def bench_vector_search():
    q = np.random.randn(384).astype(np.float32)
    q /= np.linalg.norm(q)
    vstore.search_vectors(q, top_k=10, min_similarity=0.0)

r = bench("Vector Search top-10 (384-dim, 100 vectors)", bench_vector_search, iterations=500)
results.append(r)
print_result(r)

# Graph
graph = GraphStore()
for i in range(50):
    graph.add_relationship(f"n_{i}", f"n_{(i+1)%50}", RelationType.SEMANTIC, weight=0.8)
    graph.add_relationship(f"n_{i}", f"n_{(i+7)%50}", RelationType.CAUSAL, weight=0.6)

def bench_graph_traverse():
    graph.get_neighbors(f"n_{np.random.randint(50)}")

r = bench("Graph Traverse: get_neighbors", bench_graph_traverse, iterations=500)
results.append(r)
print_result(r)

def bench_graph_path():
    graph.find_paths(f"n_0", f"n_25", max_depth=4)

r = bench("Graph Pathfinding: find_paths (depth=4)", bench_graph_path, iterations=200)
results.append(r)
print_result(r)

# ── 3. META-LEARNING: Phase 11 ───────────────────────────────
print("\n" + "─" * 72)
print("  SECTION 3: META-LEARNING (Phase 11)")
print("─" * 72)

from meta_learning_engine import MetaLearningEngine

meta = MetaLearningEngine()
X_train = [[np.random.random() for _ in range(4)] for _ in range(50)]
y_train = [np.random.randint(3) for _ in range(50)]
meta.fit(X_train, y_train)

def bench_meta_predict():
    x = [[np.random.random() for _ in range(4)]]
    meta.predict(x)

r = bench("Meta-Learning: predict (single)", bench_meta_predict, iterations=500)
results.append(r)
print_result(r)

def bench_meta_fit():
    X = [[np.random.random() for _ in range(4)] for _ in range(20)]
    y = [np.random.randint(3) for _ in range(20)]
    m = MetaLearningEngine()
    m.fit(X, y)

r = bench("Meta-Learning: fit (20 samples)", bench_meta_fit, iterations=100)
results.append(r)
print_result(r)

# ── 4. CAUSAL REASONING: Phase 12 ────────────────────────────
print("\n" + "─" * 72)
print("  SECTION 4: CAUSAL REASONING (Phase 12)")
print("─" * 72)

from causal_reasoning_engine import CausalReasoningEngine, CausalGraphBuilder

def bench_causal_observe():
    builder = CausalGraphBuilder()
    for i in range(10):
        builder.add_observation(f"obs_{i}", {
            "a": np.random.random(),
            "b": np.random.random(),
            "c": np.random.random()
        }, outcome=np.random.random())

r = bench("Causal: add 10 observations", bench_causal_observe, iterations=200)
results.append(r)
print_result(r)

causal_engine = CausalReasoningEngine()
for i in range(50):
    causal_engine.graph_builder.add_observation(f"train_{i}", {
        "x": np.random.random(),
        "y": np.random.random(),
    }, outcome=np.random.random())

def bench_causal_reason():
    causal_engine.graph_builder.discover_edges(method='correlation')

r = bench("Causal: discover edges (50 obs)", bench_causal_reason, iterations=200)
results.append(r)
print_result(r)

# ── 5. KNOWLEDGE BASE: Phase 13 ──────────────────────────────
print("\n" + "─" * 72)
print("  SECTION 5: KNOWLEDGE BASE (Phase 13)")
print("─" * 72)

from common_sense_kb import CommonSenseKnowledgeBase, KnowledgeDomain

def bench_kb_init():
    CommonSenseKnowledgeBase()

r = bench("KB: initialization (17 core facts)", bench_kb_init, iterations=200)
results.append(r)
print_result(r)

kb = CommonSenseKnowledgeBase()

def bench_kb_add():
    fid = f"bench_{time.perf_counter_ns()}"
    kb.add_fact(fid, "Test statement about something", KnowledgeDomain.GENERAL, confidence=0.9)

r = bench("KB: add_fact", bench_kb_add, iterations=500)
results.append(r)
print_result(r)

def bench_kb_search():
    kb.search_facts("knowledge reasoning transfer")

r = bench("KB: search_facts", bench_kb_search, iterations=500)
results.append(r)
print_result(r)

# ── 6. FULL PIPELINE ─────────────────────────────────────────
print("\n" + "─" * 72)
print("  SECTION 6: FULL PIPELINE (end-to-end)")
print("─" * 72)

def bench_full_pipeline():
    # 1. Vector search
    q = np.random.randn(384).astype(np.float32)
    q /= np.linalg.norm(q)
    vstore.search_vectors(q, top_k=5, min_similarity=0.0)

    # 2. Graph traverse
    graph.get_neighbors("n_0")

    # 3. Meta-learning predict
    meta.predict([[0.5, 0.3, 0.8, 0.2]])

    # 4. KB lookup
    kb.search_facts("reasoning")

r = bench("Full Pipeline: search → graph → meta → KB", bench_full_pipeline, iterations=500)
results.append(r)
print_result(r)

def bench_full_pipeline_with_db():
    # 1. DB read
    c = sqlite3.connect(str(DB))
    cur = c.cursor()
    cur.execute("SELECT content, confidence FROM memory_facts LIMIT 5")
    cur.fetchall()
    c.close()

    # 2. Vector search
    q = np.random.randn(384).astype(np.float32)
    q /= np.linalg.norm(q)
    vstore.search_vectors(q, top_k=5, min_similarity=0.0)

    # 3. Graph + Meta + KB
    graph.get_neighbors("n_0")
    meta.predict([[0.5, 0.3, 0.8, 0.2]])
    kb.search_facts("knowledge")

r = bench("Full Pipeline + DB I/O", bench_full_pipeline_with_db, iterations=200)
results.append(r)
print_result(r)


# ═══════════════════════════════════════════════════════════════
# SUMMARY REPORT
# ═══════════════════════════════════════════════════════════════

print("\n" + "═" * 72)
print("  PERFORMANCE SUMMARY")
print("═" * 72)

print(f"\n  {'Benchmark':<45} {'p50':>8} {'p99':>8} {'ops/s':>10} {'mem':>8}")
print(f"  {'─' * 45} {'─' * 8} {'─' * 8} {'─' * 10} {'─' * 8}")

for r in results:
    mem_str = f"{r.mem_delta_kb:+.0f}KB"
    print(f"  {r.name:<45} {r.p50:7.3f}m {r.p99:7.3f}m {r.throughput:>9,.0f} {mem_str:>8}")

# Overall stats
all_p50 = [r.p50 for r in results]
all_p99 = [r.p99 for r in results]
all_throughput = [r.throughput for r in results]

print(f"\n  {'─' * 72}")
print(f"  Aggregate p50:  {statistics.mean(all_p50):.3f} ms (avg across all benchmarks)")
print(f"  Aggregate p99:  {statistics.mean(all_p99):.3f} ms (avg across all benchmarks)")
print(f"  Worst p99:      {max(all_p99):.3f} ms ({results[all_p99.index(max(all_p99))].name})")
print(f"  Best throughput: {max(all_throughput):,.0f} ops/s ({results[all_throughput.index(max(all_throughput))].name})")
print(f"  Total CPU:      {sum(r.cpu_user_ms + r.cpu_sys_ms for r in results):.0f} ms")

# SLA check
print(f"\n  SLA COMPLIANCE:")
sla_pass = 0
sla_total = len(results)
for r in results:
    if r.p99 < 100:
        sla_pass += 1
        icon = "✅"
    else:
        icon = "❌"
    print(f"    {icon} {r.name}: p99={r.p99:.3f}ms {'< 100ms' if r.p99 < 100 else '>= 100ms'}")

pct = sla_pass / sla_total * 100
print(f"\n  SLA: {sla_pass}/{sla_total} ({pct:.0f}%) under 100ms p99")

if pct == 100:
    print(f"  VERDICT: ✅ ALL BENCHMARKS WITHIN SLA")
elif pct >= 80:
    print(f"  VERDICT: ⚠️  MOSTLY WITHIN SLA")
else:
    print(f"  VERDICT: ❌ SLA VIOLATIONS DETECTED")

print(f"\n{'═' * 72}")
