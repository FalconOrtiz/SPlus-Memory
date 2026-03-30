# Phase 4 - Analytics & Auto-Embeddings
**Timeline**: Week 4 (Apr 7-13)  
**Scope**: Auto-embeddings, contradiction detection, analytics dashboard, multi-agent isolation  
**Status**: Planning → Implementation

---

## Overview

Phase 4 adds intelligence and observability to the memory system:

1. **Auto-Embedding Generation** — Generate embeddings for new facts automatically
2. **Contradiction Detection** — Identify and flag conflicting facts
3. **Memory Health Dashboard** — Analytics and system monitoring
4. **Multi-Agent Isolation** — Separate Falcon/Katsumi memory spaces
5. **Continuous Improvement** — Self-optimizing memory system

---

## Task Breakdown

### Task 1: Auto-Embedding Generator (Mon-Tue, 4h)

**Create `auto_embedder.py`:**

```python
class AutoEmbedder:
    def generate_embedding(content: str) -> List[float]:
        """
        Generate embedding for new fact content.
        
        Uses existing embedder from Phase 3 or falls back to
        on-the-fly generation if needed.
        """
        
    def batch_embed(facts: List[Dict]) -> Dict[str, List[float]]:
        """Embed multiple facts efficiently."""
        
    def embed_on_insert(fact_id: str, content: str):
        """Auto-embed when fact is inserted."""
        
    def update_missing_embeddings(limit: int = 100):
        """Find facts without embeddings and generate them."""
```

**Integration:**
```python
# In memory_facts insert trigger
ON INSERT INTO memory_facts
  → Call auto_embedder.generate_embedding(content)
  → Insert into semantic_embeddings
```

### Task 2: Contradiction Detector (Tue, 3h)

**Create `contradiction_detector.py`:**

```python
class ContradictionDetector:
    def find_contradictions(query: str, top_k: int = 10) -> List[Dict]:
        """
        Find facts that contradict each other.
        
        Algorithm:
        1. Get semantic neighbors for query
        2. Compare pairs for conflict signals
        3. Return contradiction groups
        """
        
    def detect_conflict(fact_a: Dict, fact_b: Dict) -> Optional[Dict]:
        """
        Detect if two facts contradict.
        
        Signals:
        - Opposite sentiment (positive vs negative)
        - Conflicting assertions
        - Different sources claiming opposite things
        - Temporal conflicts (says X on date Y, says Y on date Z)
        """
        
    def flag_contradiction(fact_a_id: str, fact_b_id: str, reason: str):
        """Log contradiction for review."""
        
    def resolve_contradiction(canonical_id: str, conflicting_id: str):
        """Mark one as canonical, deprecate other."""
```

**Signals to detect:**
```
Type A: Opposite assertions
  "Decay weight is 0.8" vs "Decay weight is 0.2"
  
Type B: Temporal conflicts  
  "Phase 3 started Monday" vs "Phase 3 started Tuesday"
  
Type C: Source conflicts
  "Falcon says X" vs "Katsumi says not X"
  
Type D: Category conflicts
  "Memory system is working" vs "Memory system is broken"
```

### Task 3: Memory Health Dashboard (Wed-Thu, 5h)

**Create `memory_dashboard.py`:**

```python
class MemoryHealthDashboard:
    def health_report(self) -> Dict:
        """
        Comprehensive memory system health report.
        
        Metrics:
        - Total facts indexed
        - Freshness distribution (recent/medium/old/archive)
        - Deduplication rate
        - Contradiction count
        - Embedding coverage
        - Search quality (top-5 accuracy)
        - Performance metrics
        - Recommendations
        """
        
    def semantic_coverage(self) -> Dict:
        """Which topics/categories are well-covered?"""
        
    def embedding_quality(self) -> Dict:
        """Quality of embeddings (coverage %, missing %)"""
        
    def search_quality_metrics(self) -> Dict:
        """
        How good are our search results?
        - Relevance scores (avg, distribution)
        - Hit rate (queries returning >0 results)
        - Diversity (category spread in results)
        """
        
    def performance_report(self) -> Dict:
        """
        System performance metrics:
        - Query latency (p50, p95, p99)
        - Throughput
        - Cache hit rates
        - Resource usage
        """
        
    def recommendations(self) -> List[str]:
        """
        Auto-generated suggestions:
        - "Consider deduplicating X facts"
        - "Topic Y is under-covered"
        - "Z facts have no embeddings"
        - "Performance issue detected"
        """
```

