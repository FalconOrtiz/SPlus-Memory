# Agent Sync Scalability & Adaptability

**Status**: ✅ ENHANCED FOR UNLIMITED AGENT SCALING  
**Date**: 2026-03-24  
**Module**: `agent_sync_adaptive.py` (20.9 KB)

---

## Problem Statement

**Original Implementation**:
- ❌ Hardcoded for 3 specific agents (falcon, katsumi, leo)
- ❌ Fixed authority weights in code
- ❌ Not portable across deployments
- ❌ Couldn't scale to N agents

**Solution**:
- ✅ Configuration-based agent discovery
- ✅ Unlimited agent scalability (1 to N)
- ✅ Dynamic agent registration/unregistration
- ✅ Portable across any deployment

---

## How It Works

### Default Configuration

All agents defined in **`agents.json`**:

```json
{
  "agents": {
    "falcon": {
      "authority": 0.95,
      "role": "technical",
      "specializations": ["architecture", "implementation"]
    },
    "katsumi": {
      "authority": 0.90,
      "role": "patterns"
    },
    "leo": {
      "authority": 0.75,
      "role": "external"
    }
  }
}
```

### Startup Process

```
1. AdaptiveAgentSynchronizer() initialized
   ↓
2. _load_agent_config()
   ├─ Load from agents.json if exists
   └─ Fallback to DEFAULT_AGENTS if not
   ↓
3. Extract agent list & authority weights
   ├─ agents = ['falcon', 'katsumi', 'leo', ...]
   └─ authority_weights = {falcon: 0.95, katsumi: 0.90, ...}
   ↓
4. Ready to sync any configured agents
```

---

## Deployment Scenarios

### Scenario 1: Solo Deployment (1 Agent)

**agents.json**:
```json
{
  "agents": {
    "myagent": {
      "authority": 1.0,
      "role": "solo"
    }
  }
}
```

**Usage**:
```python
sync = AdaptiveAgentSynchronizer()
sync.sync_all()  # Syncs just 'myagent'
```

**Behavior**: Solo mode (no consensus needed)

---

### Scenario 2: Dual Deployment (2 Agents)

**agents.json**:
```json
{
  "agents": {
    "primary": {
      "authority": 0.95,
      "role": "primary"
    },
    "backup": {
      "authority": 0.80,
      "role": "backup"
    }
  }
}
```

**Usage**:
```python
sync = AdaptiveAgentSynchronizer()
sync.sync_all()  # Syncs both agents

# Conflict resolution:
# - Primary (0.95) authority > Backup (0.80)
# - Primary version wins
```

**Behavior**: Dual consensus (primary is tiebreaker)

---

### Scenario 3: Standard Deployment (3 Agents - Default)

**agents.json** (default):
```json
{
  "agents": {
    "falcon": {"authority": 0.95, "role": "technical"},
    "katsumi": {"authority": 0.90, "role": "patterns"},
    "leo": {"authority": 0.75, "role": "external"}
  }
}
```

**Behavior**: 
- 3/3 agents agree: consensus = min(votes) × avg_authority
- 2/3 agents agree: consensus = avg(top_2) × 0.85
- 1/3 agent: manual review needed

---

### Scenario 4: Enterprise Deployment (N Agents)

**agents.json**:
```json
{
  "agents": {
    "falcon": {"authority": 0.95, "role": "technical"},
    "katsumi": {"authority": 0.90, "role": "patterns"},
    "leo": {"authority": 0.75, "role": "external"},
    "nova": {"authority": 0.88, "role": "optimization"},
    "aria": {"authority": 0.85, "role": "coordination"},
    "system_monitor": {"authority": 0.70, "role": "monitoring"}
  }
}
```

**Behavior**: 
- Full federation across 6 agents
- Majority voting (requires 3+ agreements)
- Weighted by authority
- Scales linearly to N agents

---

## Runtime Agent Management

### Add Agent Dynamically

```python
sync = AdaptiveAgentSynchronizer()

# Register new agent at runtime
sync.register_agent(
    agent_id='nova',
    authority=0.88,
    role='optimization',
    description='Query optimizer'
)

# Now included in all future syncs
sync.sync_all()  # Includes 'nova'
```

**Saved to agents.json automatically**.

### Discover Agents from Database

```python
sync = AdaptiveAgentSynchronizer()

# Auto-discover agents from memory_facts
discovered = sync.discover_agents()
# → ['falcon', 'katsumi', 'leo', 'unknown_agent']

# Automatically registers unknown agents
```

### Remove Agent

```python
sync.unregister_agent('leo')
# → Removes from config, not synced anymore
```

