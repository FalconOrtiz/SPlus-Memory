#!/usr/bin/env python3
"""
Phase 8C: Evolution Engine — Self-Improving Memory

Skills that run autonomously to evolve the memory over time.
The memory isn't static — it learns from usage, resolves contradictions,
consolidates related facts, and prunes what's no longer useful.

Skills:
  1. VersioningSkill   — detect supersessions, build version chains
  2. ConfidenceSkill   — adjust confidence from usage patterns
  3. ConsolidationSkill — merge co-accessed facts into composites
  4. PatternSkill       — detect co-occurrence patterns (Phase 8D prep)

Each skill:
  - Runs independently on a schedule
  - Logs all changes to evolution_log
  - Never deletes data (supersede/archive, never destroy)
  - Zero LLM calls (all local heuristics)
"""

import json
import sqlite3
import re
import math
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"


@dataclass
class EvolutionResult:
    skill: str
    actions_taken: int
    details: List[str]
    duration_ms: int = 0


# ═══════════════════════════════════════════════════════════
# 1. VERSIONING SKILL
# ═══════════════════════════════════════════════════════════

class VersioningSkill:
    """
    Detects when a newer fact supersedes an older one.
    Builds version chains: old → new → newer.

    Detection methods:
      - Same domain + high text similarity = potential update
      - Contradictory values for same entity/attribute
      - Explicit "changed", "updated", "now X instead of Y" signals
    """

    UPDATE_SIGNALS = [
        r"(?:ahora|now)\s+(?:es|is|usa|use)",
        r"(?:cambi[oó]|changed|updated|moved)\s",
        r"(?:ya no|no longer|instead of)",
        r"(?:antes|before|previously|was)\b.*(?:ahora|now)\b",
        r"(?:reemplaz|replac|switch)",
        r"(?:fix|arregl|correg|solucion)",
    ]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def run(self) -> EvolutionResult:
        import time
        start = time.time()
        actions = []

        # 1. Find facts that mention updates explicitly
        actions += self._detect_explicit_updates()

        # 2. Find same-domain facts with high keyword overlap
        actions += self._detect_implicit_supersessions()

        elapsed = int((time.time() - start) * 1000)
        return EvolutionResult(
            skill="versioning",
            actions_taken=len(actions),
            details=actions,
            duration_ms=elapsed,
        )

    def _detect_explicit_updates(self) -> List[str]:
        """Find facts whose raw_content signals an update."""
        actions = []
        rows = self.conn.execute("""
            SELECT id, raw_content, keywords, created_at
            FROM quantum_facts
            WHERE status NOT IN ('abandoned')
            AND supersedes_id IS NULL
            AND raw_content IS NOT NULL
        """).fetchall()

        for row in rows:
            raw = row[1] or ""
            for pattern in self.UPDATE_SIGNALS:
                if re.search(pattern, raw, re.IGNORECASE):
                    # Find what it might supersede
                    older = self._find_older_related(row[0], row[2], row[3])
                    if older:
                        self._create_supersession(row[0], older, "explicit_signal")
                        actions.append(f"  {row[0][:10]} supersedes {older[:10]} (explicit)")
                    break

        return actions

    def _detect_implicit_supersessions(self) -> List[str]:
        """Find facts in same domain with contradictory info."""
        actions = []

        # Group facts by domain
        domains = self.conn.execute("""
            SELECT DISTINCT d.value FROM kw_bitmap b
            JOIN kw_dictionary d ON b.value_id = d.id
            WHERE b.dimension = 'domain'
        """).fetchall()

        for (domain,) in domains:
            # Get facts in this domain, ordered by time
            facts = self.conn.execute("""
                SELECT qf.id, qf.raw_content, qf.summary, qf.created_at, qf.keywords
                FROM quantum_facts qf
                JOIN kw_bitmap b ON qf.id = b.fact_id
                JOIN kw_dictionary d ON b.value_id = d.id
                WHERE b.dimension = 'domain' AND d.value = ?
                AND qf.status NOT IN ('abandoned')
                AND qf.supersedes_id IS NULL
                AND qf.superseded_by IS NULL
                ORDER BY qf.created_at ASC
            """, (domain,)).fetchall()

            if len(facts) < 2:
                continue

            # Compare consecutive facts for high similarity
            for i in range(len(facts) - 1):
                for j in range(i + 1, min(i + 5, len(facts))):
                    old_f, new_f = facts[i], facts[j]
                    sim = self._text_similarity(
                        old_f[1] or old_f[2] or "",
                        new_f[1] or new_f[2] or ""
                    )
                    if sim > 0.6:
                        # High similarity in same domain = likely update
                        self._create_supersession(new_f[0], old_f[0], "implicit_similarity")
                        actions.append(f"  {new_f[0][:10]} supersedes {old_f[0][:10]} (sim={sim:.2f})")

        return actions

    def _find_older_related(self, fact_id: str, keywords_str: str, created_at: str) -> Optional[str]:
        """Find an older fact in the same domains that this fact might replace."""
        try:
            kw = json.loads(keywords_str) if keywords_str else {}
        except (json.JSONDecodeError, TypeError):
            return None

        domains = kw.get("domain", [])
        if not domains:
            return None

        # Look in bitmap for same-domain facts created before this one
        for domain_val in domains:
            if isinstance(domain_val, int):
                continue  # skip numeric IDs
            older = self.conn.execute("""
                SELECT qf.id FROM quantum_facts qf
                JOIN kw_bitmap b ON qf.id = b.fact_id
                JOIN kw_dictionary d ON b.value_id = d.id
                WHERE b.dimension = 'domain' AND d.value = ?
                AND qf.id != ?
                AND qf.created_at < ?
                AND qf.status NOT IN ('abandoned')
                AND qf.superseded_by IS NULL
                ORDER BY qf.created_at DESC LIMIT 1
            """, (domain_val, fact_id, created_at)).fetchone()
            if older:
                return older[0]

        return None

    def _create_supersession(self, new_id: str, old_id: str, method: str):
        """Create a version chain link."""
        # Don't create duplicate chains
        existing = self.conn.execute(
            "SELECT 1 FROM quantum_facts WHERE id=? AND supersedes_id=?", (new_id, old_id)
        ).fetchone()
        if existing:
            return

        # Check that old fact isn't already superseded by something else
        already = self.conn.execute(
            "SELECT superseded_by FROM quantum_facts WHERE id=?", (old_id,)
        ).fetchone()
        if already and already[0]:
            return

        self.conn.execute(
            "UPDATE quantum_facts SET supersedes_id=? WHERE id=?", (old_id, new_id)
        )
        self.conn.execute(
            "UPDATE quantum_facts SET superseded_by=? WHERE id=?", (new_id, old_id)
        )

        # Build version chain
        chain = [old_id, new_id]
        # Walk back to find full chain
        prev = self.conn.execute(
            "SELECT supersedes_id FROM quantum_facts WHERE id=?", (old_id,)
        ).fetchone()
        if prev and prev[0]:
            chain.insert(0, prev[0])

        chain_json = json.dumps(chain)
        for cid in chain:
            self.conn.execute(
                "UPDATE quantum_facts SET version_chain=? WHERE id=?", (chain_json, cid)
            )

        # Log
        self.conn.execute("""
            INSERT INTO evolution_log (fact_id, event_type, old_value, new_value, trigger, skill_name)
            VALUES (?, 'superseded', ?, ?, ?, 'versioning')
        """, (old_id, old_id, new_id, method))

    def _text_similarity(self, a: str, b: str) -> float:
        """Simple word-overlap similarity."""
        if not a or not b:
            return 0.0
        words_a = set(re.findall(r'\w{3,}', a.lower()))
        words_b = set(re.findall(r'\w{3,}', b.lower()))
        if not words_a or not words_b:
            return 0.0
        overlap = len(words_a & words_b)
        return overlap / max(len(words_a | words_b), 1)


