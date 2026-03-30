# Phase 5 - Multi-Agent Coherence
**Timeline**: Week 5 (Apr 14-20)  
**Scope**: Agent synchronization, fact consensus, cross-agent inference, conflict resolution  
**Status**: Planning

---

## Overview

Phase 5 enables multiple AI agents (Falcon, Katsumi, LEO, etc.) to share and reason about memory coherently:

1. **Agent Synchronization** — Keep memories consistent across agents
2. **Fact Consensus** — Resolve conflicts when agents disagree
3. **Cross-Agent Inference** — Combine knowledge from multiple agents
4. **Shared Memory** — Collaborative fact base with visibility control
5. **Coherence Validation** — Ensure logical consistency

---

## Architecture: Multi-Agent System

```
┌─────────────────────────────────────────────────────────────┐
│  FALCON                KATSUMI               LEO             │
│  (Hub coordinator)    (Memory manager)     (Outreach)       │
│       ↓                    ↓                    ↓            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SHARED MEMORY CONSENSUS LAYER                       │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  Fact Consensus Engine                              │   │
│  │  ├─ Vote on fact validity                           │   │
│  │  ├─ Resolve disagreements                           │   │
│  │  └─ Establish canonical versions                    │   │
│  │                                                      │   │
│  │  Cross-Agent Reasoning                              │   │
│  │  ├─ Combine knowledge (A + B → C)                   │   │
│  │  ├─ Fill gaps with agent perspectives              │   │
│  │  └─ Validate conclusions                            │   │
│  │                                                      │   │
│  │  Coherence Monitor                                  │   │
│  │  ├─ Detect contradictions                           │   │
│  │  ├─ Track divergence                                │   │
│  │  └─ Alert on inconsistencies                        │   │
│  │                                                      │   │
│  └──────────────────────────────────────────────────────┘   │
│       ↓                    ↓                    ↓            │
│  Private facts      Shared facts          Managed facts     │
│  (Falcon only)   (All agents)          (Agent-specific)    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Task Breakdown

### Task 1: Agent Synchronization (Mon-Tue, 5h)

**Create `agent_sync.py`:**

```python
class AgentSynchronizer:
    def sync_agents(self, agents: List[str]) -> Dict:
        """
        Synchronize memory across agents.
        
        Process:
        1. Compare fact timestamps
        2. Merge updates
        3. Resolve conflicts
        4. Distribute consensus version
        """
        
    def pull_updates(self, agent_id: str) -> List[Dict]:
        """Get new facts from an agent."""
        
    def push_updates(self, agent_id: str, facts: List[Dict]) -> bool:
        """Send consensus facts to agent."""
        
    def resolve_conflict(self, fact_a: Dict, fact_b: Dict) -> Dict:
        """
        Resolve when agents have different versions.
        
        Strategy:
        1. Check timestamps (newer wins)
        2. Check confidence scores
        3. Check sources
        4. Manual override if needed
        """
        
    def get_sync_status(self) -> Dict:
        """Get synchronization health."""
```

**Database additions:**
```sql
-- Track sync events
CREATE TABLE agent_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id_from TEXT NOT NULL,
    agent_id_to TEXT NOT NULL,
    facts_synced INT,
    conflicts_resolved INT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent state tracking
CREATE TABLE agent_state (
    agent_id TEXT PRIMARY KEY,
    last_sync TIMESTAMP,
    fact_count INT,
    last_update TIMESTAMP,
    sync_status TEXT  -- 'synced', 'pending', 'conflict'
);
```

### Task 2: Fact Consensus Engine (Tue, 3h)

**Create `consensus_engine.py`:**

```python
class ConsensusEngine:
    def vote_on_fact(self, fact_id: str, agents: List[str]) -> Dict:
        """
        Have agents vote on whether fact is valid.
        
        Returns: {valid: bool, confidence: float, votes: {}}
        """
        
    def consensus_score(self, fact_id: str) -> float:
        """
        Calculate how many agents agree on a fact.
        
        Score 0.0-1.0:
        - 0.0: No agents agree
        - 0.5: Half agree
        - 1.0: All agents agree
        """
        
    def establish_canonical(self, fact_group: List[str]) -> str:
        """
        Given duplicate/conflicting facts, pick canonical.
        
        Criteria:
        1. Agent consensus
        2. Timestamp (newer)
        3. Source reliability
        4. Confidence score
        """
        
    def get_disagreements(self) -> List[Dict]:
        """Find facts where agents disagree."""