### List Configured Agents

```python
agents = sync.get_configured_agents()
# → [
#   {agent_id: 'falcon', authority: 0.95, role: 'technical', ...},
#   {agent_id: 'katsumi', authority: 0.90, role: 'patterns', ...},
#   ...
# ]
```

---

## Conflict Resolution Algorithm

### Authority-Based Resolution

Conflicts resolved by **agent authority weight** (from config):

```
Fact Version A (agent: falcon, authority: 0.95)
        VS
Fact Version B (agent: leo, authority: 0.75)

Resolution: A wins (0.95 > 0.75)
```

### Custom Authority Weights

Adjust weights in `agents.json` to influence conflict outcomes:

```json
{
  "agents": {
    "strict_agent": {
      "authority": 0.99  ← Highest priority
    },
    "trusted_agent": {
      "authority": 0.90
    },
    "lenient_agent": {
      "authority": 0.50  ← Lower priority
    }
  }
}
```

---

## Sync Report Structure

### All Agents Synced

```python
report = sync.sync_all()
# {
#   'timestamp': '2026-03-24T18:30:00Z',
#   'agents': ['falcon', 'katsumi', 'leo'],
#   'agent_count': 3,
#   'facts_pulled': 45,
#   'conflicts_detected': 3,
#   'conflicts_resolved': 3,
#   'facts_pushed': 45,
#   'status': 'complete'
# }
```

### Subset of Agents

```python
report = sync.sync_agents(['falcon', 'katsumi'])
# Syncs only these two agents, ignores 'leo'
```

### Status Check

```python
status = sync.get_sync_status()
# {
#   'agents': {
#     'falcon': {'last_sync': '2026-03-24T18:30:00Z', 'status': 'synced', 'authority': 0.95},
#     'katsumi': {'last_sync': '2026-03-24T18:30:00Z', 'status': 'synced', 'authority': 0.90},
#     'leo': {'last_sync': None, 'status': 'never_synced', 'authority': 0.75}
#   },
#   'agent_count': 3
# }
```

---

## Configuration Migration

### From Old (Hardcoded) to New (Config-Based)

**Old Code**:
```python
AGENT_AUTHORITY = {
    'falcon': 0.95,
    'katsumi': 0.90,
    'leo': 0.75
}
```

**New Config** (`agents.json`):
```json
{
  "agents": {
    "falcon": {"authority": 0.95, ...},
    "katsumi": {"authority": 0.90, ...},
    "leo": {"authority": 0.75, ...}
  }
}
```

**Migration Steps**:
1. Copy `agents.json` to `~/.hermes/memory-engine/config/`
2. Replace imports: `from agent_sync_adaptive import AdaptiveAgentSynchronizer`
3. Change usage: `sync = AdaptiveAgentSynchronizer()`
4. Everything else works the same!

---

## Use Cases

### Use Case 1: Share System Across Team

**Step 1**: Deploy memory engine
```bash
cp agents.json ~/.hermes/memory-engine/config/
```

**Step 2**: Team A customizes agents
```json
{
  "agents": {
    "team_a_agent": {"authority": 1.0},
    "shared_validator": {"authority": 0.8}
  }
}
```

**Step 3**: Team B customizes agents
```json
{
  "agents": {
    "team_b_agent": {"authority": 1.0},
    "shared_validator": {"authority": 0.8}
  }
}
```

**Result**: Same codebase, different agent configs per team

---

### Use Case 2: Gradual Agent Addition

**Month 1**: Start with 1 agent
```json
{
  "agents": {
    "falcon": {"authority": 1.0}
  }
}
```

**Month 2**: Add pattern agent
```json
{
  "agents": {
    "falcon": {"authority": 0.95},
    "katsumi": {"authority": 0.90}
  }
}
```

**Month 3**: Add external validator
```json
{
  "agents": {
    "falcon": {"authority": 0.95},
    "katsumi": {"authority": 0.90},
    "leo": {"authority": 0.75}
  }
}
```

**Result**: Grow from 1→2→3 agents without code changes

---

### Use Case 3: Specialized Deployments

**ML Training Cluster**:
```json
{
  "agents": {
    "data_processor": {"authority": 0.95},
    "model_trainer": {"authority": 0.90},
    "validator": {"authority": 0.85},
    "quality_checker": {"authority": 0.80}
  }
}
```

**Production Cluster**:
```json
{
  "agents": {
    "inference_engine": {"authority": 0.98},
    "safety_check": {"authority": 0.95}
  }
}
```

**Result**: Same engine, optimized for each environment

---

## Command-Line Interface

### Sync All Agents

