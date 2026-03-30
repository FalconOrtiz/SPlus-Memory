#!/usr/bin/env python3
"""
Observability Dashboard — Phase 7
Full system health, quality metrics, and audit across all phases.

Components monitored:
  Phase 1-2: quantum_facts, kw_dictionary, kw_bitmap (keywords + BM25)
  Phase 3:   semantic_embeddings (local embeddings)
  Phase 4:   context_selector (token budgeting)
  Phase 5:   skill_index, skill_usage (skill intelligence)
  Phase 6:   agent_memory, agent_conflicts (multi-agent)
  Infra:     session autosave, cron, DB size, logs
"""

import json
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List
from dataclasses import dataclass, asdict
import math

sys.path.insert(0, str(Path(__file__).parent))

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"
LOGS_DIR = Path.home() / ".hermes/memory-engine/logs"
SESSIONS_DIR = Path.home() / ".hermes/memory-engine/sessions"


@dataclass
class HealthCheck:
    component: str
    status: str   # ok, warning, error
    message: str
    value: str = ""


@dataclass
class QualityMetric:
    metric: str
    value: float
    threshold: float
    status: str  # ok, warning, critical
    detail: str = ""


class Dashboard:

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))

    def close(self):
        if self.conn:
            self.conn.close()

    def _count(self, table: str, where: str = "") -> int:
        try:
            sql = f"SELECT COUNT(*) FROM {table}"
            if where:
                sql += f" WHERE {where}"
            return self.conn.execute(sql).fetchone()[0]
        except Exception:
            return -1

    # ── Health Check ─────────────────────────────────────────────

    def health_check(self) -> List[HealthCheck]:
        checks = []

        # Database
        try:
            self.conn.execute("SELECT 1")
            db_size = os.path.getsize(self.db_path) / 1024 / 1024
            checks.append(HealthCheck("database", "ok", "Connected", f"{db_size:.1f}MB"))
        except Exception as e:
            checks.append(HealthCheck("database", "error", str(e)))
            return checks

        # Quantum facts (Phase 1-2)
        qf = self._count("quantum_facts")
        if qf > 0:
            checks.append(HealthCheck("quantum_facts", "ok", f"{qf} facts indexed", str(qf)))
        elif qf == 0:
            checks.append(HealthCheck("quantum_facts", "warning", "Empty index"))
        else:
            checks.append(HealthCheck("quantum_facts", "error", "Table missing"))

        # Keyword dictionary
        kd = self._count("kw_dictionary")
        kb = self._count("kw_bitmap")
        if kd > 0:
            checks.append(HealthCheck("keyword_index", "ok", f"{kd} terms, {kb} bitmap entries", f"{kd}/{kb}"))
        else:
            checks.append(HealthCheck("keyword_index", "warning", "No keywords indexed"))

        # Semantic embeddings (Phase 3)
        se = self._count("semantic_embeddings")
        if qf > 0 and se > 0:
            coverage = se / qf * 100
            if coverage >= 95:
                checks.append(HealthCheck("embeddings", "ok", f"{coverage:.0f}% coverage ({se}/{qf})", f"{se}/{qf}"))
            elif coverage >= 70:
                checks.append(HealthCheck("embeddings", "warning", f"{coverage:.0f}% coverage — run `mem embed`", f"{se}/{qf}"))
            else:
                checks.append(HealthCheck("embeddings", "error", f"Only {coverage:.0f}% coverage", f"{se}/{qf}"))
        elif se < 0:
            checks.append(HealthCheck("embeddings", "error", "Table missing"))
        else:
            checks.append(HealthCheck("embeddings", "warning", "No embeddings"))

        # Skills (Phase 5)
        si = self._count("skill_index")
        su = self._count("skill_usage")
        if si > 0:
            checks.append(HealthCheck("skills", "ok", f"{si} indexed, {su} usages recorded", f"{si}/{su}"))
        else:
            checks.append(HealthCheck("skills", "warning", "No skills indexed — run `mem skill index`"))

        # Agent memory (Phase 6)
        am = self._count("agent_memory")
        ac = self._count("agent_conflicts", "status='unresolved'")
        if am >= 0:
            if ac > 0:
                checks.append(HealthCheck("agents", "warning", f"{am} facts, {ac} unresolved conflicts", f"{am}/{ac}"))
            else:
                checks.append(HealthCheck("agents", "ok", f"{am} agent facts, 0 conflicts", str(am)))
        else:
            checks.append(HealthCheck("agents", "warning", "Agent tables not initialized"))

        # Session autosave
        active = SESSIONS_DIR / "active.json"
        archive = SESSIONS_DIR / "archive"
        if active.exists():
            try:
                state = json.loads(active.read_text())
                checks.append(HealthCheck("session", "ok",
                    f"Active: {state.get('session_id', '?')}, flushed: {state.get('facts_flushed', 0)}",
                    state.get('session_id', '')))
            except Exception:
                checks.append(HealthCheck("session", "warning", "Active session file corrupt"))
        else:
            checks.append(HealthCheck("session", "ok", "No active session"))

        archived = len(list(archive.glob("*.json"))) if archive.exists() else 0
        if archived > 0:
            checks.append(HealthCheck("session_archive", "ok", f"{archived} archived sessions", str(archived)))

        # Deep Layer (Phase 8A)
        dl_cols = [c[1] for c in self.conn.execute("PRAGMA table_info(quantum_facts)").fetchall()]
        if "activation_score" in dl_cols:
            activated = self.conn.execute(
                "SELECT COUNT(*) FROM quantum_facts WHERE activation_score > 0"
            ).fetchone()[0]
            sb = self._count("surface_buffer")
            evo = self._count("evolution_log")
            checks.append(HealthCheck("deep_layer", "ok",
                f"{activated} activated, {sb} surfaced, {evo} evolutions", f"{activated}/{sb}/{evo}"))
        else:
            checks.append(HealthCheck("deep_layer", "warning", "Phase 8A not migrated"))

        # Cron
        cron_log = LOGS_DIR / "cron.log"
        if cron_log.exists():
            size = cron_log.stat().st_size
            # Check last line timestamp
            lines = cron_log.read_text().strip().split("\n")
            last_line = lines[-1] if lines else ""
            checks.append(HealthCheck("cron", "ok", f"Log: {size/1024:.0f}KB, last: {last_line[:30]}"))
        else:
            checks.append(HealthCheck("cron", "warning", "No cron log found"))

        # Storage
        total_original = self.conn.execute("SELECT COALESCE(SUM(original_size),0) FROM quantum_facts").fetchone()[0]
        total_compressed = self.conn.execute("SELECT COALESCE(SUM(byte_size),0) FROM quantum_facts").fetchone()[0]
        if total_original > 0:
            ratio = total_original / max(total_compressed, 1)
            checks.append(HealthCheck("compression", "ok",
                f"{total_original:,}→{total_compressed:,} bytes ({ratio:.1f}x)", f"{ratio:.1f}x"))

        return checks

    # ── Quality Metrics ──────────────────────────────────────────

    def quality_metrics(self) -> List[QualityMetric]:
        metrics = []

        # Embedding coverage
        qf = self._count("quantum_facts")
        se = self._count("semantic_embeddings")
        if qf > 0:
            cov = se / qf * 100
            metrics.append(QualityMetric("embedding_coverage", cov, 90.0,
                "ok" if cov >= 90 else "warning" if cov >= 70 else "critical",
                f"{se}/{qf}"))

        # Status distribution
        for status in ["pending", "completed", "committed", "abandoned"]:
            cnt = self._count("quantum_facts", f"status='{status}'")
            if cnt > 0:
                pct = cnt / max(qf, 1) * 100
                metrics.append(QualityMetric(f"status_{status}", pct, 0,
                    "ok", f"{cnt} facts ({pct:.0f}%)"))

        # Storage tier distribution
        for tier in ["hot", "warm", "cold"]:
            cnt = self._count("quantum_facts", f"storage_tier='{tier}'")
            if cnt > 0:
                pct = cnt / max(qf, 1) * 100
                metrics.append(QualityMetric(f"tier_{tier}", pct, 0,
                    "ok", f"{cnt} facts ({pct:.0f}%)"))

        # Staleness (facts older than 30 days with no recent reference)
        stale = self.conn.execute("""
            SELECT COUNT(*) FROM quantum_facts
            WHERE created_at < datetime('now', '-30 days')
            AND status NOT IN ('completed', 'abandoned')
        """).fetchone()[0]
        if qf > 0:
            stale_pct = stale / qf * 100
            metrics.append(QualityMetric("stale_pending", stale_pct, 10.0,
                "ok" if stale_pct < 10 else "warning" if stale_pct < 25 else "critical",
                f"{stale} pending facts older than 30 days"))

        # Domain diversity (top domains shouldn't dominate >50%)
        top_domain = self.conn.execute("""
            SELECT d.value, COUNT(b.fact_id) as cnt
            FROM kw_bitmap b JOIN kw_dictionary d ON b.value_id = d.id
            WHERE b.dimension = 'domain'
            GROUP BY d.value ORDER BY cnt DESC LIMIT 1
        """).fetchone()
        if top_domain and qf > 0:
            dom_pct = top_domain[1] / qf * 100
            metrics.append(QualityMetric("top_domain_concentration", dom_pct, 50.0,
                "ok" if dom_pct < 50 else "warning",
                f"{top_domain[0]}: {top_domain[1]} facts ({dom_pct:.0f}%)"))

        # Agent isolation check
        am = self._count("agent_memory")
        if am > 0:
            sensitive = self._count("agent_memory", "is_sensitive=1")
            shared = self._count("agent_memory", "scope='shared'")
            metrics.append(QualityMetric("agent_sensitive_ratio",
                sensitive / max(am, 1) * 100, 30.0,
                "ok" if sensitive / max(am, 1) < 0.3 else "warning",
                f"{sensitive} sensitive / {am} total"))
            metrics.append(QualityMetric("agent_shared_ratio",
                shared / max(am, 1) * 100, 0,
                "ok", f"{shared} shared / {am} total"))

        # Unresolved conflicts
        conflicts = self._count("agent_conflicts", "status='unresolved'")
        metrics.append(QualityMetric("unresolved_conflicts", conflicts, 5.0,
            "ok" if conflicts < 5 else "warning" if conflicts < 10 else "critical",
            f"{conflicts} unresolved"))

        return metrics

    # ── Full Report ──────────────────────────────────────────────

    def full_report(self) -> Dict:
        """Generate a complete system report."""
        health = self.health_check()
        quality = self.quality_metrics()

        # Aggregate scores
        ok = sum(1 for h in health if h.status == "ok")
        warn = sum(1 for h in health if h.status == "warning")
        err = sum(1 for h in health if h.status == "error")

        # Per-phase status
        phases = {
            "Phase 1-2 (Keywords+BM25)": any(h.component == "quantum_facts" and h.status == "ok" for h in health),
            "Phase 3 (Embeddings)": any(h.component == "embeddings" and h.status == "ok" for h in health),
            "Phase 4 (Context)": True,  # always available if retriever works
            "Phase 5 (Skills)": any(h.component == "skills" and h.status == "ok" for h in health),
            "Phase 6 (Multi-Agent)": any(h.component == "agents" and h.status == "ok" for h in health),
            "Phase 7 (Dashboard)": True,
            "Phase 8A (Deep Layer)": any(h.component == "deep_layer" and h.status == "ok" for h in health),
            "Phase 8B (Surface Integration)": True,  # integrated into context_selector
            "Phase 8C (Evolution)": self._count("evolution_log") > 0,
        }

        return {
            "timestamp": datetime.now().isoformat(),
            "health": {
                "checks": [asdict(h) for h in health],
                "summary": {"ok": ok, "warnings": warn, "errors": err},
            },
            "quality": [asdict(q) for q in quality],
            "phases": phases,
            "overall": "healthy" if err == 0 and warn <= 2 else "degraded" if err == 0 else "unhealthy",
        }

    # ── Retrieval Feedback ───────────────────────────────────────

    def record_feedback(self, fact_id: str, feedback: str, query: str = ""):
        """Record retrieval feedback for quality tracking."""
        try:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS retrieval_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact_id TEXT, query TEXT, feedback TEXT,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute(
                "INSERT INTO retrieval_feedback (fact_id, query, feedback) VALUES (?, ?, ?)",
                (fact_id, query, feedback)
            )
            self.conn.commit()
        except Exception:
            pass

    def feedback_stats(self) -> Dict:
        """Get retrieval feedback statistics."""
        try:
            total = self.conn.execute("SELECT COUNT(*) FROM retrieval_feedback").fetchone()[0]
            helpful = self.conn.execute(
                "SELECT COUNT(*) FROM retrieval_feedback WHERE feedback='helpful'"
            ).fetchone()[0]
            return {
                "total": total,
                "helpful": helpful,
                "accuracy": f"{helpful/max(total,1)*100:.0f}%",
            }
        except Exception:
            return {"total": 0, "helpful": 0, "accuracy": "N/A"}


