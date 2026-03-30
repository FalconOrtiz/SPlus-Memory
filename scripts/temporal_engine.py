#!/usr/bin/env python3
"""
Phase 8D: Temporal Engine — Dual Timestamps + Predictive Pre-Loading

Two capabilities:
  1. Temporal Intelligence
     - Dual timestamps: document_date (when said) vs event_date (when it happens)
     - Temporal queries: "last week", "next friday", "what changed today"
     - Timeline reconstruction across sessions

  2. Predictive Pre-Loading
     - Learn time-of-day patterns (mornings = planning, afternoons = coding)
     - Learn day-of-week patterns (monday = deployment, friday = review)
     - Auto-activate domains before the user even asks
     - Feed predictions into Deep Layer for proactive surfacing
"""

import json
import sqlite3
import re
import math
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import Counter, defaultdict

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"

# ── Date extraction patterns ──────────────────────────────

DATE_PATTERNS = [
    # ISO dates
    (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),
    # DD/MM/YYYY
    (r'(\d{1,2}/\d{1,2}/\d{4})', '%d/%m/%Y'),
    # "March 23, 2026" / "23 March 2026"
    (r'(\d{1,2}\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b)', None),
    (r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4})', None),
    (r'((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2},?\s+\d{4})', None),
]

RELATIVE_TIME = {
    r'\b(?:hoy|today)\b': 0,
    r'\b(?:ayer|yesterday)\b': -1,
    r'\b(?:mañana|tomorrow)\b': 1,
    r'\b(?:la semana pasada|last week)\b': -7,
    r'\b(?:la próxima semana|next week)\b': 7,
    r'\b(?:el lunes|monday)\b': None,  # resolve dynamically
    r'\b(?:el martes|tuesday)\b': None,
    r'\b(?:el miércoles|wednesday)\b': None,
    r'\b(?:el jueves|thursday)\b': None,
    r'\b(?:el viernes|friday)\b': None,
}

MONTH_MAP_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}

WEEKDAY_MAP = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4,
    'saturday': 5, 'sunday': 6,
    'lunes': 0, 'martes': 1, 'miércoles': 2, 'jueves': 3, 'viernes': 4,
    'sábado': 5, 'domingo': 6,
}


@dataclass
class PredictionResult:
    """What the system predicts will be needed."""
    predicted_domains: List[str]
    predicted_entities: List[str]
    confidence: float
    reason: str
    time_slot: str  # e.g. "monday_morning"


@dataclass
class TemporalQuery:
    """Parsed temporal query."""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    query_type: str = "range"  # range, point, relative
    original: str = ""


# ═══════════════════════════════════════════════════════════
# 1. DATE EXTRACTOR
# ═══════════════════════════════════════════════════════════

class DateExtractor:
    """Extract dates from fact content for dual-timestamp backfill."""

    def extract_dates(self, text: str) -> List[str]:
        """Extract all date-like strings from text, return as ISO strings."""
        if not text:
            return []

        dates = []
        text_lower = text.lower()

        # Try ISO dates first
        iso_matches = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
        for m in iso_matches:
            try:
                datetime.strptime(m, '%Y-%m-%d')
                dates.append(m)
            except ValueError:
                pass

        # Try DD/MM/YYYY
        slash_matches = re.findall(r'(\d{1,2}/\d{1,2}/\d{4})', text)
        for m in slash_matches:
            try:
                d = datetime.strptime(m, '%d/%m/%Y')
                dates.append(d.strftime('%Y-%m-%d'))
            except ValueError:
                pass

        # Spanish month names: "21 de marzo", "marzo 2026"
        es_matches = re.findall(
            r'(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+(?:de\s+)?(\d{4}))?',
            text_lower
        )
        for day, month_name, year in es_matches:
            month = MONTH_MAP_ES.get(month_name)
            if month:
                yr = int(year) if year else datetime.now().year
                try:
                    d = datetime(yr, month, int(day))
                    dates.append(d.strftime('%Y-%m-%d'))
                except ValueError:
                    pass

        return list(set(dates))

    def extract_event_signals(self, text: str) -> List[str]:
        """Extract future-event signals: deadlines, meetings, launches."""
        signals = []
        text_lower = text.lower()

        event_patterns = [
            r'(?:deadline|fecha límite|due|vence)\s*:?\s*(.{5,30})',
            r'(?:launch|lanzamiento|release|deploy)\s+(?:on|el|para)\s+(.{5,30})',
            r'(?:meeting|reunión|call|llamada)\s+(?:on|el|para)\s+(.{5,30})',
            r'(?:scheduled|programado|agendado)\s+(?:for|para)\s+(.{5,30})',
        ]

        for pat in event_patterns:
            matches = re.findall(pat, text_lower)
            for m in matches:
                extracted = self.extract_dates(m)
                signals.extend(extracted)

        return signals


