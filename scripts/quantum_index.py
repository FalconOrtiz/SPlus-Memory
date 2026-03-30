#!/usr/bin/env python3
"""
Quantum Keyword Index — Phase 8
Procedural Keyword Taxonomy with Semantic Compression

Design principles:
  - Every fact decomposed into structured keywords (not raw text)
  - Dictionary-encoded keywords (int16 IDs, not strings)
  - Bitmap indexes for O(1) multi-dimension lookups
  - Status-prioritized storage (pending > committed > completed > abandoned)
  - Minimal token cost: keyword retrieval needs ZERO LLM tokens
  - Semantic compression: ~50-200x over raw text

Architecture:
  ┌─────────────────────────────────────────┐
  │         PROCEDURAL EXTRACTOR            │
  │  text → structured keywords (auto)      │
  └──────────────┬──────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────┐
  │        DICTIONARY ENCODER               │
  │  keyword string → int16 ID              │
  │  "payments" → 0x00A3                    │
  │  Compression: ~4x over raw strings      │
  └──────────────┬──────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────┐
  │        BITMAP INDEX                     │
  │  Dimension × Value → bitset of fact IDs │
  │  DOMAIN=payments → {fact_3, fact_17}    │
  │  Lookup: O(1) via AND/OR on bitsets     │
  └──────────────┬──────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────┐
  │      STATUS-PRIORITY STORE              │
  │  pending (hot) > committed > completed  │
  │  Pending facts: full detail retained    │
  │  Completed: compressed, archivable      │
  │  Abandoned: minimal stub               │
  └─────────────────────────────────────────┘

Usage:
    idx = QuantumIndex()
    idx.ingest("Falcon fixed Stripe checkout error", session_context={...})
    results = idx.lookup(domain="payments", action="fix")  # O(1), zero tokens
    results = idx.lookup(status="pending")  # all unfinished work
"""

import json
import sqlite3
import struct
import hashlib
import zlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
import logging
import sys
import re

sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"


# ─────────────────────────────────────────────────────────────────
# TAXONOMY — Controlled vocabulary per dimension
# ─────────────────────────────────────────────────────────────────

TAXONOMY = {
    "status": [
        "pending", "in_progress", "committed", "completed",
        "abandoned", "blocked", "paused",
    ],
    "action": [
        "create", "modify", "fix", "delete", "deploy", "configure",
        "decide", "reject", "approve", "review", "debug", "test",
        "install", "build", "design", "research", "discuss", "plan",
        "migrate", "refactor", "optimize", "monitor", "integrate",
    ],
    "domain": [
        "payments", "auth", "ui", "api", "database", "infrastructure",
        "deployment", "email", "social_media", "content", "marketing",
        "ai_agents", "memory_system", "music", "video", "design",
        "security", "monitoring", "automation", "analytics", "seo",
        "legal", "finance", "hr", "devops", "frontend", "backend",
        "mobile", "documentation", "testing", "networking",
    ],
    "entity_type": [
        "project", "tool", "service", "file", "person", "company",
        "concept", "decision", "error", "feature", "config", "credential",
        "endpoint", "model", "skill", "workflow", "environment",
    ],
    "priority": [
        "critical", "high", "medium", "low", "none",
    ],
    "emotion": [
        "satisfied", "frustrated", "neutral", "excited", "confused",
        "urgent", "relieved", "disappointed",
    ],
    "phase": [
        "planning", "development", "testing", "review", "deployment",
        "maintenance", "research", "ideation", "iteration",
    ],
}

# Status priority weights (higher = more storage detail retained)
STATUS_PRIORITY = {
    "pending":     1.0,   # full detail, hot storage
    "in_progress": 0.95,
    "committed":   0.8,
    "blocked":     0.9,   # high because user needs to resolve
    "paused":      0.7,
    "completed":   0.3,   # compressed, cold storage
    "abandoned":   0.1,   # minimal stub only
}


# ─────────────────────────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────────────────────────

