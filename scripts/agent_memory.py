#!/usr/bin/env python3
"""
Multi-Agent Memory Coherence for Hermes Memory Engine (Phase 6)

Isolates memory between agent identities while maintaining a shared layer.

Architecture:
    ┌─────────────────────────────────────────┐
    │           SHARED MEMORY LAYER           │
    │  (facts both agents need to know)       │
    └──────────┬──────────────┬───────────────┘
               │              │
    ┌──────────▼──────┐  ┌────▼──────────────┐
    │  HERMES MEMORY  │  │  HERMES MEMORY   │
    │  (main session) │  │  (telegram groups) │
    │  - full access  │  │  - group context   │
    │  - sensitive ok  │  │  - no secrets      │
    │  - all sources  │  │  - social context  │
    └─────────────────┘  └───────────────────┘

Agents:
    hermes  — Main session, full access, sensitive data ok
    hermes_agent — Telegram groups, social context, no secrets

Rules:
    - Each agent has a private memory scope
    - Shared facts are visible to both
    - Secrets/credentials never cross to hermes_agent
    - Conflicts between agents are detected and flagged
    - Cross-agent sharing requires explicit SHARE_WITH tag

Usage:
    mgr = AgentMemoryManager()
    mgr.add_fact("API key is xyz", agent="hermes", scope="private")
    mgr.add_fact("Falcon likes coffee", agent="hermes", scope="shared")
    
    # Hermes sees shared facts only
    facts = mgr.get_facts(agent="hermes_agent")
    
    # Hermes sees everything (own + shared)
    facts = mgr.get_facts(agent="hermes")

CLI:
    python3 agent_memory.py --add "fact" --agent hermes --scope private
    python3 agent_memory.py --query "search" --agent hermes_agent
    python3 agent_memory.py --share fact_id --with hermes_agent
    python3 agent_memory.py --conflicts
    python3 agent_memory.py --stats
"""

import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import logging
import sys

sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

AGENTS = {
    "hermes": {
        "description": "Main session agent, full access",
        "can_see": ["private", "shared"],
        "can_write": ["private", "shared"],
        "sensitive_access": True,
    },
    "hermes_agent": {
        "description": "Telegram group agent, social context only",
        "can_see": ["shared"],       # cannot see hermes-private
        "can_write": ["private", "shared"],
        "sensitive_access": False,   # never gets secrets
    },
}

# Patterns that indicate sensitive content (never share with hermes_agent)
SENSITIVE_PATTERNS = [
    r"api[_\s-]?key",
    r"password",
    r"secret",
    r"token",
    r"credential",
    r"ssh\s",
    r"\.env\b",
    r"private[_\s-]?key",
    r"\bpass\b",
    r"REDACTED",  # password pattern placeholder
]


# ─────────────────────────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────────────────────────

AGENT_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agent_facts (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    agent TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'private',
    is_sensitive BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    shared_with TEXT DEFAULT '[]',
    source_fact_id TEXT,
    FOREIGN KEY(source_fact_id) REFERENCES memory_facts(id)
);

CREATE TABLE IF NOT EXISTS agent_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    fact_a_id TEXT,
    fact_b_id TEXT,
    fact_a_content TEXT,
    fact_b_content TEXT,
    conflict_type TEXT DEFAULT 'potential',
    status TEXT DEFAULT 'unresolved',
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution TEXT
);

