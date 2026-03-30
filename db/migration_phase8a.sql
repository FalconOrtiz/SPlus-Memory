-- Phase 8A: Deep Layer — Reverse-Flow Self-Evolving Memory
-- Migration: adds activation scoring, surface buffer, context state
-- Date: 2026-03-23

-- ═══════════════════════════════════════════════════════════
-- 1. ACTIVATION SCORING on quantum_facts
-- ═══════════════════════════════════════════════════════════

-- Core activation score (recalculated by Deep Layer)
ALTER TABLE quantum_facts ADD COLUMN activation_score REAL DEFAULT 0.0;

-- Component scores for transparency/debugging
ALTER TABLE quantum_facts ADD COLUMN ctx_match_score REAL DEFAULT 0.0;    -- context relevance
ALTER TABLE quantum_facts ADD COLUMN co_access_score REAL DEFAULT 0.0;    -- co-occurrence weight
ALTER TABLE quantum_facts ADD COLUMN evolution_score REAL DEFAULT 0.0;    -- confirmation/refinement
ALTER TABLE quantum_facts ADD COLUMN confidence REAL DEFAULT 0.5;         -- evolves with use

-- Versioning chain (Supermemory-inspired)
ALTER TABLE quantum_facts ADD COLUMN supersedes_id TEXT;          -- this fact replaces which fact
ALTER TABLE quantum_facts ADD COLUMN superseded_by TEXT;          -- which fact replaced this one
ALTER TABLE quantum_facts ADD COLUMN version_chain TEXT;          -- JSON: ordered list of fact IDs in chain

-- Dual timestamps (Supermemory-inspired)
ALTER TABLE quantum_facts ADD COLUMN document_date TIMESTAMP;    -- when it was said/written
ALTER TABLE quantum_facts ADD COLUMN event_date TEXT;             -- JSON array: when events occur

-- Activation metadata
ALTER TABLE quantum_facts ADD COLUMN last_activated TIMESTAMP;
ALTER TABLE quantum_facts ADD COLUMN activation_count INTEGER DEFAULT 0;
ALTER TABLE quantum_facts ADD COLUMN last_context_hash TEXT;      -- avoid redundant recalcs

-- Index for fast activation queries (reverse-flow: bottom-up)
CREATE INDEX IF NOT EXISTS idx_qf_activation ON quantum_facts(activation_score DESC)
    WHERE status NOT IN ('abandoned');
CREATE INDEX IF NOT EXISTS idx_qf_supersedes ON quantum_facts(supersedes_id);
CREATE INDEX IF NOT EXISTS idx_qf_confidence ON quantum_facts(confidence DESC);


-- ═══════════════════════════════════════════════════════════
-- 2. SURFACE BUFFER — pre-activated facts ready for injection
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS surface_buffer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL,
    activation_score REAL NOT NULL,
    domain TEXT,                     -- active domain that triggered it
    trigger_type TEXT NOT NULL,      -- 'context', 'co_access', 'temporal', 'pattern', 'manual'
    injected_text TEXT,              -- pre-formatted text for prompt injection
    token_estimate INTEGER,          -- approximate token count
    surfaced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,            -- auto-expire stale activations
    consumed INTEGER DEFAULT 0,      -- 1 if agent already consumed this
    FOREIGN KEY(fact_id) REFERENCES quantum_facts(id)
);

CREATE INDEX IF NOT EXISTS idx_sb_active ON surface_buffer(consumed, activation_score DESC);
CREATE INDEX IF NOT EXISTS idx_sb_expires ON surface_buffer(expires_at);
CREATE INDEX IF NOT EXISTS idx_sb_domain ON surface_buffer(domain);


-- ═══════════════════════════════════════════════════════════
-- 3. CONTEXT STATE — what the system "sees" right now
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS context_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context_hash TEXT UNIQUE,        -- hash of current context fingerprint
    active_domains TEXT,             -- JSON array: ["deployment", "ai_agents"]
    active_entities TEXT,            -- JSON array: ["stripe", "hermes", "ssh"]
    active_skills TEXT,              -- JSON array: skill names in use
    active_agent TEXT,               -- which agent is active
    session_id TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    facts_activated INTEGER DEFAULT 0,  -- how many facts were triggered
    metadata TEXT                    -- JSON: additional signals
);

CREATE INDEX IF NOT EXISTS idx_cs_hash ON context_state(context_hash);
CREATE INDEX IF NOT EXISTS idx_cs_detected ON context_state(detected_at DESC);


-- ═══════════════════════════════════════════════════════════
-- 4. CO-ACCESS PATTERNS — facts that activate together
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS co_access_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id_a TEXT NOT NULL,
    fact_id_b TEXT NOT NULL,
    co_access_count INTEGER DEFAULT 1,    -- times accessed together
    strength REAL DEFAULT 0.1,            -- 0-1, grows with co_access_count
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fact_id_a, fact_id_b)
);

CREATE INDEX IF NOT EXISTS idx_co_a ON co_access_patterns(fact_id_a, strength DESC);
CREATE INDEX IF NOT EXISTS idx_co_b ON co_access_patterns(fact_id_b, strength DESC);


-- ═══════════════════════════════════════════════════════════
-- 5. EVOLUTION LOG — track how memory self-improves
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS evolution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT,
    event_type TEXT NOT NULL,         -- 'activated', 'confirmed', 'superseded',
                                      -- 'consolidated', 'confidence_up', 'confidence_down',
                                      -- 'pattern_detected', 'archived_auto'
    old_value TEXT,
    new_value TEXT,
    trigger TEXT,                     -- what caused this evolution
    skill_name TEXT,                  -- which evolution skill ran
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evo_fact ON evolution_log(fact_id);
CREATE INDEX IF NOT EXISTS idx_evo_type ON evolution_log(event_type);
CREATE INDEX IF NOT EXISTS idx_evo_time ON evolution_log(created_at DESC);


-- ═══════════════════════════════════════════════════════════
-- 6. Update engine metadata
-- ═══════════════════════════════════════════════════════════

INSERT OR REPLACE INTO engine_metadata (key, value, updated_at)
VALUES
    ('version', '8.0-alpha'),
    ('phase8a_migrated', CURRENT_TIMESTAMP),
    ('activation_threshold', '0.6'),
    ('surface_buffer_max', '50'),
    ('surface_ttl_minutes', '30');
