#!/usr/bin/env python3
"""
Alert System — Phase 6

Monitors metrics and triggers alerts when thresholds are exceeded.

Alert types:
- Performance degradation (latency > threshold)
- Consensus quality issues (disputed > threshold)
- Sync failures (conflict rate > threshold)
- Error rate spike (errors > threshold)
- Health degradation (score < threshold)

Severity levels:
- CRITICAL: Immediate action needed
- WARNING: Monitor closely
- INFO: Informational only

Usage:
    alerter = AlertSystem()
    
    # Define alert rule
    alerter.add_alert_rule(
        name='high_latency',
        condition='query_latency_avg_ms > 150',
        severity='WARNING',
        message='Query latency above 150ms'
    )
    
    # Check metrics and trigger alerts
    triggered = alerter.check_alerts(metrics)
    
    # Get alert history
    history = alerter.get_alert_history()
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/alerts.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


@dataclass
class Alert:
    """Alert definition."""
    name: str
    condition_name: str
    severity: str                # CRITICAL, WARNING, INFO
    threshold: float
    message: str
    actions: List[str]          # ['log', 'notify', 'auto_fix']
    enabled: bool = True


@dataclass
class AlertEvent:
    """Triggered alert."""
    alert_name: str
    timestamp: str
    severity: str
    message: str
    current_value: float
    threshold: float
    actions_taken: List[str]


class AlertSystem:
    """Monitor metrics and trigger alerts."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        self._ensure_tables()
        self._init_default_rules()
        self.triggered_alerts: List[AlertEvent] = []
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info("Alert system connected")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def _ensure_tables(self):
        """Ensure alert tables exist."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                condition_name TEXT,
                severity TEXT,
                threshold REAL,
                message TEXT,
                actions TEXT,
                enabled BOOLEAN DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_events (
                id INTEGER PRIMARY KEY,
                alert_name TEXT,
                severity TEXT,
                message TEXT,
                current_value REAL,
                threshold REAL,
                actions_taken TEXT,
                timestamp TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY,
                alert_name TEXT,
                triggered_count INTEGER,
                last_triggered TEXT,
                resolved BOOLEAN,
                resolved_at TEXT
            )
        """)
        
        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_events_timestamp ON alert_events(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_events_severity ON alert_events(severity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_name ON alert_rules(name)")
        
        self.conn.commit()
    
    def _init_default_rules(self):
        """Initialize default alert rules."""
        default_rules = [
            {
                'name': 'high_latency',
                'condition_name': 'query_latency_avg_ms',
                'severity': 'WARNING',
                'threshold': 150,
                'message': 'Query latency exceeding 150ms',
                'actions': ['log', 'notify']
            },
            {
                'name': 'critical_latency',
                'condition_name': 'query_latency_avg_ms',
                'severity': 'CRITICAL',
                'threshold': 250,
                'message': 'Query latency exceeding 250ms - Critical',
                'actions': ['log', 'notify', 'auto_fix']
            },
            {
                'name': 'sync_conflicts',
                'condition_name': 'sync_conflict_rate',
                'severity': 'WARNING',
                'threshold': 0.10,
                'message': 'Sync conflict rate >10%',
                'actions': ['log', 'notify']
            },
            {
                'name': 'consensus_quality',
                'condition_name': 'consensus_disputed_rate',
                'severity': 'WARNING',
                'threshold': 0.15,
                'message': 'Consensus disputed rate >15%',
                'actions': ['log', 'notify']
            },
            {
                'name': 'error_spike',
                'condition_name': 'error_count_per_minute',
                'severity': 'CRITICAL',
                'threshold': 5,
                'message': 'Error rate spike detected (>5/min)',
                'actions': ['log', 'notify', 'auto_fix']
            },
            {
                'name': 'health_degradation',
                'condition_name': 'overall_health_score',
                'severity': 'WARNING',
                'threshold': 70,
                'message': 'System health degraded (<70)',
                'actions': ['log', 'notify']
            },
            {
                'name': 'agent_offline',
                'condition_name': 'agent_sync_staleness_min',
                'severity': 'CRITICAL',
                'threshold': 30,
                'message': 'Agent sync staleness >30 minutes',
                'actions': ['log', 'notify', 'auto_fix']
            }
        ]
        
        for rule in default_rules:
            self.add_alert_rule(
                name=rule['name'],
                condition=rule['condition_name'],
                severity=rule['severity'],
                threshold=rule['threshold'],
                message=rule['message'],
                actions=rule['actions']
            )
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def add_alert_rule(
        self,
        name: str,
        condition: str,
        severity: str,
        threshold: float,
        message: str,
        actions: List[str] = None
    ) -> bool:
        """Add alert rule."""
        cursor = self.conn.cursor()
        actions = actions or ['log']
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO alert_rules
                (name, condition_name, severity, threshold, message, actions, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, condition, severity, threshold, message, json.dumps(actions),
                  datetime.now().isoformat(), datetime.now().isoformat()))
            
            self.conn.commit()
            logger_obj.info(f"Alert rule added: {name}")
            return True
        
        except Exception as e:
            logger_obj.error(f"Failed to add alert rule: {e}")
            return False
    
    def get_alert_rules(self) -> List[Dict]:
        """Get all alert rules."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT name, condition_name, severity, threshold, message, actions
                FROM alert_rules
                WHERE enabled = 1
                ORDER BY severity DESC, threshold DESC
            """)
            
            return [dict(row) for row in cursor.fetchall()]
        
        except Exception as e:
            logger_obj.error(f"Failed to get alert rules: {e}")
            return []
    
    def check_alerts(self, metrics: Dict) -> List[AlertEvent]:
        """Check metrics against alert rules."""
        self.triggered_alerts = []
        rules = self.get_alert_rules()
        
        for rule in rules:
            condition = rule['condition_name']
            threshold = rule['threshold']
            
            # Extract current value from metrics
            current_value = self._extract_metric_value(metrics, condition)
            
            if current_value is None:
                continue
            
            # Check if condition triggered
            triggered = False
            if 'rate' in condition or 'health' in condition and 'latency' not in condition:
                # Lower is better for rates, higher for health
                if 'health' in condition:
                    triggered = current_value < threshold
                else:
                    triggered = current_value > threshold
            else:
                # Higher values are worse
                triggered = current_value > threshold
            
            if triggered:
                alert = self._create_alert_event(rule, current_value)
                self.triggered_alerts.append(alert)
                
                # Record alert event
                self._record_alert_event(alert)
                
                # Execute actions
                self._execute_alert_actions(alert, rule['actions'])
        
        return self.triggered_alerts
    
    def _extract_metric_value(self, metrics: Dict, condition: str) -> Optional[float]:
        """Extract metric value from metrics dict."""
        # Navigate nested structure
        if 'query_latency_avg_ms' in condition:
            return metrics.get('query_latency', {}).get('avg_ms')
        elif 'sync_conflict_rate' in condition:
            sync_health = metrics.get('sync_health', {})
            if sync_health:
                return sum(s.get('conflict_rate', 0) for s in sync_health.values()) / len(sync_health)
            return 0
        elif 'consensus_disputed_rate' in condition:
            return metrics.get('consensus_quality', {}).get('disputed_rate', 0)
        elif 'error_count_per_minute' in condition:
            return metrics.get('error_rate', {}).get('error_rate', 0)
        elif 'overall_health_score' in condition:
            return metrics.get('overall_health', 100)
        elif 'agent_sync_staleness_min' in condition:
            # Check sync health
            sync_health = metrics.get('sync_health', {})
            if sync_health:
                return max(s.get('stale_minutes', 0) for s in sync_health.values())
            return 0
        
        return None
    
    def _create_alert_event(self, rule: Dict, current_value: float) -> AlertEvent:
        """Create alert event."""
        return AlertEvent(
            alert_name=rule['name'],
            timestamp=datetime.now().isoformat(),
            severity=rule['severity'],
            message=rule['message'],
            current_value=current_value,
            threshold=rule['threshold'],
            actions_taken=[]
        )
    
    def _record_alert_event(self, alert: AlertEvent) -> bool:
        """Record alert event to database."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO alert_events
                (alert_name, severity, message, current_value, threshold, actions_taken, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (alert.alert_name, alert.severity, alert.message, alert.current_value,
                  alert.threshold, json.dumps(alert.actions_taken), alert.timestamp))
            
            self.conn.commit()
            return True
        
        except Exception as e:
            logger_obj.error(f"Failed to record alert: {e}")
            return False
    
    def _execute_alert_actions(self, alert: AlertEvent, actions: List[str]) -> List[str]:
        """Execute alert actions."""
        executed = []
        
        for action in actions:
            try:
                if action == 'log':
                    logger_obj.warning(f"[{alert.severity}] {alert.message} (value={alert.current_value})")
                    executed.append('log')
                
                elif action == 'notify':
                    # TODO: Implement notification (email, Slack, etc)
                    logger_obj.info(f"Alert notification would be sent: {alert.alert_name}")
                    executed.append('notify')
                
                elif action == 'auto_fix':
                    logger_obj.info(f"Auto-fix triggered for: {alert.alert_name}")
                    self._trigger_auto_fix(alert)
                    executed.append('auto_fix')
            
            except Exception as e:
                logger_obj.error(f"Failed to execute action {action}: {e}")
        
        alert.actions_taken = executed
        return executed
    
    def _trigger_auto_fix(self, alert: AlertEvent):
        """Trigger automatic fixes."""
        if 'latency' in alert.alert_name:
            # Clear cache, optimize indexes
            logger_obj.info("Triggering query optimization auto-fix")
        
        elif 'sync' in alert.alert_name:
            # Resync agents
            logger_obj.info("Triggering agent resync auto-fix")
        
        elif 'consensus' in alert.alert_name:
            # Validate coherence
            logger_obj.info("Triggering coherence validation auto-fix")
        
        elif 'error' in alert.alert_name:
            # Clear error queue, restart services
            logger_obj.info("Triggering error recovery auto-fix")
        
        elif 'agent_offline' in alert.alert_name:
            # Force agent sync
            logger_obj.info("Triggering agent reconnect auto-fix")
    
    def get_alert_history(self, limit: int = 100) -> List[Dict]:
        """Get alert history."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT alert_name, severity, message, current_value, threshold, timestamp
                FROM alert_events
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
        
        except Exception as e:
            logger_obj.error(f"Failed to get alert history: {e}")
            return []
    
    def get_active_alerts(self) -> List[Dict]:
        """Get currently active/triggered alerts."""
        return [
            {
                'name': a.alert_name,
                'severity': a.severity,
                'message': a.message,
                'current_value': a.current_value,
                'threshold': a.threshold,
                'triggered_at': a.timestamp
            }
            for a in self.triggered_alerts
        ]
    
    def get_alert_summary(self, hours: int = 24) -> Dict:
        """Get alert summary."""
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(hours=hours)
        
        try:
            cursor.execute("""
                SELECT severity, COUNT(*) as count
                FROM alert_events
                WHERE timestamp > ?
                GROUP BY severity
            """, (cutoff.isoformat(),))
            
            severity_counts = {row['severity']: row['count'] for row in cursor.fetchall()}
            
            cursor.execute("""
                SELECT COUNT(DISTINCT alert_name) as unique_alerts
                FROM alert_events
                WHERE timestamp > ?
            """, (cutoff.isoformat(),))
            
            unique = cursor.fetchone()['unique_alerts']
            
            return {
                'time_window_hours': hours,
                'total_alerts': sum(severity_counts.values()),
                'by_severity': severity_counts,
                'unique_alert_types': unique,
                'critical': severity_counts.get('CRITICAL', 0),
                'warnings': severity_counts.get('WARNING', 0)
            }
        
        except Exception as e:
            logger_obj.error(f"Failed to get alert summary: {e}")
            return {}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Alert System")
    parser.add_argument('--check', action='store_true', help='Check alerts')
    parser.add_argument('--history', type=int, default=10, help='Show alert history')
    parser.add_argument('--active', action='store_true', help='Show active alerts')
    parser.add_argument('--summary', type=int, default=24, help='Show summary (hours)')
    parser.add_argument('--rules', action='store_true', help='List alert rules')
    
    args = parser.parse_args()
    
    alerter = AlertSystem()
    
    try:
        if args.rules:
            rules = alerter.get_alert_rules()
            print(f"\n✓ Alert Rules ({len(rules)}):")
            for rule in rules:
                print(f"  • {rule['name']}: {rule['severity']} - {rule['message']}")
        
        elif args.history:
            history = alerter.get_alert_history(args.history)
            print(f"\n✓ Alert History ({len(history)}):")
            for event in history[:10]:
                print(f"  [{event['severity']}] {event['alert_name']}: {event['message']}")
        
        elif args.active:
            active = alerter.get_active_alerts()
            print(f"\n✓ Active Alerts ({len(active)}):")
            for alert in active:
                print(f"  [{alert['severity']}] {alert['name']}: {alert['message']}")
        
        elif args.summary:
            summary = alerter.get_alert_summary(args.summary)
            print(f"\n✓ Alert Summary ({args.summary}h):")
            for key, val in summary.items():
                print(f"  {key}: {val}")
        
        else:
            parser.print_help()
    
    finally:
        alerter.close()


if __name__ == '__main__':
    main()