**Dashboard metrics:**

```
┌─────────────────────────────────────────────┐
│  MEMORY SYSTEM HEALTH DASHBOARD              │
├─────────────────────────────────────────────┤
│                                             │
│  📊 Fact Statistics                         │
│  ├─ Total facts: 27                         │
│  ├─ Recent: 27 (100%)                       │
│  ├─ Medium: 0                               │
│  ├─ Old: 0                                  │
│  └─ Archive: 0                              │
│                                             │
│  📚 Embeddings                              │
│  ├─ With embeddings: 317 (100%)             │
│  ├─ Without embeddings: 0                   │
│  └─ Model: bge-small-en-v1.5                │
│                                             │
│  ⚠️  Contradictions                         │
│  ├─ Total found: 0                          │
│  ├─ Flagged: 0                              │
│  └─ Resolved: 0                             │
│                                             │
│  🔄 Deduplication                           │
│  ├─ Duplicates found: 0                     │
│  ├─ Merged: 0                               │
│  └─ Dedup rate: 0.0%                        │
│                                             │
│  ⚡ Performance                             │
│  ├─ Avg query time: 75ms                    │
│  ├─ Search hit rate: 100%                   │
│  ├─ Results diversity: High                 │
│  └─ Status: ✅ HEALTHY                      │
│                                             │
└─────────────────────────────────────────────┘
```

### Task 4: Multi-Agent Isolation (Thu-Fri, 4h)

**Create `multi_agent_memory.py`:**

```python
class MultiAgentMemory:
    def __init__(self, agent_id: str):
        """
        Initialize memory for a specific agent.
        
        agent_id: 'falcon', 'katsumi', 'leo', etc.
        """
        self.agent_id = agent_id
        
    def add_fact(self, content: str, visibility: str = 'private'):
        """
        Add fact with visibility control.
        
        visibility:
        - 'private': Only this agent can access
        - 'shared': All agents can access
        - 'read_only': Can read but not modify
        """
        
    def search(self, query: str) -> List[Dict]:
        """Search facts visible to this agent."""
        
    def get_shared_facts(self) -> List[Dict]:
        """Get facts shared with this agent."""
        
    def cross_agent_inference(self, query: str) -> Dict:
        """
        Query facts from multiple agents intelligently.
        
        Example:
        - User asks about decay
        - Falcon's memory has implementation details
        - Katsumi's memory has usage patterns
        - Combine both for complete answer
        """
```

**Agent isolation schema:**

```sql
-- Add agent_id to memory_facts
ALTER TABLE memory_facts ADD COLUMN agent_id TEXT DEFAULT 'shared';
ALTER TABLE memory_facts ADD COLUMN visibility TEXT DEFAULT 'private';

-- Agent-specific indexes
CREATE INDEX idx_agent ON memory_facts(agent_id);
CREATE INDEX idx_visibility ON memory_facts(visibility);

-- Shared facts view
CREATE VIEW shared_facts AS
SELECT * FROM memory_facts
WHERE visibility = 'shared' OR agent_id = current_agent_id;
```

---

## Integration Architecture (Phase 4)

