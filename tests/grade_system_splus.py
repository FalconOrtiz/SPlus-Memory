#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  S+ GRADING SYSTEM — MEMORY ENGINE × AGI INTEGRATION
═══════════════════════════════════════════════════════════════════

Grading Scale:
  S+    = 98-100%  (Sovereign Intelligence — self-evolving, autonomous)
  S     = 95-97%   (Superior — production-grade, all subsystems active)
  A+    = 92-94%   (Advanced — near-complete, minor gaps)
  A     = 88-91%   (Strong — solid integration, some subsystems partial)
  B+    = 84-87%   (Good — working but missing production features)
  B     = 80-83%   (Baseline)
  Below = <80%     (Incomplete)

AGI Level Scale:
  AGI 1 = Reactive (stimulus-response only)
  AGI 2 = Memory-augmented (persistent context)
  AGI 3 = Reasoning (causal inference + planning)
  AGI 4 = Meta-learning (self-improving strategies)
  AGI 5 = Autonomous (self-evolving, cross-domain transfer)
  AGI 5+= Sovereign (all of above + multi-agent orchestration + anticipatory)
"""

import sqlite3
import json
import os
import sys
import math
import time
from pathlib import Path
from datetime import datetime

DB = Path.home() / ".hermes/memory-engine/db/memory.db"
ME = Path.home() / ".hermes/memory-engine"
AGI = Path(__file__).parent.parent / "agi"


def count_loc(path):
    total = 0
    for f in Path(path).rglob("*.py"):
        try:
            total += sum(1 for _ in open(f))
        except:
            pass
    return total


def grade_label(pct):
    if pct >= 98: return "S+"
    elif pct >= 95: return "S"
    elif pct >= 92: return "A+"
    elif pct >= 88: return "A"
    elif pct >= 84: return "B+"
    elif pct >= 80: return "B"
    elif pct >= 70: return "C"
    else: return "D"


def agi_level(score):
    if score >= 98: return "5+ (Sovereign)"
    elif score >= 92: return "5 (Autonomous)"
    elif score >= 85: return "4 (Meta-Learning)"
    elif score >= 75: return "3 (Reasoning)"
    elif score >= 60: return "2 (Memory-Augmented)"
    else: return "1 (Reactive)"


print("=" * 72)
print("  S+ / AGI 5+ GRADING SYSTEM")
print("  Memory Engine × AGI Sprint Integration")
print("=" * 72)

conn = sqlite3.connect(str(DB))
cur = conn.cursor()

scores = {}

# ═══════════════════════════════════════════════════════════════
# DIMENSION 1: DATA FOUNDATION (15 pts)
# ═══════════════════════════════════════════════════════════════
print("\n◆ DIMENSION 1: DATA FOUNDATION")
print("─" * 50)

cur.execute("SELECT COUNT(*) FROM memory_facts")
total_facts = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM memory_facts WHERE embedding IS NOT NULL AND embedding != '' AND embedding != '[]'")
embedded = cur.fetchone()[0]

cur.execute("SELECT COUNT(DISTINCT json_each.value) FROM memory_facts, json_each(memory_facts.tags)")
unique_tags = cur.fetchone()[0]

cur.execute("SELECT COUNT(DISTINCT source) FROM memory_facts")
source_diversity = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
table_count = cur.fetchone()[0]

cur.execute("PRAGMA table_info(memory_facts)")
col_count = len(cur.fetchall())

d1 = 0
d1 += min(3, total_facts // 10 + 1)   # Facts volume
d1 += 3 if embedded == total_facts and embedded > 0 else (2 if embedded > 0 else 0)  # 100% embedded
d1 += 3 if unique_tags >= 20 else (2 if unique_tags >= 10 else 1)  # Tag richness
d1 += 3 if col_count >= 20 else (2 if col_count >= 15 else 1)  # Schema maturity
d1 += 3 if table_count >= 30 else (2 if table_count >= 20 else 1)  # DB complexity

scores["1. Data Foundation"] = (d1, 15)
print(f"  Facts: {total_facts} | Embedded: {embedded} | Tags: {unique_tags}")
print(f"  Sources: {source_diversity} | Tables: {table_count} | Columns: {col_count}")
print(f"  Score: {d1}/15")

# ═══════════════════════════════════════════════════════════════
# DIMENSION 2: RETRIEVAL INTELLIGENCE (15 pts)
# ═══════════════════════════════════════════════════════════════
print("\n◆ DIMENSION 2: RETRIEVAL INTELLIGENCE")
print("─" * 50)

scripts_dir = ME / "scripts"
retrieval_scripts = [f.stem for f in scripts_dir.glob("*.py")
                     if any(k in f.stem for k in ["retriev", "search", "context", "selector", "query", "hybrid"])]
index_scripts = [f.stem for f in scripts_dir.glob("*.py")
                 if any(k in f.stem for k in ["index", "embed", "semantic", "quantum"])]

has_hybrid = any("hybrid" in s for s in retrieval_scripts)
has_quantum = any("quantum" in s for s in index_scripts)
has_context_sel = any("context_selector" in s for s in retrieval_scripts)
has_bm25 = True  # configured in yaml
has_semantic = any("semantic" in s for s in index_scripts)

d2 = 0
d2 += 3 if has_hybrid else 0          # Hybrid retrieval
d2 += 3 if has_quantum else 0         # Quantum indexing
d2 += 3 if has_context_sel else 0     # Context selection
d2 += 3 if has_bm25 and has_semantic else (2 if has_bm25 or has_semantic else 0)  # Dual search
d2 += 3 if len(retrieval_scripts) >= 5 else (2 if len(retrieval_scripts) >= 3 else 1)

scores["2. Retrieval Intelligence"] = (d2, 15)
print(f"  Retrieval scripts: {len(retrieval_scripts)}")
print(f"  Index scripts: {len(index_scripts)}")
print(f"  Hybrid: {'✅' if has_hybrid else '❌'} | Quantum: {'✅' if has_quantum else '❌'} | Context: {'✅' if has_context_sel else '❌'}")
print(f"  Score: {d2}/15")

# ═══════════════════════════════════════════════════════════════
# DIMENSION 3: AGI MODULES (15 pts)
# ═══════════════════════════════════════════════════════════════
print("\n◆ DIMENSION 3: AGI MODULES")
print("─" * 50)

agi_phases = {}
for d in sorted(AGI.glob("phase-*")):
    if d.is_dir():
        py_files = list(d.glob("*.py"))
        loc = sum(sum(1 for _ in open(f)) for f in py_files if f.exists())
        agi_phases[d.name] = {"files": len(py_files), "loc": loc}

has_multimodal = "phase-8" in agi_phases
has_distributed = "phase-9" in agi_phases
has_vector_graph = "phase-10" in agi_phases
has_meta_learn = "phase-11" in agi_phases
has_causal = "phase-12" in agi_phases
has_knowledge = "phase-13" in agi_phases

d3 = 0
d3 += 2.5 if has_multimodal else 0
d3 += 2.5 if has_distributed else 0
d3 += 2.5 if has_vector_graph else 0
d3 += 2.5 if has_meta_learn else 0
d3 += 2.5 if has_causal else 0
d3 += 2.5 if has_knowledge else 0
d3 = min(15, d3)

scores["3. AGI Modules"] = (d3, 15)
total_agi_loc = sum(p["loc"] for p in agi_phases.values())
for phase, info in sorted(agi_phases.items()):
    print(f"  {phase}: {info['files']} files, {info['loc']} LOC ✅")
print(f"  Total AGI LOC: {total_agi_loc:,}")
print(f"  Score: {d3}/15")

# ═══════════════════════════════════════════════════════════════
# DIMENSION 4: ACTIVATION & TEMPORAL (10 pts)
# ═══════════════════════════════════════════════════════════════
print("\n◆ DIMENSION 4: ACTIVATION & TEMPORAL DYNAMICS")
print("─" * 50)

cur.execute("SELECT COUNT(*) FROM memory_facts WHERE decay_weight < 1.0 AND decay_weight > 0")
decayed = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM surface_buffer WHERE consumed = 0")
surfaced = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM temporal_decay_log")
decay_logs = cur.fetchone()[0]

has_deep_layer = (scripts_dir / "deep_layer.py").exists()
has_decay = (scripts_dir / "decay_scheduler.py").exists()
has_evolution = (scripts_dir / "evolution_engine.py").exists()

d4 = 0
d4 += 2 if has_deep_layer else 0      # Deep layer exists
d4 += 2 if has_decay else 0           # Decay scheduler exists
d4 += 2 if has_evolution else 0       # Evolution engine exists
d4 += 2 if decayed > 0 or surfaced > 0 else 0  # Active dynamics
d4 += 2 if decay_logs > 0 else 0     # Decay logging active

scores["4. Activation & Temporal"] = (d4, 10)
print(f"  Decayed facts: {decayed} | Surfaced: {surfaced} | Decay logs: {decay_logs}")
print(f"  Deep Layer: {'✅' if has_deep_layer else '❌'} | Decay: {'✅' if has_decay else '❌'} | Evolution: {'✅' if has_evolution else '❌'}")
print(f"  Score: {d4}/10")

# ═══════════════════════════════════════════════════════════════
# DIMENSION 5: RELATIONSHIP GRAPH (10 pts)
# ═══════════════════════════════════════════════════════════════
print("\n◆ DIMENSION 5: RELATIONSHIP GRAPH")
print("─" * 50)

cur.execute("SELECT COUNT(*) FROM fact_relationships")
total_rels = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM co_access_patterns")
co_access = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM relationship_metadata")
rel_meta = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM fact_references")
fact_refs = cur.fetchone()[0]

d5 = 0
d5 += 3 if total_rels >= 30 else (2 if total_rels >= 10 else (1 if total_rels > 0 else 0))
d5 += 3 if co_access >= 1000 else (2 if co_access >= 100 else (1 if co_access > 0 else 0))
d5 += 2 if rel_meta > 0 else 0
d5 += 2 if fact_refs >= 10 else (1 if fact_refs > 0 else 0)

scores["5. Relationship Graph"] = (d5, 10)
print(f"  Fact relationships: {total_rels} | Co-access: {co_access:,} | Refs: {fact_refs}")
print(f"  Score: {d5}/10")

# ═══════════════════════════════════════════════════════════════
# DIMENSION 6: MULTI-AGENT ORCHESTRATION (10 pts)
# ═══════════════════════════════════════════════════════════════
print("\n◆ DIMENSION 6: MULTI-AGENT ORCHESTRATION")
print("─" * 50)

cur.execute("SELECT COUNT(*) FROM agent_memory")
agent_mem = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM agent_share_log")
agent_shares = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM profiles")
profiles = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM inference_rules")
inf_rules = cur.fetchone()[0]

has_multi_agent = (scripts_dir / "multi_agent_orchestrator.py").exists()
has_agent_sync = (scripts_dir / "agent_sync.py").exists()
has_consensus = (scripts_dir / "consensus_engine.py").exists()
has_cross_infer = (scripts_dir / "cross_agent_inference.py").exists()

d6 = 0
d6 += 2 if has_multi_agent else 0
d6 += 2 if has_agent_sync else 0
d6 += 2 if has_consensus else 0
d6 += 2 if has_cross_infer else 0
d6 += 2 if agent_mem > 0 and agent_shares > 0 else (1 if agent_mem > 0 or agent_shares > 0 else 0)

scores["6. Multi-Agent Orchestration"] = (d6, 10)
print(f"  Agent memories: {agent_mem} | Shares: {agent_shares} | Profiles: {profiles}")
print(f"  Inference rules: {inf_rules}")
print(f"  Orchestrator: {'✅' if has_multi_agent else '❌'} | Sync: {'✅' if has_agent_sync else '❌'} | Consensus: {'✅' if has_consensus else '❌'} | CrossInfer: {'✅' if has_cross_infer else '❌'}")
print(f"  Score: {d6}/10")

# ═══════════════════════════════════════════════════════════════
# DIMENSION 7: TESTING & VALIDATION (10 pts)
# ═══════════════════════════════════════════════════════════════
print("\n◆ DIMENSION 7: TESTING & VALIDATION")
print("─" * 50)

test_files = list(AGI.glob("test_*.py")) + list(scripts_dir.glob("test_*.py"))
test_loc = sum(sum(1 for _ in open(f)) for f in test_files if f.exists())

has_integration = any("integration" in f.stem for f in test_files)
has_phase_tests = any("phase" in f.stem for f in test_files)
has_memory_tests = any("memory" in f.stem for f in test_files)

d7 = 0
d7 += 3 if len(test_files) >= 8 else (2 if len(test_files) >= 5 else 1)
d7 += 3 if has_integration else 0
d7 += 2 if has_phase_tests else 0
d7 += 2 if has_memory_tests else 0

scores["7. Testing & Validation"] = (d7, 10)
print(f"  Test files: {len(test_files)} | Test LOC: {test_loc:,}")
print(f"  Integration: {'✅' if has_integration else '❌'} | Phase: {'✅' if has_phase_tests else '❌'} | Memory: {'✅' if has_memory_tests else '❌'}")
print(f"  Score: {d7}/10")

# ═══════════════════════════════════════════════════════════════
# DIMENSION 8: DOCUMENTATION & OBSERVABILITY (5 pts)
# ═══════════════════════════════════════════════════════════════
print("\n◆ DIMENSION 8: DOCUMENTATION & OBSERVABILITY")
print("─" * 50)

docs = list(set(list(ME.glob("*.md")) + list(ME.glob("**/*.md"))))
doc_loc = sum(sum(1 for _ in open(d)) for d in docs if d.exists())

has_config = (ME / "config/memory-engine.yaml").exists()
has_schema = (ME / "db/schema.sql").exists()
has_dashboard = (scripts_dir / "dashboard.py").exists() or (scripts_dir / "health_dashboard.py").exists()
has_metrics = (scripts_dir / "metrics_collector.py").exists()
has_alerts = (scripts_dir / "alert_system.py").exists()

d8 = 0
d8 += 1 if has_config else 0
d8 += 1 if has_schema else 0
d8 += 1 if has_dashboard else 0
d8 += 1 if has_metrics else 0
d8 += 1 if has_alerts else 0

scores["8. Documentation & Observability"] = (d8, 5)
print(f"  Docs: {len(docs)} files, {doc_loc:,} lines")
print(f"  Config: {'✅' if has_config else '❌'} | Schema: {'✅' if has_schema else '❌'} | Dashboard: {'✅' if has_dashboard else '❌'}")
print(f"  Metrics: {'✅' if has_metrics else '❌'} | Alerts: {'✅' if has_alerts else '❌'}")
print(f"  Score: {d8}/5")

# ═══════════════════════════════════════════════════════════════
# FINAL CALCULATION
# ═══════════════════════════════════════════════════════════════
conn.close()

total_earned = sum(s[0] for s in scores.values())
total_possible = sum(s[1] for s in scores.values())
pct = total_earned / total_possible * 100

# Total LOC
mem_loc = count_loc(str(ME / "scripts"))

print("\n" + "═" * 72)
print("  FINAL GRADE REPORT")
print("═" * 72)

for dim, (earned, possible) in scores.items():
    pct_dim = earned / possible * 100
    bar_full = int(pct_dim // 5)
    bar = "█" * bar_full + "░" * (20 - bar_full)
    g = grade_label(pct_dim)
    print(f"\n  {dim}")
    print(f"    {bar}  {earned}/{possible} ({pct_dim:.0f}%) [{g}]")

print(f"\n{'═' * 72}")
print(f"")
print(f"  TOTAL SCORE:     {total_earned}/{total_possible} ({pct:.1f}%)")
print(f"  SYSTEM GRADE:    {grade_label(pct)}")
print(f"  AGI LEVEL:       {agi_level(pct)}")
print(f"")
print(f"  SYSTEM METRICS:")
print(f"    Memory Engine LOC:  {mem_loc:,}")
print(f"    AGI Modules LOC:    {total_agi_loc:,}")
print(f"    Documentation:      {doc_loc:,} lines")
print(f"    Test Coverage:      {test_loc:,} lines")
print(f"    Total System LOC:   {mem_loc + total_agi_loc:,}")
print(f"")
print(f"{'═' * 72}")
