#!/usr/bin/env python3
"""
Session Context Windowing — Phase 2 Extended

Provides contextual facts by fetching N-1, N, N+1 sessions.

When a user looks at a fact, we also surface facts from:
  • Previous session (context before)
  • Current session (context within)
  • Next session (context after)

This gives rich contextual understanding.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"


@dataclass
class SessionContext:
    """Context around a fact across three sessions."""
    
    fact_id: str
    current_session_id: str
    previous_session_id: Optional[str]
    next_session_id: Optional[str]
    
    previous_facts: List[Dict]
    current_facts: List[Dict]
    next_facts: List[Dict]
    
    context_summary: str
    total_facts: int


class SessionContexter:
    """Retrieve facts with rich session context."""

    def __init__(self, db_path: Path = None, window_size: int = 5):
        self.db_path = db_path or DB_PATH
        self.window_size = window_size  # Top N facts per session
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def get_fact_session(self, fact_id: str) -> Optional[str]:
        """Get the session_id for a fact."""
        row = self.conn.execute(
            "SELECT session_id FROM quantum_facts WHERE id = ?", (fact_id,)
        ).fetchone()

        return row["session_id"] if row else None

    def get_session_facts(self, session_id: str, limit: int = None) -> List[Dict]:
        """
        Get all facts in a session, sorted by confidence/importance.
        
        Args:
            session_id: Session ID
            limit: Max facts (uses window_size if None)
        
        Returns:
            List of fact dicts
        """
        if limit is None:
            limit = self.window_size

        rows = self.conn.execute(
            """
            SELECT id, summary, domain, confidence, activation_count
            FROM quantum_facts
            WHERE session_id = ?
            AND status NOT IN ('abandoned')
            ORDER BY confidence DESC, activation_count DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

        return [dict(r) for r in rows]

    def get_adjacent_sessions(self, session_id: str) -> Dict[str, Optional[str]]:
        """
        Get previous and next session IDs.
        
        Args:
            session_id: Current session ID
        
        Returns:
            Dict with 'previous' and 'next' session IDs
        """
        # Get all unique sessions, ordered
        all_sessions = self.conn.execute(
            """
            SELECT DISTINCT session_id
            FROM quantum_facts
            WHERE session_id IS NOT NULL
            ORDER BY session_id ASC
            """
        ).fetchall()

        session_list = [s["session_id"] for s in all_sessions]

        try:
            idx = session_list.index(session_id)
        except ValueError:
            return {"previous": None, "next": None}

        previous = session_list[idx - 1] if idx > 0 else None
        next_session = session_list[idx + 1] if idx < len(session_list) - 1 else None

        return {"previous": previous, "next": next_session}

    def get_context(self, fact_id: str) -> Optional[SessionContext]:
        """
        Get rich context for a fact across three sessions.
        
        Args:
            fact_id: Fact ID
        
        Returns:
            SessionContext with N-1, N, N+1 session facts
        """
        # Get fact's session
        session_id = self.get_fact_session(fact_id)
        if not session_id:
            return None

        # Get adjacent sessions
        adjacent = self.get_adjacent_sessions(session_id)

        # Fetch facts from each session
        previous_facts = (
            self.get_session_facts(adjacent["previous"])
            if adjacent["previous"]
            else []
        )
        current_facts = self.get_session_facts(session_id)
        next_facts = (
            self.get_session_facts(adjacent["next"]) if adjacent["next"] else []
        )

        # Build context summary
        context_parts = []
        if previous_facts:
            prev_domains = ", ".join(
                set(f["domain"] for f in previous_facts if f["domain"])
            )
            context_parts.append(f"Previous: {prev_domains}")

        curr_domains = ", ".join(
            set(f["domain"] for f in current_facts if f["domain"])
        )
        context_parts.append(f"Current: {curr_domains}")

        if next_facts:
            next_domains = ", ".join(
                set(f["domain"] for f in next_facts if f["domain"])
            )
            context_parts.append(f"Next: {next_domains}")

        context_summary = " | ".join(context_parts)

        return SessionContext(
            fact_id=fact_id,
            current_session_id=session_id,
            previous_session_id=adjacent["previous"],
            next_session_id=adjacent["next"],
            previous_facts=previous_facts,
            current_facts=current_facts,
            next_facts=next_facts,
            context_summary=context_summary,
            total_facts=len(previous_facts) + len(current_facts) + len(next_facts),
        )

    def enrich_search_result(
        self, fact_id: str, base_result: Dict
    ) -> Dict:
        """
        Add context to a search result.
        
        Args:
            fact_id: Fact ID
            base_result: Base search result dict
        
        Returns:
            Enriched result with context
        """
        context = self.get_context(fact_id)

        if not context:
            base_result["context"] = None
            return base_result

        base_result["context"] = {
            "summary": context.context_summary,
            "session_id": context.current_session_id,
            "previous_session": context.previous_session_id,
            "next_session": context.next_session_id,
            "previous_facts": context.previous_facts,
            "current_facts": context.current_facts,
            "next_facts": context.next_facts,
            "total_contextual_facts": context.total_facts,
        }

        return base_result

    def get_session_timeline(self, limit: int = 10) -> List[Dict]:
        """
        Get timeline of sessions with fact counts and domains.
        
        Args:
            limit: Max sessions to return
        
        Returns:
            List of session dicts
        """
        rows = self.conn.execute(
            """
            SELECT
              session_id,
              COUNT(*) as fact_count,
              MIN(created_at) as started_at,
              MAX(created_at) as ended_at
            FROM quantum_facts
            WHERE session_id IS NOT NULL
            GROUP BY session_id
            ORDER BY session_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        sessions = []
        for row in rows:
            session_id = row["session_id"]
            facts = self.get_session_facts(session_id)
            domains = ", ".join(set(f["domain"] for f in facts if f["domain"]))

            sessions.append(
                {
                    "session_id": session_id,
                    "fact_count": row["fact_count"],
                    "domains": domains,
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                }
            )

        return sessions

    def get_status(self) -> Dict:
        """Get session context statistics."""
        session_count = self.conn.execute(
            "SELECT COUNT(DISTINCT session_id) as cnt FROM quantum_facts WHERE session_id IS NOT NULL"
        ).fetchone()["cnt"]

        facts_with_session = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM quantum_facts WHERE session_id IS NOT NULL"
        ).fetchone()["cnt"]

        total_facts = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM quantum_facts WHERE status NOT IN ('abandoned')"
        ).fetchone()["cnt"]

        coverage = (facts_with_session / max(total_facts, 1)) * 100

        return {
            "total_sessions": session_count,
            "facts_with_session": facts_with_session,
            "total_facts": total_facts,
            "session_coverage": f"{coverage:.1f}%",
        }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Session Contexter — Phase 2")
    sub = parser.add_subparsers(dest="command")

    c = sub.add_parser("context", help="Get context for a fact")
    c.add_argument("fact_id")

    sub.add_parser("timeline", help="Get session timeline")

    sub.add_parser("status", help="Session context status")

    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    contexter = SessionContexter(window_size=args.window)
    contexter.connect()

    try:
        if args.command == "context":
            context = contexter.get_context(args.fact_id)
            if args.json:
                if context:
                    print(
                        json.dumps(
                            {
                                "fact_id": context.fact_id,
                                "summary": context.context_summary,
                                "previous": context.previous_facts,
                                "current": context.current_facts,
                                "next": context.next_facts,
                            },
                            indent=2,
                            default=str,
                        )
                    )
                else:
                    print(json.dumps({"error": "No context found"}))
            else:
                if context:
                    print(f"\n  CONTEXT FOR {args.fact_id}")
                    print(f"  {'═' * 50}\n")
                    print(f"  {context.context_summary}\n")
                    print(f"  Previous Session: {len(context.previous_facts)} facts")
                    for f in context.previous_facts[:3]:
                        print(f"    • {f['summary'][:50]}")
                    print(f"\n  Current Session: {len(context.current_facts)} facts")
                    for f in context.current_facts[:3]:
                        print(f"    • {f['summary'][:50]}")
                    print(f"\n  Next Session: {len(context.next_facts)} facts")
                    for f in context.next_facts[:3]:
                        print(f"    • {f['summary'][:50]}")
                    print()
                else:
                    print(f"\n  No context found for {args.fact_id}\n")

        elif args.command == "timeline":
            timeline = contexter.get_session_timeline()
            if args.json:
                print(json.dumps(timeline, indent=2, default=str))
            else:
                print(f"\n  SESSION TIMELINE")
                print(f"  {'═' * 50}\n")
                for s in timeline:
                    print(
                        f"  {s['session_id'][:20]:20s} {s['fact_count']:3d} facts  {s['domains'][:40]}"
                    )
                print()

        elif args.command == "status":
            status = contexter.get_status()
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                print(f"\n  SESSION CONTEXT STATUS")
                print(f"  {'═' * 50}\n")
                print(f"  Total sessions:    {status['total_sessions']}")
                print(f"  Facts with session: {status['facts_with_session']}")
                print(f"  Session coverage:   {status['session_coverage']}\n")

        else:
            parser.print_help()

    finally:
        contexter.close()


if __name__ == "__main__":
    main()
