#!/usr/bin/env python3
"""
Phase 8D Integration Test

End-to-end test cycle for temporal engine + domain scheduler + deep layer.

Flow:
  1. Learn patterns (from existing heat map)
  2. Predict (get current time slot prediction)
  3. Schedule (domain scheduler activates domains)
  4. Verify (check surface buffer population)
  5. Report
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"


def test_full_cycle() -> Dict:
    """Full integration test."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": {},
    }

    # ── 1. TEMPORAL ENGINE: LEARN ────────────────────────
    print("\n  ⚙  TEST 1: Temporal Learning")
    print("  " + "─" * 50)

    from temporal_engine import TemporalOrchestrator

    orch = TemporalOrchestrator()
    orch.connect()

    try:
        heat_map = orch.learn()
        results["tests"]["temporal_learn"] = {
            "status": "pass" if heat_map else "fail",
            "slots_learned": len(heat_map),
            "top_slot": next(iter(heat_map)) if heat_map else None,
        }
        print(f"  ✔ Learned {len(heat_map)} time slots")
        for slot in list(heat_map.keys())[:2]:
            domains = sorted(heat_map[slot].items(), key=lambda x: x[1], reverse=True)
            top = ", ".join(f"{d}({c})" for d, c in domains[:3])
            print(f"    {slot:25s} {top}")
    except Exception as e:
        results["tests"]["temporal_learn"] = {"status": "fail", "error": str(e)}
        print(f"  ✖ {e}")
    finally:
        orch.close()

    # ── 2. TEMPORAL ENGINE: PREDICT ────────────────────
    print("\n  ⚙  TEST 2: Temporal Prediction")
    print("  " + "─" * 50)

    orch = TemporalOrchestrator()
    orch.connect()

    try:
        prediction = orch.predict()
        results["tests"]["temporal_predict"] = {
            "status": "pass",
            "time_slot": prediction.time_slot,
            "confidence": prediction.confidence,
            "domains": prediction.predicted_domains,
        }
        print(f"  ✔ Prediction: {prediction.time_slot}")
        print(f"    Confidence: {prediction.confidence:.2f}")
        print(f"    Domains:    {', '.join(prediction.predicted_domains) or '(none)'}")
    except Exception as e:
        results["tests"]["temporal_predict"] = {"status": "fail", "error": str(e)}
        print(f"  ✖ {e}")
    finally:
        orch.close()

    # ── 3. DOMAIN SCHEDULER: AUTO-SCHEDULE ────────────
    print("\n  ⚙  TEST 3: Domain Scheduling")
    print("  " + "─" * 50)

    from domain_scheduler import DomainScheduler

    scheduler = DomainScheduler()
    scheduler.connect()

    try:
        result = scheduler.auto_schedule()
        test_status = "pass" if result["status"] in ["ok", "skipped"] else "fail"
        results["tests"]["domain_schedule"] = {
            "status": test_status,
            "scheduler_status": result["status"],
            "activated": result.get("activated", 0),
            "surfaced": result.get("surfaced", 0),
        }
        print(f"  ✔ Scheduler status: {result['status']}")
        if result["status"] == "ok":
            print(f"    Activated: {result.get('activated', 0)} facts")
            print(f"    Surfaced:  {result.get('surfaced', 0)} facts")
        else:
            print(f"    Reason: {result.get('reason', 'unknown')}")
    except Exception as e:
        results["tests"]["domain_schedule"] = {"status": "fail", "error": str(e)}
        print(f"  ✖ {e}")
    finally:
        scheduler.close()

    # ── 4. DEEP LAYER: SURFACE BUFFER CHECK ──────────
    print("\n  ⚙  TEST 4: Surface Buffer Verification")
    print("  " + "─" * 50)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        sb_count = conn.execute("SELECT COUNT(*) as cnt FROM surface_buffer").fetchone()["cnt"]
        sb_status = conn.execute(
            "SELECT SUM(token_estimate) as total_tokens FROM surface_buffer"
        ).fetchone()

        results["tests"]["surface_buffer"] = {
            "status": "pass",
            "buffer_count": sb_count,
            "total_tokens": sb_status["total_tokens"] or 0,
        }
        print(f"  ✔ Surface Buffer status:")
        print(f"    Items:  {sb_count}")
        print(f"    Tokens: {sb_status['total_tokens'] or 0}")
    except Exception as e:
        results["tests"]["surface_buffer"] = {"status": "fail", "error": str(e)}
        print(f"  ✖ {e}")

    # ── 5. EVOLUTION LOG CHECK ─────────────────────────
    print("\n  ⚙  TEST 5: Evolution Log Verification")
    print("  " + "─" * 50)

    try:
        pred_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM evolution_log WHERE event_type LIKE '%prediction%'"
        ).fetchone()["cnt"]
        sched_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM evolution_log WHERE event_type LIKE '%scheduled%'"
        ).fetchone()["cnt"]

        results["tests"]["evolution_log"] = {
            "status": "pass",
            "predictions_logged": pred_count,
            "activations_logged": sched_count,
        }
        print(f"  ✔ Evolution Log:")
        print(f"    Prediction events:  {pred_count}")
        print(f"    Scheduling events:  {sched_count}")
    except Exception as e:
        results["tests"]["evolution_log"] = {"status": "fail", "error": str(e)}
        print(f"  ✖ {e}")

    # ── 6. HEAT MAP DATA CHECK ────────────────────────
    print("\n  ⚙  TEST 6: Heat Map Data Integrity")
    print("  " + "─" * 50)

    try:
        hm_row = conn.execute(
            "SELECT value FROM engine_metadata WHERE key='prediction_heat_map'"
        ).fetchone()

        if hm_row and hm_row[0]:
            try:
                heat_map = json.loads(hm_row[0])
                results["tests"]["heat_map"] = {
                    "status": "pass",
                    "slots": len(heat_map),
                    "total_activations": sum(
                        sum(v.values()) for v in heat_map.values()
                    ),
                }
                print(f"  ✔ Heat Map integrity:")
                print(f"    Slots: {len(heat_map)}")
                print(f"    Total activations: {sum(sum(v.values()) for v in heat_map.values())}")
            except json.JSONDecodeError:
                results["tests"]["heat_map"] = {"status": "fail", "error": "corrupt heat map"}
                print(f"  ✖ Heat map is corrupted")
        else:
            results["tests"]["heat_map"] = {"status": "fail", "error": "no heat map"}
            print(f"  ✖ No heat map found")

    except Exception as e:
        results["tests"]["heat_map"] = {"status": "fail", "error": str(e)}
        print(f"  ✖ {e}")

    finally:
        conn.close()

    # ── SUMMARY ────────────────────────────────────────
    print("\n  " + "=" * 50)
    print("  TEST SUMMARY")
    print("  " + "=" * 50 + "\n")

    passed = sum(1 for t in results["tests"].values() if t.get("status") == "pass")
    total = len(results["tests"])

    for test_name, test_result in results["tests"].items():
        icon = "✔" if test_result.get("status") == "pass" else "✖"
        print(f"  {icon} {test_name:30s} {test_result.get('status', 'unknown')}")

    print(f"\n  RESULT: {passed}/{total} tests passed\n")

    results["summary"] = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "success": passed == total,
    }

    return results