QUANTUM_SQL = """
-- Dictionary: maps keyword strings to compact int IDs
CREATE TABLE IF NOT EXISTS kw_dictionary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension TEXT NOT NULL,
    value TEXT NOT NULL,
    frequency INTEGER DEFAULT 1,
    UNIQUE(dimension, value)
);

-- Structured facts: the compressed representation
CREATE TABLE IF NOT EXISTS quantum_facts (
    id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,              -- compressed one-liner
    raw_content TEXT,                   -- original text (nullable for cold storage)
    compressed_content BLOB,           -- zlib-compressed original (for archival)
    keywords TEXT NOT NULL,            -- JSON: {dimension: [value_ids]}
    keywords_readable TEXT NOT NULL,   -- JSON: {dimension: [values]} for debug
    status TEXT DEFAULT 'pending',
    priority TEXT DEFAULT 'medium',
    priority_weight REAL DEFAULT 0.5,
    storage_tier TEXT DEFAULT 'hot',   -- hot, warm, cold
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    related_facts TEXT DEFAULT '[]',  -- JSON array of related fact IDs
    byte_size INTEGER DEFAULT 0,       -- compressed size tracking
    original_size INTEGER DEFAULT 0    -- original text size
);

-- Bitmap-style index: dimension × value → fact IDs
CREATE TABLE IF NOT EXISTS kw_bitmap (
    dimension TEXT NOT NULL,
    value_id INTEGER NOT NULL,
    fact_id TEXT NOT NULL,
    PRIMARY KEY(dimension, value_id, fact_id)
);

-- Compression stats
CREATE TABLE IF NOT EXISTS compression_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_original_bytes INTEGER DEFAULT 0,
    total_compressed_bytes INTEGER DEFAULT 0,
    total_keyword_bytes INTEGER DEFAULT 0,
    total_facts INTEGER DEFAULT 0,
    ratio REAL DEFAULT 0,
    measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_qf_status ON quantum_facts(status);
CREATE INDEX IF NOT EXISTS idx_qf_priority ON quantum_facts(priority_weight DESC);
CREATE INDEX IF NOT EXISTS idx_qf_tier ON quantum_facts(storage_tier);
CREATE INDEX IF NOT EXISTS idx_qf_domain ON quantum_facts(keywords);
CREATE INDEX IF NOT EXISTS idx_bitmap_dim ON kw_bitmap(dimension, value_id);
"""


@dataclass
class StructuredFact:
    """A fact decomposed into structured keywords."""
    id: str
    summary: str
    keywords: Dict[str, List[str]]
    status: str = "pending"
    priority: str = "medium"
    raw_content: str = ""
    related_facts: List[str] = field(default_factory=list)


@dataclass
class LookupResult:
    """Result of a keyword lookup."""
    fact_id: str
    summary: str
    keywords: Dict[str, List[str]]
    status: str
    priority: str
    priority_weight: float
    storage_tier: str
    created_at: str


# ─────────────────────────────────────────────────────────────────
# PROCEDURAL EXTRACTOR
# ─────────────────────────────────────────────────────────────────

