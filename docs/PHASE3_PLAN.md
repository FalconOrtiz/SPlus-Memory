# Phase 3 - Semantic Search & Deduplication
**Timeline**: Week 3 (Apr 7-13)  
**Scope**: Embeddings integration, similarity search, fact deduplication  
**Status**: Starting

---

## Overview

Phase 3 completes the semantic layer of the Memory Engine:

1. **Semantic Search** — Use embeddings for similarity-based retrieval
2. **Fact Deduplication** — Identify and merge duplicate facts
3. **Contradiction Detection** — Find conflicting facts
4. **Better Ranking** — Integrate embeddings into hybrid scoring
5. **Analytics** — Dashboard for memory health

---

## Current State (Already in DB)

✅ **Embeddings already exist:**
- `fact_embeddings`: 290 records (bge-small-en-v1.5, 384-dim)
- `semantic_embeddings`: 317 records
- `embedding_search_index`: Optimized search table
- `embedding_stats`: Statistics table

✅ **What we have from Phase 1-2:**
- Decay weighting (temporal)
- BM25 scoring (lexical)
- Reference logging (usage patterns)
- Co-occurrence graph (fact relationships)

❌ **What Phase 3 adds:**
- Semantic similarity scoring
- Integrated hybrid ranking (BM25 + semantic + temporal)
- Deduplication pipeline
- Contradiction detection
- Memory health analytics

---

## Architecture: Phase 3

```
┌───────────────────────────────────────────────────────────┐
│  MEMORY ENGINE - HYBRID RETRIEVAL (Phase 1-3)            │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  Query Input                                              │
│      ↓                                                    │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  HYBRID RANKING ENGINE                              │ │
│  ├─────────────────────────────────────────────────────┤ │
│  │                                                     │ │
│  │  Score = BM25(40%) + Semantic(40%) + Temporal(20%) │ │
│  │                                                     │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │ │
│  │  │ BM25 Scoring │  │ Semantic     │  │ Temporal │ │ │
│  │  │              │  │ Similarity   │  │ Decay    │ │ │
│  │  │ • Lexical    │  │              │  │          │ │ │
│  │  │   matching   │  │ • Embeddings │  │ • Age    │ │ │
│  │  │ • Term freq  │  │ • Cosine     │  │ • Usage  │ │ │
│  │  │ • IDF weight │  │   distance   │  │ • Refs   │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────┘ │ │
│  │                                                     │ │
│  └─────────────────────────────────────────────────────┘ │
│      ↓                                                    │
│  Deduplicate (similar facts merged)                      │
│      ↓                                                    │
│  Check Contradictions (conflicting facts flagged)        │
│      ↓                                                    │
│  Rank Results (top-5 returned)                           │
│      ↓                                                    │
│  Log Reference (for contextual windowing)                │
│      ↓                                                    │
│  Return with context window                              │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

---

## Task Breakdown

### Task 1: Semantic Similarity Search (Mon, 2h)

**Create `semantic_search.py`:**

```python
class SemanticSearcher:
    def semantic_search(query: str, top_k: int = 10) -> List[Dict]:
        """
        Search using embeddings + cosine similarity.
        
        1. Embed the query
        2. Calculate cosine distance to all facts
        3. Return top-K by similarity
        """
        
    def similarity_score(embedding1, embedding2) -> float:
        """Cosine similarity between two embeddings."""
        
    def batch_similarity(query_embedding, fact_embeddings) -> List[float]:
        """Vectorized similarity calculation."""
```

**Database integration:**
```sql
-- Get embedding for query
SELECT embedding FROM semantic_embeddings WHERE fact_id = ?

-- Calculate similarity for all facts
SELECT fact_id, 
       cosine_similarity(query_embedding, embedding) as score
FROM semantic_embeddings
ORDER BY score DESC
LIMIT ?
```

### Task 2: Hybrid Ranking (Tue, 2h)

**Update `hybrid_retriever.py` to use embeddings:**

```python
class HybridSearcher:
    def search(query: str) -> List[Dict]:
        """
        Combined BM25 + Semantic + Temporal ranking.
        
        final_score = 
            0.40 * bm25_score +
            0.40 * semantic_score +
            0.20 * temporal_score
        """
        
    def bm25_search(query: str) -> Dict[str, float]:
        """Lexical matching."""
        
    def semantic_search(query: str) -> Dict[str, float]:
        """Embedding-based similarity."""
        
    def temporal_search(query: str) -> Dict[str, float]:
        """Decay weight + freshness."""
        
    def combine_scores(bm25, semantic, temporal) -> Dict[str, float]:
        """Weighted combination."""
```

### Task 3: Fact Deduplication (Wed, 3h)

**Create `deduplicator.py`:**

```python
class FactDeduplicator:
    def find_duplicates(similarity_threshold: float = 0.85) -> List[List[str]]:
        """
        Find similar facts using embeddings.
        
        1. Calculate all pairwise similarities
        2. Cluster facts with similarity > threshold
        3. Identify canonical vs duplicate
        """
        
    def merge_facts(canonical_id: str, duplicate_ids: List[str]):
        """
        Merge duplicate facts:
        1. Keep canonical content
        2. Update references to canonical
        3. Preserve metadata
        4. Log merge event
        """
        
    def deduplicate_database(threshold: float = 0.85) -> Dict:
        """
        Run full deduplication:
        1. Find all duplicate groups
        2. Select canonical for each group
        3. Merge duplicates
        4. Return report
        """