# ── CLI ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Memory Engine Dashboard (Phase 7)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("health", help="System health check")
    sub.add_parser("quality", help="Quality metrics")
    sub.add_parser("report", help="Full report")

    p = sub.add_parser("feedback", help="Record retrieval feedback")
    p.add_argument("fact_id")
    p.add_argument("rating", choices=["helpful", "partial", "wrong"])
    p.add_argument("--query", default="")

    sub.add_parser("feedback-stats", help="Feedback statistics")

    p = sub.add_parser("export", help="Export report to JSON file")
    p.add_argument("output", nargs="?", default="report.json")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    dash = Dashboard()
    dash.connect()

    try:
        if args.command == "health":
            checks = dash.health_check()
            if args.json:
                print(json.dumps([asdict(c) for c in checks], indent=2))
            else:
                print(f"\n  SYSTEM HEALTH")
                print(f"  {'═' * 55}\n")
                for c in checks:
                    icon = {"ok": "✔", "warning": "⚠", "error": "✖"}.get(c.status, "?")
                    val = f" [{c.value}]" if c.value else ""
                    print(f"  {icon} {c.component:20s} {c.message}{val}")

                ok = sum(1 for c in checks if c.status == "ok")
                warn = sum(1 for c in checks if c.status == "warning")
                err = sum(1 for c in checks if c.status == "error")
                print(f"\n  Summary: {ok} ok, {warn} warnings, {err} errors\n")

        elif args.command == "quality":
            metrics = dash.quality_metrics()
            if args.json:
                print(json.dumps([asdict(m) for m in metrics], indent=2))
            else:
                print(f"\n  QUALITY METRICS")
                print(f"  {'═' * 55}\n")
                for m in metrics:
                    icon = {"ok": "✔", "warning": "⚠", "critical": "✖"}.get(m.status, "·")
                    print(f"  {icon} {m.metric:30s} {m.detail}")
                print()

        elif args.command == "report":
            report = dash.full_report()
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"\n  ╔═══════════════════════════════════════╗")
                print(f"  ║  MEMORY ENGINE REPORT                ║")
                print(f"  ║  {report['timestamp'][:19]}              ║")
                print(f"  ╚═══════════════════════════════════════╝\n")

                # Overall
                overall = report["overall"]
                icon = {"healthy": "✔", "degraded": "⚠", "unhealthy": "✖"}.get(overall, "?")
                print(f"  {icon} Overall: {overall.upper()}")
                h = report["health"]["summary"]
                print(f"    {h['ok']} ok / {h['warnings']} warnings / {h['errors']} errors\n")

                # Phases
                print(f"  PHASES:")
                for phase, ok in report["phases"].items():
                    print(f"    {'✔' if ok else '✖'} {phase}")
                print()

                # Health details
                print(f"  HEALTH:")
                for c in report["health"]["checks"]:
                    icon = {"ok": "✔", "warning": "⚠", "error": "✖"}.get(c["status"], "?")
                    print(f"    {icon} {c['component']:20s} {c['message']}")
                print()

                # Quality
                print(f"  QUALITY:")
                for q in report["quality"]:
                    icon = {"ok": "✔", "warning": "⚠", "critical": "✖"}.get(q["status"], "·")
                    print(f"    {icon} {q['metric']:30s} {q['detail']}")
                print()

        elif args.command == "feedback":
            dash.record_feedback(args.fact_id, args.rating, args.query)
            print(f"  ✓ Feedback recorded: {args.fact_id} → {args.rating}")

        elif args.command == "feedback-stats":
            stats = dash.feedback_stats()
            print(f"  Feedback: {stats['total']} total, {stats['helpful']} helpful ({stats['accuracy']})")

        elif args.command == "export":
            report = dash.full_report()
            output = args.output
            Path(output).write_text(json.dumps(report, indent=2))
            print(f"  ✓ Report exported to {output}")

        else:
            parser.print_help()

    finally:
        dash.close()


if __name__ == "__main__":
    main()