def test_temporal_queries() -> Dict:
    """Test temporal query capabilities."""
    results = {}

    from temporal_engine import TemporalOrchestrator

    orch = TemporalOrchestrator()
    orch.connect()

    print("\n  ⚙  TEST: Temporal Queries")
    print("  " + "─" * 50)

    try:
        # Test "today"
        today_facts = orch.query("today")
        results["query_today"] = len(today_facts)
        print(f"  ✔ 'today' query: {len(today_facts)} facts")

        # Test "this week"
        week_facts = orch.query("this week")
        results["query_this_week"] = len(week_facts)
        print(f"  ✔ 'this week' query: {len(week_facts)} facts")

        # Test range
        range_facts = orch.query_range("2026-03-20", "2026-03-23")
        results["query_range"] = len(range_facts)
        print(f"  ✔ range query: {len(range_facts)} facts")

    except Exception as e:
        results["error"] = str(e)
        print(f"  ✖ {e}")
    finally:
        orch.close()

    return results


if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  PHASE 8D INTEGRATION TEST")
    print("=" * 55)

    cycle_results = test_full_cycle()
    query_results = test_temporal_queries()

    print("\n" + "=" * 55)
    print("  DETAILED RESULTS")
    print("=" * 55)
    print(json.dumps(
        {
            "integration_cycle": cycle_results,
            "temporal_queries": query_results,
        },
        indent=2,
        default=str,
    ))