```

**Database updates:**
```sql
-- Mark duplicates
UPDATE memory_facts 
SET canonical_id = ?, is_active = 0
WHERE id = ?

-- Log deduplication
INSERT INTO deduplication_log (from_id, to_id, similarity, merged_at)
VALUES (?, ?, ?, ?)
```

### Task 4: Contradiction Detection (Thu, 2h)

**Create `contradiction_detector.py`:**

```python
class ContradictionDetector:
    def find_contradictions(query: str) -> List[Dict]:
        """
        Find facts that contradict each other.
        
        Algorithm:
        1. Get top semantic matches for query
        2. Compare pairs for contradiction signals
        3. Return conflict groups
        """
        
    def detect_conflict(fact_a: Dict, fact_b: Dict) -> Optional[Dict]:
        """
        Detect if two facts contradict.
        
        Signals:
        - Opposite sentiment words
        - Conflicting assertions
        - Different authors claiming different things
        """
        
    def flag_contradiction(fact_a_id: str, fact_b_id: str, reason: str):
        """Log contradiction for review."""
```

### Task 5: Analytics Dashboard (Fri, 2h)

**Create `memory_health_dashboard.py`:**

```python
class MemoryHealthDashboard:
    def health_report(self) -> Dict:
        """
        Generate memory system health report:
        - Total facts
        - Deduplication rate
        - Contradiction count
        - Coverage by category
        - Freshness distribution
        - Search quality metrics
        """
        
    def semantic_coverage(self) -> Dict:
        """
        Which topics are well-covered by embeddings?
        """
        
    def deduplication_stats(self) -> Dict:
        """
        How many duplicates found/merged?
        """
        
    def contradiction_stats(self) -> Dict:
        """
        How many contradictions detected?
        """
```

---

## Integration with Phase 1-2

### Hybrid Ranking Weights

Update the hybrid scoring to use embeddings:

```
Before (Phase 1-2):
  Score = BM25(40%) + Semantic_Placeholder(40%) + Temporal(20%)
  Semantic = fixed 0.5 (placeholder)

After (Phase 3):
  Score = BM25(40%) + Semantic_Actual(40%) + Temporal(20%)
  Semantic = cosine_similarity(query_embedding, fact_embedding)
```

### Reference Logging Integration

Contextual windowing (Phase 2) already logs references. Phase 3 uses semantic scores:

```python
# In reference logger
logger.log_reference(
    fact_ids=['fact_1', 'fact_2'],
    context=query,
    relevance_scores={
        'fact_1': 0.95,  # Updated with semantic scores
        'fact_2': 0.87
    }
)
```

### Context Window Optimization

The optimizer (Phase 2) already handles diverse strategies. Phase 3 improves scoring:

```python
# In context optimizer
optimizer = ContextWindowOptimizer(token_budget=4000)

# Now uses semantic scores for better relevance ranking
window = optimizer.find_optimal_window(
    query=query,
    available_facts=facts,
    strategy='adaptive'  # Now considers semantic similarity
)
```

---

## Database Schema Updates

No new tables needed — use existing `semantic_embeddings`.

**New indexes for performance:**

```sql
-- Similarity search optimization
CREATE INDEX idx_se_created ON semantic_embeddings(created_at DESC);

-- Deduplication tracking
ALTER TABLE memory_facts ADD COLUMN canonical_id TEXT;
ALTER TABLE memory_facts ADD COLUMN merge_reason TEXT;
CREATE INDEX idx_canonical ON memory_facts(canonical_id);

-- Contradiction tracking
CREATE TABLE IF NOT EXISTS contradictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id_a TEXT NOT NULL,
    fact_id_b TEXT NOT NULL,
    conflict_type TEXT,  -- 'opposite', 'incompatible', 'inconsistent'
    confidence REAL DEFAULT 0.5,
    first_detected TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fact_id_a, fact_id_b),
    FOREIGN KEY(fact_id_a) REFERENCES memory_facts(id),
    FOREIGN KEY(fact_id_b) REFERENCES memory_facts(id)
);
```

---

## Success Criteria (Week 3)

By end of Friday (Apr 13):

- ✅ Semantic search operational (<100ms per query)
- ✅ Hybrid ranking integrated (40/40/20 weighting)
- ✅ Duplicates identified and flagged (0-5% duplication rate)
- ✅ Contradictions detected (0-2% contradiction rate)
- ✅ Health dashboard running
- ✅ All tests passing
- ✅ Ready for Phase 4

---

## Phase 4 Preview (Week 4+)

- **Smart Context Injection** — Context window selection using semantic + temporal + usage
- **Multi-agent Isolation** — Separate Falcon/Katsumi memory spaces
- **Skill Triggers** — When to use memory vs other tools
- **Observability** — Real-time memory system monitoring

---

## Files to Create

```
semantic_search.py              (~15 KB)
deduplicator.py                 (~18 KB)
contradiction_detector.py        (~12 KB)
memory_health_dashboard.py       (~14 KB)
test_phase3.py                  (~10 KB)

Total: ~70 KB
```

---

**Owner**: Hermes Memory Architecture  
**Start**: Week 3 (Apr 7)  
**Status**: Ready to begin