# ═══════════════════════════════════════════════════════════
# 2. TEMPORAL BACKFILL
# ═══════════════════════════════════════════════════════════

class TemporalBackfill:
    """Backfill dual timestamps for existing facts."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.extractor = DateExtractor()

    def backfill(self) -> Dict:
        """Backfill document_date and event_date for all facts."""
        stats = {"document_dates": 0, "event_dates": 0, "total": 0}

        rows = self.conn.execute("""
            SELECT id, raw_content, created_at, document_date, event_date
            FROM quantum_facts
            WHERE status NOT IN ('abandoned')
        """).fetchall()

        stats["total"] = len(rows)

        for fid, raw, created_at, doc_date, evt_date in rows:
            updated = False

            # Backfill document_date from created_at if missing
            if not doc_date and created_at:
                self.conn.execute(
                    "UPDATE quantum_facts SET document_date=? WHERE id=?",
                    (created_at, fid)
                )
                stats["document_dates"] += 1
                updated = True

            # Extract event_date from content if missing
            if not evt_date and raw:
                dates = self.extractor.extract_dates(raw)
                event_signals = self.extractor.extract_event_signals(raw)
                all_dates = list(set(dates + event_signals))

                if all_dates:
                    self.conn.execute(
                        "UPDATE quantum_facts SET event_date=? WHERE id=?",
                        (json.dumps(all_dates), fid)
                    )
                    stats["event_dates"] += 1
                    updated = True

        self.conn.commit()
        return stats


# ═══════════════════════════════════════════════════════════
# 3. TEMPORAL QUERY ENGINE
# ═══════════════════════════════════════════════════════════

class TemporalQueryEngine:
    """Answer time-based questions about memory."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def query_range(self, start: str, end: str, domain: str = None) -> List[Dict]:
        """Get facts within a date range."""
        where = "WHERE document_date BETWEEN ? AND ? AND status NOT IN ('abandoned')"
        params = [start, end]

        if domain:
            where += """
                AND id IN (
                    SELECT b.fact_id FROM kw_bitmap b
                    JOIN kw_dictionary d ON b.value_id = d.id
                    WHERE b.dimension = 'domain' AND d.value = ?
                )
            """
            params.append(domain)

        rows = self.conn.execute(f"""
            SELECT id, summary, raw_content, document_date, event_date,
                   confidence, activation_count
            FROM quantum_facts
            {where}
            ORDER BY document_date DESC
        """, params).fetchall()

        return [dict(r) for r in rows]

    def query_events(self, start: str, end: str) -> List[Dict]:
        """Get facts with events occurring in a date range."""
        rows = self.conn.execute("""
            SELECT id, summary, raw_content, document_date, event_date,
                   confidence, activation_count
            FROM quantum_facts
            WHERE event_date IS NOT NULL
            AND status NOT IN ('abandoned')
            ORDER BY document_date DESC
        """).fetchall()

        results = []
        for r in rows:
            try:
                evt_dates = json.loads(r["event_date"])
                for ed in evt_dates:
                    if start <= ed <= end:
                        results.append(dict(r))
                        break
            except (json.JSONDecodeError, TypeError):
                pass

        return results

    def query_relative(self, text: str) -> List[Dict]:
        """Parse relative time queries and execute."""
        text_lower = text.lower()
        now = datetime.now()

        # "today" / "hoy"
        if re.search(r'\b(?:hoy|today)\b', text_lower):
            day = now.strftime('%Y-%m-%d')
            return self.query_range(day, day + 'T23:59:59')

        # "yesterday" / "ayer"
        if re.search(r'\b(?:ayer|yesterday)\b', text_lower):
            day = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            return self.query_range(day, day + 'T23:59:59')

        # "this week" / "esta semana"
        if re.search(r'\b(?:esta semana|this week)\b', text_lower):
            start = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
            end = now.strftime('%Y-%m-%d') + 'T23:59:59'
            return self.query_range(start, end)

        # "last week" / "semana pasada"
        if re.search(r'\b(?:semana pasada|last week)\b', text_lower):
            end = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
            start = (now - timedelta(days=now.weekday() + 7)).strftime('%Y-%m-%d')
            return self.query_range(start, end)

        # "last N days"
        m = re.search(r'(?:last|últimos?)\s+(\d+)\s+(?:days|días)', text_lower)
        if m:
            days = int(m.group(1))
            start = (now - timedelta(days=days)).strftime('%Y-%m-%d')
            end = now.strftime('%Y-%m-%d') + 'T23:59:59'
            return self.query_range(start, end)

        # Specific weekday
        for day_name, weekday_num in WEEKDAY_MAP.items():
            if day_name in text_lower:
                # Find the most recent occurrence of that day
                days_back = (now.weekday() - weekday_num) % 7
                if days_back == 0:
                    days_back = 0  # today
                target = (now - timedelta(days=days_back)).strftime('%Y-%m-%d')
                return self.query_range(target, target + 'T23:59:59')

        return []


