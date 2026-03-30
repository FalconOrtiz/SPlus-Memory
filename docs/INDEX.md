# Hermes Memory Engine - Complete File Index

**Phase 1-2: Semantic Retrieval + Temporal Weighting**  
Created: 2026-03-23  
Status: Production Ready ✅

---

## Quick Navigation

### Start Here
- **README.md** - Full user guide with examples
- **PHASE_1_2_SUMMARY.txt** - Executive summary
- **STATUS.md** - Deployment status & checklist

### Implementation
- **IMPLEMENTATION.md** - Detailed 7-phase project plan
- **scripts/memory_engine.py** - Main engine (init, search, decay)
- **scripts/hybrid_retriever.py** - Ranking algorithm
- **db/schema.sql** - Database schema (8 tables)

### Configuration
- **config/memory-engine.yaml** - All settings (embeddings, decay, retrieval)

### Setup & Testing
- **scripts/init_memory_engine.sh** - One-command initialization
- **scripts/test_memory_engine.py** - 25+ unit/integration tests

### This File
- **INDEX.md** - You are here

---

## File Descriptions

### Documentation Files

#### README.md (9.2 KB)
**Purpose**: User guide and reference manual  
**Contains**:
- Architecture overview
- Quick start (5 steps)
- Configuration reference
- Scoring breakdown (BM25, semantic, temporal)
- Database schema explanation
- Phase 2+ preview
- Performance notes
- Troubleshooting

**Read if**: You're setting up for the first time or need reference

---

#### IMPLEMENTATION.md (10.5 KB)
**Purpose**: Detailed implementation plan for all phases  
**Contains**:
- Phase 1-2 tasks and rollout
- Week-by-week timeline
- Testing strategy
- Performance benchmarks
- Deployment checklist
- Rollback procedures
- Next phases preview (3-7)

**Read if**: You're implementing or planning the deployment

---

#### STATUS.md (7.5 KB)
**Purpose**: Current deployment status and technical details  
**Contains**:
- What was built (summary)
- Technical details (scoring, decay model)
- Files created (with sizes)
- How to deploy (5 steps)
- Integration points
- Testing checklist
- Known limitations
- Success metrics

**Read if**: You want to know what's ready and what's not

---

#### PHASE_1_2_SUMMARY.txt (17.0 KB)
**Purpose**: Executive overview with all key information  
**Contains**:
- What was built (components)
- Hybrid ranking algorithm (with example)
- Temporal decay model (with table)
- Database schema (8 tables)
- Quick start (6 commands)
- Integration points (3 ways)
- Expected improvements
- Performance benchmarks
- Next phases roadmap
- Deployment checklist
- Critical files listing

**Read if**: You want complete overview without going to multiple files

---

#### INDEX.md (This File)
**Purpose**: Navigation guide for all files

---

### Code Files

#### scripts/memory_engine.py (17.3 KB)
**Purpose**: Main memory engine with CLI interface  
**Key Classes**:
- `MemoryEngine`: Main engine class
  - `connect()`: Database connection
  - `init_db()`: Schema initialization
  - `add_fact()`: Insert with deduplication
  - `bm25_score()`: Lexical scoring
  - `calculate_decay_weight()`: Temporal decay
  - `get_freshness_tier()`: Tier classification
  - `hybrid_search()`: Top-K hybrid search
  - `update_decay_weights()`: Recalculate all weights
  - `get_status()`: System status report

**Key Models**:
- `MemoryFact`: Dataclass for facts
- `SearchResult`: Ranked search result

**CLI Commands**:
```bash
--init              Initialize database
--query TEXT        Hybrid search (top-5)
--status            Show engine status
--decay             Recalculate temporal decay
--add-fact TEXT     Add single fact
--source TEXT       Source for fact (default: manual)
```

**Use When**: You need to interact with the memory engine directly

---

#### scripts/hybrid_retriever.py (11.4 KB)
**Purpose**: Retrieval system with hybrid ranking  
**Key Classes**:
- `RankedResult`: Result with detailed scoring
  - `bm25_score`, `semantic_score`, `temporal_score`, `reference_score`
  - `combined_score` (calculated automatically)
  - `to_dict()`: JSON serialization

- `HybridRetriever`: Retrieval engine
  - `search()`: Hybrid search (BM25 + semantic + temporal)
  - `search_with_context()`: With neighboring facts
  - `search_json()`: JSON output
  - `_bm25_score()`: Lexical scoring
  - `_calculate_temporal_score()`: Freshness weighting
  - `_calculate_reference_score()`: Usage tracking

**Use When**: You need to understand the ranking algorithm or extend it

---

#### scripts/init_memory_engine.sh (3.2 KB)
**Purpose**: Automated setup and initialization  
**Steps**:
1. Check Python version
2. Install dependencies (PyYAML, sqlite3)
3. Create directories
4. Initialize database
5. Verify installation

**Use When**: First-time setup or resetting the system

---

#### scripts/test_memory_engine.py (14.8 KB)
**Purpose**: Comprehensive test suite (25+ tests)  
**Test Categories**:
- BM25 Scoring Tests (4 tests)
- Temporal Decay Tests (5 tests)
- Freshness Tier Tests (4 tests)
- Database Operations Tests (4 tests)
- Integration Tests (3 tests)
- Status Tests (2 tests)

**Run**:
```bash
python3 scripts/test_memory_engine.py
```

**Use When**: You want to validate the system before deployment

---

### Database Files