```

**Voting mechanism:**
```
Falcon sees fact_123: "Decay algorithm uses e^(-0.05*days)"
  └─ Confidence: 0.95 (from implementation)
  
Katsumi sees fact_124: "Decay formula is exponential"
  └─ Confidence: 0.88 (from documentation)
  
LEO sees fact_125: "Decay formula not yet verified"
  └─ Confidence: 0.60 (from status)

Consensus Engine:
  fact_123 and fact_124 → Very similar
  fact_125 → Contradicts consensus
  
Result: fact_123 canonical, fact_124 merged, fact_125 flagged
```

### Task 3: Cross-Agent Inference (Wed, 4h)

**Create `cross_agent_inference.py`:**

```python
class CrossAgentInference:
    def infer_from_agents(self, query: str) -> Dict:
        """
        Query all agents, combine insights.
        
        Process:
        1. Query Falcon (implementation details)
        2. Query Katsumi (patterns, relationships)
        3. Query LEO (external perspective)
        4. Combine findings
        5. Validate conclusion
        """
        
    def fill_knowledge_gaps(self, partial_fact: Dict) -> Dict:
        """
        Given incomplete fact, ask other agents to fill gaps.
        
        Example:
        - Fact: "Phase 3 started..."
        - Missing: exact date
        - Query other agents
        - Combine answers
        """
        
    def cross_validate(self, claim: str) -> Dict:
        """
        Check claim against all agent memories.
        
        Returns: {valid: bool, confidence: float, sources: []}
        """
        
    def generate_synthesis(self, topic: str) -> str:
        """
        Create unified view by synthesizing all agents.
        
        "Based on Falcon's implementation data, Katsumi's 
        patterns, and LEO's feedback, the decay system..."
        """
```

**Multi-agent query flow:**
```
User: "Tell me about the decay system"
  ↓
Query Falcon (technical depth)
  ├─ BM25 + temporal + semantic = top-5
  ├─ Score: [0.95, 0.87, 0.78, 0.72, 0.68]
  └─ Focus: Implementation

Query Katsumi (pattern recognition)
  ├─ Same query, different weights
  ├─ Score: [0.88, 0.92, 0.85, 0.70, 0.65]
  └─ Focus: Relationships

Query LEO (external validation)
  ├─ Cross-reference with external sources
  ├─ Score: [0.78, 0.82, 0.73, 0.60, 0.55]
  └─ Focus: Verification

Synthesize:
  ├─ Compare results
  ├─ Weight by agent reliability
  ├─ Identify gaps
  ├─ Create unified answer
  └─ Return with confidence scores
```

### Task 4: Coherence Validator (Thu, 3h)

**Create `coherence_validator.py`:**

```python
class CoherenceValidator:
    def validate_coherence(self) -> Dict:
        """
        Check memory system for logical consistency.
        
        Checks:
        1. No contradictions
        2. Temporal ordering valid
        3. Cause-effect relationships intact
        4. Category consistency
        5. Source reliability
        """
        
    def detect_divergence(self, agent_id: str) -> List[Dict]:
        """
        Find where an agent's memory diverges from consensus.
        
        Returns facts that:
        - Conflict with consensus
        - Are outdated
        - Have low confidence
        """
        
    def repair_coherence(self, conflicts: List[Dict]) -> Dict:
        """
        Automatically repair incoherent memory.
        
        Actions:
        - Merge duplicates
        - Flag contradictions
        - Update timestamps
        - Adjust confidence scores
        """
        
    def get_coherence_score(self) -> float:
        """
        Overall system coherence (0-1).
        
        1.0: Perfect consistency
        0.8+: Minor conflicts
        0.6-0.8: Manageable divergence
        <0.6: Needs repair
        """
```

**Coherence checks:**
```
Temporal Coherence:
  "Phase 1 started Mar 30" ✓
  "Phase 2 started Apr 1" ✓
  "Phase 3 started Mar 24" ✗ (before Phase 1!)

Logical Coherence:
  "Decay weight: 0.8" ✓
  "Freshness tier: recent" ✓
  "Age: 90 days" ✗ (contradiction!)

Source Coherence:
  Falcon (impl): 0.95 reliability
  Katsumi (mgmt): 0.90 reliability
  LEO (external): 0.75 reliability
  
  Combine weighted by reliability
