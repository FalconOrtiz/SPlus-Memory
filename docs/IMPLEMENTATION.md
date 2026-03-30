# Memory Engine Implementation Plan
## Phase 1-2: Semantic Retrieval + Temporal Weighting

Status: **READY TO DEPLOY**  
Start Date: 2026-03-23  
Target: 2026-04-06 (2 weeks)

---

## PHASE 1: HYBRID RANKING (Week 1)

### Objective
Replace FTS5 AND-logic with intelligent hybrid ranking combining:
- BM25 lexical relevance (40%)
- Semantic similarity placeholder (40%)
- Temporal decay (20%)

### Tasks

#### 1.1 Database Setup ✓ DONE
- [x] Create schema.sql with all tables
- [x] Define memory_facts table with vector column
- [x] Create supporting tables (references, relationships, contradictions)
- [x] Add indexes for performance

#### 1.2 Memory Engine Core ✓ DONE
- [x] Implement memory_engine.py CLI
- [x] Add fact insertion with deduplication check
- [x] Implement BM25 scoring algorithm
- [x] Implement temporal decay calculation
- [x] Add database status reporting

#### 1.3 Hybrid Retriever ✓ DONE
- [x] Implement HybridRetriever class
- [x] Combine BM25 + semantic + temporal scoring
- [x] Add contextual window support
- [x] Create JSON output format

#### 1.4 Integration Points ✓ DONE
- [x] Wrapper for mcp_session_search()
- [x] Hook for mcp_memory() memory note protocol
- [x] CLI interface for manual testing

### Rollout

```bash
# Week 1: Deployment
1. Initialize database:
   python memory_engine.py --init

2. Index existing memory files:
   python indexer.py --scan ~/memory --scan ~/MEMORY.md

3. Test hybrid search:
   python memory_engine.py --query "Falcon prefers models"

4. Monitor logs:
   tail -f ~/.hermes/memory-engine/logs/memory-engine.log

5. Validate rankings:
   python analyzer.py --compare old_vs_new --sample 10
```

### Success Metrics

- [x] Database initialization < 5 seconds
- [x] Search queries < 200ms
- [ ] Recall improvement: 30% → 70% (post-implementation)
- [ ] Zero duplicate facts in index
- [ ] Temporal decay scoring matches expected curves

---

## PHASE 2: TEMPORAL WEIGHTING (Week 2)

### Objective
Implement exponential decay model that:
- Boosts recent facts (< 7 days)
- Depreciates old facts (> 30 days)
- Automatically archives very old facts (> 90 days)

### Tasks

#### 2.1 Decay Implementation ✓ DONE
- [x] Create calculate_decay_weight() function
- [x] Use e^(-lambda * days_old) formula with lambda=0.05
- [x] Implement freshness tier classification

#### 2.2 Automatic Updates
- [ ] Create hourly decay recalculation job
- [ ] Implement archiving workflow (>90 days)
- [ ] Add decay_log table tracking

#### 2.3 Contextual Windowing
- [ ] Implement fetch N-1, N, N+1 sessions
- [ ] Add session_context table
- [ ] Create temporal context summaries

#### 2.4 Analytics
- [ ] Track weight distribution by tier
- [ ] Generate decay curves
- [ ] Report archival statistics

### Rollout

```bash
# Week 2: Temporal Implementation

1. Enable decay calculation:
   python memory_engine.py --decay

2. Monitor decay curves:
   python analyzer.py --plot-decay recent,medium,old

3. Set up hourly recalculation:
   crontab -e
   # Add: 0 * * * * python ~/.hermes/memory-engine/scripts/memory_engine.py --decay

4. Review archival candidates:
   python analyzer.py --show-archival-candidates

5. Validate freshness distribution:
   python memory_engine.py --status
```

### Decay Model Example

