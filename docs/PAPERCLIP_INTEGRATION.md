# Paperclip Integration Guide

## Overview

Hermes Memory Engine is integrated with Paperclip Control Plane for agent coordination.

**Bridge:** `paperclip_bridge.py` (400 LOC)

**Architecture:**
```
Hermes Memory Engine (SQLite)
  ↓
Paperclip Bridge (REST client)
  ↓
Paperclip Control Plane API (Express/Node)
  ↓
Agent Registry + Activity Log
```

## Agent Hierarchy

```
IRE Digital (company)
├── Hermes (hub) — Orchestrates all agents
│   ├── Hermes (memory) — Facts, embeddings, predictions
│   ├── LEO (outreach) — Email, LinkedIn automation
│   ├── NOVA (execution) — Task runner
│   └── ARIA (analysis) — Data analysis
```

Hermes reports to Hermes hub which coordinates decisions.

## Setup

### 1. Environment Variables

```bash
export PAPERCLIP_BASE_URL="http://localhost:3100"  # or production URL
export PAPERCLIP_COMPANY_ID="ire-digital"
export HERMES_AGENT_ID="hermes-memory"
export HERMES_HUB_ID="hermes_agent-hub"
export PAPERCLIP_API_KEY="your-api-key"  # optional for local dev
```

### 2. API Key

Get an API key from Paperclip dashboard:
```
POST /api/companies/{company_id}/agents/{agent_id}/keys
```

Store securely. In local dev, can be omitted.

### 3. Test Connection

```bash
python3 paperclip_bridge.py status
```

Expected output:
```
PAPERCLIP BRIDGE STATUS
══════════════════════════════════════════════════

Connected:       True

HERMES STATS:
  facts_indexed             290
  domains_active            16
  embeddings                316
  heat_map_slots            1
  recent_actions_1h         0

AGENTS (5):
  hermes_agent-hub          active
  leo-outreach         idle
  nova-executor        paused
  aria-analyst         active
```

## Operations

### Sync State to Paperclip

Send Hermes memory statistics to control plane:

```bash
python3 paperclip_bridge.py sync
```

Happens automatically every 6 hours via cron.

### Log Actions

When Hermes makes important decisions, log them:

```python
from paperclip_bridge import PaperclipBridge, MemoryAction

bridge = PaperclipBridge()
bridge.connect()

action = MemoryAction(
    action_id="hermes_predict_1234",
    action_type="prediction",
    agent_id="hermes-memory",
    facts_affected=15,
    domains=["memory_system", "ai_agents"],
    confidence=0.85,
    reason="Predicted monday_evening needs memory_system domain",
    timestamp=datetime.now().isoformat(),
)

bridge.log_action(action)
bridge.close()
```

### Query Agent Status

Check what other agents are doing:

```bash
# List all agents
python3 paperclip_bridge.py agents

# Get specific agent (via code)
from paperclip_bridge import PaperclipBridge

bridge = PaperclipBridge()
bridge.connect()
leo_status = bridge.get_agent_status("leo-outreach")
print(leo_status.status)  # "active", "idle", "paused", "error"
bridge.close()
```

### Coordinate with Hermes

When Hermes makes a major decision (like archiving facts or making predictions), notify Hermes:

```python
bridge.coordinate_with_hermes_agent(
    action_type="archive",
    payload={
        "facts_affected": 45,
        "domains": ["old_content"],
        "confidence": 0.9,
        "reason": "Auto-archived facts >90 days old"
    }
)
```

Hermes then:
1. Logs the action
2. Notifies relevant agents (NOVA for cleanup, ARIA for analysis)
3. Updates company audit trail

## Integration Points

### 1. Temporal Engine → Paperclip

When Phase 8D predictive pre-loading runs:
- Log prediction to Paperclip
- Notify Hermes of domain activation
- Track heat map changes

```python
# In temporal_engine.py
from paperclip_bridge import PaperclipBridge

bridge = PaperclipBridge()
bridge.coordinate_with_hermes_agent(
    "temporal_prediction",
    {
        "domains": prediction.predicted_domains,
        "time_slot": prediction.time_slot,
        "confidence": prediction.confidence,
    }
)
```

### 2. Decay Scheduler → Paperclip

When facts are archived automatically:
- Log to Paperclip activity stream
- Hermes can trigger cleanup tasks in other agents

