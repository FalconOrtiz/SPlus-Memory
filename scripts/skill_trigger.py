#!/usr/bin/env python3
"""
Skill Trigger Engine — Phase 5
Auto-detect and suggest skills based on user queries.

Uses the same fastembed model as the memory engine for consistency.
Scores skills using: semantic similarity (50%), keyword triggers (35%),
usage history (15%).

Integrates with Hermes skill system (~/.hermes/skills/).
"""

import json
import sqlite3
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

sys.path.insert(0, str(Path(__file__).parent))
from semantic_index import SemanticIndex

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"
SKILLS_DIR = Path.home() / ".hermes/skills"


@dataclass
class SkillMatch:
    name: str
    category: str
    description: str
    score: float
    semantic_score: float
    keyword_score: float
    usage_score: float
    times_used: int = 0
    success_rate: float = 0.0
    triggers: List[str] = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS skill_index (
    name TEXT PRIMARY KEY,
    category TEXT,
    description TEXT,
    triggers TEXT,
    keywords TEXT,
    embedding BLOB,
    path TEXT,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skill_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    query TEXT,
    outcome TEXT DEFAULT 'unknown',
    notes TEXT,
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_su_name ON skill_usage(skill_name);
"""


class SkillTriggerEngine:
    """Matches queries to skills using hybrid scoring."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._sem = None

    @property
    def sem(self):
        if self._sem is None:
            self._sem = SemanticIndex(self.db_path)
            self._sem.conn = self.conn
        return self._sem

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

    # ── Indexing ──────────────────────────────────────────────────

    def index_skills(self) -> int:
        """
        Parse all SKILL.md files and index them with embeddings.
        Supports YAML frontmatter format used by Hermes.
        """
        count = 0

        # Find all SKILL.md files
        if not SKILLS_DIR.exists():
            logger.warning(f"Skills dir not found: {SKILLS_DIR}")
            return 0

        for skill_path in SKILLS_DIR.rglob("SKILL.md"):
            try:
                text = skill_path.read_text(encoding="utf-8", errors="replace")
                meta = self._parse_skill_md(text, skill_path)
                if not meta:
                    continue

                name = meta["name"]
                category = meta.get("category", "")
                description = meta.get("description", "")
                triggers = meta.get("triggers", [])
                keywords = meta.get("keywords", [])

                if not description:
                    continue

                # Build embedding text: name + category + description + triggers
                embed_text = f"{name} {category} {description} {' '.join(triggers)} {' '.join(keywords)}"

                # Generate embedding
                import numpy as np
                vec = SemanticIndex.encode_one(embed_text)
                blob = SemanticIndex.vec_to_blob(vec)

                # Store
                self.conn.execute("""
                    INSERT OR REPLACE INTO skill_index
                    (name, category, description, triggers, keywords, embedding, path)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    name, category, description,
                    json.dumps(triggers),
                    json.dumps(keywords),
                    blob,
                    str(skill_path),
                ))
                count += 1

            except Exception as e:
                logger.debug(f"Skip {skill_path}: {e}")

        self.conn.commit()
        return count

    @staticmethod
    def _parse_skill_md(text: str, path: Path) -> Optional[Dict]:
        """Parse a SKILL.md file with YAML frontmatter."""
        meta = {}

        # Try YAML frontmatter
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    import yaml
                    fm = yaml.safe_load(parts[1])
                    if fm and isinstance(fm, dict):
                        meta = fm
                except Exception:
                    pass

        # Fallback: extract from markdown headers
        if not meta.get("description"):
            # First non-empty line after title
            lines = text.split("\n")
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("---"):
                    meta.setdefault("description", line[:200])
                    break

        # Derive name from path
        meta.setdefault("name", path.parent.name)

        # Derive category from parent directory
        rel = path.relative_to(SKILLS_DIR) if str(path).startswith(str(SKILLS_DIR)) else path
        parts = rel.parts
        if len(parts) > 2:
            meta.setdefault("category", parts[0])
        elif len(parts) > 1:
            meta.setdefault("category", "general")

        # Extract triggers from text patterns
        triggers = meta.get("triggers", [])
        if isinstance(triggers, str):
            triggers = [triggers]

        # Auto-extract trigger phrases from "Use when:" sections
        use_when = re.findall(r'(?:Use when|Trigger|When to use)[:\s]+(.+?)(?:\n|$)', text, re.IGNORECASE)
        for phrase in use_when:
            triggers.append(phrase.strip()[:100])

        meta["triggers"] = triggers

        # Extract keywords from tags/labels
        kw = meta.get("keywords", meta.get("tags", []))
        if isinstance(kw, str):
            kw = [kw]
        meta["keywords"] = kw

        return meta

    # ── Matching ─────────────────────────────────────────────────

    def match(self, query: str, top_k: int = 5, min_score: float = 0.2) -> List[SkillMatch]:
        """
        Match a query to relevant skills.

        Scoring:
          semantic:  50% — embedding cosine similarity
          keyword:   35% — trigger phrase + name + description matching
          usage:     15% — historical success rate
        """
        import numpy as np

        # Embed query
        query_vec = SemanticIndex.encode_one(query)

        # Load all indexed skills
        rows = self.conn.execute("""
            SELECT name, category, description, triggers, keywords, embedding
            FROM skill_index
        """).fetchall()

        if not rows:
            return []

        results = []
        for name, category, description, triggers_json, keywords_json, emb_blob in rows:
            if not emb_blob:
                continue

            # Semantic score
            stored_vec = SemanticIndex.blob_to_vec(emb_blob)
            semantic = max(0.0, float(SemanticIndex.cosine_similarity(query_vec, stored_vec)))

            # Keyword score
            triggers = json.loads(triggers_json) if triggers_json else []
            keywords = json.loads(keywords_json) if keywords_json else []
            keyword = self._keyword_score(query, name, description, triggers, keywords)

            # Usage score
            usage = self._usage_score(name)

            # Combined
            combined = semantic * 0.50 + keyword * 0.35 + usage["score"] * 0.15

            if combined >= min_score:
                results.append(SkillMatch(
                    name=name,
                    category=category,
                    description=description,
                    score=combined,
                    semantic_score=semantic,
                    keyword_score=keyword,
                    usage_score=usage["score"],
                    times_used=usage["times_used"],
                    success_rate=usage["success_rate"],
                    triggers=triggers,
                ))

        results.sort(key=lambda m: m.score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _keyword_score(query: str, name: str, description: str,
                       triggers: List[str], keywords: List[str]) -> float:
        """Score based on keyword/trigger matching."""
        q_lower = query.lower()
        q_terms = set(q_lower.split())
        score = 0.0

        # Skill name in query
        name_parts = set(name.lower().replace("-", " ").replace("_", " ").split())
        name_overlap = len(q_terms & name_parts)
        if name_overlap > 0:
            score += 0.5 * (name_overlap / max(len(name_parts), 1))

        # Trigger phrases
        for trigger in triggers:
            if isinstance(trigger, str) and trigger.lower() in q_lower:
                score += 0.8
                break

        # Keywords/tags
        for kw in keywords:
            if isinstance(kw, str) and kw.lower() in q_lower:
                score += 0.3
                break

        # Description word overlap
        desc_words = set(description.lower().split())
        desc_overlap = len(q_terms & desc_words)
        if desc_overlap > 0:
            score += 0.2 * min(1.0, desc_overlap / 3)

        return min(1.0, score)

    def _usage_score(self, skill_name: str) -> Dict:
        """Bayesian usage score."""
        rows = self.conn.execute(
            "SELECT outcome FROM skill_usage WHERE skill_name = ?",
            (skill_name,)
        ).fetchall()

        if not rows:
            return {"score": 0.5, "times_used": 0, "success_rate": 0.0}

        total = len(rows)
        successes = sum(1 for r in rows if r[0] == "success")
        success_rate = successes / total if total > 0 else 0.0

        # Bayesian blend: prior 0.5 fades after 10 uses
        prior_weight = max(0.0, 1.0 - total / 10.0)
        score = prior_weight * 0.5 + (1 - prior_weight) * success_rate

        return {"score": score, "times_used": total, "success_rate": success_rate}

    # ── Usage Tracking ───────────────────────────────────────────

    def record_usage(self, skill_name: str, query: str = "",
                     outcome: str = "unknown", notes: str = ""):
        """Record skill usage and outcome."""
        self.conn.execute("""
            INSERT INTO skill_usage (skill_name, query, outcome, notes)
            VALUES (?, ?, ?, ?)
        """, (skill_name, query, outcome, notes))
        self.conn.commit()

    # ── Dependency Chain ─────────────────────────────────────────

    def get_dependency_chain(self, skill_name: str) -> List[str]:
        """
        Get skill dependencies (if defined in SKILL.md frontmatter).
        Returns ordered list: dependencies first, then the skill itself.
        """
        row = self.conn.execute(
            "SELECT path FROM skill_index WHERE name = ?", (skill_name,)
        ).fetchone()

        if not row or not row[0]:
            return [skill_name]

        path = Path(row[0])
        if not path.exists():
            return [skill_name]

        text = path.read_text(encoding="utf-8", errors="replace")
        meta = self._parse_skill_md(text, path)
        deps = meta.get("dependencies", meta.get("requires", []))

        if isinstance(deps, str):
            deps = [deps]

        return deps + [skill_name]

    # ── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        total_indexed = self.conn.execute("SELECT COUNT(*) FROM skill_index").fetchone()[0]
        total_usages = self.conn.execute("SELECT COUNT(*) FROM skill_usage").fetchone()[0]

        categories = self.conn.execute("""
            SELECT category, COUNT(*) FROM skill_index GROUP BY category ORDER BY COUNT(*) DESC
        """).fetchall()

        top_used = self.conn.execute("""
            SELECT skill_name, COUNT(*) as cnt,
                   SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) as wins
            FROM skill_usage GROUP BY skill_name ORDER BY cnt DESC LIMIT 10
        """).fetchall()

        return {
            "total_indexed": total_indexed,
            "total_usages": total_usages,
            "categories": {r[0]: r[1] for r in categories},
            "top_used": [{"name": r[0], "uses": r[1], "successes": r[2]} for r in top_used],
        }


# ── CLI ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Skill Trigger Engine (Phase 5)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("index", help="Index all skills from ~/.hermes/skills/")

    p = sub.add_parser("match", help="Match query to skills")
    p.add_argument("query", nargs="+")
    p.add_argument("--top", type=int, default=5)

    p = sub.add_parser("record", help="Record skill usage")
    p.add_argument("skill")
    p.add_argument("outcome", choices=["success", "partial", "failed", "unknown"])
    p.add_argument("--notes", default="")

    p = sub.add_parser("chain", help="Get dependency chain")
    p.add_argument("skill")

    sub.add_parser("stats", help="Usage statistics")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    engine = SkillTriggerEngine()
    engine.connect()

    try:
        if args.command == "index":
            count = engine.index_skills()
            print(f"  ✓ Indexed {count} skills")

        elif args.command == "match":
            query = " ".join(args.query)
            matches = engine.match(query, top_k=args.top)

            if args.json:
                print(json.dumps([{
                    "name": m.name, "category": m.category,
                    "score": round(m.score, 3),
                    "semantic": round(m.semantic_score, 3),
                    "keyword": round(m.keyword_score, 3),
                    "description": m.description[:100],
                } for m in matches], indent=2))
            else:
                print(f"\n  SKILL MATCH: {query}")
                print(f"  {'─' * 55}\n")
                if not matches:
                    print("  No matching skills found.\n")
                else:
                    for i, m in enumerate(matches, 1):
                        bar = "█" * int(m.score * 20)
                        print(f"  [{i}] {m.name} ({m.category})")
                        print(f"      Score: {m.score:.3f} {bar}")
                        print(f"      Sem: {m.semantic_score:.2f} | KW: {m.keyword_score:.2f} | Use: {m.usage_score:.2f}")
                        if m.times_used:
                            print(f"      History: {m.times_used} uses, {m.success_rate*100:.0f}% success")
                        print(f"      {m.description[:80]}")
                        print()

        elif args.command == "record":
            engine.record_usage(args.skill, outcome=args.outcome, notes=args.notes)
            print(f"  ✓ Recorded: {args.skill} → {args.outcome}")

        elif args.command == "chain":
            chain = engine.get_dependency_chain(args.skill)
            print(f"  Chain: {' → '.join(chain)}")

        elif args.command == "stats":
            stats = engine.get_stats()
            if args.json:
                print(json.dumps(stats, indent=2))
            else:
                print(f"\n  SKILL TRIGGER STATS")
                print(f"  {'─' * 55}")
                print(f"  Indexed:  {stats['total_indexed']} skills")
                print(f"  Usages:   {stats['total_usages']} recorded")
                if stats["categories"]:
                    print(f"\n  Categories:")
                    for cat, cnt in stats["categories"].items():
                        print(f"    {cat}: {cnt}")
                if stats["top_used"]:
                    print(f"\n  Top used:")
                    for t in stats["top_used"]:
                        print(f"    {t['name']}: {t['uses']} uses ({t['successes']} success)")
                print()

        else:
            parser.print_help()

    finally:
        engine.close()


if __name__ == "__main__":
    main()
