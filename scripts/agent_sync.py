#!/usr/bin/env python3
"""
Agent Synchronizer — Phase 5

Synchronizes memory across multiple AI agents (Falcon, Katsumi, LEO).

Capabilities:
- Detect new/updated facts from each agent
- Merge changes intelligently
- Resolve conflicts with intelligent fallback
- Track synchronization status
- Audit trail of all syncs

Usage:
    sync = AgentSynchronizer()
    
    # Sync between two agents
    report = sync.sync_agents(['falcon', 'katsumi'])
    
    # Pull updates from agent
    updates = sync.pull_updates('falcon')
    
    # Push consensus facts
    sync.push_updates('katsumi', consensus_facts)
    
    # Get sync status
    status = sync.get_sync_status()
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/agent-sync.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'

# Agent authority weights (used in conflict resolution)
AGENT_AUTHORITY = {
    'falcon': 0.95,    # Technical authority
    'katsumi': 0.90,   # System patterns
    'leo': 0.75        # External validation
}


class AgentSynchronizer:
    """Synchronize memory across agents."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        self.agents = list(AGENT_AUTHORITY.keys())
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def pull_updates(self, agent_id: str) -> List[Dict]:
        """
        Get new/updated facts from an agent.
        
        Args:
            agent_id: Agent to pull from ('falcon', 'katsumi', 'leo')
        
        Returns:
            List of new/updated facts
        """
        cursor = self.conn.cursor()
        
        try:
            # Get last sync time for this agent
            cursor.execute("""
                SELECT last_sync FROM agent_state WHERE agent_id = ?
            """, (agent_id,))
            
            row = cursor.fetchone()
            last_sync = row['last_sync'] if row else None
            
            # Get facts updated since last sync
            if last_sync:
                cursor.execute("""
                    SELECT *
                    FROM memory_facts
                    WHERE agent_id = ? AND updated_at > ?
                    ORDER BY updated_at DESC
                """, (agent_id, last_sync))
            else:
                cursor.execute("""
                    SELECT *
                    FROM memory_facts
                    WHERE agent_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 100
                """, (agent_id,))
            
            updates = [dict(row) for row in cursor.fetchall()]
            logger_obj.info(f"Pulled {len(updates)} updates from {agent_id}")
            return updates
            
        except Exception as e:
            logger_obj.error(f"Failed to pull updates from {agent_id}: {e}")
            return []
    
    def push_updates(
        self,
        agent_id: str,
        facts: List[Dict]
    ) -> Tuple[int, List[str]]:
        """
        Push consensus facts to agent.
        
        Args:
            agent_id: Target agent
            facts: Facts to push
        
        Returns:
            (num_pushed, list_of_errors)
        """
        cursor = self.conn.cursor()
        pushed = 0
        errors = []
        
        try:
            for fact in facts:
                try:
                    cursor.execute("""
                        UPDATE memory_facts
                        SET updated_at = ?,
                            agent_id = CASE WHEN agent_id = 'shared' THEN 'shared' ELSE ? END
                        WHERE id = ?
                    """, (datetime.now().isoformat(), agent_id, fact['id']))
                    
                    if cursor.rowcount > 0:
                        pushed += 1
                except Exception as e:
                    errors.append(f"Fact {fact['id']}: {str(e)}")
            
            self.conn.commit()
            logger_obj.info(f"Pushed {pushed} facts to {agent_id}")
            return pushed, errors
            
        except Exception as e:
            self.conn.rollback()
            logger_obj.error(f"Failed to push updates to {agent_id}: {e}")
            return 0, [str(e)]
    
    def resolve_conflict(
        self,
        fact_a: Dict,
        fact_b: Dict
    ) -> Dict:
        """
        Resolve conflict between two versions of a fact.
        
        Strategy:
        1. Newer timestamp wins
        2. Higher authority agent wins
        3. Higher confidence wins
        4. Manual override flag wins
        
        Args:
            fact_a: First version
            fact_b: Second version
        
        Returns:
            Canonical fact
        """
        # Strategy 1: Newer wins
        time_a = fact_a.get('updated_at') or fact_a.get('created_at', '')
        time_b = fact_b.get('updated_at') or fact_b.get('created_at', '')
        
        if time_a > time_b:
            logger_obj.info(f"Conflict resolved by timestamp (A newer)")
            return fact_a
        elif time_b > time_a:
            logger_obj.info(f"Conflict resolved by timestamp (B newer)")
            return fact_b
        
        # Strategy 2: Agent authority
        agent_a = fact_a.get('agent_id', 'shared')
        agent_b = fact_b.get('agent_id', 'shared')
        
        auth_a = AGENT_AUTHORITY.get(agent_a, 0.5)
        auth_b = AGENT_AUTHORITY.get(agent_b, 0.5)
        
        if auth_a > auth_b:
            logger_obj.info(f"Conflict resolved by authority ({agent_a} > {agent_b})")
            return fact_a
        elif auth_b > auth_a:
            logger_obj.info(f"Conflict resolved by authority ({agent_b} > {agent_a})")
            return fact_b
        
        # Strategy 3: Confidence
        conf_a = fact_a.get('confidence', 0.5)
        conf_b = fact_b.get('confidence', 0.5)
        
        if conf_a > conf_b:
            logger_obj.info(f"Conflict resolved by confidence (A={conf_a} > B={conf_b})")
            return fact_a
        else:
            logger_obj.info(f"Conflict resolved by confidence (B={conf_b} >= A={conf_a})")
            return fact_b
    
    def sync_agents(self, agents: List[str] = None) -> Dict:
        """
        Synchronize facts across multiple agents.
        
        Process:
        1. Pull updates from all agents
        2. Identify conflicts
        3. Resolve via consensus rules
        4. Push canonical versions back
        
        Args:
            agents: List of agent IDs (default: all)
        
        Returns:
            Sync report
        """
        agents = agents or self.agents
        logger_obj.info(f"Starting sync for agents: {agents}")
        
        cursor = self.conn.cursor()
        report = {
            'agents': agents,
            'facts_pulled': 0,
            'conflicts_detected': 0,
            'conflicts_resolved': 0,
            'facts_pushed': 0,
            'timestamp': datetime.now().isoformat(),
            'status': 'complete'
        }
        
        try:
            # Pull updates from all agents
            all_updates = {}
            for agent in agents:
                updates = self.pull_updates(agent)
                all_updates[agent] = updates
                report['facts_pulled'] += len(updates)
            
            # Find duplicates/conflicts
            fact_by_id = defaultdict(list)
            for agent, facts in all_updates.items():
                for fact in facts:
                    fact_by_id[fact['id']].append((agent, fact))
            
            # Resolve conflicts
            canonical_facts = {}
            for fact_id, versions in fact_by_id.items():
                if len(versions) == 1:
                    # No conflict
                    canonical_facts[fact_id] = versions[0][1]
                else:
                    # Conflict detected
                    report['conflicts_detected'] += 1
                    
                    # Resolve iteratively
                    canonical = versions[0][1]
                    for agent, fact in versions[1:]:
                        canonical = self.resolve_conflict(canonical, fact)
                    
                    canonical_facts[fact_id] = canonical
                    report['conflicts_resolved'] += 1
            
            # Push canonical versions to shared storage
            for fact in canonical_facts.values():
                cursor.execute("""
                    UPDATE memory_facts
                    SET agent_id = 'shared',
                        updated_at = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), fact['id']))
                report['facts_pushed'] += 1
            
            self.conn.commit()
            
            # Update agent state
            for agent in agents:
                cursor.execute("""
                    INSERT OR REPLACE INTO agent_state
                    (agent_id, last_sync, sync_status)
                    VALUES (?, ?, 'synced')
                """, (agent, datetime.now().isoformat()))
            
            self.conn.commit()
            
            logger_obj.info(f"Sync complete: {report}")
            return report
            
        except Exception as e:
            self.conn.rollback()
            logger_obj.error(f"Sync failed: {e}")
            report['status'] = 'failed'
            report['error'] = str(e)
            return report
    
    def get_sync_status(self) -> Dict:
        """Get current synchronization status."""
        cursor = self.conn.cursor()
        
        try:
            status = {}
            for agent in self.agents:
                cursor.execute("""
                    SELECT last_sync, fact_count, sync_status
                    FROM agent_state
                    WHERE agent_id = ?
                """, (agent,))
                
                row = cursor.fetchone()
                if row:
                    status[agent] = {
                        'last_sync': row['last_sync'],
                        'fact_count': row['fact_count'],
                        'status': row['sync_status']
                    }
                else:
                    status[agent] = {
                        'last_sync': None,
                        'fact_count': 0,
                        'status': 'never_synced'
                    }
            
            return {
                'agents': status,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get sync status: {e}")
            return {}
    
    def get_sync_history(self, limit: int = 10) -> List[Dict]:
        """Get recent sync events."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT *
                FROM agent_sync_log
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            history = [dict(row) for row in cursor.fetchall()]
            logger_obj.info(f"Retrieved {len(history)} sync events")
            return history
            
        except Exception as e:
            logger_obj.error(f"Failed to get sync history: {e}")
            return []


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Agent Synchronizer")
    parser.add_argument('--sync', nargs='*', metavar='AGENT',
                        help='Sync agents (default: all)')
    parser.add_argument('--status', action='store_true',
                        help='Get sync status')
    parser.add_argument('--history', type=int, default=10,
                        help='Show sync history')
    parser.add_argument('--pull', metavar='AGENT',
                        help='Pull updates from agent')
    
    args = parser.parse_args()
    
    sync = AgentSynchronizer()
    
    try:
        if args.sync is not None:
            agents = args.sync if args.sync else None
            report = sync.sync_agents(agents)
            print(f"\n✓ Sync Report:")
            for key, val in report.items():
                print(f"  {key}: {val}")
        
        elif args.status:
            status = sync.get_sync_status()
            print(f"\n✓ Sync Status:")
            for agent, info in status.get('agents', {}).items():
                print(f"  {agent}:")
                for k, v in info.items():
                    print(f"    {k}: {v}")
        
        elif args.history:
            history = sync.get_sync_history(args.history)
            print(f"\n✓ Sync History ({len(history)} events):")
            for event in history:
                print(f"  {event['timestamp']}: {event['agent_id_from']} → {event['agent_id_to']}")
        
        elif args.pull:
            updates = sync.pull_updates(args.pull)
            print(f"\n✓ Updates from {args.pull} ({len(updates)} facts):")
            for fact in updates[:5]:
                print(f"  • {fact['id']}: {fact['content'][:60]}...")
    
    finally:
        sync.close()


if __name__ == '__main__':
    main()
