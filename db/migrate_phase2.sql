-- Phase 2 Decay Automation Migration
-- Adds columns for temporal decay and freshness tier tracking

-- Add columns to quantum_facts if they don't exist
ALTER TABLE quantum_facts ADD COLUMN decay_weight REAL DEFAULT 1.0;
ALTER TABLE quantum_facts ADD COLUMN freshness_tier TEXT DEFAULT 'recent';
ALTER TABLE quantum_facts ADD COLUMN archived_at TIMESTAMP DEFAULT NULL;

-- Create temporal_decay_log table if it doesn't exist
CREATE TABLE IF NOT EXISTS temporal_decay_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL,
    old_weight REAL,
    new_weight REAL,
    old_tier TEXT,
    new_tier TEXT,
    days_old INTEGER,
    archived INTEGER DEFAULT 0,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(fact_id) REFERENCES quantum_facts(id)
);

-- Create index on temporal_decay_log
CREATE INDEX IF NOT EXISTS idx_decay_log_fact_id ON temporal_decay_log(fact_id);
CREATE INDEX IF NOT EXISTS idx_decay_log_created_at ON temporal_decay_log(created_at);

-- Create fact_embeddings table if it doesn't exist
CREATE TABLE IF NOT EXISTS fact_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL UNIQUE,
    embedding TEXT NOT NULL,
    dimension INTEGER,
    provider TEXT DEFAULT 'mock',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(fact_id) REFERENCES quantum_facts(id)
);

-- Create index on fact_embeddings
CREATE INDEX IF NOT EXISTS idx_embeddings_fact_id ON fact_embeddings(fact_id);

-- Backfill decay_weight (1.0 for all) and freshness_tier (recent for all)
UPDATE quantum_facts SET decay_weight = 1.0, freshness_tier = 'recent' WHERE status NOT IN ('abandoned');
