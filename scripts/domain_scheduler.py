#!/usr/bin/env python3
"""
Phase 8D: Domain Scheduler — Auto-activation based on temporal predictions

Bridges Temporal Engine predictions into automatic domain activation.
When time-based patterns suggest certain domains will be needed,
the scheduler triggers them proactively into the Deep Layer.

Flow:
  TemporalOrchestrator.predict()
    → DomainScheduler.schedule()
      → DeepLayer.process()
        → Surface Buffer populated
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"


@dataclass
class ScheduledActivation:
    """A scheduled domain activation."""
    domains: List[str]
    confidence: float
    reason: str
    time_slot: str
    triggered_at: str
    deep_layer_result: Optional[Dict] = None


class DomainScheduler:
    """
    Auto-activate domains based on temporal predictions.
    
    Strategy:
      1. Prediction says "monday_morning needs memory_system + ai_agents"
      2. Scheduler creates a synthetic activation signal
      3. Feeds it through DeepLayer.process()
      4. Facts bubble up to Surface Buffer automatically
      5. Agent sees them pre-loaded when session starts
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

    def schedule(
        self,
        predicted_domains: List[str],
        confidence: float,
        time_slot: str,
        reason: str,
        deep_layer=None,
    ) -> ScheduledActivation:
        """
        Schedule a domain activation from temporal prediction.
        
        Args:
            predicted_domains: List of domain strings (e.g. ["memory_system", "ai_agents"])
            confidence: Float 0-1 from the prediction
            time_slot: String like "monday_morning"
            reason: Description of why this activation was triggered
            deep_layer: Optional DeepLayer instance. If None, imports and creates.
        
        Returns:
            ScheduledActivation with result from DeepLayer
        """
        if not predicted_domains or confidence < 0.15:
            return ScheduledActivation(
                domains=[],
                confidence=confidence,
                reason=f"skipped: low confidence ({confidence})",
                time_slot=time_slot,
                triggered_at=datetime.now().isoformat(),
                deep_layer_result=None,
            )

        # Build synthetic activation signal from domains
        signal = " ".join(predicted_domains)

        # Import Deep Layer if not provided
        if deep_layer is None:
            from deep_layer import DeepLayer

            deep_layer = DeepLayer()
            deep_layer.connect()
            own_dl = True
        else:
            own_dl = False

        try:
            # Feed through Deep Layer
            result = deep_layer.process(
                signal,
                agent="scheduler",
                skills=["temporal_engine"],
                session_id=f"schedule_{time_slot}_{datetime.now().timestamp()}",
            )

            # Log the activation
            self.conn.execute(
                """
                INSERT INTO evolution_log 
                  (fact_id, event_type, old_value, new_value, trigger, skill_name, created_at)
                VALUES (NULL, 'scheduled_activation', ?, ?, ?, 'domain_scheduler', CURRENT_TIMESTAMP)
                """,
                (
                    json.dumps(predicted_domains),
                    json.dumps(result),
                    f"time_slot={time_slot},conf={confidence:.2f}",
                ),
            )
            self.conn.commit()

            return ScheduledActivation(
                domains=predicted_domains,
                confidence=confidence,
                reason=reason,
                time_slot=time_slot,
                triggered_at=datetime.now().isoformat(),
                deep_layer_result=result,
            )

        finally:
            if own_dl:
                deep_layer.close()

    def schedule_from_prediction(self, prediction, deep_layer=None) -> ScheduledActivation:
        """
        Convenience: take a PredictionResult and schedule it.
        
        Args:
            prediction: PredictionResult from TemporalOrchestrator.predict()
            deep_layer: Optional DeepLayer instance
        
        Returns:
            ScheduledActivation
        """
        return self.schedule(
            predicted_domains=prediction.predicted_domains,
            confidence=prediction.confidence,
            time_slot=prediction.time_slot,
            reason=prediction.reason,
            deep_layer=deep_layer,
        )

    def auto_schedule(self, deep_layer=None) -> Dict:
        """
        Full pipeline: predict → schedule → activate.
        
        This is the main entry point for autonomous domain scheduling.
        Call this periodically (via cron) to keep domains pre-loaded.
        
        Returns:
            Dict with activation results
        """
        from temporal_engine import TemporalOrchestrator

        orch = TemporalOrchestrator()
        orch.connect()

        if deep_layer is None:
            from deep_layer import DeepLayer

            deep_layer = DeepLayer()
            deep_layer.connect()
            own_dl = True
        else:
            own_dl = False

        try:
            # Get current prediction
            prediction = orch.predict()

            if not prediction.predicted_domains or prediction.confidence < 0.15:
                return {
                    "status": "skipped",
                    "reason": f"low confidence: {prediction.confidence}",
                    "prediction": asdict(prediction),
                }

            # Schedule it
            activation = self.schedule_from_prediction(prediction, deep_layer)

            return {
                "status": "ok",
                "prediction": {
                    "domains": prediction.predicted_domains,
                    "confidence": prediction.confidence,
                    "time_slot": prediction.time_slot,
                },
                "activation": asdict(activation),
                "deep_layer_result": activation.deep_layer_result,
            }

        finally:
            orch.close()
            if own_dl:
                deep_layer.close()

    def schedule_all_time_slots(self, deep_layer=None) -> Dict:
        """
        Generate predictions for all known time slots and schedule them.
        Useful for pre-populating the surface buffer comprehensively.
        
        Returns:
            Dict mapping time_slot → ScheduledActivation
        """
        from temporal_engine import TemporalOrchestrator

        orch = TemporalOrchestrator()
        orch.connect()

        if deep_layer is None:
            from deep_layer import DeepLayer

            deep_layer = DeepLayer()
            deep_layer.connect()
            own_dl = True
        else:
            own_dl = False

        # Get all slots from heat map
        hm_row = self.conn.execute(
            "SELECT value FROM engine_metadata WHERE key='prediction_heat_map'"
        ).fetchone()

        results = {}
        try:
            if hm_row and hm_row[0]:
                try:
                    heat_map = json.loads(hm_row[0])
                except (json.JSONDecodeError, TypeError):
                    heat_map = {}

                # For each slot, build a dummy prediction and schedule
                for slot in sorted(heat_map.keys()):
                    domains = sorted(
                        heat_map[slot].items(), key=lambda x: x[1], reverse=True
                    )
                    domain_names = [d[0] for d in domains[:3]]  # Top 3 domains
                    confidence = min(0.9, len(domains) * 0.1)

                    activation = self.schedule(
                        predicted_domains=domain_names,
                        confidence=confidence,
                        time_slot=slot,
                        reason=f"comprehensive: {', '.join(domain_names)}",
                        deep_layer=deep_layer,
                    )

                    results[slot] = asdict(activation)

        finally:
            orch.close()
            if own_dl:
                deep_layer.close()

        return results

    def get_schedule_status(self) -> Dict:
        """Get stats on recent scheduled activations."""
        rows = self.conn.execute(
            """
            SELECT event_type, COUNT(*) as cnt, 
                   MAX(created_at) as last_run
            FROM evolution_log
            WHERE event_type IN ('scheduled_activation', 'prediction')
            GROUP BY event_type
            ORDER BY created_at DESC
            """
        ).fetchall()

        return {
            "scheduled_activations": dict(rows) or {},
            "total": sum(r[1] for r in rows),
        }


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Domain Scheduler — Phase 8D")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("auto", help="Auto-schedule: predict → activate (main entry point)")
    sub.add_parser("all", help="Schedule all known time slots comprehensively")
    sub.add_parser("status", help="Scheduling status and history")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    scheduler = DomainScheduler()
    scheduler.connect()

    try:
        if args.command == "auto":
            result = scheduler.auto_schedule()
            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(f"\n  AUTO-SCHEDULE")
                print(f"  {'═' * 50}\n")
                if result["status"] == "ok":
                    pred = result["prediction"]
                    print(f"  Domains:    {', '.join(pred['domains'])}")
                    print(f"  Confidence: {pred['confidence']:.2f}")
                    print(f"  Slot:       {pred['time_slot']}")
                    print(f"  Activated:  {result['deep_layer_result'].get('activated', 0)} facts")
                    print(f"  Surfaced:   {result['deep_layer_result'].get('surfaced', 0)} facts\n")
                else:
                    print(f"  Status: {result['status']}")
                    print(f"  Reason: {result['reason']}\n")

        elif args.command == "all":
            results = scheduler.schedule_all_time_slots()
            if args.json:
                print(json.dumps(results, indent=2, default=str))
            else:
                print(f"\n  COMPREHENSIVE SCHEDULING")
                print(f"  {'═' * 50}\n")
                for slot, activation in results.items():
                    print(f"  {slot:25s} {', '.join(activation['domains'])}")
                print(f"\n  {len(results)} time slots scheduled\n")

        elif args.command == "status":
            status = scheduler.get_schedule_status()
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                print(f"\n  SCHEDULE STATUS")
                print(f"  {'═' * 50}\n")
                print(f"  Total events: {status['total']}")
                for evt_type, cnt in status["scheduled_activations"].items():
                    print(f"    {evt_type}: {cnt}")
                print()

        else:
            parser.print_help()

    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