CREATE TABLE IF NOT EXISTS agent_share_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_facts_agent ON agent_facts(agent);
CREATE INDEX IF NOT EXISTS idx_agent_facts_scope ON agent_facts(scope);
CREATE INDEX IF NOT EXISTS idx_agent_conflicts_status ON agent_conflicts(status);
"""


@dataclass
class AgentFact:
    """A fact scoped to an agent."""
    id: str
    content: str
    agent: str
    scope: str  # "private" or "shared"
    is_sensitive: bool = False
    created_at: str = ""
    shared_with: List[str] = field(default_factory=list)


@dataclass
class Conflict:
    """A detected conflict between agents."""
    agent_a: str
    agent_b: str
    fact_a: str
    fact_b: str
    conflict_type: str
    status: str = "unresolved"


# ─────────────────────────────────────────────────────────────────
# AGENT MEMORY MANAGER
# ─────────────────────────────────────────────────────────────────

class AgentMemoryManager:
    """Manages multi-agent memory with isolation and sharing."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from embedder import Embedder
                self._embedder = Embedder()
            except Exception:
                pass
        return self._embedder

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(AGENT_TABLES_SQL)
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

    # ── sensitivity detection ────────────────────────────────────

    @staticmethod
    def is_sensitive(content: str) -> bool:
        """Detect if content contains sensitive information."""
        content_lower = content.lower()
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, content_lower):
                return True
        return False

    # ── add facts ────────────────────────────────────────────────

    def add_fact(self, content: str, agent: str, scope: str = "private",
                 force_sensitive: Optional[bool] = None) -> str:
        """
        Add a fact scoped to an agent.
        
        Args:
            content: The fact text
            agent: "hermes" or "hermes_agent"
            scope: "private" (agent-only) or "shared" (both agents)
            force_sensitive: Override auto-detection
        
        Returns:
            fact_id
        """
        if agent not in AGENTS:
            raise ValueError(f"Unknown agent: {agent}. Must be one of {list(AGENTS.keys())}")

        # Auto-detect sensitivity
        sensitive = force_sensitive if force_sensitive is not None else self.is_sensitive(content)

        # SECURITY: sensitive content from hermes_agent is blocked from shared scope
        if sensitive and scope == "shared":
            logger.warning(f"Sensitive content blocked from shared scope")
            scope = "private"

        # SECURITY: sensitive content never goes to hermes_agent
        if sensitive and agent == "hermes_agent":
            logger.warning(f"Sensitive content blocked from hermes_agent agent")
            return ""

        import hashlib
        fact_id = f"af_{hashlib.md5(content.encode()).hexdigest()[:12]}"

        # Check duplicate
        existing = self.conn.execute(
            "SELECT id FROM agent_facts WHERE id = ?", (fact_id,)
        ).fetchone()
        if existing:
            logger.info(f"Duplicate agent fact: {fact_id}")
            return fact_id

        self.conn.execute("""
            INSERT INTO agent_facts (id, content, agent, scope, is_sensitive, shared_with)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fact_id, content, agent, scope, sensitive, json.dumps([])))
        self.conn.commit()

        logger.info(f"Added agent fact: {fact_id} (agent={agent}, scope={scope}, sensitive={sensitive})")
        return fact_id

    # ── query facts ──────────────────────────────────────────────

    def get_facts(self, agent: str, query: str = None,
                  top_k: int = 10) -> List[AgentFact]:
        """
        Get facts visible to an agent.
        
        Hermes sees: own private + all shared
        Hermes sees: own private + shared (non-sensitive only)
        """
        if agent not in AGENTS:
            raise ValueError(f"Unknown agent: {agent}")

        agent_config = AGENTS[agent]

        # Build visibility query
        conditions = []
        params = []

        # Own private facts
        conditions.append("(agent = ? AND scope = 'private')")
        params.append(agent)

        # Shared facts
        if "shared" in agent_config["can_see"]:
            if agent_config["sensitive_access"]:
                conditions.append("(scope = 'shared')")
            else:
                # Hermes: shared but not sensitive
                conditions.append("(scope = 'shared' AND is_sensitive = 0)")

        # Also include facts explicitly shared with this agent
        conditions.append(f"(shared_with LIKE '%\"{agent}\"%')")

        where = " OR ".join(conditions)

        rows = self.conn.execute(f"""
            SELECT id, content, agent, scope, is_sensitive, created_at, shared_with
            FROM agent_facts
            WHERE {where}
            ORDER BY created_at DESC
        """, params).fetchall()

        facts = [
            AgentFact(
                id=r[0], content=r[1], agent=r[2], scope=r[3],
                is_sensitive=bool(r[4]), created_at=r[5] or "",
                shared_with=json.loads(r[6]) if r[6] else [],
            )
            for r in rows
        ]

        # If query provided, rank by semantic similarity
        if query and self.embedder and facts:
            query_vec = self.embedder.embed(query)
            scored = []
            for f in facts:
                fvec = self.embedder.embed(f.content)
                sim = self.embedder.cosine_similarity(query_vec, fvec)
                scored.append((f, sim))
            scored.sort(key=lambda x: x[1], reverse=True)
            facts = [f for f, _ in scored[:top_k]]
        else:
            facts = facts[:top_k]

        return facts

    # ── sharing ──────────────────────────────────────────────────

    def share_fact(self, fact_id: str, to_agent: str, reason: str = "") -> bool:
        """
        Share a fact with another agent.
        
        Security checks:
          - Sensitive facts cannot be shared with hermes_agent
          - Fact must exist
          - Target agent must be valid
        """
        if to_agent not in AGENTS:
            raise ValueError(f"Unknown agent: {to_agent}")

        row = self.conn.execute(
            "SELECT content, agent, is_sensitive, shared_with FROM agent_facts WHERE id = ?",
            (fact_id,)
        ).fetchone()

        if not row:
            logger.error(f"Fact not found: {fact_id}")
            return False

        content, from_agent, is_sensitive, shared_json = row

        # SECURITY: never share sensitive with hermes_agent
        if is_sensitive and to_agent == "hermes_agent":
            logger.warning(f"BLOCKED: Cannot share sensitive fact {fact_id} with hermes_agent")
            return False

        # Update shared_with
        shared = json.loads(shared_json) if shared_json else []
        if to_agent not in shared:
            shared.append(to_agent)
            self.conn.execute(
                "UPDATE agent_facts SET shared_with = ? WHERE id = ?",
                (json.dumps(shared), fact_id)
            )

            # Log the share
            self.conn.execute("""
                INSERT INTO agent_share_log (fact_id, from_agent, to_agent, reason)
                VALUES (?, ?, ?, ?)
            """, (fact_id, from_agent, to_agent, reason))

            self.conn.commit()
            logger.info(f"Shared {fact_id} from {from_agent} → {to_agent}")

        return True

    # ── conflict detection ───────────────────────────────────────

    def detect_conflicts(self) -> List[Conflict]:
        """
        Detect potential conflicts between agent memories.
        
        A conflict is when:
          - Two agents have facts about the same topic that contradict
          - A shared fact and a private fact disagree
          - Same entity has different values across agents
        """
        conflicts = []

        # Get all facts by agent
        hermes_facts = self.get_facts("hermes", top_k=1000)
        hermes_agent_facts = self.get_facts("hermes_agent", top_k=1000)

        if not self.embedder or not hermes_facts or not hermes_agent_facts:
            return conflicts

        # Cross-compare using semantic similarity
        # High similarity + different content = potential conflict
        for hf in hermes_facts:
            hvec = self.embedder.embed(hf.content)
            for kf in hermes_agent_facts:
                if hf.id == kf.id:
                    continue
                kvec = self.embedder.embed(kf.content)
                sim = self.embedder.cosine_similarity(hvec, kvec)

                # High similarity (>0.85) but different content = potential conflict
                if sim > 0.85 and hf.content.lower() != kf.content.lower():
                    conflict = Conflict(
                        agent_a="hermes",
                        agent_b="hermes_agent",
                        fact_a=hf.content,
                        fact_b=kf.content,
                        conflict_type="high_similarity_diff_content",
                    )
                    conflicts.append(conflict)

                    # Store in DB
                    self.conn.execute("""
                        INSERT INTO agent_conflicts
                        (agent_a, agent_b, fact_a_id, fact_b_id, fact_a_content, fact_b_content, conflict_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, ("hermes", "hermes_agent", hf.id, kf.id, hf.content, kf.content,
                          "high_similarity_diff_content"))

        self.conn.commit()
        return conflicts

    # ── import existing facts ────────────────────────────────────

    def import_from_memory_facts(self, default_agent: str = "hermes") -> int:
        """
        Import existing memory_facts into agent_facts with proper scoping.
        
        Rules:
          - Facts with sensitive content → hermes private
          - General facts → shared
          - System/config facts → hermes private
        """
        rows = self.conn.execute("""
            SELECT id, content, source FROM memory_facts
            WHERE is_active = 1
        """).fetchall()

        imported = 0
        for fact_id, content, source in rows:
            sensitive = self.is_sensitive(content)

            # Determine scope
            if sensitive:
                scope = "private"
                agent = "hermes"
            elif source in ("system",):
                scope = "private"
                agent = "hermes"
            else:
                scope = "shared"
                agent = default_agent

            # Check if already imported
            existing = self.conn.execute(
                "SELECT id FROM agent_facts WHERE source_fact_id = ?", (fact_id,)
            ).fetchone()
            if existing:
                continue

            import hashlib
            af_id = f"af_{hashlib.md5(content.encode()).hexdigest()[:12]}"

            try:
                self.conn.execute("""
                    INSERT OR IGNORE INTO agent_facts
                    (id, content, agent, scope, is_sensitive, source_fact_id, shared_with)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (af_id, content, agent, scope, sensitive, fact_id, json.dumps([])))
                imported += 1
            except Exception as e:
                logger.warning(f"Failed to import {fact_id}: {e}")

        self.conn.commit()
        logger.info(f"Imported {imported} facts into agent memory")
        return imported

    # ── stats ────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get multi-agent memory statistics."""
        stats = {}

        for agent_name in AGENTS:
            total = self.conn.execute(
                "SELECT COUNT(*) FROM agent_facts WHERE agent = ?", (agent_name,)
            ).fetchone()[0]

            private = self.conn.execute(
                "SELECT COUNT(*) FROM agent_facts WHERE agent = ? AND scope = 'private'",
                (agent_name,)
            ).fetchone()[0]

            shared = self.conn.execute(
                "SELECT COUNT(*) FROM agent_facts WHERE agent = ? AND scope = 'shared'",
                (agent_name,)
            ).fetchone()[0]

            sensitive = self.conn.execute(
                "SELECT COUNT(*) FROM agent_facts WHERE agent = ? AND is_sensitive = 1",
                (agent_name,)
            ).fetchone()[0]

            stats[agent_name] = {
                "total": total,
                "private": private,
                "shared": shared,
                "sensitive": sensitive,
            }

        # Shared facts visible to all
        total_shared = self.conn.execute(
            "SELECT COUNT(*) FROM agent_facts WHERE scope = 'shared'"
        ).fetchone()[0]

        conflicts = self.conn.execute(
            "SELECT COUNT(*) FROM agent_conflicts WHERE status = 'unresolved'"
        ).fetchone()[0]

        shares = self.conn.execute(
            "SELECT COUNT(*) FROM agent_share_log"
        ).fetchone()[0]

        return {
            "agents": stats,
            "total_shared_facts": total_shared,
            "unresolved_conflicts": conflicts,
            "total_shares": shares,
        }


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Multi-Agent Memory (Phase 6)")
    parser.add_argument("--add", type=str, help="Add a fact")
    parser.add_argument("--agent", type=str, default="hermes", help="Agent: hermes or hermes_agent")
    parser.add_argument("--scope", type=str, default="private", choices=["private", "shared"])
    parser.add_argument("--query", type=str, help="Query facts visible to agent")
    parser.add_argument("--share", type=str, help="Share a fact ID with another agent")
    parser.add_argument("--with-agent", type=str, dest="with_agent", help="Target agent for sharing")
    parser.add_argument("--import-facts", action="store_true", help="Import from memory_facts")
    parser.add_argument("--conflicts", action="store_true", help="Detect conflicts")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    mgr = AgentMemoryManager()
    mgr.connect()

    try:
        if args.add:
            fid = mgr.add_fact(args.add, agent=args.agent, scope=args.scope)
            if fid:
                print(f"✓ Added: {fid} (agent={args.agent}, scope={args.scope})")
            else:
                print("✗ Blocked (sensitive content)")

        elif args.query:
            facts = mgr.get_facts(args.agent, query=args.query, top_k=10)
            print(f"\n╔═══════════════════════════════════════════════════════╗")
            print(f"║ AGENT QUERY: '{args.query}' (as {args.agent})")
            print(f"╚═══════════════════════════════════════════════════════╝\n")
            for i, f in enumerate(facts, 1):
                sens = " [SENSITIVE]" if f.is_sensitive else ""
                print(f"  [{i}] {f.scope.upper()}{sens} | {f.agent}")
                print(f"      {f.content[:80]}")
            if not facts:
                print("  No facts visible to this agent.")
            print()

        elif args.share and args.with_agent:
            ok = mgr.share_fact(args.share, args.with_agent)
            if ok:
                print(f"✓ Shared {args.share} → {args.with_agent}")
            else:
                print(f"✗ Share blocked (sensitive or not found)")

        elif args.import_facts:
            count = mgr.import_from_memory_facts()
            print(f"✓ Imported {count} facts into agent memory")

        elif args.conflicts:
            conflicts = mgr.detect_conflicts()
            print(f"\n╔═══════════════════════════════════════════════════════╗")
            print(f"║ CONFLICT DETECTION")
            print(f"╚═══════════════════════════════════════════════════════╝\n")
            if conflicts:
                for c in conflicts:
                    print(f"  ⚠ {c.agent_a} vs {c.agent_b} ({c.conflict_type})")
                    print(f"    A: {c.fact_a[:60]}")
                    print(f"    B: {c.fact_b[:60]}")
                    print()
            else:
                print("  ✓ No conflicts detected.")
            print()

        elif args.stats:
            stats = mgr.get_stats()
            if args.json:
                print(json.dumps(stats, indent=2))
            else:
                print(f"\n╔═══════════════════════════════════════════════════════╗")
                print(f"║ MULTI-AGENT MEMORY STATS")
                print(f"╚═══════════════════════════════════════════════════════╝\n")
                for agent_name, data in stats["agents"].items():
                    config = AGENTS[agent_name]
                    sens_label = "✓" if config["sensitive_access"] else "✗"
                    print(f"  ◆ {agent_name.upper()} — {config['description']}")
                    print(f"    Total: {data['total']} | Private: {data['private']} | Shared: {data['shared']} | Sensitive: {data['sensitive']}")
                    print(f"    Sensitive access: {sens_label}")
                    print()
                print(f"  Shared pool: {stats['total_shared_facts']} facts")
                print(f"  Conflicts:   {stats['unresolved_conflicts']} unresolved")
                print(f"  Shares:      {stats['total_shares']} cross-agent")
                print()

        else:
            parser.print_help()

    finally:
        mgr.close()


if __name__ == "__main__":
    main()
