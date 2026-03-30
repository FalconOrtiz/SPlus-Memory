#!/usr/bin/env python3
"""
Health Dashboard — Phase 6

Real-time monitoring dashboard for memory engine.

Displays:
- System health score (0-100)
- Query latency (p50, p95, p99)
- Throughput (queries/second)
- Agent status (sync health, accuracy)
- Consensus quality (disputed rate)
- Error rate & breakdown
- Alert status (active alerts)
- Memory usage

CLI dashboard with auto-refresh.
Can also export JSON for web dashboard integration.

Usage:
    dashboard = HealthDashboard()
    dashboard.render_terminal()
    
    # Or get JSON for web dashboard
    json_data = dashboard.get_json_snapshot()
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List
from datetime import datetime
import time
import sys

logging.basicConfig(level=logging.WARNING)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


class HealthDashboard:
    """Real-time health dashboard."""
    
    def __init__(self, db_path: Path = None, metrics_collector=None, alert_system=None):
        self.db_path = db_path or DB_PATH
        self.metrics_collector = metrics_collector
        self.alert_system = alert_system
    
    def get_json_snapshot(self) -> Dict:
        """Get dashboard data as JSON."""
        if not self.metrics_collector:
            return {}
        
        metrics = self.metrics_collector.get_metrics(minutes=60)
        dashboard = self.metrics_collector.get_dashboard_snapshot()
        
        alerts = []
        if self.alert_system:
            alerts = self.alert_system.get_active_alerts()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'health': {
                'overall': dashboard['overall_health'],
                'latency_ms': dashboard['latency_ms'],
                'throughput_qps': dashboard['throughput_qps'],
                'sync_health': dashboard['sync_health'],
                'consensus_quality': dashboard['consensus_quality'],
                'error_rate': dashboard['error_rate']
            },
            'agents': dashboard['agents'],
            'metrics': metrics,
            'alerts': alerts,
            'status': 'operational' if dashboard['overall_health'] > 70 else 'degraded'
        }
    
    def render_terminal(self, refresh_interval: int = 30, iterations: int = None):
        """Render dashboard in terminal with auto-refresh."""
        iteration = 0
        
        try:
            while iterations is None or iteration < iterations:
                self._clear_screen()
                self._print_header()
                
                data = self.get_json_snapshot()
                
                if data:
                    self._print_health_score(data['health'])
                    self._print_performance(data['health'])
                    self._print_agents(data['agents'])
                    self._print_alerts(data['alerts'])
                    self._print_footer()
                else:
                    print("No data available yet. Collecting metrics...")
                
                iteration += 1
                
                if iterations is None or iteration < iterations:
                    print(f"\nRefreshing in {refresh_interval}s (Press Ctrl+C to exit)...")
                    time.sleep(refresh_interval)
        
        except KeyboardInterrupt:
            print("\n\nDashboard closed.")
    
    @staticmethod
    def _clear_screen():
        """Clear terminal screen."""
        print("\033[2J\033[H", end="")
    
    @staticmethod
    def _print_header():
        """Print dashboard header."""
        print("╔════════════════════════════════════════════════════════════════════════════╗")
        print("║          HERMES MEMORY ENGINE — HEALTH DASHBOARD                          ║")
        print("║                    Phase 6 & 7: Production Monitoring                     ║")
        print("╚════════════════════════════════════════════════════════════════════════════╝")
        print()
    
    @staticmethod
    def _print_health_score(health: Dict):
        """Print overall health score."""
        overall = health['overall']
        
        # Color coding
        if overall >= 90:
            status = "🟢 EXCELLENT"
            bar = "█" * 18 + "░" * 2
        elif overall >= 70:
            status = "🟡 GOOD"
            bar = "█" * int(overall / 5.5) + "░" * (18 - int(overall / 5.5))
        else:
            status = "🔴 DEGRADED"
            bar = "█" * int(overall / 5.5) + "░" * (18 - int(overall / 5.5))
        
        print(f"  Overall Health: {status}")
        print(f"  [{bar}] {overall:.1f}/100")
        print()
    
    @staticmethod
    def _print_performance(health: Dict):
        """Print performance metrics."""
        print("  PERFORMANCE METRICS")
        print("  ─" * 40)
        
        latency = health['latency_ms']
        throughput = health['throughput_qps']
        sync_health = health['sync_health']
        consensus_quality = health['consensus_quality']
        error_rate = health['error_rate']
        
        # Latency
        if latency < 100:
            latency_status = "✓ EXCELLENT"
        elif latency < 150:
            latency_status = "✓ GOOD"
        elif latency < 250:
            latency_status = "⚠ WARNING"
        else:
            latency_status = "✗ CRITICAL"
        
        print(f"  Latency (avg):  {latency:.2f}ms  {latency_status}")
        print(f"  Throughput:     {throughput:.1f} q/s")
        print(f"  Sync Health:    {sync_health:.1f}/100")
        print(f"  Consensus:      {consensus_quality:.1f}/100")
        print(f"  Error Rate:     {error_rate:.0f} errors")
        print()
    
    @staticmethod
    def _print_agents(agents: Dict):
        """Print per-agent status."""
        print("  AGENT STATUS")
        print("  ─" * 40)
        
        agent_names = {
            'falcon': 'Falcon (Technical)',
            'hermes_agent': 'Hermes (Patterns)',
            'leo': 'LEO (External)'
        }
        
        for agent_id, info in agents.items():
            accuracy = info.get('accuracy', 0)
            authority = info.get('authority', 0)
            
            # Accuracy bar
            bar = "█" * int(accuracy * 10) + "░" * (10 - int(accuracy * 10))
            
            name = agent_names.get(agent_id, agent_id)
            print(f"  {name:20} [{bar}] {accuracy:.2f}")
        
        print()
    
    @staticmethod
    def _print_alerts(alerts: List[Dict]):
        """Print active alerts."""
        print("  ACTIVE ALERTS")
        print("  ─" * 40)
        
        if not alerts:
            print("  ✓ No active alerts")
        else:
            critical = [a for a in alerts if a['severity'] == 'CRITICAL']
            warnings = [a for a in alerts if a['severity'] == 'WARNING']
            
            if critical:
                print(f"  🔴 CRITICAL ({len(critical)}):")
                for alert in critical[:3]:
                    print(f"     • {alert['name']}: {alert['message']}")
            
            if warnings:
                print(f"  🟡 WARNING ({len(warnings)}):")
                for alert in warnings[:3]:
                    print(f"     • {alert['name']}: {alert['message']}")
        
        print()
    
    @staticmethod
    def _print_footer():
        """Print dashboard footer."""
        print("  ─" * 40)
        print(f"  Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  Phase: 6 & 7 (Production Monitoring)")


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Health Dashboard")
    parser.add_argument('--refresh', type=int, default=30,
                        help='Refresh interval in seconds')
    parser.add_argument('--iterations', type=int, default=None,
                        help='Number of iterations (default: infinite)')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    
    args = parser.parse_args()
    
    # Try to import metrics collector & alert system
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from metrics_collector import MetricsCollector
        from alert_system import AlertSystem
        
        collector = MetricsCollector()
        alerter = AlertSystem()
        dashboard = HealthDashboard(
            metrics_collector=collector,
            alert_system=alerter
        )
    except ImportError:
        dashboard = HealthDashboard()
    
    try:
        if args.json:
            data = dashboard.get_json_snapshot()
            print(json.dumps(data, indent=2))
        else:
            dashboard.render_terminal(
                refresh_interval=args.refresh,
                iterations=args.iterations
            )
    
    finally:
        try:
            collector.close()
            alerter.close()
        except:
            pass


if __name__ == '__main__':
    main()