```

### Task 5: Integration & Testing (Fri, 4h)

**Create `test_phase5.py` & `multi_agent_orchestrator.py`:**

```python
class MultiAgentOrchestrator:
    def __init__(self):
        self.agents = {
            'falcon': Agent(agent_id='falcon'),
            'katsumi': Agent(agent_id='katsumi'),
            'leo': Agent(agent_id='leo')
        }
        self.sync = AgentSynchronizer()
        self.consensus = ConsensusEngine()
        self.inference = CrossAgentInference()
        self.validator = CoherenceValidator()
        
    def query_unified(self, query: str) -> Dict:
        """
        Query all agents, synthesize answer.
        
        1. Get results from all agents
        2. Compare & validate
        3. Synthesize unified answer
        4. Return with confidence
        """
        
    def synchronize_all(self) -> Dict:
        """Sync all agents to consensus."""
        
    def repair_all(self) -> Dict:
        """Detect and repair all coherence issues."""
```

---

## Integration Points

### With Phase 1-4

```
Phase 1: Decay Engine
  └─ Each agent uses same decay algorithm
  └─ Sync ensures all see same weights

Phase 2: Contextual Windowing
  └─ Reference tracking per agent
  └─ Shared references for consensus facts

Phase 3: Semantic Search
  └─ Same embeddings across agents
  └─ Cross-agent similarity

Phase 4: Analytics
  └─ Per-agent dashboards
  └─ System-wide health metrics
```

### Database Schema

```sql
-- Agent identity
ALTER TABLE memory_facts ADD COLUMN agent_id TEXT;
ALTER TABLE memory_facts ADD COLUMN visibility TEXT;
  -- 'private': agent only
  -- 'shared': all agents
  -- 'managed': agent-specific with sync

-- Consensus tracking
CREATE TABLE consensus_votes (
    fact_id TEXT,
    agent_id TEXT,
    voted_valid BOOLEAN,
    confidence REAL,
    timestamp TIMESTAMP,
    PRIMARY KEY (fact_id, agent_id)
);

-- Sync history
CREATE TABLE sync_history (
    from_agent TEXT,
    to_agent TEXT,
    facts_synced INT,
    conflicts INT,
    timestamp TIMESTAMP
);

-- Coherence metrics
CREATE TABLE coherence_metrics (
    timestamp TIMESTAMP,
    temporal_score REAL,
    logical_score REAL,
    source_score REAL,
    overall_score REAL
);
```

---

## Success Criteria (Week 5)

By end of Friday (Apr 20):

- ✅ Agent synchronization operational
- ✅ Consensus voting working (all agents can vote)
- ✅ Cross-agent inference producing unified answers
- ✅ Coherence validation detecting inconsistencies
- ✅ Multi-agent queries working (Falcon + Katsumi + LEO)
- ✅ Conflict resolution automatic
- ✅ All tests passing
- ✅ Performance: <200ms for multi-agent queries
- ✅ Ready for Phase 6 (Observability)

---

## Performance Targets

| Operation | Target | Status |
|-----------|--------|--------|
| Single-agent query | <100ms | From Phase 1-4 ✅ |
| Multi-agent query | <200ms | Phase 5 target |
| Synchronization | <500ms | Phase 5 target |
| Consensus vote | <100ms | Phase 5 target |
| Coherence check | <200ms | Phase 5 target |

---

## Files to Create

```
agent_sync.py                (~14 KB)
consensus_engine.py          (~16 KB)
cross_agent_inference.py     (~18 KB)
coherence_validator.py       (~14 KB)
multi_agent_orchestrator.py  (~12 KB)
test_phase5.py               (~12 KB)

Total: ~86 KB
```

---

## Phase 6+ Preview

**Phase 6: Observability** (Week 6)
- Real-time dashboard UI
- Agent health monitors
- Memory visualization
- Performance analytics

**Phase 7: Production** (Week 7)
- Full system integration
- Performance optimization
- Security hardening
- Documentation finalization

---

## Agent Personas

### Falcon
**Role**: Hub coordinator, technical authority
**Memory Style**: Implementation-focused, precise
**Authority**: 0.95 (implementation knowledge)
**Scope**: System architecture, technical decisions

### Katsumi
**Role**: Memory manager, pattern recognition
**Memory Style**: Relationship-focused, holistic
**Authority**: 0.90 (system patterns)
**Scope**: System health, fact relationships

### LEO
**Role**: Outreach & validation
**Memory Style**: External perspective, customer-focused
**Authority**: 0.75 (external validation)
**Scope**: User feedback, external requirements

---

**Owner**: Hermes Memory Architecture  
**Start**: Week 5 (Apr 14)  
**Duration**: 1 week (5 days)  
**Status**: Planning phase
