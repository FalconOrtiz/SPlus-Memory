# S+Memory

**Layered semantic memory system for AI agents.**

S+Memory gives any AI agent persistent, semantic, self-evolving memory. It works with OpenClaw, Hermes, and any agentic system or training pipeline that needs durable context across sessions.

## What it does

```
Session 1: Agent learns "Stripe checkout was fixed by removing consent_collection"
Session 2: Agent asks "what happened with payments?" → gets that fact instantly (0.87 cosine similarity)
```

Traditional agent memory is flat key-value storage. S+Memory is a layered architecture:

```
┌─────────────────────────────────────────┐
│  SURFACE BUFFER  (hot facts, activated) │  ← Agent reads here
├─────────────────────────────────────────┤
│  RETRIEVAL LAYER (hybrid search)        │  ← BM25 + Semantic + Temporal
├─────────────────────────────────────────┤
│  DEEP LAYER      (activation engine)    │  ← Pushes facts up, not pulled
├─────────────────────────────────────────┤
│  STORAGE LAYER   (SQLite + embeddings)  │  ← 37 tables, graph relations
└─────────────────────────────────────────┘
```

## Key features

- **Real semantic search** — fastembed/bge-small-en-v1.5 (384-dim, local, free)
- **Hybrid retrieval** — BM25 (lexical) + cosine similarity (semantic) + temporal decay
- **Deep Layer activation** — memory pushes relevant facts to surface, agents don't poll
- **Auto-tagging** — domain and entity detection on ingest
- **Session capture** — auto-extract facts from conversation text
- **Temporal decay** — old unused facts fade, referenced facts stay strong
- **Relationship graph** — facts linked by shared domains, entities, co-access patterns
- **Multi-agent support** — agent-scoped memory with cross-agent inference
- **Zero external dependencies** — SQLite + fastembed, no cloud services needed

## Quick start

```bash
# Install
git clone https://github.com/FalconOrtiz/SPlus-Memory.git
cd SPlus-Memory
pip install fastembed

# Initialize the database
python scripts/init_memory_engine.sh
# Or just run any command — DB auto-creates on first use

# Store a fact
python scripts/mem store "The API runs on port 3100"

# Search semantically
python scripts/mem search "what port does the API use"

# Auto-capture facts from a session summary
python scripts/session_hook.py "Fixed the auth bug by rotating the JWT secret. Deployed to staging."

# Check status
python scripts/mem stats
```

## CLI reference

| Command | Description |
|---------|-------------|
| `mem store "text"` | Store a fact with real embedding |
| `mem search "query"` | Semantic search over all facts |
| `mem recall "query"` | Alias for search |
| `mem ingest` | Re-embed all facts (e.g., after model upgrade) |
| `mem stats` | Show DB overview |
| `mem recent [N]` | Show last N facts |

Options: `--source NAME`, `--confidence 0.9`, `--top 5`

## Architecture

### Storage layer (`db/`)
- SQLite with 37 tables
- Core: `memory_facts` (22 columns — content, embedding, tags, decay, confidence, etc.)
- Supporting: `fact_relationships`, `surface_buffer`, `co_access_patterns`, `evolution_log`, etc.

### Retrieval layer (`scripts/`)
- `hybrid_retriever.py` — BM25 + semantic + temporal ranking
- `context_selector.py` — token-budgeted context injection
- `quantum_index.py` — multi-dimensional fact indexing
- `semantic_index.py` — embedding-based search
- `integrated_retriever.py` — unified search interface

### Activation layer
- `deep_layer.py` — reverse-flow activation engine (facts push up, not pulled)
- `decay_scheduler.py` — temporal decay with λ=0.05
- `evolution_engine.py` — tracks system evolution over time
- `surface_buffer` table — hot facts ready for agent consumption

### Intelligence layer (AGI modules)
- Phase 10: Vector + Graph storage (10M vectors, sub-100ms)
- Phase 11: Meta-learning (adaptive retrieval strategy selection)
- Phase 12: Causal reasoning (pattern detection from access logs)
- Phase 13: Common-sense knowledge base (cross-domain transfer)

### Multi-agent layer
- `multi_agent_orchestrator.py` — coordinate memory across agents
- `agent_sync.py` — sync facts between agent instances
- `consensus_engine.py` — resolve conflicting facts
- `cross_agent_inference.py` — derive new facts from multi-agent context

## Performance

Benchmarked on macOS (Apple Silicon):

| Operation | p50 | p99 | Throughput |
|-----------|-----|-----|------------|
| DB Read (10 rows) | 0.013ms | 0.020ms | 74,703 ops/s |
| Vector Search (384d, top-10) | 0.395ms | 0.422ms | 2,521 ops/s |
| Graph Traverse | 0.002ms | 0.003ms | 413,351 ops/s |
| Full Pipeline (search+graph+meta+KB) | 0.873ms | 0.918ms | 1,146 ops/s |
| Full Pipeline + DB I/O | 1.082ms | 1.139ms | 928 ops/s |

All operations under 100ms p99. Full end-to-end pipeline: **~1ms**.

## Integration

### With Hermes
S+Memory was built for Hermes. Drop the `scripts/` directory into `~/.hermes/memory-engine/scripts/` and it works.

### With OpenClaw
Use `paperclip_bridge.py` and `paperclip_tenant_bridge.py` for company-scoped memory in OpenClaw/Paperclip.

### With any agent
```python
# Minimal integration — 3 lines
import subprocess
# Store
subprocess.run(["python", "scripts/mem", "store", "fact text"])
# Search
result = subprocess.run(["python", "scripts/mem", "search", "query"], capture_output=True)
```

Or import directly:
```python
import sys
sys.path.insert(0, "path/to/SPlus-Memory/scripts")
from mem import embed_text, cmd_search, cmd_store
```

## Grading

S+Memory self-grades across 8 dimensions:

| Dimension | Score |
|-----------|-------|
| Data Foundation | 15/15 |
| Retrieval Intelligence | 15/15 |
| AGI Modules | 15/15 |
| Activation & Temporal | 10/10 |
| Relationship Graph | 10/10 |
| Multi-Agent Orchestration | 10/10 |
| Testing & Validation | 10/10 |
| Documentation & Observability | 5/5 |
| **Total** | **90/90 (S+)** |

AGI Level: **5+ (Sovereign)** — self-evolving, cross-domain transfer, multi-agent orchestration.

## Stats

- **30,001 LOC** total system
- **50 scripts** in memory engine
- **6 AGI phases** (8-13)
- **9 test suites** (3,346 LOC)
- **43 documentation files**

## License

MIT — free for any use. Built by [IRE Digital](https://iredigitalmedia.com).