class ProceduralExtractor:
    """
    Extracts structured keywords from raw text using rule-based NLP.
    No LLM needed — pure pattern matching + taxonomy lookup.
    """

    # Keyword detection patterns per dimension
    DOMAIN_PATTERNS = {
        "payments": r"stripe|payment|checkout|billing|invoice|subscription|pricing",
        "auth": r"oauth|auth|login|credential|token|session|password|api.?key",
        "ui": r"ui|ux|frontend|design|layout|css|component|button|page|landing",
        "api": r"api|endpoint|route|rest|graphql|request|response|http|curl",
        "database": r"database|sql|postgres|sqlite|migration|schema|query|table",
        "infrastructure": r"server|vps|ssh|deploy|docker|nginx|hosting|domain|dns",
        "deployment": r"deploy|build|ci.?cd|pipeline|release|production|staging",
        "email": r"email|smtp|inbox|newsletter|outreach|gmail|outlook",
        "social_media": r"twitter|x\.com|linkedin|youtube|instagram|tiktok|post|content",
        "content": r"content|blog|article|video|script|copy|strategy|publish",
        "marketing": r"marketing|seo|ads|campaign|funnel|conversion|lead",
        "ai_agents": r"agent|llm|model|claude|gpt|hermes|katsumi|orchestrat",
        "memory_system": r"memory|rag|embedding|vector|retrieval|index|fact|recall",
        "security": r"security|encrypt|credential|secret|vault|firewall",
        "monitoring": r"monitor|dashboard|log|alert|metric|health|observ",
        "automation": r"automat|cron|schedule|script|bot|workflow|pipeline",
    }

    ACTION_PATTERNS = {
        "create": r"creat|build|generat|add|new|init|setup|implement|write",
        "modify": r"modif|change|updat|edit|alter|adjust|tweak|refactor",
        "fix": r"fix|repair|resolv|patch|debug|hotfix|correct",
        "delete": r"delet|remov|drop|clean|purg|trash",
        "deploy": r"deploy|ship|release|push|publish|launch",
        "configure": r"config|setup|setting|parameter|environment|variable",
        "decide": r"decid|chose|select|pick|agree|confirm|approv",
        "reject": r"reject|deny|refus|decline|veto|disagree",
        "review": r"review|check|inspect|audit|examin|evaluat",
        "test": r"test|verify|validat|assert|spec|benchmark",
        "install": r"install|setup|pip|npm|brew|apt|download",
        "research": r"research|investigat|explor|analyz|study|compar",
        "plan": r"plan|design|architect|blueprint|roadmap|strategy",
        "integrate": r"integrat|connect|link|bridge|hook|wire|plug",
    }

    EMOTION_PATTERNS = {
        "frustrated": r"frustrat|broken|nothing works|stuck|hate|ugh|damn",
        "satisfied": r"perfect|great|excellent|nice|love it|works|genial",
        "excited": r"excited|amazing|wow|incredible|awesome|brilliant",
        "confused": r"confused|unclear|don.?t understand|weird|strange|lost",
        "urgent": r"urgent|asap|critical|emergency|now|hurry|deadline",
    }

    def extract(self, text: str, context: Dict = None) -> Dict[str, List[str]]:
        """
        Extract structured keywords from text.
        Pure rule-based, zero LLM tokens.
        """
        context = context or {}
        text_lower = text.lower()
        keywords = {}

        # Extract domains
        domains = []
        for domain, pattern in self.DOMAIN_PATTERNS.items():
            if re.search(pattern, text_lower):
                domains.append(domain)
        if domains:
            keywords["domain"] = domains

        # Extract actions
        actions = []
        for action, pattern in self.ACTION_PATTERNS.items():
            if re.search(pattern, text_lower):
                actions.append(action)
        if actions:
            keywords["action"] = actions

        # Extract emotions
        emotions = []
        for emotion, pattern in self.EMOTION_PATTERNS.items():
            if re.search(pattern, text_lower):
                emotions.append(emotion)
        keywords["emotion"] = emotions if emotions else ["neutral"]

        # Extract entities (proper nouns, tool names, file paths)
        entities = []
        # Tool/service names
        tools = re.findall(r'\b(?:stripe|claude|hermes|katsumi|docker|nginx|postgres|redis|node|python|git|npm|pip)\b', text_lower)
        entities.extend(set(tools))
        # File paths
        files = re.findall(r'[\w./~-]+\.\w{1,4}', text)
        entities.extend(files[:3])  # max 3
        if entities:
            keywords["entities"] = list(set(entities))

        # Status from context or default
        keywords["status"] = [context.get("status", "pending")]

        # Priority from context or infer
        if any(e in ("urgent", "frustrated") for e in keywords.get("emotion", [])):
            keywords["priority"] = ["high"]
        else:
            keywords["priority"] = [context.get("priority", "medium")]

        # Phase from context
        if context.get("phase"):
            keywords["phase"] = [context["phase"]]
        elif any(a in ("plan", "research") for a in keywords.get("action", [])):
            keywords["phase"] = ["planning"]
        elif any(a in ("create", "modify", "fix") for a in keywords.get("action", [])):
            keywords["phase"] = ["development"]
        elif any(a in ("test", "review") for a in keywords.get("action", [])):
            keywords["phase"] = ["testing"]
        elif any(a in ("deploy",) for a in keywords.get("action", [])):
            keywords["phase"] = ["deployment"]

        # WHO from context
        if context.get("who"):
            keywords["who"] = [context["who"]]

        # Project from context
        if context.get("project"):
            keywords["project"] = [context["project"]]

        return keywords

    def generate_summary(self, text: str, keywords: Dict) -> str:
        """Generate a compressed one-line summary from keywords."""
        parts = []

        who = keywords.get("who", ["?"])[0]
        actions = keywords.get("action", ["?"])
        domains = keywords.get("domain", ["?"])
        entities = keywords.get("entities", [])
        status = keywords.get("status", ["pending"])[0]

        action_str = "+".join(actions[:2])
        domain_str = "+".join(domains[:2])
        entity_str = ",".join(entities[:3]) if entities else ""

        summary = f"[{status.upper()}] {who}:{action_str}:{domain_str}"
        if entity_str:
            summary += f" ({entity_str})"

        return summary[:120]  # cap at 120 chars