# ═══════════════════════════════════════════════════════════
# 4. PREDICTIVE PRE-LOADER
# ═══════════════════════════════════════════════════════════

class PredictivePreLoader:
    """
    Learns usage patterns and predicts what domains will be needed.

    Tracks:
      - Time-of-day patterns (morning/afternoon/evening/night)
      - Day-of-week patterns (mon-sun)
      - Builds a heat map: time_slot → domain → frequency
    """

    TIME_SLOTS = {
        (6, 10): "morning",
        (10, 14): "midday",
        (14, 18): "afternoon",
        (18, 22): "evening",
        (22, 6): "night",
    }

    WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def learn_patterns(self) -> Dict:
        """Analyze activation history to learn time patterns."""
        # Get all activation events with timestamps
        rows = self.conn.execute("""
            SELECT el.created_at, el.fact_id, el.trigger
            FROM evolution_log el
            WHERE el.event_type = 'activated'
            AND el.created_at > datetime('now', '-30 days')
        """).fetchall()

        # Build heat map: slot → domain → count
        heat_map = defaultdict(lambda: defaultdict(int))

        for created_at, fact_id, trigger in rows:
            try:
                dt = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                continue

            slot = self._get_time_slot(dt)

            # Get domains for this fact
            domains = self.conn.execute("""
                SELECT d.value FROM kw_bitmap b
                JOIN kw_dictionary d ON b.value_id = d.id
                WHERE b.dimension = 'domain' AND b.fact_id = ?
            """, (fact_id,)).fetchall()

            for (domain,) in domains:
                heat_map[slot][domain] += 1

        # Store heat map
        self.conn.execute("""
            INSERT OR REPLACE INTO engine_metadata (key, value, updated_at)
            VALUES ('prediction_heat_map', ?, CURRENT_TIMESTAMP)
        """, (json.dumps({k: dict(v) for k, v in heat_map.items()}),))
        self.conn.commit()

        return {k: dict(v) for k, v in heat_map.items()}

    def predict(self, when: datetime = None) -> PredictionResult:
        """Predict what domains will be needed at a given time."""
        if when is None:
            when = datetime.now()

        slot = self._get_time_slot(when)

        # Load heat map
        row = self.conn.execute(
            "SELECT value FROM engine_metadata WHERE key='prediction_heat_map'"
        ).fetchone()

        if not row or not row[0]:
            return PredictionResult([], [], 0.0, "no data", slot)

        try:
            heat_map = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return PredictionResult([], [], 0.0, "corrupt data", slot)

        slot_data = heat_map.get(slot, {})
        if not slot_data:
            return PredictionResult([], [], 0.1, f"no data for {slot}", slot)

        # Sort domains by frequency
        sorted_domains = sorted(slot_data.items(), key=lambda x: x[1], reverse=True)
        total = sum(v for _, v in sorted_domains)

        # Top domains (>10% of activity in this slot)
        predicted_domains = []
        for domain, count in sorted_domains:
            pct = count / max(total, 1)
            if pct >= 0.10:
                predicted_domains.append(domain)
            if len(predicted_domains) >= 5:
                break

        # Entities from those domains (most activated)
        predicted_entities = []
        if predicted_domains:
            for domain in predicted_domains[:3]:
                facts = self.conn.execute("""
                    SELECT qf.raw_content FROM quantum_facts qf
                    JOIN kw_bitmap b ON qf.id = b.fact_id
                    JOIN kw_dictionary d ON b.value_id = d.id
                    WHERE b.dimension = 'domain' AND d.value = ?
                    AND qf.activation_count > 0
                    ORDER BY qf.activation_count DESC LIMIT 3
                """, (domain,)).fetchall()

                for (raw,) in facts:
                    if raw:
                        # Extract entity mentions
                        from deep_layer import ENTITY_PATTERNS
                        for pat, entity in ENTITY_PATTERNS.items():
                            if re.search(pat, raw.lower()):
                                if entity not in predicted_entities:
                                    predicted_entities.append(entity)
                                    if len(predicted_entities) >= 5:
                                        break

        # Confidence based on data density
        confidence = min(0.9, len(sorted_domains) * 0.1 + (total / 100) * 0.3)

        return PredictionResult(
            predicted_domains=predicted_domains,
            predicted_entities=predicted_entities,
            confidence=round(confidence, 2),
            reason=f"heat_map[{slot}]: {', '.join(f'{d}({c})' for d, c in sorted_domains[:5])}",
            time_slot=slot,
        )

    def predict_and_activate(self, deep_layer=None) -> Dict:
        """
        Predict what's needed NOW and feed it to the Deep Layer.
        This is the predictive pre-loading loop.
        
        Uses DomainScheduler for structured activation.
        """
        prediction = self.predict()

        if not prediction.predicted_domains or prediction.confidence < 0.2:
            return {"prediction": asdict(prediction), "activated": 0, "status": "low_confidence"}

        if deep_layer is None:
            from deep_layer import DeepLayer
            deep_layer = DeepLayer()
            deep_layer.connect()
            own_dl = True
        else:
            own_dl = False

        try:
            # Use DomainScheduler for clean separation of concerns
            from domain_scheduler import DomainScheduler
            scheduler = DomainScheduler(self.db_path)
            scheduler.connect()
            
            try:
                activation = scheduler.schedule_from_prediction(prediction, deep_layer)
                
                # Log the predictive activation
                self.conn.execute("""
                    INSERT INTO evolution_log (fact_id, event_type, new_value, trigger, skill_name)
                    VALUES (NULL, 'prediction_activation', ?, ?, 'temporal')
                """, (
                    json.dumps(asdict(prediction)),
                    f"slot={prediction.time_slot},conf={prediction.confidence}",
                ))
                self.conn.commit()
                
                return {
                    "prediction": asdict(prediction),
                    "activation": asdict(activation),
                    "activated": activation.deep_layer_result.get("activated", 0) if activation.deep_layer_result else 0,
                    "surfaced": activation.deep_layer_result.get("surfaced", 0) if activation.deep_layer_result else 0,
                    "status": activation.deep_layer_result.get("status", "ok") if activation.deep_layer_result else "scheduled",
                }
            finally:
                scheduler.close()
                
        finally:
            if own_dl:
                deep_layer.close()

    def _get_time_slot(self, dt: datetime) -> str:
        """Get the time slot key for a datetime."""
        weekday = self.WEEKDAYS[dt.weekday()]
        hour = dt.hour

        if 6 <= hour < 10:
            period = "morning"
        elif 10 <= hour < 14:
            period = "midday"
        elif 14 <= hour < 18:
            period = "afternoon"
        elif 18 <= hour < 22:
            period = "evening"
        else:
            period = "night"

        return f"{weekday}_{period}"


