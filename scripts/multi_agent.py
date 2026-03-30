#!/usr/bin/env python3
"""
Multi-Agent Memory — Phase 6
Isolated memory spaces with a shared layer.

Architecture:
  ┌─────────────────────────────────────────────┐
  │              SHARED LAYER                   │
  │  Facts visible to all agents                │
  │  (infrastructure, credentials, decisions)   │
  └──────────────┬──────────────┬───────────────┘
                 │              │
  ┌──────────────▼──┐   ┌──────▼──────────────┐
  │  HERMES PRIVATE │   │  HERMES PRIVATE    │
  │  Main session   │   │  Telegram persona   │
  │  Full access    │   │  Group chat rules   │
  │  System admin   │   │  Social filters     │
  └─────────────────┘   └─────────────────────┘

Scopes:
  private    — only the owning agent can see
  shared     — all agents can see
  sensitive  — only owner, never shared (credentials, keys)

Agents:
  hermes   — main CLI agent, full access
  hermes_agent  — Telegram persona, social-aware
  leo      — outreach/sales agent
  nova     — support agent
  aria     — analytics agent

Rules:
  - Each agent has its own namespace in quantum_facts
  - Shared facts are replicated to all agents on ingest
  - Sensitive facts never leave the owner's namespace
  - Conflicts detected when agents store contradictory facts
  - Resolution: owner's fact wins, conflict logged for review
"""

import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent))
from quantum_index import QuantumIndex, ProceduralExtractor

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"

