#!/usr/bin/env python3
"""
Metrics Collector — Phase 6

Collects and aggregates performance metrics for the memory engine.

Metrics tracked:
- Query latency (min/max/avg/p95/p99)
- Throughput (queries/second)
- Agent performance per role
- Consensus quality (disputed %)
- Sync health per agent
- Memory usage
- Error rates

Usage:
    collector = MetricsCollector()
    
    # Record a query
    collector.record_query('falcon', duration_ms=85, success=True)
    
    # Record agent vote
    collector.record_vote(agent_id, fact_id, confidence, latency_ms)
    
    # Get metrics
    metrics = collector.get_metrics()
    
    # Get dashboard data
    dashboard = collector.get_dashboard_snapshot()
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import statistics

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/metrics.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


@dataclass
class MetricSnapshot:
    """Point-in-time metric snapshot."""
    timestamp: str
    metric_name: str
    value: float
    labels: Dict[str, str]  # {agent_id, query_type, etc}


class MetricsCollector:
    """Collect and aggregate memory engine metrics."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        self._ensure_tables()
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info("Metrics collector connected")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def _ensure_tables(self):
        """Ensure metrics tables exist."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics_query_latency (
                id INTEGER PRIMARY KEY,
                agent_id TEXT,
                latency_ms REAL,
                success BOOLEAN,
                query_type TEXT,
                timestamp TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics_agent_performance (
                id INTEGER PRIMARY KEY,
                agent_id TEXT,
                metric_name TEXT,
                value REAL,
                timestamp TEXT,
                UNIQUE(agent_id, metric_name, timestamp)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics_consensus (
                id INTEGER PRIMARY KEY,
                fact_id TEXT,
                agreement_level INTEGER,
                consensus_score REAL,
                disputed BOOLEAN,
                timestamp TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics_sync (
                id INTEGER PRIMARY KEY,
                agent_id TEXT,
                sync_duration_ms REAL,
                facts_synced INTEGER,
                conflicts INTEGER,
                timestamp TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics_errors (
                id INTEGER PRIMARY KEY,
                component TEXT,
                error_type TEXT,
                message TEXT,
                timestamp TEXT
            )
        """)
        
        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_query_timestamp ON metrics_query_latency(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_agent ON metrics_agent_performance(agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_consensus_timestamp ON metrics_consensus(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_sync_agent ON metrics_sync(agent_id)")
        
        self.conn.commit()
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def record_query(
        self,
        agent_id: str,
        latency_ms: float,
        success: bool = True,
        query_type: str = 'hybrid'
    ) -> bool:
        """Record a query execution."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO metrics_query_latency
                (agent_id, latency_ms, success, query_type, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (agent_id, latency_ms, success, query_type, datetime.now().isoformat()))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger_obj.error(f"Failed to record query: {e}")
            return False
    
    def record_vote(
        self,
        agent_id: str,
        fact_id: str,
        confidence: float,
        latency_ms: float = 0
    ) -> bool:
        """Record an agent vote."""
        cursor = self.conn.cursor()
        
        try:
            # Also record as agent performance metric
            cursor.execute("""
                INSERT INTO metrics_agent_performance
                (agent_id, metric_name, value, timestamp)
                VALUES (?, ?, ?, ?)
            """, (agent_id, 'vote_confidence', confidence, datetime.now().isoformat()))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger_obj.error(f"Failed to record vote: {e}")
            return False
    
    def record_sync(
        self,
        agent_id: str,
        duration_ms: float,
        facts_synced: int,
        conflicts: int = 0
    ) -> bool:
        """Record agent synchronization."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO metrics_sync
                (agent_id, sync_duration_ms, facts_synced, conflicts, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (agent_id, duration_ms, facts_synced, conflicts, datetime.now().isoformat()))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger_obj.error(f"Failed to record sync: {e}")
            return False
    
    def record_consensus(
        self,
        fact_id: str,
        agreement_level: int,
        consensus_score: float,
        disputed: bool = False
    ) -> bool:
        """Record consensus result."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO metrics_consensus
                (fact_id, agreement_level, consensus_score, disputed, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (fact_id, agreement_level, consensus_score, disputed, datetime.now().isoformat()))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger_obj.error(f"Failed to record consensus: {e}")
            return False
    
    def record_error(
        self,
        component: str,
        error_type: str,
        message: str
    ) -> bool:
        """Record an error."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO metrics_errors
                (component, error_type, message, timestamp)
                VALUES (?, ?, ?, ?)
            """, (component, error_type, message, datetime.now().isoformat()))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger_obj.error(f"Failed to record error: {e}")
            return False
    
    def get_query_latency_stats(self, minutes: int = 60) -> Dict:
        """Get query latency statistics."""
        cursor = self.conn.cursor()
        
        try:
            cutoff = datetime.now() - timedelta(minutes=minutes)
            cursor.execute("""
                SELECT agent_id, latency_ms
                FROM metrics_query_latency
                WHERE timestamp > ? AND success = 1
                ORDER BY latency_ms
            """, (cutoff.isoformat(),))
            
            rows = cursor.fetchall()
            
            if not rows:
                return {
                    'agent_id': 'all',
                    'count': 0,
                    'min_ms': 0,
                    'max_ms': 0,
                    'avg_ms': 0,
                    'p50_ms': 0,
                    'p95_ms': 0,
                    'p99_ms': 0
                }
            
            latencies = [row['latency_ms'] for row in rows]
            
            return {
                'agent_id': 'all',
                'count': len(latencies),
                'min_ms': round(min(latencies), 2),
                'max_ms': round(max(latencies), 2),
                'avg_ms': round(statistics.mean(latencies), 2),
                'p50_ms': round(statistics.median(latencies), 2),
                'p95_ms': round(statistics.quantiles(latencies, n=20)[18], 2) if len(latencies) > 20 else round(statistics.median(latencies), 2),
                'p99_ms': round(statistics.quantiles(latencies, n=100)[98], 2) if len(latencies) > 100 else round(max(latencies), 2)
            }
        
        except Exception as e:
            logger_obj.error(f"Failed to get latency stats: {e}")
            return {}
    
    def get_agent_accuracy(self, minutes: int = 60) -> Dict[str, Dict]:
        """Get per-agent accuracy metrics."""
        cursor = self.conn.cursor()
        
        try:
            cutoff = datetime.now() - timedelta(minutes=minutes)
            cursor.execute("""
                SELECT agent_id, COUNT(*) as votes, AVG(value) as avg_confidence
                FROM metrics_agent_performance
                WHERE timestamp > ? AND metric_name = 'vote_confidence'
                GROUP BY agent_id
            """, (cutoff.isoformat(),))
            
            results = {}
            for row in cursor.fetchall():
                results[row['agent_id']] = {
                    'votes': row['votes'],
                    'avg_confidence': round(row['avg_confidence'], 4),
                    'authority': {'falcon': 0.95, 'katsumi': 0.90, 'leo': 0.75}.get(row['agent_id'], 0.5)
                }
            
            return results
        
        except Exception as e:
            logger_obj.error(f"Failed to get agent accuracy: {e}")
            return {}
    
    def get_sync_health(self, minutes: int = 60) -> Dict[str, Dict]:
        """Get synchronization health per agent."""
        cursor = self.conn.cursor()
        
        try:
            cutoff = datetime.now() - timedelta(minutes=minutes)
            cursor.execute("""
                SELECT agent_id,
                       COUNT(*) as sync_count,
                       AVG(sync_duration_ms) as avg_sync_ms,
                       SUM(facts_synced) as total_facts,
                       SUM(conflicts) as total_conflicts
                FROM metrics_sync
                WHERE timestamp > ?
                GROUP BY agent_id
            """, (cutoff.isoformat(),))
            
            results = {}
            for row in cursor.fetchall():
                conflict_rate = (row['total_conflicts'] / row['total_facts']) if row['total_facts'] > 0 else 0
                health = max(0, 100 - (conflict_rate * 100))
                
                results[row['agent_id']] = {
                    'sync_count': row['sync_count'],
                    'avg_sync_ms': round(row['avg_sync_ms'], 2),
                    'total_facts': row['total_facts'],
                    'total_conflicts': row['total_conflicts'],
                    'conflict_rate': round(conflict_rate, 4),
                    'health_score': round(health, 1)
                }
            
            return results
        
        except Exception as e:
            logger_obj.error(f"Failed to get sync health: {e}")
            return {}
    
    def get_consensus_quality(self, minutes: int = 60) -> Dict:
        """Get consensus voting quality."""
        cursor = self.conn.cursor()
        
        try:
            cutoff = datetime.now() - timedelta(minutes=minutes)
            cursor.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN disputed THEN 1 ELSE 0 END) as disputed_count,
                       AVG(consensus_score) as avg_score,
                       AVG(agreement_level) as avg_agreement
                FROM metrics_consensus
                WHERE timestamp > ?
            """, (cutoff.isoformat(),))
            
            row = cursor.fetchone()
            
            total = row['total'] or 0
            disputed = row['disputed_count'] or 0
            
            return {
                'total_votes': total,
                'disputed_facts': disputed,
                'disputed_rate': round((disputed / total) if total > 0 else 0, 4),
                'avg_consensus_score': round(row['avg_score'] or 0, 4),
                'avg_agreement_level': round(row['avg_agreement'] or 0, 2),
                'quality_score': max(0, 100 - ((disputed / total) * 100)) if total > 0 else 0
            }
        
        except Exception as e:
            logger_obj.error(f"Failed to get consensus quality: {e}")
            return {}
    
    def get_error_rate(self, minutes: int = 60) -> Dict:
        """Get error rate and breakdown."""
        cursor = self.conn.cursor()
        
        try:
            cutoff = datetime.now() - timedelta(minutes=minutes)
            cursor.execute("""
                SELECT component, error_type, COUNT(*) as count
                FROM metrics_errors
                WHERE timestamp > ?
                GROUP BY component, error_type
                ORDER BY count DESC
            """, (cutoff.isoformat(),))
            
            errors = [
                {
                    'component': row['component'],
                    'type': row['error_type'],
                    'count': row['count']
                }
                for row in cursor.fetchall()
            ]
            
            total_errors = sum(e['count'] for e in errors)
            
            return {
                'total_errors': total_errors,
                'errors_by_component': errors,
                'error_rate': total_errors  # per window
            }
        
        except Exception as e:
            logger_obj.error(f"Failed to get error rate: {e}")
            return {}
    
    def get_metrics(self, minutes: int = 60) -> Dict:
        """Get comprehensive metrics."""
        return {
            'timestamp': datetime.now().isoformat(),
            'window_minutes': minutes,
            'query_latency': self.get_query_latency_stats(minutes),
            'agent_accuracy': self.get_agent_accuracy(minutes),
            'sync_health': self.get_sync_health(minutes),
            'consensus_quality': self.get_consensus_quality(minutes),
            'error_rate': self.get_error_rate(minutes)
        }
    
    def get_dashboard_snapshot(self) -> Dict:
        """Get real-time dashboard snapshot."""
        metrics = self.get_metrics(minutes=60)
        
        # Calculate overall health
        latency_health = max(0, 100 - (metrics['query_latency'].get('avg_ms', 0) / 2))
        sync_health = statistics.mean(
            [s['health_score'] for s in metrics['sync_health'].values()]
        ) if metrics['sync_health'] else 50
        consensus_quality = metrics['consensus_quality'].get('quality_score', 50)
        
        overall_health = (latency_health + sync_health + consensus_quality) / 3
        
        return {
            'timestamp': datetime.now().isoformat(),
            'overall_health': round(overall_health, 1),
            'latency_ms': round(metrics['query_latency'].get('avg_ms', 0), 2),
            'throughput_qps': self._calculate_throughput(),
            'sync_health': sync_health,
            'consensus_quality': consensus_quality,
            'error_rate': metrics['error_rate']['error_rate'],
            'agents': {
                agent: {
                    'accuracy': info.get('avg_confidence', 0),
                    'authority': info.get('authority', 0)
                }
                for agent, info in metrics['agent_accuracy'].items()
            }
        }
    
    def _calculate_throughput(self) -> float:
        """Calculate queries per second."""
        cursor = self.conn.cursor()
        
        try:
            cutoff = datetime.now() - timedelta(minutes=1)
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM metrics_query_latency
                WHERE timestamp > ? AND success = 1
            """, (cutoff.isoformat(),))
            
            row = cursor.fetchone()
            return row['count'] if row else 0
        
        except:
            return 0


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Metrics Collector")
    parser.add_argument('--metrics', action='store_true', help='Get metrics snapshot')
    parser.add_argument('--dashboard', action='store_true', help='Get dashboard snapshot')
    parser.add_argument('--latency', action='store_true', help='Get latency stats')
    parser.add_argument('--agents', action='store_true', help='Get agent accuracy')
    parser.add_argument('--sync', action='store_true', help='Get sync health')
    parser.add_argument('--consensus', action='store_true', help='Get consensus quality')
    parser.add_argument('--errors', action='store_true', help='Get error rate')
    parser.add_argument('--window', type=int, default=60, help='Time window in minutes')
    
    args = parser.parse_args()
    
    collector = MetricsCollector()
    
    try:
        if args.metrics:
            metrics = collector.get_metrics(args.window)
            print(f"\n✓ Metrics ({args.window}m window):")
            print(f"  Latency: {metrics['query_latency']}")
            print(f"  Agents: {metrics['agent_accuracy']}")
            print(f"  Sync: {metrics['sync_health']}")
            print(f"  Consensus: {metrics['consensus_quality']}")
            print(f"  Errors: {metrics['error_rate']}")
        
        elif args.dashboard:
            snapshot = collector.get_dashboard_snapshot()
            print(f"\n✓ Dashboard Snapshot:")
            print(f"  Overall Health: {snapshot['overall_health']}/100")
            print(f"  Latency: {snapshot['latency_ms']}ms")
            print(f"  Throughput: {snapshot['throughput_qps']} q/s")
            print(f"  Sync Health: {snapshot['sync_health']}/100")
            print(f"  Consensus Quality: {snapshot['consensus_quality']}/100")
            print(f"  Error Rate: {snapshot['error_rate']}")
        
        elif args.latency:
            stats = collector.get_query_latency_stats(args.window)
            print(f"\n✓ Latency Stats ({args.window}m):")
            for key, val in stats.items():
                print(f"  {key}: {val}")
        
        elif args.agents:
            accuracy = collector.get_agent_accuracy(args.window)
            print(f"\n✓ Agent Accuracy ({args.window}m):")
            for agent, info in accuracy.items():
                print(f"  {agent}: {info}")
        
        elif args.sync:
            health = collector.get_sync_health(args.window)
            print(f"\n✓ Sync Health ({args.window}m):")
            for agent, info in health.items():
                print(f"  {agent}: health={info['health_score']}, syncs={info['sync_count']}")
        
        elif args.consensus:
            quality = collector.get_consensus_quality(args.window)
            print(f"\n✓ Consensus Quality ({args.window}m):")
            for key, val in quality.items():
                print(f"  {key}: {val}")
        
        elif args.errors:
            errors = collector.get_error_rate(args.window)
            print(f"\n✓ Error Rate ({args.window}m):")
            print(f"  Total Errors: {errors['total_errors']}")
            for err in errors['errors_by_component']:
                print(f"  {err['component']}/{err['type']}: {err['count']}")
        
        else:
            parser.print_help()
    
    finally:
        collector.close()


if __name__ == '__main__':
    main()
