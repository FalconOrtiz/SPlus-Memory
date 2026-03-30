# Week 2 - Contextual Windowing Phase
**Timeline**: Wednesday, April 1 - Friday, April 3  
**Phase**: Phase 1-2 → Phase 3 Transition  
**Status**: Ready to Start

---

## Overview

After successful Decay Engine implementation (Mon-Tue), we move to **Contextual Windowing** — the ability to track how facts are used together and reconstruct conversation context.

**What it does:**
- Tracks which facts are referenced together
- Reconstructs multi-fact conversations
- Calculates "windows" of related context
- Provides smart token budgeting

---

## Core Concepts

### Fact References Tracking
When a fact is used in a response, we log:
- Which fact was referenced
- What context prompted its use
- What other facts appeared in same response
- How recent/relevant the reference was

### Session Context Reconstruction
Given a query, we can reconstruct:
- Multi-turn conversation flow
- Fact clusters (groups that appeared together)
- Context windows (related facts)
- Optimal token budgets

### Smart Window Sizing
Algorithms to determine:
- How many facts to include in context
- Which facts are most relevant
- How to balance relevance vs. token cost
- When to create separate context windows

---

## Implementation Tasks

### Task 1: Fact References Table Setup (Wed morning, 1h)

**Current Schema:**
```sql
CREATE TABLE fact_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL,
    referenced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    context TEXT,  -- the query/prompt that triggered reference
    response_facts TEXT,  -- JSON array of other facts in same response
    response_tokens INT,  -- total tokens used
    relevance_score REAL,  -- how relevant was this fact to the prompt
    FOREIGN KEY(fact_id) REFERENCES memory_facts(id)
);
```

**What to do:**
1. Verify table exists and indexes are created
2. Add any missing columns (reference_count, last_reference_date)
3. Create analytics indexes
4. Test insertion performance

### Task 2: Implement Reference Logging (Wed afternoon, 2h)

**Create `fact_reference_logger.py`:**
```python
class FactReferenceLogger:
    def log_reference(self, fact_id, context, response_facts, tokens):
        # Insert into fact_references table
        # Update memory_facts.referenced_count
        # Update memory_facts.last_referenced
        # Calculate relevance_score
        
    def get_fact_co_occurrences(self, fact_id, limit=10):
        # Return facts that appear with this fact
        
    def get_context_window(self, fact_id, size=5):
        # Return facts related to this one
```

**Integration points:**
- Hook into hybrid_retriever.py
- Log every time a fact is returned in top-5
- Track response token count

### Task 3: Session Context Reconstruction (Thu morning, 2h)

**Create `session_context_builder.py`:**
```python
class SessionContextBuilder:
    def reconstruct_from_facts(self, fact_ids):
        # Build a coherent context from multiple facts
        # Order facts by logical flow
        # Identify gaps/missing context
        
    def find_related_facts(self, fact_id, depth=2):
        # Find facts that reference similar topics
        # Return in order of relevance
        
    def estimate_context_size(self, fact_ids):
        # Estimate tokens needed for these facts
        # Suggest optimal subset if over budget
```

**What it does:**
- Takes a list of facts
- Returns them ordered by conversation flow
- Suggests additional facts for context
- Estimates token count

### Task 4: Smart Window Sizing Algorithm (Thu afternoon, 2h)

**Create `context_window_optimizer.py`:**
```python
class ContextWindowOptimizer:
    def find_optimal_window(self, query, available_facts, token_budget=4000):
        # Find best subset of facts for token budget
        # Use relevance scoring
        # Avoid redundant facts
        
    def estimate_token_cost(self, facts):
        # Estimate tokens for fact set
        
    def cluster_facts_by_relevance(self, query, facts):
        # Group related facts
        # Identify primary vs supporting facts
```

**Algorithm:**
1. Score each fact by relevance to query
2. Sort by (relevance * freshness * recentness)
3. Add facts until token budget hit
4. Remove redundant facts
5. Return optimal window

### Task 5: Integration & Testing (Fri, 3h)

**Wire everything together:**
```python
# In hybrid_retriever.py
def search_with_context(self, query, context_window_size=5):
    # Get top-5 facts
    facts = self.hybrid_search(query)
    
    # Build context window
    window = self.context_builder.reconstruct(facts)
    
    # Log references
    self.reference_logger.log_reference(
        fact_ids=[f['id'] for f in facts],
        context=query,
        response_tokens=estimated_tokens
    )
    
    return facts, window
```

**Test cases:**
1. Single fact retrieval + logging
2. Multi-fact window reconstruction
3. Token budget estimation
4. Co-occurrence tracking
5. Performance: window building <50ms

---

## Database Additions

Add these columns to `memory_facts`:
```sql
ALTER TABLE memory_facts ADD COLUMN reference_count INT DEFAULT 0;
ALTER TABLE memory_facts ADD COLUMN last_referenced TIMESTAMP;
ALTER TABLE memory_facts ADD COLUMN co_occurrence_facts TEXT;  -- JSON
```

Create new table:
```sql
CREATE TABLE fact_co_occurrences (
    fact_id_1 TEXT NOT NULL,
    fact_id_2 TEXT NOT NULL,
    co_occurrence_count INT DEFAULT 1,
    last_co_occurred TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (fact_id_1, fact_id_2),
    FOREIGN KEY(fact_id_1) REFERENCES memory_facts(id),
    FOREIGN KEY(fact_id_2) REFERENCES memory_facts(id)
);

CREATE INDEX idx_co_occurrence_fact1 ON fact_co_occurrences(fact_id_1);
CREATE INDEX idx_co_occurrence_count ON fact_co_occurrences(co_occurrence_count DESC);
```

---

## Success Criteria

By end of Friday (Apr 3):
- [ ] Fact references being logged automatically
- [ ] Session context reconstruction working
- [ ] Smart window sizing algorithm tested
- [ ] Co-occurrence tracking 100% accurate
- [ ] Window building <50ms performance
- [ ] 100+ reference events logged
- [ ] Zero data corruption

---

## Expected Outcomes

**By Friday evening:**
- ✅ Facts tracked with their usage context
- ✅ Can reconstruct multi-fact conversations
- ✅ Smart token budgeting working
- ✅ Reference patterns emerging
- ✅ Ready for Phase 3 (embeddings)

---

## Commands for Next Phase

```bash
# Initialize contextual windowing
python3 ~/.hermes/memory-engine/scripts/fact_reference_logger.py --init

# Log a reference manually
python3 ~/.hermes/memory-engine/scripts/fact_reference_logger.py \
  --log-reference fact_03b4456daae2 \
  --context "Query about decay algorithm" \
  --response-facts "[fact_1, fact_2]" \
  --tokens 150

# Get co-occurrences
python3 ~/.hermes/memory-engine/scripts/fact_reference_logger.py \
  --get-cooccurrences fact_03b4456daae2

# Reconstruct session
python3 ~/.hermes/memory-engine/scripts/session_context_builder.py \
  --reconstruct "[fact_1, fact_2, fact_3]"

# Find optimal window
python3 ~/.hermes/memory-engine/scripts/context_window_optimizer.py \
  --optimize "query text" \
  --budget 4000
```

---

## Notes for Wednesday Morning

1. Review current `fact_references` schema - verify all columns exist
2. Create three new Python scripts (reference_logger, context_builder, optimizer)
3. Add database columns and tables
4. Write unit tests first (TDD approach)
5. Then wire into hybrid_retriever

**First test:** Log 5 facts as a "group" and retrieve them together.

---

**Created**: 2026-03-24  
**Owner**: Hermes Memory Architecture  
**Phase**: 1-2 → 3 Transition