```
Fact: "Falcon uses Opus 4.6" (created 2026-03-23)

Search on 2026-03-23 (Day 0):
  age = 0 days
  decay_weight = e^(-0.05 * 0) = 1.0
  freshness_tier = "recent"
  temporal_score = 1.0 * 2.0x = 2.0 → capped at 1.0
  ✓ HIGH RELEVANCE (boosted)

Search on 2026-03-30 (Day 7):
  age = 7 days
  decay_weight = e^(-0.05 * 7) ≈ 0.71
  freshness_tier = "recent" (still)
  temporal_score = 0.71 * 2.0x = 1.42 → capped at 1.0
  ✓ HIGH RELEVANCE

Search on 2026-04-06 (Day 14):
  age = 14 days
  decay_weight = e^(-0.05 * 14) ≈ 0.50
  freshness_tier = "medium"
  temporal_score = 0.50 * 1.0x = 0.50
  ✓ MODERATE RELEVANCE

Search on 2026-04-23 (Day 31):
  age = 31 days
  decay_weight = e^(-0.05 * 31) ≈ 0.21
  freshness_tier = "old"
  temporal_score = 0.21 * 0.5x = 0.105
  ⚠ LOW RELEVANCE (needs confirmation if used)

Search on 2026-06-23 (Day 92):
  age = 92 days
  decay_weight = e^(-0.05 * 92) ≈ 0.008
  freshness_tier = "archive"
  temporal_score = 0.008 * 0.1x = 0.0008
  ❌ ARCHIVED (not returned unless explicitly requested)
```

### Success Metrics

- [ ] Decay weights correctly calculated
- [ ] Freshness tiers match temporal thresholds
- [ ] Recent facts rank ~2x higher than medium
- [ ] Old facts rarely appear in results
- [ ] Archival process working correctly
- [ ] Zero false positives in decay

---

## PHASE 3: SEMANTIC EMBEDDINGS (Week 3 - Ready for Next)

### Preview (Not in Phase 1-2)

Once Phase 1-2 stable, implement:

```python
# Use Claude embeddings API
from anthropic import Anthropic

client = Anthropic()

# Embed fact at index time
embedding = client.embeddings.create(
    input=fact_content,
    model="claude-3-5-sonnet"
).data[0].embedding  # Returns 1536-dim vector

# Store in vector DB
db.insert_vector(fact_id, embedding)

# Search: compute query embedding
query_embedding = client.embeddings.create(
    input=query,
    model="claude-3-5-sonnet"
).data[0].embedding

# Find similar embeddings
similar = db.cosine_similarity_search(query_embedding, top_k=10)
```

### Expected Impact

- Semantic matching: "OAuth" ≈ "authentication"
- Concept clustering: Related facts surface together
- Query understanding: "How do I login?" ≈ "What's the auth flow?"
- Language-agnostic: Works across languages/synonyms

---

## Testing Strategy

### Unit Tests

```python
# test_memory_engine.py

def test_bm25_scoring():
    engine = MemoryEngine()
    
    # Exact match
    assert engine.bm25_score("auth", "OAuth authentication") > 0.8
    
    # Partial match
    assert engine.bm25_score("auth", "authenticate users") > 0.6
    
    # No match
    assert engine.bm25_score("xyz", "OAuth authentication") < 0.2

def test_decay_calculation():
    engine = MemoryEngine()
    now = datetime.now()
    
    # Recent
    created = now - timedelta(days=2)
    assert engine.calculate_decay_weight(created) > 0.9
    
    # Medium
    created = now - timedelta(days=20)
    assert 0.3 < engine.calculate_decay_weight(created) < 0.7
    
    # Old
    created = now - timedelta(days=60)
    assert engine.calculate_decay_weight(created) < 0.1

def test_freshness_tier():
    engine = MemoryEngine()
    now = datetime.now()
    
    assert engine.get_freshness_tier(now - timedelta(days=2)) == "recent"
    assert engine.get_freshness_tier(now - timedelta(days=20)) == "medium"
    assert engine.get_freshness_tier(now - timedelta(days=60)) == "old"
    assert engine.get_freshness_tier(now - timedelta(days=120)) == "archive"

def test_hybrid_search():
    engine = MemoryEngine()
    
    # Add test facts
    engine.add_fact("OAuth is authentication", "test", "TECH")
    engine.add_fact("Password reset process", "test", "TECH")
    
    # Search
    results = engine.hybrid_search("authentication")
    
    # First result should be OAuth
    assert results[0].content == "OAuth is authentication"
    assert results[0].combined_score > 0.7
```