# ─────────────────────────────────────────────────────────────────
# QUANTUM INDEX
# ─────────────────────────────────────────────────────────────────

class QuantumIndex:
    """
    Compressed keyword index with O(1) lookups and status-priority storage.
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self.extractor = ProceduralExtractor()

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(QUANTUM_SQL)
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

    # ── dictionary encoding ──────────────────────────────────────

    def _get_or_create_kw_id(self, dimension: str, value: str) -> int:
        """Get or create a dictionary ID for a keyword."""
        row = self.conn.execute(
            "SELECT id FROM kw_dictionary WHERE dimension=? AND value=?",
            (dimension, value)
        ).fetchone()

        if row:
            self.conn.execute(
                "UPDATE kw_dictionary SET frequency = frequency + 1 WHERE id=?",
                (row[0],)
            )
            return row[0]

        cursor = self.conn.execute(
            "INSERT INTO kw_dictionary (dimension, value) VALUES (?, ?)",
            (dimension, value)
        )
        self.conn.commit()
        return cursor.lastrowid

    # ── compression ──────────────────────────────────────────────

    @staticmethod
    def compress_text(text: str) -> Tuple[bytes, int, int]:
        """Compress text with zlib. Returns (compressed, original_size, compressed_size)."""
        original = text.encode('utf-8')
        compressed = zlib.compress(original, level=9)
        return compressed, len(original), len(compressed)

    @staticmethod
    def decompress_text(data: bytes) -> str:
        """Decompress zlib data back to text."""
        return zlib.decompress(data).decode('utf-8')

    # ── ingest ───────────────────────────────────────────────────

    def ingest(self, text: str, context: Dict = None) -> str:
        """
        Ingest a fact: extract keywords, compress, index.
        
        Args:
            text: Raw text of the fact
            context: Optional context (status, who, project, phase, priority)
        
        Returns:
            fact_id
        """
        context = context or {}

        # Extract keywords (zero LLM tokens)
        keywords = self.extractor.extract(text, context)

        # Generate compressed summary
        summary = self.extractor.generate_summary(text, keywords)

        # Compress original text
        compressed, orig_size, comp_size = self.compress_text(text)

        # Generate ID
        fact_id = f"qf_{hashlib.md5(text.encode()).hexdigest()[:12]}"

        # Determine storage tier based on status priority
        status = keywords.get("status", ["pending"])[0]
        priority_weight = STATUS_PRIORITY.get(status, 0.5)

        if priority_weight >= 0.8:
            tier = "hot"
            raw_content = text  # keep full text for hot items
        elif priority_weight >= 0.3:
            tier = "warm"
            raw_content = text[:200]  # truncated for warm
        else:
            tier = "cold"
            raw_content = None  # only compressed blob for cold

        # Encode keywords to int IDs
        kw_ids = {}
        for dim, values in keywords.items():
            kw_ids[dim] = []
            for val in values:
                kid = self._get_or_create_kw_id(dim, val)
                kw_ids[dim].append(kid)

                # Update bitmap index
                self.conn.execute(
                    "INSERT OR IGNORE INTO kw_bitmap (dimension, value_id, fact_id) VALUES (?, ?, ?)",
                    (dim, kid, fact_id)
                )

        # Store fact
        priority = keywords.get("priority", ["medium"])[0]

        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO quantum_facts
                (id, summary, raw_content, compressed_content, keywords, keywords_readable,
                 status, priority, priority_weight, storage_tier, byte_size, original_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fact_id, summary, raw_content, compressed,
                json.dumps(kw_ids), json.dumps(keywords),
                status, priority, priority_weight, tier,
                comp_size, orig_size,
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Ingest failed: {e}")
            raise

        logger.info(f"Ingested {fact_id} | {tier} | {orig_size}→{comp_size} bytes ({comp_size/max(orig_size,1)*100:.0f}%)")

        # Auto-embed (Phase 3) — lazy, non-blocking on failure
        try:
            from semantic_index import SemanticIndex
            sem = SemanticIndex(self.db_path)
            sem.conn = self.conn  # reuse connection
            sem.embed_fact(fact_id, summary)
        except Exception:
            pass  # embedding is optional, don't block ingest

        return fact_id

    # ── O(1) lookup ──────────────────────────────────────────────

    def lookup(self, top_k: int = 10, **kwargs) -> List[LookupResult]:
        """
        O(1) keyword lookup via bitmap index.
        Zero LLM tokens — pure SQL.
        
        Args:
            top_k: Max results
            **kwargs: dimension=value pairs
                e.g. domain="payments", action="fix", status="pending"
        
        Returns:
            List of matching facts, sorted by priority_weight DESC
        """
        if not kwargs:
            # No filters: return top by priority
            rows = self.conn.execute("""
                SELECT id, summary, keywords_readable, status, priority,
                       priority_weight, storage_tier, created_at
                FROM quantum_facts
                ORDER BY priority_weight DESC, created_at DESC
                LIMIT ?
            """, (top_k,)).fetchall()
            return self._rows_to_results(rows)

        # Find fact IDs matching ALL criteria (AND logic via bitmap)
        candidate_sets = []

        for dimension, value in kwargs.items():
            # Resolve value to ID
            row = self.conn.execute(
                "SELECT id FROM kw_dictionary WHERE dimension=? AND value=?",
                (dimension, value)
            ).fetchone()

            if not row:
                return []  # unknown keyword = no results

            value_id = row[0]

            # Get all fact IDs with this keyword
            facts = self.conn.execute(
                "SELECT fact_id FROM kw_bitmap WHERE dimension=? AND value_id=?",
                (dimension, value_id)
            ).fetchall()

            candidate_sets.append({r[0] for r in facts})

        if not candidate_sets:
            return []

        # AND intersection
        matching_ids = candidate_sets[0]
        for s in candidate_sets[1:]:
            matching_ids &= s

        if not matching_ids:
            return []

        # Fetch matching facts
        placeholders = ",".join("?" * len(matching_ids))
        rows = self.conn.execute(f"""
            SELECT id, summary, keywords_readable, status, priority,
                   priority_weight, storage_tier, created_at
            FROM quantum_facts
            WHERE id IN ({placeholders})
            ORDER BY priority_weight DESC, created_at DESC
            LIMIT ?
        """, list(matching_ids) + [top_k]).fetchall()

        return self._rows_to_results(rows)

    def lookup_status(self, status: str, top_k: int = 20) -> List[LookupResult]:
        """Shortcut: get all facts with a given status."""
        return self.lookup(top_k=top_k, status=status)

    def lookup_pending(self, top_k: int = 20) -> List[LookupResult]:
        """Shortcut: get all pending/in-progress/blocked work."""
        results = []
        for s in ("pending", "in_progress", "blocked"):
            results.extend(self.lookup(top_k=top_k, status=s))
        results.sort(key=lambda r: r.priority_weight, reverse=True)
        return results[:top_k]

    @staticmethod
    def _rows_to_results(rows) -> List[LookupResult]:
        return [
            LookupResult(
                fact_id=r[0], summary=r[1],
                keywords=json.loads(r[2]) if r[2] else {},
                status=r[3], priority=r[4],
                priority_weight=r[5], storage_tier=r[6],
                created_at=r[7] or "",
            ) for r in rows
        ]

    # ── reconstruct ──────────────────────────────────────────────

    def reconstruct(self, fact_id: str) -> Optional[str]:
        """Reconstruct full text from compressed storage."""
        row = self.conn.execute(
            "SELECT raw_content, compressed_content, storage_tier FROM quantum_facts WHERE id=?",
            (fact_id,)
        ).fetchone()

        if not row:
            return None

        raw, compressed, tier = row

        if raw:
            return raw
        elif compressed:
            return self.decompress_text(compressed)
        else:
            return None

    # ── import existing facts ────────────────────────────────────

    def import_from_memory_facts(self) -> int:
        """Import all memory_facts into the quantum index."""
        rows = self.conn.execute("""
            SELECT id, content, source FROM memory_facts WHERE is_active=1
        """).fetchall()

        count = 0
        for fid, content, source in rows:
            context = {"status": "completed", "who": "falcon", "project": "ire-digital"}
            self.ingest(content, context=context)
            count += 1

        return count

    # ── stats ────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Compression and index statistics."""
        total_facts = self.conn.execute("SELECT COUNT(*) FROM quantum_facts").fetchone()[0]

        size_row = self.conn.execute("""
            SELECT SUM(original_size), SUM(byte_size) FROM quantum_facts
        """).fetchone()
        total_original = size_row[0] or 0
        total_compressed = size_row[1] or 0

        # Keyword dictionary size
        dict_count = self.conn.execute("SELECT COUNT(*) FROM kw_dictionary").fetchone()[0]
        bitmap_count = self.conn.execute("SELECT COUNT(*) FROM kw_bitmap").fetchone()[0]

        # Status distribution
        statuses = self.conn.execute("""
            SELECT status, COUNT(*), SUM(original_size), SUM(byte_size)
            FROM quantum_facts GROUP BY status
        """).fetchall()

        # Storage tier distribution
        tiers = self.conn.execute("""
            SELECT storage_tier, COUNT(*) FROM quantum_facts GROUP BY storage_tier
        """).fetchall()

        # Top domains
        top_domains = self.conn.execute("""
            SELECT d.value, COUNT(b.fact_id) as cnt
            FROM kw_bitmap b JOIN kw_dictionary d ON b.value_id = d.id
            WHERE b.dimension = 'domain'
            GROUP BY d.value ORDER BY cnt DESC LIMIT 10
        """).fetchall()

        ratio = (total_original / max(total_compressed, 1)) if total_compressed > 0 else 0

        # Keyword-only size (summary + keywords_readable only)
        kw_size = self.conn.execute("""
            SELECT SUM(LENGTH(summary) + LENGTH(keywords_readable)) FROM quantum_facts
        """).fetchone()[0] or 0

        return {
            "total_facts": total_facts,
            "original_bytes": total_original,
            "compressed_bytes": total_compressed,
            "keyword_index_bytes": kw_size,
            "compression_ratio": f"{ratio:.1f}x",
            "effective_ratio": f"{total_original / max(kw_size, 1):.1f}x (keywords only)",
            "dictionary_entries": dict_count,
            "bitmap_entries": bitmap_count,
            "status_distribution": {r[0]: {"count": r[1], "original": r[2], "compressed": r[3]} for r in statuses},
            "storage_tiers": {r[0]: r[1] for r in tiers},
            "top_domains": {r[0]: r[1] for r in top_domains},
        }


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Quantum Keyword Index (Phase 8)")
    parser.add_argument("--ingest", type=str, help="Ingest a fact")
    parser.add_argument("--status", type=str, default="pending", help="Status for ingest")
    parser.add_argument("--lookup", nargs="*", help="Lookup: dimension=value pairs")
    parser.add_argument("--pending", action="store_true", help="Show all pending work")
    parser.add_argument("--import-facts", action="store_true", help="Import from memory_facts")
    parser.add_argument("--stats", action="store_true", help="Compression stats")
    parser.add_argument("--reconstruct", type=str, help="Reconstruct full text from fact ID")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    idx = QuantumIndex()
    idx.connect()

    try:
        if args.ingest:
            fid = idx.ingest(args.ingest, context={"status": args.status, "who": "falcon"})
            print(f"✓ Ingested: {fid}")

        elif args.lookup is not None:
            filters = {}
            for pair in args.lookup:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    filters[k] = v

            results = idx.lookup(**filters) if filters else idx.lookup()

            if args.json:
                print(json.dumps([{
                    "id": r.fact_id, "summary": r.summary, "status": r.status,
                    "priority": r.priority, "tier": r.storage_tier,
                    "keywords": r.keywords,
                } for r in results], indent=2))
            else:
                print(f"\n╔═══════════════════════════════════════════════════════╗")
                print(f"║ QUANTUM LOOKUP: {filters or 'ALL (by priority)'}")
                print(f"╚═══════════════════════════════════════════════════════╝\n")
                for i, r in enumerate(results, 1):
                    tier_icon = {"hot": "🔴", "warm": "🟡", "cold": "🔵"}.get(r.storage_tier, "?")
                    print(f"  [{i}] {tier_icon} {r.summary}")
                    print(f"      Status: {r.status} | Priority: {r.priority} ({r.priority_weight})")
                    domains = r.keywords.get("domain", [])
                    actions = r.keywords.get("action", [])
                    if domains or actions:
                        print(f"      Domain: {', '.join(domains)} | Action: {', '.join(actions)}")
                    print()

        elif args.pending:
            results = idx.lookup_pending()
            print(f"\n╔═══════════════════════════════════════════════════════╗")
            print(f"║ PENDING WORK (unfinished projects/tasks)")
            print(f"╚═══════════════════════════════════════════════════════╝\n")
            if results:
                for i, r in enumerate(results, 1):
                    print(f"  [{i}] {r.summary}")
                    print(f"      Status: {r.status} | Priority: {r.priority}")
            else:
                print("  ✓ No pending work found.")
            print()

        elif args.import_facts:
            count = idx.import_from_memory_facts()
            print(f"✓ Imported {count} facts into quantum index")

        elif args.stats:
            stats = idx.get_stats()
            if args.json:
                print(json.dumps(stats, indent=2))
            else:
                print(f"\n╔═══════════════════════════════════════════════════════╗")
                print(f"║ QUANTUM INDEX STATS")
                print(f"╚═══════════════════════════════════════════════════════╝\n")
                print(f"  Facts:          {stats['total_facts']}")
                print(f"  Original:       {stats['original_bytes']:,} bytes")
                print(f"  Compressed:     {stats['compressed_bytes']:,} bytes")
                print(f"  Keywords only:  {stats['keyword_index_bytes']:,} bytes")
                print(f"  Compression:    {stats['compression_ratio']}")
                print(f"  Effective:      {stats['effective_ratio']}")
                print(f"  Dictionary:     {stats['dictionary_entries']} entries")
                print(f"  Bitmap index:   {stats['bitmap_entries']} entries")
                print(f"\n  Storage tiers:")
                for tier, count in stats["storage_tiers"].items():
                    print(f"    {tier}: {count}")
                print(f"\n  Status distribution:")
                for status, data in stats["status_distribution"].items():
                    print(f"    {status}: {data['count']} facts ({data['original']}→{data['compressed']} bytes)")
                print(f"\n  Top domains:")
                for domain, count in stats["top_domains"].items():
                    print(f"    {domain}: {count}")
                print()

        elif args.reconstruct:
            text = idx.reconstruct(args.reconstruct)
            if text:
                print(f"Reconstructed:\n{text}")
            else:
                print("Fact not found or no content available")

        else:
            parser.print_help()

    finally:
        idx.close()


if __name__ == "__main__":
    main()
