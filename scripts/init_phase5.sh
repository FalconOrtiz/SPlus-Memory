#!/bin/bash

# Phase 5 Initialization Script
# Initializes multi-agent coherence system

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DB_PATH="$HOME/.hermes/memory-engine/db/memory.db"
LOG_DIR="$HOME/.hermes/memory-engine/logs"

echo "═══════════════════════════════════════════════════════════"
echo "  Phase 5: Multi-Agent Coherence System Initialization"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Check Python
echo "✓ Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 not found. Install Python 3.8+ and try again."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "  Python $PYTHON_VERSION found ✓"
echo ""

# Check database exists
echo "✓ Checking database..."
if [ ! -f "$DB_PATH" ]; then
    echo "✗ Database not found at $DB_PATH"
    echo "  Run Phase 1 initialization first"
    exit 1
fi
echo "  Database found ✓"
echo ""

# Create log directory
echo "✓ Setting up logging..."
mkdir -p "$LOG_DIR"
touch "$LOG_DIR/agent-sync.log"
touch "$LOG_DIR/consensus.log"
touch "$LOG_DIR/inference.log"
touch "$LOG_DIR/coherence.log"
touch "$LOG_DIR/orchestrator.log"
echo "  Logs created ✓"
echo ""

# Initialize Phase 5 database tables
echo "✓ Creating Phase 5 tables..."
sqlite3 "$DB_PATH" <<EOF
-- Agent votes table
CREATE TABLE IF NOT EXISTS agent_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (fact_id) REFERENCES memory_facts(id),
    UNIQUE(fact_id, agent_id)
);

-- Agent state tracking
CREATE TABLE IF NOT EXISTS agent_state (
    agent_id TEXT PRIMARY KEY,
    last_sync TEXT,
    fact_count INTEGER DEFAULT 0,
    sync_status TEXT DEFAULT 'never_synced'
);

-- Agent synchronization log
CREATE TABLE IF NOT EXISTS agent_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id_from TEXT,
    agent_id_to TEXT,
    facts_synced INTEGER,
    conflicts_resolved INTEGER DEFAULT 0,
    timestamp TEXT NOT NULL
);

-- Consensus log
CREATE TABLE IF NOT EXISTS consensus_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL,
    consensus_score REAL,
    approver TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (fact_id) REFERENCES memory_facts(id)
);

-- Agent performance log
CREATE TABLE IF NOT EXISTS agent_performance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    search_time_ms REAL,
    timestamp TEXT NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_agent_votes_fact ON agent_votes(fact_id);
CREATE INDEX IF NOT EXISTS idx_agent_votes_agent ON agent_votes(agent_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_timestamp ON agent_sync_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_consensus_fact ON consensus_log(fact_id);
CREATE INDEX IF NOT EXISTS idx_perf_agent ON agent_performance_log(agent_id);

-- Initialize agent state
INSERT OR IGNORE INTO agent_state (agent_id, last_sync, fact_count, sync_status)
VALUES ('falcon', NULL, 0, 'never_synced');
INSERT OR IGNORE INTO agent_state (agent_id, last_sync, fact_count, sync_status)
VALUES ('katsumi', NULL, 0, 'never_synced');
INSERT OR IGNORE INTO agent_state (agent_id, last_sync, fact_count, sync_status)
VALUES ('leo', NULL, 0, 'never_synced');
EOF

echo "  Tables created ✓"
echo ""

# Verify Python modules
echo "✓ Verifying Phase 5 modules..."
MODULES=(
    "agent_sync.py"
    "consensus_engine.py"
    "cross_agent_inference.py"
    "coherence_validator.py"
    "multi_agent_orchestrator.py"
    "test_phase5.py"
)

for module in "${MODULES[@]}"; do
    if [ -f "$SCRIPT_DIR/$module" ]; then
        echo "  ✓ $module"
    else
        echo "  ✗ $module NOT FOUND"
        exit 1
    fi
done
echo ""

# Test imports
echo "✓ Testing Python imports..."
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
try:
    from agent_sync import AgentSynchronizer
    from consensus_engine import ConsensusEngine
    from cross_agent_inference import CrossAgentInferencer
    from coherence_validator import CoherenceValidator
    from multi_agent_orchestrator import MultiAgentOrchestrator
    print('  All Phase 5 modules imported ✓')
except Exception as e:
    print(f'  Import error: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "  ✗ Import test failed"
    exit 1
fi
echo ""

# Run quick validation
echo "✓ Running quick validation..."
python3 -c "
import sys
import sqlite3
sys.path.insert(0, '$SCRIPT_DIR')

# Check database
db_path = '$DB_PATH'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Verify tables exist
tables = [
    'agent_votes',
    'agent_state',
    'agent_sync_log',
    'consensus_log',
    'agent_performance_log'
]

for table in tables:
    cursor.execute(f\"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'\")
    if not cursor.fetchone():
        print(f'  ✗ Table {table} not found')
        sys.exit(1)

# Check agent_state initialized
cursor.execute('SELECT COUNT(*) FROM agent_state')
count = cursor.fetchone()[0]
if count != 3:
    print(f'  ✗ Expected 3 agents, found {count}')
    sys.exit(1)

print('  Database validation passed ✓')
conn.close()
" || exit 1
echo ""

# Run tests
echo "✓ Running Phase 5 tests..."
python3 "$SCRIPT_DIR/test_phase5.py" --specific agent_sync 2>&1 | grep -E "(OK|FAIL|ERROR)" || true
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "  Phase 5 Initialization Complete ✓"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Quick start:"
echo ""
echo "  # Process a query through full pipeline"
echo "  python3 -c \""
echo "    from multi_agent_orchestrator import MultiAgentOrchestrator"
echo "    orch = MultiAgentOrchestrator()"
echo "    result = orch.process_query('What is the memory system?')"
echo "    print(f'Answer: {result[\"unified_answer\"]}')"
echo "    print(f'Confidence: {result[\"pipeline\"][\"inference\"][\"confidence\"]}')"
echo "  \""
echo ""
echo "  # Check system health"
echo "  python3 $SCRIPT_DIR/multi_agent_orchestrator.py --health"
echo ""
echo "  # Run full test suite"
echo "  python3 $SCRIPT_DIR/test_phase5.py --verbose"
echo ""
echo "Documentation:"
echo "  $SCRIPT_DIR/../PHASE5_STATUS.md"
echo ""
