#!/usr/bin/env python3
"""
Adaptive Agent Synchronizer — Phase 5 Enhanced

Synchronizes memory across ANY number of configured agents dynamically.

Key Improvements:
✓ Zero hard-coded agent lists
✓ Dynamic agent discovery from config
✓ Scales from 1 to N agents
✓ Configurable authority weights per deployment
✓ Auto-detects new/removed agents
✓ Works with any agent naming convention

Default Config (easily customizable):
  {
    "agents": {
      "falcon": {"authority": 0.95, "role": "technical"},
      "katsumi": {"authority": 0.90, "role": "patterns"},
      "leo": {"authority": 0.75, "role": "external"}
    }
  }

But works with ANY agent count:
  - 1 agent: Solo mode
  - 2 agents: Dual consensus
  - 3+ agents: Multi-agent federation
  - N agents: Unlimited scaling

Usage:
    sync = AdaptiveAgentSynchronizer()
    
    # Auto-detect agents from config
    sync.discover_agents()
    
    # Sync all configured agents
    report = sync.sync_all()
    
    # Add new agent dynamically
    sync.register_agent('nova', authority=0.88, role='optimization')
    
    # Get available agents
    agents = sync.get_configured_agents()
    
    # Sync specific subset
    report = sync.sync_agents(['falcon', 'katsumi'])
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
from collections import defaultdict

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
CONFIG_PATH = Path.home() / '.hermes/memory-engine/config/agents.json'


# DEFAULT AGENT CONFIGURATION
DEFAULT_AGENTS = {
    "falcon": {
        "authority": 0.95,
        "role": "technical",
        "description": "Technical implementation expert"
    },
    "katsumi": {
        "authority": 0.90,
        "role": "patterns",
        "description": "Pattern recognition & temporal context"
    },
    "leo": {
        "authority": 0.75,
        "role": "external",
        "description": "External validation & outreach"
    }
}


class AdaptiveAgentSynchronizer:
    """Synchronize memory across dynamically configured agents."""
    
    def __init__(self, db_path: Path = None, config_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.config_path = config_path or CONFIG_PATH
        self.conn = None
        self._connect()
        
        # Agent configuration (loaded from config or defaults)
        self.agent_config: Dict[str, Dict] = {}
        self.agents: List[str] = []
        self.authority_weights: Dict[str, float] = {}
        
        # Load configuration
        self._load_agent_config()
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def _load_agent_config(self):
        """Load agent configuration from file or use defaults."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    self.agent_config = config.get('agents', DEFAULT_AGENTS)
                logger_obj.info(f"Loaded {len(self.agent_config)} agents from config")
            else:
                logger_obj.info("No config file found, using defaults")
                self.agent_config = DEFAULT_AGENTS
                self._save_agent_config()
        
        except Exception as e:
            logger_obj.warning(f"Failed to load config: {e}, using defaults")
            self.agent_config = DEFAULT_AGENTS
        
        # Extract agent list and authority weights
        self.agents = list(self.agent_config.keys())
        self.authority_weights = {
            agent: config.get('authority', 0.5)
            for agent, config in self.agent_config.items()
        }
        
        logger_obj.info(f"Configured agents: {self.agents}")
    
    def _save_agent_config(self):
        """Save current agent configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            config = {
                "timestamp": datetime.now().isoformat(),
                "agents": self.agent_config
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger_obj.info(f"Saved agent config to {self.config_path}")
        
        except Exception as e:
            logger_obj.error(f"Failed to save config: {e}")
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def register_agent(
        self,
        agent_id: str,
        authority: float = 0.5,
        role: str = "generic",
        description: str = None
    ) -> bool:
        """
        Register a new agent dynamically.
        
        Args:
            agent_id: Unique agent identifier
            authority: Authority weight (0.0-1.0)
            role: Agent role/specialization
            description: Optional description
        
        Returns:
            True if registered successfully
        """
        if agent_id in self.agents:
            logger_obj.warning(f"Agent {agent_id} already registered")
            return False
        
        if not (0.0 <= authority <= 1.0):
            logger_obj.error(f"Invalid authority: {authority}")
            return False
        
        # Add to configuration
        self.agent_config[agent_id] = {
            "authority": authority,
            "role": role,
            "description": description or f"Agent {agent_id}"
        }
        
        self.agents.append(agent_id)
        self.authority_weights[agent_id] = authority
        
        # Initialize agent state
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO agent_state
                (agent_id, last_sync, fact_count, sync_status)
                VALUES (?, NULL, 0, 'initialized')
            """, (agent_id,))
            self.conn.commit()
        except Exception as e:
            logger_obj.error(f"Failed to initialize agent state: {e}")
            return False
        
        # Save configuration
        self._save_agent_config()
        
        logger_obj.info(f"Registered agent: {agent_id} (authority={authority}, role={role})")
        return True
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from configuration."""
        if agent_id not in self.agents:
            logger_obj.warning(f"Agent {agent_id} not found")
            return False
        
        # Remove from configuration
        del self.agent_config[agent_id]
        self.agents.remove(agent_id)
        del self.authority_weights[agent_id]
        
        # Save configuration
        self._save_agent_config()
        
        logger_obj.info(f"Unregistered agent: {agent_id}")
        return True
    
    def get_configured_agents(self) -> List[Dict]:
        """Get list of configured agents with details."""
        return [
            {
                'agent_id': agent_id,
                **self.agent_config[agent_id]
            }
            for agent_id in self.agents
        ]
    
    def discover_agents(self) -> List[str]:
        """
        Auto-discover agents from database.
        
        Finds all agents with facts and registers them if unknown.
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT DISTINCT agent_id FROM memory_facts
                WHERE agent_id NOT IN ('shared', 'system')
            """)
            
            discovered = set(row['agent_id'] for row in cursor.fetchall())
            existing = set(self.agents)
            
            new_agents = discovered - existing
            if new_agents:
                logger_obj.info(f"Discovered new agents: {new_agents}")
                for agent_id in new_agents:
                    # Register with default authority
                    self.register_agent(agent_id, authority=0.5, role='discovered')
            
            return list(discovered)
        
        except Exception as e:
            logger_obj.error(f"Failed to discover agents: {e}")
            return self.agents
    
    def pull_updates(self, agent_id: str) -> List[Dict]:
        """Get new/updated facts from an agent."""
        if agent_id not in self.agents:
            logger_obj.warning(f"Agent {agent_id} not configured")
            return []
        
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
        """Push consensus facts to agent."""
        if agent_id not in self.agents:
            logger_obj.warning(f"Agent {agent_id} not configured")
            return 0, [f"Agent {agent_id} not found"]
        
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
        
        Uses authority weights from configuration.
        """
        # Strategy 1: Newer timestamp wins
        time_a = fact_a.get('updated_at') or fact_a.get('created_at', '')
        time_b = fact_b.get('updated_at') or fact_b.get('created_at', '')
        
        if time_a > time_b:
            return fact_a
        elif time_b > time_a:
            return fact_b
        
        # Strategy 2: Agent authority (from config)
        agent_a = fact_a.get('agent_id', 'shared')
        agent_b = fact_b.get('agent_id', 'shared')
        
        auth_a = self.authority_weights.get(agent_a, 0.5)
        auth_b = self.authority_weights.get(agent_b, 0.5)
        
        if auth_a > auth_b:
            logger_obj.info(f"Conflict resolved by authority ({agent_a}={auth_a} > {agent_b}={auth_b})")
            return fact_a
        elif auth_b > auth_a:
            logger_obj.info(f"Conflict resolved by authority ({agent_b}={auth_b} > {agent_a}={auth_a})")
            return fact_b
        
        # Strategy 3: Confidence
        conf_a = fact_a.get('confidence', 0.5)
        conf_b = fact_b.get('confidence', 0.5)
        
        if conf_a > conf_b:
            return fact_a
        else:
            return fact_b
    
    def sync_all(self) -> Dict:
        """Synchronize all configured agents."""
        return self.sync_agents(self.agents)
    
    def sync_agents(self, agents: List[str] = None) -> Dict:
        """
        Synchronize facts across agents.
        
        Args:
            agents: List of agent IDs to sync (default: all configured)
        
        Returns:
            Sync report
        """
        agents = agents or self.agents
        
        # Validate agents
        invalid = set(agents) - set(self.agents)
        if invalid:
            logger_obj.warning(f"Skipping invalid agents: {invalid}")
            agents = [a for a in agents if a in self.agents]
        
        if not agents:
            logger_obj.warning("No valid agents to sync")
            return {'status': 'no_agents', 'agents_synced': 0}
        
        logger_obj.info(f"Starting sync for {len(agents)} agents: {agents}")
        
        cursor = self.conn.cursor()
        report = {
            'timestamp': datetime.now().isoformat(),
            'agents': agents,
            'agent_count': len(agents),
            'facts_pulled': 0,
            'conflicts_detected': 0,
            'conflicts_resolved': 0,
            'facts_pushed': 0,
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
        """Get current synchronization status for all agents."""
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
                        'status': row['sync_status'],
                        'authority': self.authority_weights.get(agent, 0.5)
                    }
                else:
                    status[agent] = {
                        'last_sync': None,
                        'fact_count': 0,
                        'status': 'never_synced',
                        'authority': self.authority_weights.get(agent, 0.5)
                    }
            
            return {
                'agents': status,
                'agent_count': len(self.agents),
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger_obj.error(f"Failed to get sync status: {e}")
            return {}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Adaptive Agent Synchronizer")
    parser.add_argument('--sync-all', action='store_true',
                        help='Sync all configured agents')
    parser.add_argument('--sync', nargs='*', metavar='AGENT',
                        help='Sync specific agents')
    parser.add_argument('--status', action='store_true',
                        help='Get sync status')
    parser.add_argument('--agents', action='store_true',
                        help='List configured agents')
    parser.add_argument('--discover', action='store_true',
                        help='Discover agents from database')
    parser.add_argument('--register', nargs=2, metavar=('AGENT_ID', 'AUTHORITY'),
                        help='Register new agent')
    
    args = parser.parse_args()
    
    sync = AdaptiveAgentSynchronizer()
    
    try:
        if args.sync_all:
            report = sync.sync_all()
            print(f"\n✓ Sync All Agents ({len(sync.agents)} agents):")
            for key, val in report.items():
                print(f"  {key}: {val}")
        
        elif args.sync is not None:
            agents = args.sync if args.sync else sync.agents
            report = sync.sync_agents(agents)
            print(f"\n✓ Sync Report:")
            for key, val in report.items():
                print(f"  {key}: {val}")
        
        elif args.status:
            status = sync.get_sync_status()
            print(f"\n✓ Sync Status ({status['agent_count']} agents):")
            for agent, info in status.get('agents', {}).items():
                print(f"  {agent}: {info}")
        
        elif args.agents:
            agents = sync.get_configured_agents()
            print(f"\n✓ Configured Agents ({len(agents)}):")
            for agent in agents:
                print(f"  • {agent['agent_id']}: {agent['role']} (authority={agent['authority']})")
                print(f"    {agent['description']}")
        
        elif args.discover:
            discovered = sync.discover_agents()
            print(f"\n✓ Discovered {len(discovered)} agents:")
            for agent in discovered:
                print(f"  • {agent}")
        
        elif args.register:
            agent_id, authority = args.register
            result = sync.register_agent(agent_id, float(authority))
            print(f"\n✓ Agent registration: {'success' if result else 'failed'}")
        
        else:
            parser.print_help()
    
    finally:
        sync.close()


if __name__ == '__main__':
    main()