# ═══════════════════════════════════════════════════════════
# 2. CONFIDENCE SKILL
# ═══════════════════════════════════════════════════════════

class ConfidenceSkill:
    """
    Adjusts fact confidence based on usage patterns.

    Confidence UP when:
      - Fact is activated frequently (activation_count high)
      - Fact appears in co-access patterns (used with other facts)
      - Fact has been confirmed via feedback

    Confidence DOWN when:
      - Fact is never activated (stale)
      - Fact has been superseded
      - Fact has negative feedback

    Confidence thresholds:
      > 0.8  = axiom (core knowledge, rarely challenged)
      0.5-0.8 = active (normal working knowledge)
      0.2-0.5 = fading (needs re-confirmation)
      < 0.2  = candidate for archival
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def run(self) -> EvolutionResult:
        import time
        start = time.time()
        actions = []

        actions += self._boost_frequently_activated()
        actions += self._boost_co_accessed()
        actions += self._decay_unused()
        actions += self._penalize_superseded()
        actions += self._archive_low_confidence()

        self.conn.commit()
        elapsed = int((time.time() - start) * 1000)
        return EvolutionResult(
            skill="confidence",
            actions_taken=len(actions),
            details=actions,
            duration_ms=elapsed,
        )

    def _boost_frequently_activated(self) -> List[str]:
        """Facts with high activation_count get confidence boost."""
        actions = []
        rows = self.conn.execute("""
            SELECT id, confidence, activation_count
            FROM quantum_facts
            WHERE activation_count > 2
            AND confidence < 0.95
            AND status NOT IN ('abandoned')
        """).fetchall()

        for fid, conf, act_count in rows:
            # Logarithmic boost: diminishing returns
            boost = min(0.15, math.log(act_count + 1) * 0.04)
            new_conf = min(0.95, (conf or 0.5) + boost)

            if new_conf > (conf or 0.5) + 0.01:
                self.conn.execute(
                    "UPDATE quantum_facts SET confidence=? WHERE id=?", (new_conf, fid)
                )
                self.conn.execute("""
                    INSERT INTO evolution_log (fact_id, event_type, old_value, new_value, trigger, skill_name)
                    VALUES (?, 'confidence_up', ?, ?, ?, 'confidence')
                """, (fid, str(round(conf or 0.5, 3)), str(round(new_conf, 3)),
                      f"activation_count={act_count}"))
                actions.append(f"  {fid[:10]} conf {conf:.2f}→{new_conf:.2f} (activated {act_count}x)")

        return actions

    def _boost_co_accessed(self) -> List[str]:
        """Facts in strong co-access patterns get small boost."""
        actions = []
        rows = self.conn.execute("""
            SELECT DISTINCT fact_id_a as fid FROM co_access_patterns WHERE strength > 0.3
            UNION
            SELECT DISTINCT fact_id_b as fid FROM co_access_patterns WHERE strength > 0.3
        """).fetchall()

        for (fid,) in rows:
            fact = self.conn.execute(
                "SELECT confidence FROM quantum_facts WHERE id=? AND status NOT IN ('abandoned')", (fid,)
            ).fetchone()
            if not fact:
                continue

            conf = fact[0] or 0.5
            new_conf = min(0.90, conf + 0.03)

            if new_conf > conf + 0.01:
                self.conn.execute(
                    "UPDATE quantum_facts SET confidence=? WHERE id=?", (new_conf, fid)
                )
                actions.append(f"  {fid[:10]} conf {conf:.2f}→{new_conf:.2f} (co-accessed)")

        return actions

    def _decay_unused(self) -> List[str]:
        """Facts never activated and older than 7 days lose confidence."""
        actions = []
        rows = self.conn.execute("""
            SELECT id, confidence, created_at
            FROM quantum_facts
            WHERE (activation_count IS NULL OR activation_count = 0)
            AND last_activated IS NULL
            AND confidence > 0.2
            AND status NOT IN ('abandoned')
            AND created_at < datetime('now', '-7 days')
        """).fetchall()

        for fid, conf, created in rows:
            conf = conf or 0.5
            try:
                days_old = (datetime.now() - datetime.fromisoformat(created)).days
            except (ValueError, TypeError):
                days_old = 30

            # Gentle decay: -0.02 per week of inactivity
            decay = min(0.1, (days_old / 7) * 0.02)
            new_conf = max(0.1, conf - decay)

            if conf - new_conf > 0.01:
                self.conn.execute(
                    "UPDATE quantum_facts SET confidence=? WHERE id=?", (new_conf, fid)
                )
                self.conn.execute("""
                    INSERT INTO evolution_log (fact_id, event_type, old_value, new_value, trigger, skill_name)
                    VALUES (?, 'confidence_down', ?, ?, ?, 'confidence')
                """, (fid, str(round(conf, 3)), str(round(new_conf, 3)),
                      f"unused_{days_old}d"))
                actions.append(f"  {fid[:10]} conf {conf:.2f}→{new_conf:.2f} (unused {days_old}d)")

        return actions

    def _penalize_superseded(self) -> List[str]:
        """Superseded facts drop confidence significantly."""
        actions = []
        rows = self.conn.execute("""
            SELECT id, confidence FROM quantum_facts
            WHERE superseded_by IS NOT NULL
            AND superseded_by != ''
            AND confidence > 0.2
        """).fetchall()

        for fid, conf in rows:
            conf = conf or 0.5
            new_conf = max(0.1, conf * 0.5)  # halve confidence

            if conf - new_conf > 0.01:
                self.conn.execute(
                    "UPDATE quantum_facts SET confidence=? WHERE id=?", (new_conf, fid)
                )
                actions.append(f"  {fid[:10]} conf {conf:.2f}→{new_conf:.2f} (superseded)")

        return actions

    def _archive_low_confidence(self) -> List[str]:
        """Facts with very low confidence get moved to cold storage."""
        actions = []
        rows = self.conn.execute("""
            SELECT id, confidence, storage_tier FROM quantum_facts
            WHERE confidence < 0.2
            AND confidence > 0
            AND storage_tier != 'cold'
            AND status NOT IN ('abandoned')
        """).fetchall()

        for fid, conf, tier in rows:
            self.conn.execute(
                "UPDATE quantum_facts SET storage_tier='cold' WHERE id=?", (fid,)
            )
            self.conn.execute("""
                INSERT INTO evolution_log (fact_id, event_type, old_value, new_value, trigger, skill_name)
                VALUES (?, 'archived_auto', ?, 'cold', ?, 'confidence')
            """, (fid, tier, f"confidence={conf:.2f}"))
            actions.append(f"  {fid[:10]} {tier}→cold (conf={conf:.2f})")

        return actions


# ═══════════════════════════════════════════════════════════
# 3. CONSOLIDATION SKILL
# ═══════════════════════════════════════════════════════════

class ConsolidationSkill:
    """
    Merges facts that are always accessed together into composite facts.

    Rules:
      - Two facts with co_access strength > 0.5 AND accessed > 3 times together
      - Creates a new composite fact with combined content
      - Original facts get superseded_by = composite
      - Reduces token cost (1 fact instead of 2)
    """

    MIN_STRENGTH = 0.5
    MIN_CO_COUNT = 3

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def run(self) -> EvolutionResult:
        import time
        start = time.time()
        actions = []

        actions += self._merge_strong_pairs()

        self.conn.commit()
        elapsed = int((time.time() - start) * 1000)
        return EvolutionResult(
            skill="consolidation",
            actions_taken=len(actions),
            details=actions,
            duration_ms=elapsed,
        )

    def _merge_strong_pairs(self) -> List[str]:
        """Find and merge strongly co-accessed fact pairs."""
        actions = []

        pairs = self.conn.execute("""
            SELECT fact_id_a, fact_id_b, co_access_count, strength
            FROM co_access_patterns
            WHERE strength >= ? AND co_access_count >= ?
            ORDER BY strength DESC
            LIMIT 20
        """, (self.MIN_STRENGTH, self.MIN_CO_COUNT)).fetchall()

        merged_ids = set()

        for fid_a, fid_b, count, strength in pairs:
            # Skip if either already merged in this run
            if fid_a in merged_ids or fid_b in merged_ids:
                continue

            # Skip if either is already superseded
            a = self.conn.execute(
                "SELECT id, summary, raw_content, keywords, superseded_by FROM quantum_facts WHERE id=?", (fid_a,)
            ).fetchone()
            b = self.conn.execute(
                "SELECT id, summary, raw_content, keywords, superseded_by FROM quantum_facts WHERE id=?", (fid_b,)
            ).fetchone()

            if not a or not b:
                continue
            if a[4] or b[4]:  # already superseded
                continue

            # Create composite
            composite_id = f"cf_{hashlib.md5(f'{fid_a}:{fid_b}'.encode()).hexdigest()[:12]}"

            # Check if composite already exists
            existing = self.conn.execute(
                "SELECT 1 FROM quantum_facts WHERE id=?", (composite_id,)
            ).fetchone()
            if existing:
                continue

            raw_a = a[2] or a[1] or ""
            raw_b = b[2] or b[1] or ""
            composite_raw = f"{raw_a}\n---\n{raw_b}"
            composite_summary = f"[CONSOLIDATED] {(a[1] or '')[:40]} + {(b[1] or '')[:40]}"

            # Merge keywords
            try:
                kw_a = json.loads(a[3]) if a[3] else {}
                kw_b = json.loads(b[3]) if b[3] else {}
            except (json.JSONDecodeError, TypeError):
                kw_a, kw_b = {}, {}

            merged_kw = {}
            for key in set(list(kw_a.keys()) + list(kw_b.keys())):
                vals_a = kw_a.get(key, [])
                vals_b = kw_b.get(key, [])
                if isinstance(vals_a, list) and isinstance(vals_b, list):
                    merged_kw[key] = list(set(vals_a + vals_b))
                else:
                    merged_kw[key] = vals_a or vals_b

            # Build readable keywords
            kw_readable = ", ".join(
                f"{k}: {v}" for k, v in merged_kw.items()
                if isinstance(v, list) and v
            )[:200]

            # Insert composite
            self.conn.execute("""
                INSERT INTO quantum_facts
                    (id, summary, raw_content, keywords, keywords_readable,
                     status, storage_tier,
                     created_at, updated_at, confidence, activation_count,
                     version_chain, byte_size, original_size)
                VALUES (?, ?, ?, ?, ?,
                        'committed', 'hot',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0.7, 0,
                        ?, ?, ?)
            """, (
                composite_id,
                composite_summary,
                composite_raw,
                json.dumps(merged_kw),
                kw_readable,
                json.dumps([fid_a, fid_b, composite_id]),
                len(composite_raw.encode()),
                len(raw_a.encode()) + len(raw_b.encode()),
            ))

            # Mark originals as superseded
            self.conn.execute(
                "UPDATE quantum_facts SET superseded_by=? WHERE id=?", (composite_id, fid_a)
            )
            self.conn.execute(
                "UPDATE quantum_facts SET superseded_by=? WHERE id=?", (composite_id, fid_b)
            )

            # Log
            self.conn.execute("""
                INSERT INTO evolution_log (fact_id, event_type, old_value, new_value, trigger, skill_name)
                VALUES (?, 'consolidated', ?, ?, ?, 'consolidation')
            """, (composite_id, f"{fid_a}+{fid_b}", composite_id,
                  f"strength={strength:.2f},count={count}"))

            merged_ids.add(fid_a)
            merged_ids.add(fid_b)
            actions.append(f"  {fid_a[:10]}+{fid_b[:10]} → {composite_id[:14]} (str={strength:.2f})")

        return actions


# ═══════════════════════════════════════════════════════════
# 4. PATTERN SKILL (co-occurrence detection)
# ═══════════════════════════════════════════════════════════

class PatternSkill:
    """
    Detects co-occurrence patterns and strengthens co-access links.
    Prepares data for predictive pre-loading (Phase 8D).
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def run(self) -> EvolutionResult:
        import time
        start = time.time()
        actions = []

        actions += self._strengthen_activation_patterns()
        actions += self._detect_domain_pairs()

        self.conn.commit()
        elapsed = int((time.time() - start) * 1000)
        return EvolutionResult(
            skill="pattern",
            actions_taken=len(actions),
            details=actions,
            duration_ms=elapsed,
        )

    def _strengthen_activation_patterns(self) -> List[str]:
        """
        Facts activated in the same context_state get co-access boost.
        Look at evolution_log for facts activated with same trigger hash.
        """
        actions = []

        # Group activations by trigger (context hash)
        triggers = self.conn.execute("""
            SELECT trigger, GROUP_CONCAT(fact_id) as facts
            FROM evolution_log
            WHERE event_type = 'activated'
            AND created_at > datetime('now', '-7 days')
            GROUP BY trigger
            HAVING COUNT(fact_id) >= 2
        """).fetchall()

        for trigger, facts_str in triggers:
            fact_ids = list(set(facts_str.split(",")))
            if len(fact_ids) < 2:
                continue

            # Record co-access for pairs (limit to top 10 per trigger)
            for i, a in enumerate(fact_ids[:10]):
                for b in fact_ids[i+1:10]:
                    pair = tuple(sorted([a, b]))
                    existing = self.conn.execute(
                        "SELECT id, co_access_count, strength FROM co_access_patterns WHERE fact_id_a=? AND fact_id_b=?",
                        pair
                    ).fetchone()

                    if existing:
                        new_count = existing[1] + 1
                        new_strength = min(1.0, 0.1 + new_count * 0.05)
                        if new_strength > existing[2]:
                            self.conn.execute("""
                                UPDATE co_access_patterns
                                SET co_access_count=?, strength=?, last_seen=CURRENT_TIMESTAMP
                                WHERE id=?
                            """, (new_count, new_strength, existing[0]))
                    else:
                        self.conn.execute("""
                            INSERT OR IGNORE INTO co_access_patterns (fact_id_a, fact_id_b)
                            VALUES (?, ?)
                        """, pair)

        # Count new strong patterns
        strong = self.conn.execute(
            "SELECT COUNT(*) FROM co_access_patterns WHERE strength >= 0.3"
        ).fetchone()[0]
        actions.append(f"  {strong} strong co-access patterns (>= 0.3)")

        return actions

    def _detect_domain_pairs(self) -> List[str]:
        """Detect which domains frequently appear together."""
        actions = []

        pairs = self.conn.execute("""
            SELECT d1.value as dom1, d2.value as dom2, COUNT(*) as cnt
            FROM kw_bitmap b1
            JOIN kw_bitmap b2 ON b1.fact_id = b2.fact_id AND b1.value_id < b2.value_id
            JOIN kw_dictionary d1 ON b1.value_id = d1.id
            JOIN kw_dictionary d2 ON b2.value_id = d2.id
            WHERE b1.dimension = 'domain' AND b2.dimension = 'domain'
            GROUP BY d1.value, d2.value
            HAVING cnt >= 3
            ORDER BY cnt DESC
            LIMIT 10
        """).fetchall()

        if pairs:
            for dom1, dom2, cnt in pairs:
                actions.append(f"  domain pair: {dom1}+{dom2} ({cnt} facts)")

        return actions


