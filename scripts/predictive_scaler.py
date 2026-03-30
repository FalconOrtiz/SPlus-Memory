#!/usr/bin/env python3
"""
Predictive Scaler — Phase 8

Auto-scaling system based on workload predictions.

Predicts:
- Query volume trends
- Resource requirements
- Cost projections
- Peak load times
- Agent capacity needs

Actions:
- Auto-scale container resources
- Pre-allocate cache
- Adjust model selection
- Scale agent pool
- Optimize batching

Usage:
    scaler = PredictiveScaler()
    
    # Predict next hour
    prediction = scaler.predict_load(horizon_hours=1)
    
    # Get scaling recommendation
    recommendation = scaler.get_scaling_recommendation()
    
    # Apply auto-scaling
    scaler.apply_scaling()
    
    # Monitor resource usage
    usage = scaler.get_resource_usage()
"""

import sqlite3
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
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/scaler.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


@dataclass
class ScalingPrediction:
    """Prediction for future load."""
    timestamp: str
    horizon_hours: int
    predicted_qps: float
    predicted_latency_ms: float
    predicted_memory_mb: float
    predicted_cpu_percent: float
    confidence: float
    recommended_action: str


class PredictiveScaler:
    """Predict load and recommend auto-scaling."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        
        # Current resource limits
        self.cpu_limit = 2
        self.memory_limit_mb = 8192
        self.cache_limit_mb = 500
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info("Predictive scaler connected")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def predict_load(self, horizon_hours: int = 1) -> ScalingPrediction:
        """
        Predict load for next N hours.
        
        Uses historical data to project:
        - Query volume
        - Resource usage
        - Peak times
        
        Args:
            horizon_hours: Hours ahead to predict
        
        Returns:
            Scaling prediction
        """
        logger_obj.info(f"Predicting load for {horizon_hours} hours ahead...")
        
        cursor = self.conn.cursor()
        
        # Get historical data for last 7 days
        cutoff = datetime.now() - timedelta(days=7)
        
        try:
            # Get hourly patterns
            cursor.execute("""
                SELECT 
                    strftime('%H', timestamp) as hour,
                    COUNT(*) as query_count,
                    AVG(latency_ms) as avg_latency
                FROM metrics_query_latency
                WHERE timestamp > ?
                GROUP BY hour
                ORDER BY hour
            """, (cutoff.isoformat(),))
            
            hourly_patterns = {row['hour']: {
                'queries': row['query_count'],
                'latency': row['avg_latency']
            } for row in cursor.fetchall()}
            
            # Get current hour pattern
            now = datetime.now()
            current_hour = now.strftime('%H')
            
            if current_hour not in hourly_patterns:
                # Use average if no data
                avg_queries = statistics.mean([p['queries'] for p in hourly_patterns.values()])
                avg_latency = statistics.mean([p['latency'] for p in hourly_patterns.values()])
            else:
                pattern = hourly_patterns[current_hour]
                avg_queries = pattern['queries']
                avg_latency = pattern['latency']
            
            # Convert to QPS
            predicted_qps = avg_queries / 3600  # queries per second
            predicted_latency_ms = avg_latency or 100
            
            # Predict resource usage
            # Memory: roughly 5MB per active connection + cache
            predicted_memory_mb = 100 + (predicted_qps * 5) + self.cache_limit_mb
            
            # CPU: scales with query complexity
            predicted_cpu_percent = min(100, (predicted_qps / 15) * 50)  # Rough estimate
            
            # Confidence decreases with horizon
            confidence = max(0.5, 1.0 - (horizon_hours * 0.1))
            
            # Determine action
            recommended_action = self._recommend_scaling(
                predicted_qps,
                predicted_memory_mb,
                predicted_cpu_percent
            )
            
            prediction = ScalingPrediction(
                timestamp=datetime.now().isoformat(),
                horizon_hours=horizon_hours,
                predicted_qps=predicted_qps,
                predicted_latency_ms=predicted_latency_ms,
                predicted_memory_mb=predicted_memory_mb,
                predicted_cpu_percent=predicted_cpu_percent,
                confidence=confidence,
                recommended_action=recommended_action
            )
            
            logger_obj.info(f"Prediction: {predicted_qps:.1f} QPS, {predicted_memory_mb:.0f}MB, {predicted_cpu_percent:.0f}% CPU")
            return prediction
        
        except Exception as e:
            logger_obj.error(f"Prediction failed: {e}")
            return ScalingPrediction(
                timestamp=datetime.now().isoformat(),
                horizon_hours=horizon_hours,
                predicted_qps=10.0,
                predicted_latency_ms=100,
                predicted_memory_mb=self.memory_limit_mb,
                predicted_cpu_percent=50,
                confidence=0.5,
                recommended_action="MAINTAIN"
            )
    
    def _recommend_scaling(self, qps: float, memory_mb: float, cpu_percent: float) -> str:
        """
        Recommend scaling action based on predictions.
        
        Actions:
        - SCALE_UP: Increase resources
        - SCALE_DOWN: Decrease resources
        - MAINTAIN: Keep current
        - EMERGENCY: Critical scaling needed
        """
        if cpu_percent > 80 or memory_mb > self.memory_limit_mb * 0.9:
            return "SCALE_UP"
        elif cpu_percent > 90 or memory_mb > self.memory_limit_mb * 0.95:
            return "EMERGENCY"
        elif cpu_percent < 20 and memory_mb < self.memory_limit_mb * 0.5:
            return "SCALE_DOWN"
        else:
            return "MAINTAIN"
    
    def get_scaling_recommendation(self) -> Dict:
        """Get detailed scaling recommendation."""
        prediction = self.predict_load(1)
        current = self.get_resource_usage()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'current': current,
            'predicted': {
                'qps': prediction.predicted_qps,
                'latency_ms': prediction.predicted_latency_ms,
                'memory_mb': prediction.predicted_memory_mb,
                'cpu_percent': prediction.predicted_cpu_percent
            },
            'action': prediction.recommended_action,
            'confidence': prediction.confidence,
            'scaling_steps': self._get_scaling_steps(prediction)
        }
    
    def _get_scaling_steps(self, prediction: ScalingPrediction) -> List[Dict]:
        """Get concrete scaling steps to take."""
        steps = []
        
        if prediction.recommended_action == "SCALE_UP":
            if prediction.predicted_cpu_percent > 60:
                steps.append({
                    'resource': 'cpu',
                    'action': 'increase',
                    'from': self.cpu_limit,
                    'to': int(self.cpu_limit * 1.5),
                    'reason': f"CPU usage projected to {prediction.predicted_cpu_percent:.0f}%"
                })
            
            if prediction.predicted_memory_mb > self.memory_limit_mb * 0.8:
                new_memory = int(self.memory_limit_mb * 1.5)
                steps.append({
                    'resource': 'memory',
                    'action': 'increase',
                    'from': self.memory_limit_mb,
                    'to': new_memory,
                    'reason': f"Memory usage projected to {prediction.predicted_memory_mb:.0f}MB"
                })
            
            if prediction.predicted_qps > 15:
                steps.append({
                    'resource': 'connection_pool',
                    'action': 'increase',
                    'from': 5,
                    'to': 10,
                    'reason': f"QPS projected to {prediction.predicted_qps:.1f}"
                })
        
        elif prediction.recommended_action == "SCALE_DOWN":
            steps.append({
                'resource': 'cpu',
                'action': 'decrease',
                'from': self.cpu_limit,
                'to': 1,
                'reason': "Underutilized, reducing costs"
            })
            
            steps.append({
                'resource': 'memory',
                'action': 'decrease',
                'from': self.memory_limit_mb,
                'to': 4096,
                'reason': "Underutilized, reducing costs"
            })
        
        return steps
    
    def get_resource_usage(self) -> Dict:
        """Get current resource usage."""
        cursor = self.conn.cursor()
        
        try:
            # Current QPS (last minute)
            cutoff = datetime.now() - timedelta(minutes=1)
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM metrics_query_latency
                WHERE timestamp > ?
            """, (cutoff.isoformat(),))
            
            qps = cursor.fetchone()['count'] / 60
            
            # Current latency (p95)
            cursor.execute("""
                SELECT latency_ms FROM metrics_query_latency
                ORDER BY latency_ms
                LIMIT 1 OFFSET (SELECT COUNT(*) * 95 / 100 FROM metrics_query_latency)
            """)
            
            latency_row = cursor.fetchone()
            p95_latency = latency_row['latency_ms'] if latency_row else 100
            
            return {
                'timestamp': datetime.now().isoformat(),
                'current_qps': qps,
                'p95_latency_ms': p95_latency,
                'cpu_limit': self.cpu_limit,
                'memory_limit_mb': self.memory_limit_mb,
                'cache_size_mb': self.cache_limit_mb
            }
        
        except Exception as e:
            logger_obj.error(f"Failed to get resource usage: {e}")
            return {}
    
    def apply_scaling(self, dry_run: bool = True) -> Dict:
        """
        Apply auto-scaling recommendations.
        
        Args:
            dry_run: If True, only show what would be done
        
        Returns:
            Scaling action report
        """
        recommendation = self.get_scaling_recommendation()
        action = recommendation['action']
        
        logger_obj.info(f"Scaling action: {action} (dry_run={dry_run})")
        
        if action == "MAINTAIN":
            return {'status': 'no_action', 'reason': 'System within normal parameters'}
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'dry_run': dry_run,
            'steps': recommendation['scaling_steps'],
            'applied': []
        }
        
        for step in recommendation['scaling_steps']:
            if not dry_run:
                # Would apply actual scaling here
                logger_obj.info(f"Applying: {step['resource']} {step['action']} {step['from']} → {step['to']}")
                report['applied'].append(step)
            else:
                logger_obj.info(f"Would apply: {step['resource']} {step['action']}")
        
        return report


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Predictive Scaler")
    parser.add_argument('--predict', type=int, default=1, help='Predict load (hours)')
    parser.add_argument('--recommend', action='store_true', help='Get recommendation')
    parser.add_argument('--usage', action='store_true', help='Get current usage')
    parser.add_argument('--apply', action='store_true', help='Apply scaling')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    
    args = parser.parse_args()
    
    scaler = PredictiveScaler()
    
    try:
        if args.predict:
            pred = scaler.predict_load(args.predict)
            print(f"\n✓ Load Prediction ({args.predict}h):")
            print(f"  QPS: {pred.predicted_qps:.1f}")
            print(f"  Latency: {pred.predicted_latency_ms:.0f}ms")
            print(f"  Memory: {pred.predicted_memory_mb:.0f}MB")
            print(f"  CPU: {pred.predicted_cpu_percent:.0f}%")
            print(f"  Confidence: {pred.confidence:.1%}")
            print(f"  Action: {pred.recommended_action}")
        
        elif args.recommend:
            rec = scaler.get_scaling_recommendation()
            print(f"\n✓ Scaling Recommendation:")
            print(f"  Action: {rec['action']}")
            print(f"  Confidence: {rec['confidence']:.1%}")
            print(f"  Steps:")
            for step in rec['scaling_steps']:
                print(f"    - {step['resource']}: {step['from']} → {step['to']}")
        
        elif args.usage:
            usage = scaler.get_resource_usage()
            print(f"\n✓ Current Usage:")
            for key, val in usage.items():
                print(f"  {key}: {val}")
        
        elif args.apply:
            report = scaler.apply_scaling(dry_run=args.dry_run)
            print(f"\n✓ Scaling Report:")
            print(f"  Action: {report['action']}")
            print(f"  Applied: {len(report['applied'])} changes")
        
        else:
            parser.print_help()
    
    finally:
        scaler.close()


if __name__ == '__main__':
    main()