```
┌─────────────────────────────────────────────────────┐
│  MEMORY ENGINE - COMPLETE WITH ANALYTICS (Phase 4) │
├─────────────────────────────────────────────────────┤
│                                                     │
│  INPUT: Query + Agent Context                      │
│    ↓                                                │
│  Check Agent Isolation (multi_agent_memory)        │
│    ↓                                                │
│  Hybrid Ranking (BM25 + Semantic + Temporal)       │
│    ↓                                                │
│  Auto-Embedding (if needed)                        │
│    ↓                                                │
│  Contradiction Detection                           │
│    ↓                                                │
│  Deduplication                                      │
│    ↓                                                │
│  Context Reconstruction                            │
│    ↓                                                │
│  Token Optimization                                │
│    ↓                                                │
│  Log to Dashboard (analytics)                      │
│    ↓                                                │
│  Return: Top-5 + Context + Metadata               │
│                                                     │
│  Dashboard: Real-time health metrics               │
│    • Embedding coverage                            │
│    • Contradiction rate                            │
│    • Search quality                                │
│    • Performance                                    │
│    • Recommendations                               │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Database Schema Updates (Phase 4)

```sql
-- Add auto-embedding trigger
CREATE TRIGGER auto_embed_on_insert
AFTER INSERT ON memory_facts
FOR EACH ROW
EXECUTE FUNCTION auto_embed_new_fact(NEW.id, NEW.content);

-- Add agent tracking
ALTER TABLE memory_facts ADD COLUMN agent_id TEXT DEFAULT 'shared';
ALTER TABLE memory_facts ADD COLUMN visibility TEXT DEFAULT 'private';

-- Contradiction table (already exists, but verify schema)
CREATE TABLE IF NOT EXISTS contradictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id_a TEXT NOT NULL,
    fact_id_b TEXT NOT NULL,
    conflict_type TEXT,  -- 'opposite', 'temporal', 'source', 'category'
    confidence REAL DEFAULT 0.5,
    first_detected TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fact_id_a, fact_id_b),
    FOREIGN KEY(fact_id_a) REFERENCES memory_facts(id),
    FOREIGN KEY(fact_id_b) REFERENCES memory_facts(id)
);

-- Dashboard metrics table
CREATE TABLE IF NOT EXISTS dashboard_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    agent_id TEXT DEFAULT 'system'
);
```

---

## Success Criteria (Week 4)

By end of Friday (Apr 13):

- ✅ Auto-embeddings working (0 missing embeddings)
- ✅ Contradiction detection operational (detect conflicts)
- ✅ Dashboard running (health metrics visible)
- ✅ Multi-agent isolation implemented
- ✅ Performance: <100ms for all operations
- ✅ All tests passing
- ✅ Documentation complete
- ✅ Ready for Phase 5 (Multi-agent coherence)

---

## Timeline

**Monday (Apr 7)**
- Auto-Embedding Generator (4h)
- Tests passing by EOD

**Tuesday (Apr 8)**
- Contradiction Detector (3h)
- Integration tests

**Wednesday (Apr 9)**
- Memory Health Dashboard (3h)
- Metrics collection

**Thursday (Apr 10)**
- Multi-Agent Isolation (4h)
- Agent queries working

**Friday (Apr 11)**
- Integration testing
- Documentation
- Phase 4 complete

---

## Files to Create

```
auto_embedder.py              (~12 KB)
contradiction_detector.py     (~14 KB)
memory_dashboard.py           (~18 KB)
multi_agent_memory.py         (~15 KB)
test_phase4.py                (~10 KB)

Total: ~70 KB
```

---

## Phase 5+ Preview

**Phase 5: Multi-Agent Coherence** (Week 5)
- Falcon/Katsumi memory synchronization
- Shared fact consensus
- Cross-agent inference
- Conflict resolution

**Phase 6: Observability** (Week 6)
- Real-time dashboard UI
- Performance monitoring
- Memory optimization
- Self-improvement loops

**Phase 7: Production Deploy** (Week 7)
- Full system integration
- Performance optimization
- Documentation finalization
- Production readiness

---

**Owner**: Hermes Memory Architecture  
**Start**: Week 4 (Apr 7)  
**Status**: Ready to begin
