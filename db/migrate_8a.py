#!/usr/bin/env python3
"""Phase 8A migration — executed statement by statement."""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'memory.db')
conn = sqlite3.connect(DB)

def run(sql, label=""):
    try:
        conn.execute(sql)
        print(f"  ok  {label}")
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
            print(f"  skip {label} (exists)")
        else:
            print(f"  ERR  {label}: {e}")

print("Phase 8A Migration")
print("=" * 55)

# 1. ALTER quantum_facts
alters = [
    ("activation_score", "REAL DEFAULT 0.0"),
    ("ctx_match_score", "REAL DEFAULT 0.0"),
    ("co_access_score", "REAL DEFAULT 0.0"),
    ("evolution_score", "REAL DEFAULT 0.0"),
    ("confidence", "REAL DEFAULT 0.5"),
    ("supersedes_id", "TEXT"),
    ("superseded_by", "TEXT"),
    ("version_chain", "TEXT"),
    ("document_date", "TIMESTAMP"),
    ("event_date", "TEXT"),
    ("last_activated", "TIMESTAMP"),
    ("activation_count", "INTEGER DEFAULT 0"),
    ("last_context_hash", "TEXT"),
]

print("\n[quantum_facts columns]")
for col, typedef in alters:
    run(f"ALTER TABLE quantum_facts ADD COLUMN {col} {typedef}", col)

# 2. Indexes on quantum_facts
print("\n[quantum_facts indexes]")
run("CREATE INDEX IF NOT EXISTS idx_qf_activation ON quantum_facts(activation_score DESC)", "idx_qf_activation")
run("CREATE INDEX IF NOT EXISTS idx_qf_supersedes ON quantum_facts(supersedes_id)", "idx_qf_supersedes")
run("CREATE INDEX IF NOT EXISTS idx_qf_confidence ON quantum_facts(confidence DESC)", "idx_qf_confidence")

# 3. surface_buffer
print("\n[surface_buffer]")
run("""
CREATE TABLE IF NOT EXISTS surface_buffer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL,
    activation_score REAL NOT NULL,
    domain TEXT,
    trigger_type TEXT NOT NULL,
    injected_text TEXT,
    token_estimate INTEGER,
    surfaced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    consumed INTEGER DEFAULT 0,
    FOREIGN KEY(fact_id) REFERENCES quantum_facts(id)
)
""", "CREATE TABLE")
run("CREATE INDEX IF NOT EXISTS idx_sb_active ON surface_buffer(consumed, activation_score DESC)", "idx_sb_active")
run("CREATE INDEX IF NOT EXISTS idx_sb_expires ON surface_buffer(expires_at)", "idx_sb_expires")
run("CREATE INDEX IF NOT EXISTS idx_sb_domain ON surface_buffer(domain)", "idx_sb_domain")

# 4. context_state
print("\n[context_state]")
run("""
CREATE TABLE IF NOT EXISTS context_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context_hash TEXT UNIQUE,
    active_domains TEXT,
    active_entities TEXT,
    active_skills TEXT,
    active_agent TEXT,
    session_id TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    facts_activated INTEGER DEFAULT 0,
    metadata TEXT
)
""", "CREATE TABLE")
run("CREATE INDEX IF NOT EXISTS idx_cs_hash ON context_state(context_hash)", "idx_cs_hash")
run("CREATE INDEX IF NOT EXISTS idx_cs_detected ON context_state(detected_at DESC)", "idx_cs_detected")

# 5. co_access_patterns
print("\n[co_access_patterns]")
run("""
CREATE TABLE IF NOT EXISTS co_access_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id_a TEXT NOT NULL,
    fact_id_b TEXT NOT NULL,
    co_access_count INTEGER DEFAULT 1,
    strength REAL DEFAULT 0.1,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fact_id_a, fact_id_b)
)
""", "CREATE TABLE")
run("CREATE INDEX IF NOT EXISTS idx_co_a ON co_access_patterns(fact_id_a, strength DESC)", "idx_co_a")
run("CREATE INDEX IF NOT EXISTS idx_co_b ON co_access_patterns(fact_id_b, strength DESC)", "idx_co_b")

# 6. evolution_log
print("\n[evolution_log]")
run("""
CREATE TABLE IF NOT EXISTS evolution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT,
    event_type TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    trigger TEXT,
    skill_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""", "CREATE TABLE")
run("CREATE INDEX IF NOT EXISTS idx_evo_fact ON evolution_log(fact_id)", "idx_evo_fact")
run("CREATE INDEX IF NOT EXISTS idx_evo_type ON evolution_log(event_type)", "idx_evo_type")
run("CREATE INDEX IF NOT EXISTS idx_evo_time ON evolution_log(created_at DESC)", "idx_evo_time")

# 7. Metadata
print("\n[engine_metadata]")
run("INSERT OR REPLACE INTO engine_metadata (key, value, updated_at) VALUES ('version', '8.0-alpha', CURRENT_TIMESTAMP)", "version")
run("INSERT OR REPLACE INTO engine_metadata (key, value, updated_at) VALUES ('phase8a_migrated', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", "phase8a_migrated")
run("INSERT OR REPLACE INTO engine_metadata (key, value, updated_at) VALUES ('activation_threshold', '0.6', CURRENT_TIMESTAMP)", "threshold")
run("INSERT OR REPLACE INTO engine_metadata (key, value, updated_at) VALUES ('surface_buffer_max', '50', CURRENT_TIMESTAMP)", "buffer_max")
run("INSERT OR REPLACE INTO engine_metadata (key, value, updated_at) VALUES ('surface_ttl_minutes', '30', CURRENT_TIMESTAMP)", "ttl")

conn.commit()

# Verify
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

cols = [c[1] for c in conn.execute("PRAGMA table_info(quantum_facts)").fetchall()]
expected_cols = [c[0] for c in alters]
ok_cols = sum(1 for c in expected_cols if c in cols)
print(f"\n  quantum_facts: {ok_cols}/{len(expected_cols)} new columns")

for t in ['surface_buffer', 'context_state', 'co_access_patterns', 'evolution_log']:
    exists = conn.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE name='{t}'").fetchone()[0]
    print(f"  {t}: {'ok' if exists else 'MISSING'}")

ver = conn.execute("SELECT value FROM engine_metadata WHERE key='version'").fetchone()
print(f"\n  Engine version: {ver[0]}")

conn.close()
print("\nDone.")
