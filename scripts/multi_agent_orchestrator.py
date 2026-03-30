#!/usr/bin/env python3
"""
Multi-Agent Orchestrator — Phase 5

Central coordinator for Phase 5 multi-agent coherence system.

Orchestrates:
- Agent synchronization (pull/push updates)
- Consensus voting on facts
- Cross-agent inference (unified queries)
- Coherence validation (detect/repair)
- Performance monitoring

Architecture:
    User Query
        ↓
    Orchestrator
        ├→ Agent Sync (sync across agents)
        ├→ Consensus Engine (vote on facts)
        ├→ Cross-Agent Inference (query all)
        ├→ Coherence Validator (check consistency)
        └→ Unified Response (synthesized answer)

Usage:
    orchestrator = MultiAgentOrchestrator()
    
    # Unified query with all systems
    response = orchestrator.process_query("What is the memory system?")
    
    # Background maintenance
    orchestrator.maintain()
    
    # Health check
    health = orchestrator.get_health()
    
    # Get status
    status = orchestrator.get_status()
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import time
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/orchestrator.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'

# Import Phase 5 modules
import sys
script_dir = Path.home() / '.hermes/memory-engine/scripts'
sys.path.insert(0, str(script_dir))

try:
    from agent_sync import AgentSynchronizer
    from consensus_engine import ConsensusEngine
    from cross_agent_inference import CrossAgentInferencer
    from coherence_validator import CoherenceValidator
except ImportError as e:
    logger_obj.warning(f"Could not import Phase 5 modules: {e}")


@dataclass
class OrchestratorStatus:
    """Status of orchestrator."""
    timestamp: str
    agents_synced: List[str]
    consensus_facts: int
    coherence_health: float  # 0-100
    last_sync: str
    last_inference: str
    performance_ms: float


class MultiAgentOrchestrator:
    """Coordinates all Phase 5 systems."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        
        # Initialize Phase 5 components
        self.synchronizer = AgentSynchronizer(db_path)
        self.voter = ConsensusEngine(db_path)
        self.inferencer = CrossAgentInferencer(db_path)
        self.validator = CoherenceValidator(db_path)
        
        self.agents = ['falcon', 'hermes_agent', 'leo']
        self.status = {
            'last_sync': None,
            'last_inference': None,
            'last_validation': None
        }
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info("Orchestrator connected")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def close(self):
        """Close connections."""
        if self.conn:
            self.conn.close()
        self.synchronizer.close()
        self.voter.close()
        self.inferencer.close()
        self.validator.close()
    
    def process_query(self, query: str) -> Dict:
        """
        Process user query through full Phase 5 pipeline.
        
        Steps:
        1. Synchronize agents
        2. Query all agents
        3. Vote on results
        4. Validate coherence
        5. Synthesize answer
        
        Args:
            query: User query
        
        Returns:
            Comprehensive response
        """
        start = time.time()
        logger_obj.info(f"Processing query: {query}")
        
        response = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'pipeline': {}
        }
        
        try:
            # Step 1: Synchronize agents
            logger_obj.info("Step 1: Synchronizing agents...")
            sync_report = self.synchronizer.sync_agents(self.agents)
            response['pipeline']['sync'] = {
                'status': sync_report['status'],
                'facts_synced': sync_report['facts_pushed'],
                'conflicts_resolved': sync_report['conflicts_resolved']
            }
            self.status['last_sync'] = datetime.now().isoformat()
            
            # Step 2: Cross-agent inference
            logger_obj.info("Step 2: Running cross-agent inference...")
            inference = self.inferencer.query(query)
            inference_dict = self.inferencer.to_dict(inference)
            response['pipeline']['inference'] = {
                'confidence': inference_dict['confidence'],
                'agents_queried': len(inference_dict['agent_results']),
                'results_combined': len(inference_dict['combined_ranking']),
                'sources': inference_dict['sources']
            }
            response['unified_answer'] = inference_dict['unified_answer']
            self.status['last_inference'] = datetime.now().isoformat()
            
            # Step 3: Consensus voting
            logger_obj.info("Step 3: Running consensus voting...")
            consensus_count = 0
            disputed_count = 0
            
            # Get disputed facts and vote on them
            disputed = self.voter.get_disputed_facts(threshold=0.70)
            for fact in disputed:
                consensus = self.voter.calculate_consensus(fact['fact_id'])
                consensus_count += 1
            
            response['pipeline']['consensus'] = {
                'voted_facts': consensus_count,
                'disputed_facts': len(disputed),
                'consensus_quality': f"Good" if len(disputed) < 5 else f"Needs review"
            }
            
            # Step 4: Coherence validation
            logger_obj.info("Step 4: Validating coherence...")
            validation_report = self.validator.validate_all()
            response['pipeline']['coherence'] = {
                'health_score': validation_report['health_score'],
                'violations': validation_report['total_violations'],
                'critical': validation_report['violations_by_severity'].get('critical', 0)
            }
            self.status['last_validation'] = datetime.now().isoformat()
            
            # Auto-repair if violations found
            if validation_report['total_violations'] > 0:
                logger_obj.info("Auto-repairing violations...")
                repair_report = self.validator.auto_repair()
                response['pipeline']['coherence']['repairs_attempted'] = repair_report.get('repaired', 0)
            
            elapsed = time.time() - start
            response['performance_ms'] = round(elapsed * 1000, 2)
            response['status'] = 'complete'
            
            logger_obj.info(f"Query processed: {elapsed*1000:.2f}ms")
            
        except Exception as e:
            logger_obj.error(f"Pipeline error: {e}")
            response['status'] = 'error'
            response['error'] = str(e)
        
        return response
    
    def maintain(self) -> Dict:
        """
        Run background maintenance.
        
        Tasks:
        - Sync agents
        - Validate coherence
        - Auto-repair violations
        - Cleanup old entries
        
        Returns:
            Maintenance report
        """
        logger_obj.info("Starting background maintenance...")
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'sync': None,
            'validation': None,
            'cleanup': None
        }
        
        try:
            # Sync all agents
            logger_obj.info("Syncing agents...")
            sync_result = self.synchronizer.sync_agents(self.agents)
            report['sync'] = {
                'status': sync_result['status'],
                'facts_synced': sync_result['facts_pushed'],
                'conflicts': sync_result['conflicts_resolved']
            }
            
            # Validate coherence
            logger_obj.info("Validating coherence...")
            validation = self.validator.validate_all()
            report['validation'] = {
                'health_score': validation['health_score'],
                'violations': validation['total_violations']
            }
            
            # Auto-repair if needed
            if validation['total_violations'] > 0:
                logger_obj.info("Auto-repairing...")
                repair = self.validator.auto_repair()
                report['validation']['repairs'] = repair.get('repaired', 0)
            
            # Cleanup old sync logs (keep last 100)
            cursor = self.conn.cursor()
            cursor.execute("""
                DELETE FROM agent_sync_log
                WHERE timestamp < (
                    SELECT timestamp FROM agent_sync_log
                    ORDER BY timestamp DESC
                    LIMIT 1 OFFSET 100
                )
            """)
            
            self.conn.commit()
            report['cleanup'] = {
                'old_logs_removed': cursor.rowcount
            }
            
            logger_obj.info("Maintenance complete")
            report['status'] = 'complete'
            
        except Exception as e:
            logger_obj.error(f"Maintenance failed: {e}")
            report['status'] = 'failed'
            report['error'] = str(e)
        
        return report
    
    def get_health(self) -> Dict:
        """Get system health status."""
        try:
            # Coherence health
            validation = self.validator.validate_all()
            coherence_health = validation['health_score']
            
            # Sync health
            sync_status = self.synchronizer.get_sync_status()
            synced_agents = sum(
                1 for s in sync_status.get('agents', {}).values()
                if s.get('status') == 'synced'
            )
            sync_health = (synced_agents / 3) * 100 if synced_agents else 0
            
            # Consensus health
            disputed = self.voter.get_disputed_facts(threshold=0.70)
            consensus_health = max(0, 100 - (len(disputed) * 10))
            
            # Overall health
            overall = (coherence_health + sync_health + consensus_health) / 3
            
            return {
                'overall': round(overall, 1),
                'coherence': round(coherence_health, 1),
                'sync': round(sync_health, 1),
                'consensus': round(consensus_health, 1),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get health: {e}")
            return {'error': str(e)}
    
    def get_status(self) -> Dict:
        """Get complete orchestrator status."""
        try:
            health = self.get_health()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'health': health,
                'last_operations': {
                    'sync': self.status['last_sync'],
                    'inference': self.status['last_inference'],
                    'validation': self.status['last_validation']
                },
                'agents': self.agents,
                'phase': 5,
                'status': 'operational'
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get status: {e}")
            return {'error': str(e)}
    
    def get_performance_metrics(self) -> Dict:
        """Get performance metrics."""
        cursor = self.conn.cursor()
        
        try:
            # Query latencies from logs
            cursor.execute("""
                SELECT agent_id, AVG(search_time_ms) as avg_latency
                FROM agent_performance_log
                WHERE timestamp > datetime('now', '-1 hour')
                GROUP BY agent_id
            """)
            
            agent_latencies = {row['agent_id']: row['avg_latency'] for row in cursor.fetchall()}
            
            return {
                'timestamp': datetime.now().isoformat(),
                'agent_latencies_ms': agent_latencies,
                'target_latency': 200,
                'status': 'operational'
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get metrics: {e}")
            return {'error': str(e)}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-Agent Orchestrator")
    parser.add_argument('--query', metavar='QUERY',
                        help='Process a query')
    parser.add_argument('--maintain', action='store_true',
                        help='Run background maintenance')
    parser.add_argument('--health', action='store_true',
                        help='Check system health')
    parser.add_argument('--status', action='store_true',
                        help='Get full status')
    parser.add_argument('--metrics', action='store_true',
                        help='Show performance metrics')
    
    args = parser.parse_args()
    
    orchestrator = MultiAgentOrchestrator()
    
    try:
        if args.query:
            result = orchestrator.process_query(args.query)
            print(f"\n✓ Query Response:")
            print(f"  Status: {result['status']}")
            print(f"  Performance: {result.get('performance_ms', 'N/A')}ms")
            print(f"\n✓ Answer:")
            print(f"  {result.get('unified_answer', 'No answer')}")
            print(f"\n✓ Pipeline Results:")
            for stage, info in result.get('pipeline', {}).items():
                print(f"  {stage}: {info}")
        
        elif args.maintain:
            report = orchestrator.maintain()
            print(f"\n✓ Maintenance Report:")
            for key, val in report.items():
                print(f"  {key}: {val}")
        
        elif args.health:
            health = orchestrator.get_health()
            print(f"\n✓ System Health:")
            print(f"  Overall: {health.get('overall', 'N/A')}/100")
            print(f"  Coherence: {health.get('coherence', 'N/A')}/100")
            print(f"  Sync: {health.get('sync', 'N/A')}/100")
            print(f"  Consensus: {health.get('consensus', 'N/A')}/100")
        
        elif args.status:
            status = orchestrator.get_status()
            print(f"\n✓ Orchestrator Status:")
            print(f"  Phase: {status.get('phase')}")
            print(f"  Status: {status.get('status')}")
            print(f"  Agents: {', '.join(status.get('agents', []))}")
            print(f"\n✓ Health: {status.get('health')}")
        
        elif args.metrics:
            metrics = orchestrator.get_performance_metrics()
            print(f"\n✓ Performance Metrics:")
            for agent, latency in metrics.get('agent_latencies_ms', {}).items():
                print(f"  {agent}: {latency:.2f}ms")
        
        else:
            parser.print_help()
    
    finally:
        orchestrator.close()


if __name__ == '__main__':
    main()