#### db/schema.sql (5.8 KB)
**Purpose**: SQLite database schema definition  
**Tables**:
1. `memory_facts` - Core facts with embeddings
2. `temporal_decay_log` - Historical decay tracking
3. `fact_references` - When facts are used
4. `fact_relationships` - Semantic connections
5. `session_context` - Session summaries
6. `audit_log` - Modification history
7. `contradictions` - Conflict detection
8. `engine_metadata` - System state

**Indexes**: 9 optimized indexes for performance

**Use When**: You need to understand the data model

---

### Configuration Files

#### config/memory-engine.yaml (3.4 KB)
**Purpose**: Complete system configuration  
**Sections**:
- ENGINE: Name, version, phase, mode
- EMBEDDINGS: Provider, model, dimensions, caching
- VECTOR_DB: Engine, path, indexes, tables
- RETRIEVAL: Weights (BM25 40%, semantic 40%, temporal 20%)
- TEMPORAL_WEIGHTING: Decay, tiers, lambda
- MEMORY_NOTES: Protocol, types, auto-embedding
- SOURCES: Priority order, polling intervals
- INDEXES: Primary and secondary
- CACHE: Settings and TTL
- LOGGING: Level, format, rotation
- PERFORMANCE: Batch size, parallelism
- QUALITY_CHECKS: Dedup, contradiction, staleness

**Use When**: You need to adjust settings or understand configuration

---

## How to Use This System

### First Time Setup
1. Read: **README.md** (overview)
2. Run: **init_memory_engine.sh** (setup)
3. Check: **STATUS.md** (verify)
4. Test: **test_memory_engine.py** (validate)

### Daily Operations
1. Add facts: `memory_engine.py --add-fact`
2. Search: `memory_engine.py --query`
3. Check status: `memory_engine.py --status`
4. Update decay: `memory_engine.py --decay` (hourly via cron)

### Understanding the System
1. Read: **PHASE_1_2_SUMMARY.txt** (complete overview)
2. Study: **IMPLEMENTATION.md** (detailed plan)
3. Review: **db/schema.sql** (data model)
4. Explore: **memory_engine.py** (implementation)

### Troubleshooting
- Check: **README.md** (troubleshooting section)
- Review: **logs/memory-engine.log** (error details)
- Validate: **test_memory_engine.py** (system health)
- Consult: **STATUS.md** (known issues)

### Next Phases
- Read: **IMPLEMENTATION.md** (Phase 3-7 details)
- Plan: Week-by-week timeline
- Implement: Use Phase 3 tasks as checklist

---

## File Organization

```
~/.hermes/memory-engine/
│
├── README.md                     User guide (START HERE)
├── IMPLEMENTATION.md             Detailed project plan
├── STATUS.md                     Deployment status
├── PHASE_1_2_SUMMARY.txt         Executive summary
├── INDEX.md                      This file
│
├── config/
│   └── memory-engine.yaml        Configuration
│
├── db/
│   ├── schema.sql                Database schema
│   ├── memory.db                 (created on init)
│   └── embedding-cache/          (embedding cache)
│
├── scripts/
│   ├── memory_engine.py          Main engine (17.3 KB)
│   ├── hybrid_retriever.py       Ranking logic (11.4 KB)
│   ├── init_memory_engine.sh     Setup script (3.2 KB)
│   ├── test_memory_engine.py     Test suite (14.8 KB)
│   ├── indexer.py                (skeleton)
│   └── analyzer.py               (skeleton)
│
└── logs/
    └── memory-engine.log         Operational logs
```

---

## Quick Reference: Commands

### Initialize
```bash
bash ~/.hermes/memory-engine/scripts/init_memory_engine.sh
```

### Status
```bash
python3 ~/.hermes/memory-engine/scripts/memory_engine.py --status
```

### Add Fact
```bash
python3 ~/.hermes/memory-engine/scripts/memory_engine.py \
  --add-fact "Your fact here" \
  --source "manual"
```

### Search
```bash
python3 ~/.hermes/memory-engine/scripts/memory_engine.py \
  --query "search terms"
```

### Update Decay
```bash
python3 ~/.hermes/memory-engine/scripts/memory_engine.py --decay
```

### Run Tests
```bash
python3 ~/.hermes/memory-engine/scripts/test_memory_engine.py
```

---

## Key Metrics

| Component | Size | Purpose |
|-----------|------|---------|
| memory_engine.py | 17.3 KB | Main engine |
| hybrid_retriever.py | 11.4 KB | Ranking |
| test_memory_engine.py | 14.8 KB | 25+ tests |
| schema.sql | 5.8 KB | 8 tables |
| config/memory-engine.yaml | 3.4 KB | Settings |
| init_memory_engine.sh | 3.2 KB | Setup |
| Documentation | 45+ KB | Guides |
| **Total** | **~100 KB** | **Complete system** |

---

## Document Timeline

Created: 2026-03-23  
Last Updated: 2026-03-23  
Phase: 1-2 (Complete)  
Status: ✅ Ready for Production

---

## Support

### Questions?
- See **README.md** for user guide
- See **IMPLEMENTATION.md** for technical details
- Check **STATUS.md** for deployment info

### Issues?
- Review **logs/memory-engine.log**
- Run **test_memory_engine.py**
- Check **README.md** troubleshooting section

### Next Phases?
- Read **IMPLEMENTATION.md** Phase 3-7 section
- Follow weekly timeline
- Use included skeleton files

---

**Status**: ✅ Production Ready  
**Deployed**: [After init runs]  
**Owner**: Hermes Memory Team

---