KNOWN_AGENTS = {"hermes", "hermes_agent", "leo", "nova", "aria"}
SCOPES = {"private", "shared", "sensitive"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_memory (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'private',
    fact_id TEXT,
    content TEXT NOT NULL,
    keywords TEXT,
    status TEXT DEFAULT 'committed',
    is_sensitive INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    shared_with TEXT DEFAULT '[]',
    source_agent TEXT,
    FOREIGN KEY(fact_id) REFERENCES quantum_facts(id)
);

CREATE TABLE IF NOT EXISTS agent_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    fact_a TEXT NOT NULL,
    fact_b TEXT NOT NULL,
    content_a TEXT,
    content_b TEXT,
    conflict_type TEXT DEFAULT 'contradiction',
    status TEXT DEFAULT 'unresolved',
    resolution TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_share_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    scope TEXT,
    shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_am_agent ON agent_memory(agent);
CREATE INDEX IF NOT EXISTS idx_am_scope ON agent_memory(scope);
CREATE INDEX IF NOT EXISTS idx_am_fact ON agent_memory(fact_id);
CREATE INDEX IF NOT EXISTS idx_ac_status ON agent_conflicts(status);
"""

# Scope detection patterns
SENSITIVE_PATTERNS = [
    r"password|passwd|api.?key|secret|token|credential",
    r"ssh.*pass|private.?key|\.env\b",
]

SHARED_PATTERNS = [
    r"infraestruct|server|vps|domain|dns|deploy",
    r"decided|acordamos|the plan is|architecture",
    r"todos? (los|all) agents?|company.?wide|global",
]


@dataclass
class AgentFact:
    id: str
    agent: str
    scope: str
    content: str
    keywords: Dict
    status: str
    is_sensitive: bool
    created_at: str
    shared_with: List[str] = field(default_factory=list)


@dataclass
class Conflict:
    id: int
    agent_a: str
    agent_b: str
    content_a: str
    content_b: str
    conflict_type: str
    status: str


class MultiAgentMemory:
    """
    Multi-agent memory with isolation, sharing, and conflict detection.
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self.idx = None
        self.extractor = ProceduralExtractor()

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
        self.idx = QuantumIndex(self.db_path)
        self.idx.conn = self.conn

    def close(self):
        if self.conn:
            self.conn.close()

    # ── Scope Detection ──────────────────────────────────────────

    def detect_scope(self, text: str) -> str:
        """Auto-detect scope from content."""
        import re
        text_lower = text.lower()

        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, text_lower):
                return "sensitive"

        for pattern in SHARED_PATTERNS:
            if re.search(pattern, text_lower):
                return "shared"

        return "private"

    # ── Ingest ───────────────────────────────────────────────────

    def ingest(self, agent: str, text: str, scope: str = None,
               status: str = "committed", context: Dict = None) -> str:
        """
        Ingest a fact for a specific agent.

        Auto-detects scope if not provided.
        Shared facts are visible to all agents.
        Sensitive facts are locked to the owning agent.
        """
        context = context or {}

        if agent not in KNOWN_AGENTS:
            KNOWN_AGENTS.add(agent)

        # Auto-detect scope
        if scope is None:
            scope = self.detect_scope(text)

        is_sensitive = 1 if scope == "sensitive" else 0

        # Ingest into quantum index
        ctx = {**context, "status": status, "who": agent}
        fact_id = self.idx.ingest(text, context=ctx)

        # Store agent-scoped record
        import hashlib
        am_id = f"am_{hashlib.md5(f'{agent}:{fact_id}'.encode()).hexdigest()[:12]}"

        keywords = self.extractor.extract(text, ctx)

        shared_with = []
        if scope == "shared":
            shared_with = list(KNOWN_AGENTS - {agent})

        self.conn.execute("""
            INSERT OR REPLACE INTO agent_memory
            (id, agent, scope, fact_id, content, keywords, status,
             is_sensitive, shared_with, source_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            am_id, agent, scope, fact_id, text,
            json.dumps(keywords), status, is_sensitive,
            json.dumps(shared_with), agent,
        ))

        # Log sharing
        if scope == "shared":
            for target in shared_with:
                self.conn.execute("""
                    INSERT INTO agent_share_log (fact_id, from_agent, to_agent, scope, reason)
                    VALUES (?, ?, ?, ?, ?)
                """, (fact_id, agent, target, scope, "auto-shared"))

        self.conn.commit()

        # Check for conflicts with other agents
        self._check_conflicts(agent, am_id, text, keywords)

        return am_id

    # ── Query ────────────────────────────────────────────────────

    def query(self, agent: str, top_k: int = 10, scope_filter: str = None,
              status_filter: str = None) -> List[AgentFact]:
        """
        Get facts visible to an agent.
        Includes: own facts + shared facts from other agents.
        Excludes: other agents' private/sensitive facts.
        """
        conditions = []
        params = []

        # Own facts OR shared with this agent
        conditions.append("(agent = ? OR (scope = 'shared' AND shared_with LIKE ?))")
        params.extend([agent, f'%"{agent}"%'])

        # Never show other agents' sensitive facts
        conditions.append("NOT (agent != ? AND scope = 'sensitive')")
        params.append(agent)

        if scope_filter:
            conditions.append("scope = ?")
            params.append(scope_filter)

        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)

        where = " AND ".join(conditions)
        params.append(top_k)

        rows = self.conn.execute(f"""
            SELECT id, agent, scope, content, keywords, status,
                   is_sensitive, created_at, shared_with
            FROM agent_memory
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ?
        """, params).fetchall()

        return [
            AgentFact(
                id=r[0], agent=r[1], scope=r[2], content=r[3],
                keywords=json.loads(r[4]) if r[4] else {},
                status=r[5], is_sensitive=bool(r[6]),
                created_at=r[7] or "",
                shared_with=json.loads(r[8]) if r[8] else [],
            )
            for r in rows
        ]

    def search(self, agent: str, query: str, top_k: int = 5) -> List[AgentFact]:
        """
        Search facts visible to an agent using keyword matching.
        """
        # Get all visible facts
        all_facts = self.query(agent, top_k=100)

        if not all_facts:
            return []

        # Score by keyword overlap
        q_terms = set(query.lower().split())
        scored = []

        for fact in all_facts:
            text_lower = fact.content.lower()
            overlap = sum(1 for t in q_terms if t in text_lower)
            if overlap > 0:
                score = overlap / len(q_terms)
                scored.append((score, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:top_k]]

    # ── Sharing ──────────────────────────────────────────────────

    def share(self, fact_id: str, from_agent: str, to_agent: str,
              reason: str = "manual") -> bool:
        """Explicitly share a fact with another agent."""
        row = self.conn.execute(
            "SELECT id, scope, is_sensitive, shared_with FROM agent_memory WHERE id = ? AND agent = ?",
            (fact_id, from_agent)
        ).fetchone()

        if not row:
            return False

        if row[2]:  # is_sensitive
            return False  # cannot share sensitive facts

        shared = json.loads(row[3]) if row[3] else []
        if to_agent not in shared:
            shared.append(to_agent)

        self.conn.execute("""
            UPDATE agent_memory SET shared_with = ?, scope = 'shared'
            WHERE id = ?
        """, (json.dumps(shared), fact_id))

        self.conn.execute("""
            INSERT INTO agent_share_log (fact_id, from_agent, to_agent, scope, reason)
            VALUES (?, ?, ?, 'shared', ?)
        """, (fact_id, from_agent, to_agent, reason))

        self.conn.commit()
        return True

    # ── Conflict Detection ───────────────────────────────────────

    def _check_conflicts(self, agent: str, fact_id: str, content: str,
                         keywords: Dict):
        """
        Check if this fact contradicts facts from other agents.
        Uses keyword overlap + action contradiction detection.
        """
        # Get facts from other agents in the same domain
        domains = keywords.get("domain", [])
        if not domains:
            return

        for domain in domains:
            rows = self.conn.execute("""
                SELECT id, agent, content, keywords FROM agent_memory
                WHERE agent != ? AND keywords LIKE ?
                ORDER BY created_at DESC LIMIT 20
            """, (agent, f'%"{domain}"%')).fetchall()

            for row in rows:
                other_id, other_agent, other_content, other_kw_json = row
                other_kw = json.loads(other_kw_json) if other_kw_json else {}

                # Check for action contradictions
                my_actions = set(keywords.get("action", []))
                their_actions = set(other_kw.get("action", []))

                contradictions = {
                    ("create", "delete"), ("delete", "create"),
                    ("approve", "reject"), ("reject", "approve"),
                    ("deploy", "delete"), ("delete", "deploy"),
                }

                for my_a in my_actions:
                    for their_a in their_actions:
                        if (my_a, their_a) in contradictions:
                            self.conn.execute("""
                                INSERT INTO agent_conflicts
                                (agent_a, agent_b, fact_a, fact_b,
                                 content_a, content_b, conflict_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                agent, other_agent, fact_id, other_id,
                                content[:200], other_content[:200],
                                f"{my_a}_vs_{their_a}",
                            ))

        self.conn.commit()

    def get_conflicts(self, status: str = "unresolved") -> List[Conflict]:
        """Get all conflicts, optionally filtered by status."""
        rows = self.conn.execute("""
            SELECT id, agent_a, agent_b, content_a, content_b,
                   conflict_type, status
            FROM agent_conflicts
            WHERE status = ?
            ORDER BY detected_at DESC
        """, (status,)).fetchall()

        return [
            Conflict(id=r[0], agent_a=r[1], agent_b=r[2],
                     content_a=r[3], content_b=r[4],
                     conflict_type=r[5], status=r[6])
            for r in rows
        ]

    def resolve_conflict(self, conflict_id: int, resolution: str):
        """Resolve a conflict."""
        self.conn.execute("""
            UPDATE agent_conflicts
            SET status = 'resolved', resolution = ?, resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (resolution, conflict_id))
        self.conn.commit()

    # ── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Per-agent memory statistics."""
        agents = self.conn.execute("""
            SELECT agent, scope, COUNT(*) as cnt
            FROM agent_memory
            GROUP BY agent, scope
        """).fetchall()

        per_agent = {}
        for agent, scope, count in agents:
            if agent not in per_agent:
                per_agent[agent] = {"total": 0, "private": 0, "shared": 0, "sensitive": 0}
            per_agent[agent][scope] = count
            per_agent[agent]["total"] += count

        total = self.conn.execute("SELECT COUNT(*) FROM agent_memory").fetchone()[0]
        conflicts = self.conn.execute(
            "SELECT COUNT(*) FROM agent_conflicts WHERE status='unresolved'"
        ).fetchone()[0]
        shares = self.conn.execute("SELECT COUNT(*) FROM agent_share_log").fetchone()[0]

        return {
            "total_facts": total,
            "per_agent": per_agent,
            "unresolved_conflicts": conflicts,
            "total_shares": shares,
            "known_agents": sorted(KNOWN_AGENTS),
        }


# ── CLI ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Multi-Agent Memory (Phase 6)")
    sub = parser.add_subparsers(dest="command")

    # ingest
    p = sub.add_parser("ingest", help="Ingest fact for an agent")
    p.add_argument("agent", choices=list(KNOWN_AGENTS))
    p.add_argument("text", nargs="+")
    p.add_argument("--scope", choices=list(SCOPES))
    p.add_argument("--status", default="committed")

    # query
    p = sub.add_parser("query", help="Query agent's visible facts")
    p.add_argument("agent", choices=list(KNOWN_AGENTS))
    p.add_argument("--scope", choices=list(SCOPES))
    p.add_argument("--status", type=str)
    p.add_argument("--top", type=int, default=10)

    # search
    p = sub.add_parser("search", help="Search agent's memory")
    p.add_argument("agent")
    p.add_argument("query", nargs="+")
    p.add_argument("--top", type=int, default=5)

    # share
    p = sub.add_parser("share", help="Share fact between agents")
    p.add_argument("fact_id")
    p.add_argument("from_agent")
    p.add_argument("to_agent")

    # conflicts
    sub.add_parser("conflicts", help="Show unresolved conflicts")

    # resolve
    p = sub.add_parser("resolve", help="Resolve a conflict")
    p.add_argument("conflict_id", type=int)
    p.add_argument("resolution")

    # stats
    sub.add_parser("stats", help="Per-agent statistics")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ma = MultiAgentMemory()
    ma.connect()

    try:
        if args.command == "ingest":
            text = " ".join(args.text)
            fid = ma.ingest(args.agent, text, scope=args.scope, status=args.status)
            scope = ma.detect_scope(text) if not args.scope else args.scope
            print(f"  ✓ {args.agent}:{scope} → {fid}")

        elif args.command == "query":
            facts = ma.query(args.agent, top_k=args.top,
                           scope_filter=args.scope, status_filter=args.status)
            if args.json:
                print(json.dumps([{
                    "id": f.id, "agent": f.agent, "scope": f.scope,
                    "content": f.content[:100], "status": f.status,
                } for f in facts], indent=2))
            else:
                print(f"\n  {args.agent.upper()} MEMORY ({len(facts)} facts)")
                print(f"  {'─' * 55}\n")
                for f in facts:
                    scope_icon = {"private": "🔒", "shared": "🌐", "sensitive": "⚠"}.get(f.scope, "?")
                    owner = f"[{f.agent}]" if f.agent != args.agent else ""
                    print(f"  {scope_icon} {f.content[:80]} {owner}")
                print()

        elif args.command == "search":
            query = " ".join(args.query)
            facts = ma.search(args.agent, query, top_k=args.top)
            print(f"\n  SEARCH ({args.agent}): {query}")
            print(f"  {'─' * 55}\n")
            for f in facts:
                scope_icon = {"private": "🔒", "shared": "🌐", "sensitive": "⚠"}.get(f.scope, "?")
                print(f"  {scope_icon} {f.content[:80]}")
            print()

        elif args.command == "share":
            ok = ma.share(args.fact_id, args.from_agent, args.to_agent)
            print(f"  {'✓ Shared' if ok else '✗ Failed (sensitive or not found)'}")

        elif args.command == "conflicts":
            conflicts = ma.get_conflicts()
            if args.json:
                print(json.dumps([{
                    "id": c.id, "agents": f"{c.agent_a} vs {c.agent_b}",
                    "type": c.conflict_type, "status": c.status,
                    "a": c.content_a[:60], "b": c.content_b[:60],
                } for c in conflicts], indent=2))
            else:
                print(f"\n  CONFLICTS ({len(conflicts)} unresolved)")
                print(f"  {'─' * 55}\n")
                if not conflicts:
                    print("  ✓ No conflicts.\n")
                for c in conflicts:
                    print(f"  [{c.id}] {c.agent_a} vs {c.agent_b} ({c.conflict_type})")
                    print(f"    A: {c.content_a[:60]}")
                    print(f"    B: {c.content_b[:60]}")
                    print()

        elif args.command == "resolve":
            ma.resolve_conflict(args.conflict_id, args.resolution)
            print(f"  ✓ Conflict {args.conflict_id} resolved")

        elif args.command == "stats":
            stats = ma.get_stats()
            if args.json:
                print(json.dumps(stats, indent=2))
            else:
                print(f"\n  MULTI-AGENT STATS")
                print(f"  {'─' * 55}")
                print(f"  Total facts: {stats['total_facts']}")
                print(f"  Agents: {', '.join(stats['known_agents'])}")
                print(f"  Conflicts: {stats['unresolved_conflicts']} unresolved")
                print(f"  Shares: {stats['total_shares']}")
                if stats["per_agent"]:
                    print(f"\n  Per agent:")
                    for agent, data in stats["per_agent"].items():
                        print(f"    {agent:12s} total:{data['total']:3d}  priv:{data['private']:3d}  shared:{data['shared']:3d}  sens:{data['sensitive']:3d}")
                print()

        else:
            parser.print_help()

    finally:
        ma.close()


if __name__ == "__main__":
    main()