# ═══════════════════════════════════════════════════════════
# 5. EVOLUTION ORCHESTRATOR
# ═══════════════════════════════════════════════════════════

class EvolutionOrchestrator:
    """
    Runs all evolution skills in sequence.
    Called by cron or manually via `mem evolve run`.
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def run_all(self) -> List[EvolutionResult]:
        """Run all evolution skills in order."""
        results = []

        skills = [
            VersioningSkill(self.conn),
            ConfidenceSkill(self.conn),
            PatternSkill(self.conn),
            ConsolidationSkill(self.conn),  # last — depends on co-access data
        ]

        for skill in skills:
            try:
                result = skill.run()
                self.conn.commit()
                results.append(result)
            except Exception as e:
                results.append(EvolutionResult(
                    skill=skill.__class__.__name__,
                    actions_taken=-1,
                    details=[f"  ERROR: {str(e)}"],
                ))

        # Record run in metadata
        self.conn.execute("""
            INSERT OR REPLACE INTO engine_metadata (key, value, updated_at)
            VALUES ('last_evolution_run', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        total_actions = sum(r.actions_taken for r in results if r.actions_taken > 0)
        self.conn.execute("""
            INSERT OR REPLACE INTO engine_metadata (key, value, updated_at)
            VALUES ('last_evolution_actions', ?, CURRENT_TIMESTAMP)
        """, (str(total_actions),))
        self.conn.commit()

        return results

    def run_single(self, skill_name: str) -> EvolutionResult:
        """Run a single evolution skill."""
        skill_map = {
            "versioning": VersioningSkill,
            "confidence": ConfidenceSkill,
            "consolidation": ConsolidationSkill,
            "pattern": PatternSkill,
        }
        cls = skill_map.get(skill_name)
        if not cls:
            return EvolutionResult(skill=skill_name, actions_taken=-1,
                                   details=[f"Unknown skill: {skill_name}"])

        skill = cls(self.conn)
        result = skill.run()
        self.conn.commit()
        return result

    def get_status(self) -> Dict:
        """Get evolution engine status."""
        last_run = self.conn.execute(
            "SELECT value FROM engine_metadata WHERE key='last_evolution_run'"
        ).fetchone()
        last_actions = self.conn.execute(
            "SELECT value FROM engine_metadata WHERE key='last_evolution_actions'"
        ).fetchone()

        # Recent evolution events
        recent = self.conn.execute("""
            SELECT event_type, COUNT(*) as cnt
            FROM evolution_log
            WHERE created_at > datetime('now', '-24 hours')
            GROUP BY event_type ORDER BY cnt DESC
        """).fetchall()

        # Confidence distribution
        conf_dist = self.conn.execute("""
            SELECT
                SUM(CASE WHEN confidence > 0.8 THEN 1 ELSE 0 END) as axioms,
                SUM(CASE WHEN confidence BETWEEN 0.5 AND 0.8 THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN confidence BETWEEN 0.2 AND 0.5 THEN 1 ELSE 0 END) as fading,
                SUM(CASE WHEN confidence < 0.2 THEN 1 ELSE 0 END) as archive_candidates
            FROM quantum_facts WHERE status NOT IN ('abandoned')
        """).fetchone()

        # Version chains
        chains = self.conn.execute(
            "SELECT COUNT(*) FROM quantum_facts WHERE superseded_by IS NOT NULL AND superseded_by != ''"
        ).fetchone()[0]

        # Co-access patterns
        patterns = self.conn.execute(
            "SELECT COUNT(*) FROM co_access_patterns WHERE strength >= 0.3"
        ).fetchone()[0]

        return {
            "last_run": last_run[0] if last_run else "never",
            "last_actions": int(last_actions[0]) if last_actions else 0,
            "recent_events": {r[0]: r[1] for r in recent},
            "confidence": {
                "axioms": conf_dist[0] or 0,
                "active": conf_dist[1] or 0,
                "fading": conf_dist[2] or 0,
                "archive_candidates": conf_dist[3] or 0,
            },
            "version_chains": chains,
            "strong_patterns": patterns,
        }


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evolution Engine — Phase 8C")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Run all evolution skills")

    p = sub.add_parser("skill", help="Run a single skill")
    p.add_argument("name", choices=["versioning", "confidence", "consolidation", "pattern"])

    sub.add_parser("status", help="Evolution engine status")

    p = sub.add_parser("history", help="Recent evolution events")
    p.add_argument("--n", type=int, default=20)

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    orch = EvolutionOrchestrator()
    orch.connect()

    try:
        if args.command == "run":
            results = orch.run_all()
            if args.json:
                print(json.dumps([asdict(r) for r in results], indent=2))
            else:
                print(f"\n  EVOLUTION RUN")
                print(f"  {'═' * 50}\n")
                total = 0
                total_ms = 0
                for r in results:
                    icon = "✔" if r.actions_taken >= 0 else "✖"
                    print(f"  {icon} {r.skill:20s} {r.actions_taken} actions  ({r.duration_ms}ms)")
                    for d in r.details[:5]:
                        print(f"    {d}")
                    if len(r.details) > 5:
                        print(f"    ... +{len(r.details)-5} more")
                    total += max(0, r.actions_taken)
                    total_ms += r.duration_ms
                print(f"\n  Total: {total} actions in {total_ms}ms\n")

        elif args.command == "skill":
            result = orch.run_single(args.name)
            if args.json:
                print(json.dumps(asdict(result), indent=2))
            else:
                print(f"\n  {result.skill}: {result.actions_taken} actions ({result.duration_ms}ms)")
                for d in result.details:
                    print(f"  {d}")
                print()

        elif args.command == "status":
            status = orch.get_status()
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                print(f"\n  EVOLUTION STATUS")
                print(f"  {'═' * 50}\n")
                print(f"  Last run:     {status['last_run']}")
                print(f"  Last actions: {status['last_actions']}")
                print(f"\n  CONFIDENCE DISTRIBUTION:")
                c = status['confidence']
                print(f"    Axioms (>0.8):    {c['axioms']}")
                print(f"    Active (0.5-0.8): {c['active']}")
                print(f"    Fading (0.2-0.5): {c['fading']}")
                print(f"    Archive (<0.2):   {c['archive_candidates']}")
                print(f"\n  Version chains:   {status['version_chains']} superseded facts")
                print(f"  Strong patterns:  {status['strong_patterns']} co-access pairs")
                if status['recent_events']:
                    print(f"\n  RECENT (24h):")
                    for evt, cnt in status['recent_events'].items():
                        print(f"    {evt}: {cnt}")
                print()

        elif args.command == "history":
            rows = orch.conn.execute("""
                SELECT fact_id, event_type, old_value, new_value, trigger, skill_name, created_at
                FROM evolution_log ORDER BY created_at DESC LIMIT ?
            """, (args.n,)).fetchall()

            print(f"\n  EVOLUTION HISTORY (last {args.n})")
            print(f"  {'═' * 50}\n")
            for r in rows:
                skill = r["skill_name"] or "?"
                print(f"  {r['created_at'][:19]}  [{skill:13s}] {r['event_type']:17s} {(r['fact_id'] or '')[:12]}")
                if r['old_value'] and r['new_value']:
                    print(f"    {r['old_value'][:30]} → {r['new_value'][:30]}")
            print()

        else:
            parser.print_help()

    finally:
        orch.close()


if __name__ == "__main__":
    main()