```python
# In decay_scheduler.py
bridge.coordinate_with_hermes_agent(
    "auto_archive",
    {
        "facts_affected": len(facts_to_archive),
        "reason": "Auto-archiving facts >90 days old"
    }
)
```

### 3. Evolution Engine → Paperclip

When memory self-improves:
- Log improvement to audit trail
- Hermes tracks system health

### 4. Content Scheduler → Paperclip

When posts/videos are queued:
- Log to Paperclip so LEO knows what's scheduled
- Coordinate timing with LEO's send schedule

## API Reference

### `PaperclipBridge` Class

```python
bridge = PaperclipBridge(
    base_url="http://localhost:3100",
    company_id="ire-digital",
    api_key="..."
)

# Sync state
bridge.sync_memory_state() → Dict

# Log action
bridge.log_action(action: MemoryAction) → bool

# Check other agents
bridge.get_agent_status(agent_id: str) → AgentStatus
bridge.list_agents() → List[AgentStatus]

# Coordinate
bridge.coordinate_with_hermes_agent(action_type: str, payload: Dict) → bool

# Get config
bridge.get_hermes_agent_config() → Dict

# Health
bridge.get_status() → Dict
```

## CLI Commands

```bash
# Status
python3 paperclip_bridge.py status [--json]

# Sync
python3 paperclip_bridge.py sync [--json]

# List agents
python3 paperclip_bridge.py agents [--json]

# Log action
python3 paperclip_bridge.py log {action_type} \
  --facts 45 \
  --domains domain1 domain2 \
  --reason "description"

# Get Hermes config
python3 paperclip_bridge.py hermes_agent [--json]

# Custom base URL / API key
python3 paperclip_bridge.py status \
  --base-url "https://paperclip.example.com" \
  --api-key "sk-..."
```

## Cron Jobs

Add to crontab:

```bash
# Sync every 6 hours
0 */6 * * * python3 ~/.hermes/memory-engine/scripts/paperclip_bridge.py sync

# Daily audit report
0 2 * * * python3 ~/.hermes/memory-engine/scripts/paperclip_bridge.py status --json >> /tmp/hermes-audit.log
```

## Troubleshooting

### "Connection refused"
- Check Paperclip is running
- Verify `PAPERCLIP_BASE_URL`
- Check firewall rules

### "Agent not found"
- Verify agent ID matches Paperclip registry
- Check company scoping

### "Missing API key"
- Get key from Paperclip dashboard
- Set `PAPERCLIP_API_KEY` environment variable

### "Activity log not appearing"
- Check API key has `activities:write` permission
- Verify company ID is correct
- Check Paperclip audit trail for errors

## Examples

### Example 1: Log a Prediction

```python
from paperclip_bridge import PaperclipBridge, MemoryAction
from datetime import datetime

bridge = PaperclipBridge()
bridge.connect()

action = MemoryAction(
    action_id="pred_monday_evening",
    action_type="temporal_prediction",
    agent_id="hermes-memory",
    facts_affected=128,
    domains=["memory_system", "deployment", "ai_agents"],
    confidence=0.85,
    reason="Predicted monday_evening will need memory_system domain",
    timestamp=datetime.now().isoformat(),
)

bridge.log_action(action)
bridge.close()
```

### Example 2: Check if LEO is Active

```python
bridge = PaperclipBridge()
bridge.connect()

leo = bridge.get_agent_status("leo-outreach")
if leo and leo.status == "active":
    print("LEO is ready for outreach")
else:
    print("LEO is paused or offline")

bridge.close()
```

### Example 3: Notify Hermes of Archive

```python
bridge = PaperclipBridge()
bridge.connect()

# After archiving old facts
bridge.coordinate_with_hermes_agent(
    action_type="archive_complete",
    payload={
        "facts_affected": 45,
        "domains_affected": ["old_content", "deprecated"],
        "confidence": 1.0,
        "reason": "Cleaned up facts older than 90 days per retention policy"
    }
)

bridge.close()
```

## Future Work

- [ ] Webhook listeners for agent state changes
- [ ] Real-time sync of fact changes
- [ ] Agent-to-agent communication queue
- [ ] Distributed decision making between agents
- [ ] Cross-agent memory sharing (read Hermes facts from LEO, NOVA)