```bash
python3 agent_sync_adaptive.py --sync-all
# Syncs all configured agents

Output:
✓ Sync All Agents (3 agents):
  timestamp: 2026-03-24T18:30:00Z
  agents: ['falcon', 'katsumi', 'leo']
  agent_count: 3
  facts_pulled: 45
  conflicts_resolved: 3
  facts_pushed: 45
  status: complete
```

### Sync Specific Agents

```bash
python3 agent_sync_adaptive.py --sync falcon katsumi
# Syncs only falcon and katsumi, skips leo
```

### List Agents

```bash
python3 agent_sync_adaptive.py --agents
# Configured Agents (3):
#   • falcon: technical (authority=0.95)
#     Technical expert: system architecture, implementation, code optimization
#   • katsumi: patterns (authority=0.90)
#     Pattern expert: memory, relationships, temporal context, integration
#   • leo: external (authority=0.75)
#     External expert: outreach, validation, communication, social
```

### Discover Agents

```bash
python3 agent_sync_adaptive.py --discover
# Discovered 3 agents:
#   • falcon
#   • katsumi
#   • leo
```

### Register New Agent

```bash
python3 agent_sync_adaptive.py --register nova 0.88
# ✓ Agent registration: success
# Now in agents.json and included in syncs
```

### Check Status

```bash
python3 agent_sync_adaptive.py --status
# Sync Status (3 agents):
#   falcon: {last_sync: 2026-03-24T18:30:00Z, status: synced, authority: 0.95}
#   katsumi: {last_sync: 2026-03-24T18:30:00Z, status: synced, authority: 0.90}
#   leo: {last_sync: None, status: never_synced, authority: 0.75}
```

---

## Integration with Phase 5-7

### In Multi-Agent Orchestrator

```python
# Old way (hardcoded)
from agent_sync import AgentSynchronizer
sync = AgentSynchronizer()
sync.sync_agents(['falcon', 'katsumi', 'leo'])

# New way (config-based)
from agent_sync_adaptive import AdaptiveAgentSynchronizer
sync = AdaptiveAgentSynchronizer()
sync.sync_all()  # Reads from agents.json
```

### In Consensus Engine

```python
# Consensus voting uses configured authority weights
agent_results = {
    'falcon': 0.95,
    'katsumi': 0.92,
    'leo': 0.88
}

# Authority weights from agents.json
# Score = min(votes) × avg_authority
# 0.88 × ((0.95 + 0.90 + 0.75) / 3) = 0.88 × 0.867 = 0.76
```

### In Cross-Agent Inference

```python
# Agent specialization from config
agent_config['falcon']['specializations']  # [architecture, implementation, ...]
agent_config['katsumi']['specializations'] # [patterns, relationships, ...]

# Routes queries to best-fit agents automatically
```

---

## Backward Compatibility

✅ **Old Code Works**:
```python
# Still works - uses defaults
sync = AdaptiveAgentSynchronizer()
sync.sync_all()
# → Uses DEFAULT_AGENTS (falcon, katsumi, leo)
```

✅ **No Breaking Changes**:
- Same API as original
- Same sync logic
- Same conflict resolution

✅ **Gradual Migration**:
- Create agents.json
- No code changes needed
- System auto-detects and uses config

---

## Summary

| Feature | Old | New |
|---------|-----|-----|
| Agent Count | 3 (hardcoded) | 1 to N (configurable) |
| Portability | ❌ Hardcoded | ✅ Config-based |
| Authority Weights | Code (restart needed) | agents.json (dynamic) |
| Agent Addition | Code change | JSON edit |
| Discovery | None | Auto-discover |
| Scalability | Limited | Unlimited |
| Deployment Flexibility | Low | High |

---

## File Locations

```
~/.hermes/memory-engine/
├── scripts/
│   └── agent_sync_adaptive.py    (20.9 KB) NEW
├── config/
│   └── agents.json              (2.1 KB) NEW
└── AGENT_SYNC_SCALABILITY.md    (This file)
```

---

## Quick Start

```bash
# 1. Use new adaptive sync
from agent_sync_adaptive import AdaptiveAgentSynchronizer

# 2. Initialize (auto-loads agents.json)
sync = AdaptiveAgentSynchronizer()

# 3. Sync all configured agents
report = sync.sync_all()

# 4. Check status
status = sync.get_sync_status()

# 5. Add agents dynamically
sync.register_agent('nova', authority=0.88)
```

---

**Status**: ✅ PRODUCTION READY FOR UNLIMITED AGENT SCALING  
**Backward Compatible**: ✅ YES  
**Configuration Required**: ✅ agents.json (auto-generated)

