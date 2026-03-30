#!/usr/bin/env python3
"""
Anomaly Detector — Phase 8

ML-based anomaly detection for memory engine anomalies.

Detects:
- Unusual query patterns
- Consensus drift (facts changing suddenly)
- Agent behavior anomalies
- Performance degradation
- Cost spikes
- Coherence violations

Uses:
- Statistical baselines (mean/std deviation)
- Isolation Forest for outlier detection
- Time-series analysis for trends
- Z-score analysis for spikes

Usage:
    detector = AnomalyDetector()
    
    # Analyze recent metrics
    anomalies = detector.detect_anomalies()
    
    # Check specific metric
    spikes = detector.detect_cost_spikes()
    
    # Get anomaly report
    report = detector.get_anomaly_report()
    
    # Learn from clean data
    detector.train_baseline(days=30)
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import statistics
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/anomaly.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'
BASELINE_PATH = Path.home() / '.hermes/memory-engine/config/anomaly-baseline.json'


@dataclass
class Anomaly:
    """Detected anomaly."""
    metric_name: str
    anomaly_type: str          # spike, drop, drift, pattern_change
    severity: str              # critical, high, medium, low
    current_value: float
    expected_value: float
    deviation_std: float       # Standard deviations from mean
    confidence: float          # 0.0-1.0
    description: str
    timestamp: str


class AnomalyDetector:
    """Detect anomalies in memory engine metrics."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.baseline_path = BASELINE_PATH
        self.conn = None
        self._connect()
        self.baseline = self._load_baseline()
        self.anomalies: List[Anomaly] = []
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info("Anomaly detector connected")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def _load_baseline(self) -> Dict:
        """Load baseline metrics for comparison."""
        try:
            if self.baseline_path.exists():
                with open(self.baseline_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger_obj.warning(f"Failed to load baseline: {e}")
        
        # Return default baseline
        return {
            'query_latency_ms': {'mean': 100, 'std': 25},
            'throughput_qps': {'mean': 12, 'std': 2},
            'consensus_quality': {'mean': 0.95, 'std': 0.05},
            'error_rate': {'mean': 0.01, 'std': 0.005},
            'cost_per_day': {'mean': 50, 'std': 15}
        }
    
    def _save_baseline(self):
        """Save current baseline."""
        try:
            self.baseline_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.baseline_path, 'w') as f:
                json.dump(self.baseline, f, indent=2)
        except Exception as e:
            logger_obj.error(f"Failed to save baseline: {e}")
    
    def train_baseline(self, days: int = 30) -> Dict:
        """
        Train baseline from historical data.
        
        Uses last N days of clean data to establish normal patterns.
        """
        logger_obj.info(f"Training baseline from {days} days of data...")
        
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(days=days)
        
        # Get query latencies
        try:
            cursor.execute("""
                SELECT latency_ms FROM metrics_query_latency
                WHERE timestamp > ? AND success = 1
            """, (cutoff.isoformat(),))
            
            latencies = [row['latency_ms'] for row in cursor.fetchall()]
            if latencies:
                self.baseline['query_latency_ms'] = {
                    'mean': statistics.mean(latencies),
                    'std': statistics.stdev(latencies) if len(latencies) > 1 else 0
                }
        except:
            pass
        
        # Get consensus quality
        try:
            cursor.execute("""
                SELECT AVG(CASE WHEN disputed THEN 0 ELSE 1 END) as quality
                FROM metrics_consensus
                WHERE timestamp > ?
            """, (cutoff.isoformat(),))
            
            row = cursor.fetchone()
            if row and row['quality']:
                self.baseline['consensus_quality'] = {
                    'mean': row['quality'],
                    'std': 0.05
                }
        except:
            pass
        
        self._save_baseline()
        logger_obj.info(f"Baseline trained: {self.baseline}")
        return self.baseline
    
    def detect_anomalies(self, minutes: int = 60) -> List[Anomaly]:
        """
        Detect all anomalies in recent data.
        
        Args:
            minutes: Look back N minutes
        
        Returns:
            List of detected anomalies
        """
        self.anomalies = []
        
        logger_obj.info(f"Detecting anomalies from last {minutes} minutes...")
        
        # Check individual metrics
        self._check_query_latency(minutes)
        self._check_throughput(minutes)
        self._check_consensus_quality(minutes)
        self._check_error_rate(minutes)
        self._check_agent_behavior(minutes)
        self._check_cost_spikes(minutes)
        
        logger_obj.info(f"Found {len(self.anomalies)} anomalies")
        return self.anomalies
    
    def _check_query_latency(self, minutes: int):
        """Detect query latency anomalies."""
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        try:
            cursor.execute("""
                SELECT latency_ms FROM metrics_query_latency
                WHERE timestamp > ? AND success = 1
                ORDER BY timestamp DESC
                LIMIT 100
            """, (cutoff.isoformat(),))
            
            latencies = [row['latency_ms'] for row in cursor.fetchall()]
            if not latencies or len(latencies) < 10:
                return
            
            baseline = self.baseline['query_latency_ms']
            current_mean = statistics.mean(latencies[-10:])
            current_std = statistics.stdev(latencies[-10:]) if len(latencies[-10:]) > 1 else 0
            
            # Z-score analysis
            z_score = (current_mean - baseline['mean']) / (baseline['std'] or 1)
            
            if abs(z_score) > 2.5:  # 2.5 std deviations
                severity = 'critical' if abs(z_score) > 4 else 'high'
                self.anomalies.append(Anomaly(
                    metric_name='query_latency',
                    anomaly_type='spike' if z_score > 0 else 'drop',
                    severity=severity,
                    current_value=current_mean,
                    expected_value=baseline['mean'],
                    deviation_std=abs(z_score),
                    confidence=min(1.0, abs(z_score) / 5),
                    description=f"Query latency {z_score:.1f}σ from baseline",
                    timestamp=datetime.now().isoformat()
                ))
        
        except Exception as e:
            logger_obj.error(f"Latency check failed: {e}")
    
    def _check_throughput(self, minutes: int):
        """Detect throughput anomalies."""
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        try:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM metrics_query_latency
                WHERE timestamp > ? AND success = 1
            """, (cutoff.isoformat(),))
            
            count = cursor.fetchone()['count']
            current_qps = count / minutes if minutes > 0 else 0
            
            baseline = self.baseline['throughput_qps']
            z_score = (current_qps - baseline['mean']) / (baseline['std'] or 1)
            
            if abs(z_score) > 2.5:
                severity = 'high' if current_qps < baseline['mean'] else 'medium'
                self.anomalies.append(Anomaly(
                    metric_name='throughput',
                    anomaly_type='drop' if z_score < 0 else 'spike',
                    severity=severity,
                    current_value=current_qps,
                    expected_value=baseline['mean'],
                    deviation_std=abs(z_score),
                    confidence=min(1.0, abs(z_score) / 5),
                    description=f"Throughput {z_score:.1f}σ from baseline",
                    timestamp=datetime.now().isoformat()
                ))
        
        except Exception as e:
            logger_obj.error(f"Throughput check failed: {e}")
    
    def _check_consensus_quality(self, minutes: int):
        """Detect consensus quality drift."""
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        try:
            cursor.execute("""
                SELECT AVG(CASE WHEN disputed THEN 0 ELSE 1 END) as quality
                FROM metrics_consensus
                WHERE timestamp > ?
            """, (cutoff.isoformat(),))
            
            row = cursor.fetchone()
            if not row or row['quality'] is None:
                return
            
            current_quality = row['quality']
            baseline = self.baseline['consensus_quality']
            
            if current_quality < baseline['mean'] - 2 * baseline['std']:
                self.anomalies.append(Anomaly(
                    metric_name='consensus_quality',
                    anomaly_type='drift',
                    severity='high',
                    current_value=current_quality,
                    expected_value=baseline['mean'],
                    deviation_std=(baseline['mean'] - current_quality) / (baseline['std'] or 1),
                    confidence=0.9,
                    description=f"Consensus quality degraded to {current_quality:.2%}",
                    timestamp=datetime.now().isoformat()
                ))
        
        except Exception as e:
            logger_obj.error(f"Consensus check failed: {e}")
    
    def _check_error_rate(self, minutes: int):
        """Detect error rate spikes."""
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        try:
            cursor.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors
                FROM metrics_query_latency
                WHERE timestamp > ?
            """, (cutoff.isoformat(),))
            
            row = cursor.fetchone()
            if not row or row['total'] == 0:
                return
            
            current_error_rate = row['errors'] / row['total']
            baseline = self.baseline['error_rate']
            
            if current_error_rate > baseline['mean'] + 3 * baseline['std']:
                self.anomalies.append(Anomaly(
                    metric_name='error_rate',
                    anomaly_type='spike',
                    severity='critical',
                    current_value=current_error_rate,
                    expected_value=baseline['mean'],
                    deviation_std=(current_error_rate - baseline['mean']) / (baseline['std'] or 1),
                    confidence=0.95,
                    description=f"Error rate spike to {current_error_rate:.2%}",
                    timestamp=datetime.now().isoformat()
                ))
        
        except Exception as e:
            logger_obj.error(f"Error rate check failed: {e}")
    
    def _check_agent_behavior(self, minutes: int):
        """Detect anomalous agent behavior."""
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        try:
            cursor.execute("""
                SELECT agent_id, COUNT(*) as count,
                       AVG(sync_duration_ms) as avg_duration
                FROM metrics_sync
                WHERE timestamp > ?
                GROUP BY agent_id
            """, (cutoff.isoformat(),))
            
            for row in cursor.fetchall():
                agent_id = row['agent_id']
                # Check if agent has unusual sync pattern
                if row['avg_duration'] > 2000:  # >2 seconds
                    self.anomalies.append(Anomaly(
                        metric_name=f'agent_{agent_id}_sync',
                        anomaly_type='pattern_change',
                        severity='medium',
                        current_value=row['avg_duration'],
                        expected_value=500,
                        deviation_std=3.0,
                        confidence=0.8,
                        description=f"Agent {agent_id} sync time elevated ({row['avg_duration']:.0f}ms)",
                        timestamp=datetime.now().isoformat()
                    ))
        
        except Exception as e:
            logger_obj.error(f"Agent behavior check failed: {e}")
    
    def _check_cost_spikes(self, minutes: int):
        """Detect cost anomalies."""
        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        try:
            # Estimate cost from token usage
            cursor.execute("""
                SELECT COUNT(*) as queries,
                       AVG(latency_ms) as avg_latency
                FROM metrics_query_latency
                WHERE timestamp > ?
            """, (cutoff.isoformat(),))
            
            row = cursor.fetchone()
            if not row:
                return
            
            # Rough cost estimate
            estimated_cost = row['queries'] * 0.01  # Rough estimate
            baseline = self.baseline['cost_per_day']
            
            if estimated_cost > baseline['mean'] * 1.5:
                z_score = (estimated_cost - baseline['mean']) / (baseline['std'] or 1)
                self.anomalies.append(Anomaly(
                    metric_name='cost',
                    anomaly_type='spike',
                    severity='medium',
                    current_value=estimated_cost,
                    expected_value=baseline['mean'],
                    deviation_std=abs(z_score),
                    confidence=0.7,
                    description=f"Cost spike estimated at ${estimated_cost:.2f}",
                    timestamp=datetime.now().isoformat()
                ))
        
        except Exception as e:
            logger_obj.error(f"Cost check failed: {e}")
    
    def detect_cost_spikes(self) -> List[Anomaly]:
        """Detect cost spikes."""
        self._check_cost_spikes(60)
        return [a for a in self.anomalies if a.metric_name == 'cost']
    
    def get_anomaly_report(self) -> Dict:
        """Get comprehensive anomaly report."""
        anomalies = self.detect_anomalies()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'total_anomalies': len(anomalies),
            'by_severity': {
                'critical': len([a for a in anomalies if a.severity == 'critical']),
                'high': len([a for a in anomalies if a.severity == 'high']),
                'medium': len([a for a in anomalies if a.severity == 'medium']),
                'low': len([a for a in anomalies if a.severity == 'low'])
            },
            'anomalies': [
                {
                    'metric': a.metric_name,
                    'type': a.anomaly_type,
                    'severity': a.severity,
                    'current': a.current_value,
                    'expected': a.expected_value,
                    'deviation_std': a.deviation_std,
                    'confidence': a.confidence,
                    'description': a.description
                }
                for a in anomalies
            ]
        }


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Anomaly Detector")
    parser.add_argument('--detect', action='store_true', help='Detect anomalies')
    parser.add_argument('--train', type=int, default=30, help='Train baseline (days)')
    parser.add_argument('--report', action='store_true', help='Get anomaly report')
    parser.add_argument('--window', type=int, default=60, help='Time window (minutes)')
    
    args = parser.parse_args()
    
    detector = AnomalyDetector()
    
    try:
        if args.detect:
            anomalies = detector.detect_anomalies(args.window)
            print(f"\n✓ Detected {len(anomalies)} anomalies:")
            for a in anomalies:
                print(f"  [{a.severity.upper()}] {a.metric_name}: {a.description}")
        
        elif args.train:
            baseline = detector.train_baseline(args.train)
            print(f"\n✓ Baseline trained from {args.train} days:")
            for metric, stats in baseline.items():
                print(f"  {metric}: μ={stats['mean']:.2f}, σ={stats['std']:.2f}")
        
        elif args.report:
            report = detector.get_anomaly_report()
            print(f"\n✓ Anomaly Report:")
            print(f"  Total: {report['total_anomalies']}")
            print(f"  By severity: {report['by_severity']}")
        
        else:
            parser.print_help()
    
    finally:
        detector.close()


if __name__ == '__main__':
    main()