# ═══════════════════════════════════════════════════════════
# 5. DOMAIN SCHEDULER
# ═══════════════════════════════════════════════════════════

class DomainScheduler:
    """
    Auto-activates domains based on historical patterns.

    Uses the heat map to determine which domains should be "warm" at any given
    time, then feeds those domains directly into the Deep Layer's ContextMonitor
    so facts from those domains get boosted before the user even asks.

    Schedule types:
      - time_based: activate domains based on time slot (e.g. monday_morning → deployment)
      - event_based: activate domains when event_date approaches (e.g. deadline in 2 days)
      - recurring: activate domains that appear in >60% of a time slot's history
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_scheduled_domains(self, when: datetime = None) -> Dict:
        """
        Get domains that should be auto-activated right now.
        Returns {domain: {reason, confidence, source}}.
        """
        if when is None:
            when = datetime.now()

        scheduled = {}

        # ── Time-based scheduling ──
        time_scheduled = self._time_based(when)
        for domain, info in time_scheduled.items():
            scheduled[domain] = info

        # ── Event-based scheduling ──
        event_scheduled = self._event_based(when)
        for domain, info in event_scheduled.items():
            if domain not in scheduled or info["confidence"] > scheduled[domain]["confidence"]:
                scheduled[domain] = info

        # ── Recurring pattern boost ──
        recurring = self._recurring_patterns(when)
        for domain, info in recurring.items():
            if domain not in scheduled:
                scheduled[domain] = info
            else:
                # Boost confidence if domain appears in multiple sources
                scheduled[domain]["confidence"] = min(0.95, scheduled[domain]["confidence"] + 0.1)
                scheduled[domain]["reason"] += f" + {info['reason']}"

        return scheduled

    def _time_based(self, when: datetime) -> Dict:
        """Activate domains based on heat map for current time slot."""
        loader = PredictivePreLoader(self.conn)
        slot = loader._get_time_slot(when)

        row = self.conn.execute(
            "SELECT value FROM engine_metadata WHERE key='prediction_heat_map'"
        ).fetchone()

        if not row or not row[0]:
            return {}

        try:
            heat_map = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return {}

        slot_data = heat_map.get(slot, {})
        if not slot_data:
            return {}

        total = sum(slot_data.values())
        result = {}

        for domain, count in slot_data.items():
            pct = count / max(total, 1)
            if pct >= 0.15:  # domain needs >15% of slot activity
                result[domain] = {
                    "reason": f"time_slot({slot}): {pct:.0%} of activity",
                    "confidence": round(min(0.85, pct + 0.2), 2),
                    "source": "time_based",
                    "slot": slot,
                    "frequency": count,
                }

        return result

    def _event_based(self, when: datetime) -> Dict:
        """Activate domains for facts with upcoming event_date."""
        result = {}
        horizon = (when + timedelta(days=3)).strftime('%Y-%m-%d')
        today = when.strftime('%Y-%m-%d')

        rows = self.conn.execute("""
            SELECT qf.id, qf.event_date, qf.summary
            FROM quantum_facts qf
            WHERE qf.event_date IS NOT NULL
            AND qf.status NOT IN ('abandoned')
        """).fetchall()

        for fid, evt_json, summary in rows:
            try:
                evt_dates = json.loads(evt_json)
            except (json.JSONDecodeError, TypeError):
                continue

            for ed in evt_dates:
                if today <= ed <= horizon:
                    # Get domains for this fact
                    domains = self.conn.execute("""
                        SELECT d.value FROM kw_bitmap b
                        JOIN kw_dictionary d ON b.value_id = d.id
                        WHERE b.dimension = 'domain' AND b.fact_id = ?
                    """, (fid,)).fetchall()

                    days_until = (datetime.strptime(ed, '%Y-%m-%d') - when).days
                    urgency = max(0.5, 1.0 - (days_until * 0.15))

                    for (domain,) in domains:
                        if domain not in result or urgency > result[domain]["confidence"]:
                            result[domain] = {
                                "reason": f"event in {days_until}d: {(summary or '')[:40]}",
                                "confidence": round(urgency, 2),
                                "source": "event_based",
                                "event_date": ed,
                                "fact_id": fid,
                            }

        return result

    def _recurring_patterns(self, when: datetime) -> Dict:
        """Find domains that consistently appear at this time across multiple weeks."""
        loader = PredictivePreLoader(self.conn)
        weekday = loader.WEEKDAYS[when.weekday()]

        row = self.conn.execute(
            "SELECT value FROM engine_metadata WHERE key='prediction_heat_map'"
        ).fetchone()

        if not row or not row[0]:
            return {}

        try:
            heat_map = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return {}

        # Count how many slots for this weekday have each domain
        weekday_slots = {k: v for k, v in heat_map.items() if k.startswith(weekday)}
        if not weekday_slots:
            return {}

        domain_appearances = defaultdict(int)
        for slot, domains in weekday_slots.items():
            for domain in domains:
                domain_appearances[domain] += 1

        total_slots = len(weekday_slots)
        result = {}

        for domain, appearances in domain_appearances.items():
            pct = appearances / total_slots
            if pct >= 0.6:  # appears in 60%+ of this weekday's slots
                result[domain] = {
                    "reason": f"recurring({weekday}): {appearances}/{total_slots} slots",
                    "confidence": round(min(0.8, pct * 0.7), 2),
                    "source": "recurring",
                }

        return result

    def activate_scheduled(self, deep_layer=None) -> Dict:
        """
        Get scheduled domains and push them into the Deep Layer.
        This is the autonomous pre-activation loop.
        """
        scheduled = self.get_scheduled_domains()

        if not scheduled:
            return {"scheduled": {}, "activated": 0, "status": "nothing_scheduled"}

        if deep_layer is None:
            from deep_layer import DeepLayer
            deep_layer = DeepLayer()
            deep_layer.connect()
            own_dl = True
        else:
            own_dl = False

        try:
            # Build signal from scheduled domains
            domain_list = list(scheduled.keys())
            reasons = [f"{d}: {info['reason']}" for d, info in scheduled.items()]
            signal = f"scheduled domains: {' '.join(domain_list)}"

            result = deep_layer.process(
                signal,
                agent="scheduler",
                skills=[],
                session_id=f"schedule_{datetime.now().strftime('%Y%m%d_%H%M')}",
            )

            # Log the scheduling event
            self.conn.execute("""
                INSERT INTO evolution_log (fact_id, event_type, new_value, trigger, skill_name)
                VALUES (NULL, 'scheduled_activation', ?, ?, 'domain_scheduler')
            """, (
                json.dumps(scheduled, default=str),
                f"domains={','.join(domain_list)}",
            ))
            self.conn.commit()

            return {
                "scheduled": scheduled,
                "domains": domain_list,
                "activated": result.get("activated", 0),
                "surfaced": result.get("surfaced", 0),
                "status": "ok",
            }
        finally:
            if own_dl:
                deep_layer.close()


# ═══════════════════════════════════════════════════════════
# 6. TEMPORAL ORCHESTRATOR
# ═══════════════════════════════════════════════════════════

class TemporalOrchestrator:
    """Main entry point for Phase 8D temporal operations."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def backfill(self) -> Dict:
        bf = TemporalBackfill(self.conn)
        return bf.backfill()

    def query(self, text: str) -> List[Dict]:
        engine = TemporalQueryEngine(self.conn)
        return engine.query_relative(text)

    def query_range(self, start: str, end: str, domain: str = None) -> List[Dict]:
        engine = TemporalQueryEngine(self.conn)
        return engine.query_range(start, end, domain)

    def query_events(self, start: str, end: str) -> List[Dict]:
        engine = TemporalQueryEngine(self.conn)
        return engine.query_events(start, end)

    def learn(self) -> Dict:
        loader = PredictivePreLoader(self.conn)
        return loader.learn_patterns()

    def predict(self) -> PredictionResult:
        loader = PredictivePreLoader(self.conn)
        return loader.predict()

    def predict_and_activate(self) -> Dict:
        loader = PredictivePreLoader(self.conn)
        return loader.predict_and_activate()

    def schedule(self) -> Dict:
        """Get current domain schedule."""
        sched = DomainScheduler(self.conn)
        return sched.get_scheduled_domains()

    def schedule_activate(self) -> Dict:
        """Run domain scheduler → Deep Layer pipeline."""
        sched = DomainScheduler(self.conn)
        return sched.activate_scheduled()

    def full_cycle(self) -> Dict:
        """
        Run the full temporal cycle:
          1. Backfill any new timestamps
          2. Learn patterns from recent activity
          3. Predict what's needed now
          4. Schedule domains
          5. Activate via Deep Layer
        Returns combined results.
        """
        results = {}

        # 1. Backfill
        bf = TemporalBackfill(self.conn)
        results["backfill"] = bf.backfill()

        # 2. Learn
        loader = PredictivePreLoader(self.conn)
        results["heat_map_slots"] = len(loader.learn_patterns())

        # 3. Predict
        prediction = loader.predict()
        results["prediction"] = {
            "slot": prediction.time_slot,
            "domains": prediction.predicted_domains,
            "confidence": prediction.confidence,
        }

        # 4. Schedule
        sched = DomainScheduler(self.conn)
        scheduled = sched.get_scheduled_domains()
        results["scheduled_domains"] = list(scheduled.keys())
        results["schedule_details"] = scheduled

        # 5. Activate
        if scheduled:
            activation = sched.activate_scheduled()
            results["activated"] = activation.get("activated", 0)
            results["surfaced"] = activation.get("surfaced", 0)
            results["activation_status"] = activation.get("status", "unknown")
        else:
            results["activated"] = 0
            results["surfaced"] = 0
            results["activation_status"] = "nothing_scheduled"

        return results

    def get_status(self) -> Dict:
        # Dual timestamp coverage
        total = self.conn.execute(
            "SELECT COUNT(*) FROM quantum_facts WHERE status NOT IN ('abandoned')"
        ).fetchone()[0]
        has_doc = self.conn.execute(
            "SELECT COUNT(*) FROM quantum_facts WHERE document_date IS NOT NULL"
        ).fetchone()[0]
        has_evt = self.conn.execute(
            "SELECT COUNT(*) FROM quantum_facts WHERE event_date IS NOT NULL"
        ).fetchone()[0]

        # Heat map
        hm_row = self.conn.execute(
            "SELECT value FROM engine_metadata WHERE key='prediction_heat_map'"
        ).fetchone()
        heat_map = {}
        if hm_row and hm_row[0]:
            try:
                heat_map = json.loads(hm_row[0])
            except (json.JSONDecodeError, TypeError):
                pass

        # Predictions count
        pred_count = self.conn.execute(
            "SELECT COUNT(*) FROM evolution_log WHERE event_type='prediction'"
        ).fetchone()[0]

        return {
            "total_facts": total,
            "document_dates": has_doc,
            "event_dates": has_evt,
            "doc_coverage": f"{has_doc/max(total,1)*100:.0f}%",
            "evt_coverage": f"{has_evt/max(total,1)*100:.0f}%",
            "heat_map_slots": len(heat_map),
            "predictions_made": pred_count,
            "heat_map_top": {
                k: sorted(v.items(), key=lambda x: x[1], reverse=True)[:3]
                for k, v in list(heat_map.items())[:5]
            } if heat_map else {},
        }


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Temporal Engine — Phase 8D")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("backfill", help="Backfill dual timestamps for all facts")
    sub.add_parser("status", help="Temporal engine status")

    p = sub.add_parser("query", help="Temporal query")
    p.add_argument("text", nargs="+")

    p = sub.add_parser("range", help="Query date range")
    p.add_argument("start", help="Start date YYYY-MM-DD")
    p.add_argument("end", help="End date YYYY-MM-DD")
    p.add_argument("--domain", default=None)

    sub.add_parser("learn", help="Learn time patterns from activation history")
    sub.add_parser("predict", help="Predict what's needed now")
    sub.add_parser("preload", help="Predict and activate (feed Deep Layer)")
    sub.add_parser("schedule", help="Show which domains are scheduled for activation now")
    sub.add_parser("activate", help="Run domain scheduler → Deep Layer pipeline")
    sub.add_parser("cycle", help="Run full temporal cycle (backfill→learn→predict→schedule→activate)")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    orch = TemporalOrchestrator()
    orch.connect()

    try:
        if args.command == "backfill":
            stats = orch.backfill()
            if args.json:
                print(json.dumps(stats, indent=2))
            else:
                print(f"\n  TEMPORAL BACKFILL")
                print(f"  {'═' * 50}\n")
                print(f"  Total facts:     {stats['total']}")
                print(f"  Document dates:  {stats['document_dates']} backfilled")
                print(f"  Event dates:     {stats['event_dates']} extracted\n")

        elif args.command == "status":
            status = orch.get_status()
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                print(f"\n  TEMPORAL STATUS")
                print(f"  {'═' * 50}\n")
                print(f"  Facts:         {status['total_facts']}")
                print(f"  Doc dates:     {status['document_dates']} ({status['doc_coverage']})")
                print(f"  Event dates:   {status['event_dates']} ({status['evt_coverage']})")
                print(f"  Heat map:      {status['heat_map_slots']} time slots learned")
                print(f"  Predictions:   {status['predictions_made']}\n")
                if status['heat_map_top']:
                    print(f"  TOP PATTERNS:")
                    for slot, domains in status['heat_map_top'].items():
                        doms = ", ".join(f"{d}({c})" for d, c in domains)
                        print(f"    {slot:25s} {doms}")
                print()

        elif args.command == "query":
            text = " ".join(args.text)
            results = orch.query(text)
            if args.json:
                print(json.dumps(results, indent=2, default=str))
            else:
                print(f"\n  TEMPORAL QUERY: {text}")
                print(f"  {'═' * 50}\n")
                if results:
                    for r in results[:15]:
                        doc = r.get("document_date", "?")
                        if doc and len(doc) > 10:
                            doc = doc[:10]
                        conf = r.get("confidence", 0)
                        print(f"  {doc}  [{conf:.1f}] {(r.get('summary','') or '')[:60]}")
                else:
                    print("  (no results)")
                print()

        elif args.command == "range":
            results = orch.query_range(args.start, args.end, args.domain)
            print(f"\n  RANGE: {args.start} → {args.end}" + (f" [{args.domain}]" if args.domain else ""))
            print(f"  {'═' * 50}\n")
            for r in results[:20]:
                doc = (r.get("document_date") or "?")[:10]
                print(f"  {doc}  {(r.get('summary','') or '')[:60]}")
            print(f"\n  {len(results)} facts\n")

        elif args.command == "learn":
            heat_map = orch.learn()
            if args.json:
                print(json.dumps(heat_map, indent=2))
            else:
                print(f"\n  PATTERN LEARNING")
                print(f"  {'═' * 50}\n")
                print(f"  {len(heat_map)} time slots analyzed\n")
                for slot in sorted(heat_map.keys()):
                    domains = sorted(heat_map[slot].items(), key=lambda x: x[1], reverse=True)
                    top = ", ".join(f"{d}({c})" for d, c in domains[:4])
                    print(f"  {slot:25s} {top}")
                print()

        elif args.command == "predict":
            prediction = orch.predict()
            if args.json:
                print(json.dumps(asdict(prediction), indent=2))
            else:
                print(f"\n  PREDICTION")
                print(f"  {'═' * 50}\n")
                print(f"  Time slot:  {prediction.time_slot}")
                print(f"  Confidence: {prediction.confidence}")
                print(f"  Domains:    {prediction.predicted_domains}")
                print(f"  Entities:   {prediction.predicted_entities}")
                print(f"  Reason:     {prediction.reason}\n")

        elif args.command == "preload":
            result = orch.predict_and_activate()
            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                p = result["prediction"]
                print(f"\n  PREDICTIVE PRE-LOAD")
                print(f"  {'═' * 50}\n")
                print(f"  Slot:      {p['time_slot']}")
                print(f"  Domains:   {p['predicted_domains']}")
                print(f"  Conf:      {p['confidence']}")
                print(f"  Activated: {result.get('activated', 0)}")
                print(f"  Surfaced:  {result.get('surfaced', 0)}")
                print(f"  Status:    {result['status']}\n")

        else:
            parser.print_help()

    finally:
        orch.close()


if __name__ == "__main__":
    main()