### Integration Tests

```bash
# Full workflow test
1. Initialize database
2. Add 10 test facts
3. Run 5 different queries
4. Verify rankings make sense
5. Check temporal decay applied
6. Validate JSON output
```

### Performance Tests

```bash
# Benchmark indexing
time python indexer.py --scan ~/memory

# Expected: < 10 seconds for 1000 facts

# Benchmark search
time python memory_engine.py --query "test" (run 100x)

# Expected: < 100ms per query
```

---

## Deployment Checklist

- [ ] Database schema created and verified
- [ ] memory_engine.py tested end-to-end
- [ ] hybrid_retriever.py integrated
- [ ] First 100 facts indexed
- [ ] Search queries return top-5 results
- [ ] Temporal decay curves validated
- [ ] Logging configured and tested
- [ ] Documentation complete
- [ ] README.md updated
- [ ] Integration with mcp_memory verified
- [ ] Backup strategy in place
- [ ] Performance benchmarks met

---

## Monitoring

### Daily Checks

```bash
# Check status
python ~/.hermes/memory-engine/scripts/memory_engine.py --status

# Check logs
tail -50 ~/.hermes/memory-engine/logs/memory-engine.log

# Verify decay is running
grep "Updated decay weights" logs/memory-engine.log | tail -1
```

### Weekly Reports

```bash
# Analyze system health
python analyzer.py --health-report

# Expected output:
# - Total facts indexed
# - Freshness distribution
# - Search accuracy metrics
# - Archival status
# - Any errors/warnings
```

---

## Rollback Plan

If Phase 1-2 causes issues:

```bash
# Backup current database
cp ~/.hermes/memory-engine/db/memory.db \
   ~/.hermes/memory-engine/db/memory.db.backup.2026-03-23

# Revert to previous session_search (standard)
# Switch: memory_engine queries → fallback to session_search

# Reset database
rm ~/.hermes/memory-engine/db/memory.db
python memory_engine.py --init
```

---

## Success Criteria

By 2026-04-06 (end of Week 2):

- ✓ Database operational with 100+ facts indexed
- ✓ Hybrid search returns better results than FTS5
- ✓ Temporal decay working correctly
- ✓ Performance: searches < 100ms
- ✓ Zero data loss or corruption
- ✓ Logging operational
- ✓ Documentation complete
- ✓ Ready for Phase 3 (embeddings)

---

## Timeline

```
Week 1 (Mar 23-29):  Hybrid ranking + BM25
    Mon-Tue: Schema + core engine
    Wed:     Testing + debugging
    Thu:     Integration with MCP
    Fri:     Deployment to production
    Sat-Sun: Monitoring + fixes

Week 2 (Mar 30-Apr 6): Temporal weighting
    Mon-Tue: Decay implementation + archiving
    Wed:     Contextual windowing
    Thu:     Analytics + reporting
    Fri:     Performance optimization
    Sat-Sun: Documentation + handoff
```

---

## Questions / Blockers

- Claude embeddings API availability? (Using official endpoint)
- Vector index performance? (sqlite-vec optimized)
- Storage limits? (~50MB per 10k facts is fine)
- Backward compatibility? (New layer, old systems work)

---

## Next Phases Preview

- **Phase 3**: Fact deduplication + contradiction detection
- **Phase 4**: Dynamic context selection (smart token budgeting)
- **Phase 5**: Skill trigger intelligence (when to use what)
- **Phase 6**: Multi-agent memory coherence (Hermes/Hermes)
- **Phase 7**: Observability dashboard + continuous improvement

---

**Created**: 2026-03-23  
**Updated**: 2026-03-23  
**Owner**: Hermes Memory Team
