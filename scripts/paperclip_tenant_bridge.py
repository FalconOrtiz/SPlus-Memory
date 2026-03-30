#!/usr/bin/env python3
"""
Paperclip Multi-Tenant Memory Bridge — Phase 9

Integración del Memory Engine con Paperclip control plane.

Propósito:
- Aislar memoria por company_id (Paperclip tenant)
- Sincronizar agentes (Falcon > Katsumi > LEO > NOVA/ARIA)
- Gestionar presupuesto de tokens por agent
- Coordinar contexto entre agentes de la misma company

Arquitectura:
    Paperclip API (companies/agents/tasks/costs)
         ↓
    TenantMemoryBridge
         ↓
    MemoryEngine (company-scoped facts)
         ↓
    Agent Context (isolated by company)

Flujo:
1. Board crea company en Paperclip
2. Bridge registra company en memory-engine
3. Agentes hacen requests → Bridge fetch contexto scoped
4. Contexto se pasa a agent, retorna costs
5. Bridge registra costs en Paperclip + memory

Ejemplo:
    # Crear tenant
    bridge = TenantMemoryBridge(api_base="http://localhost:3100")
    bridge.register_company("iredigital-001", "IRE Digital")
    
    # Consultar contexto para un agente
    context = bridge.get_agent_context("agent-uuid", query="campaign strategy")
    
    # Registrar cost después de ejecución
    bridge.record_agent_cost("agent-uuid", tokens_used=2500, cost_cents=150)
"""

import sqlite3
import logging
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import hashlib
import uuid

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/tenant-bridge.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


@dataclass
class TenantConfig:
    """Configuration for a tenant (company)."""
    company_id: str
    company_name: str
    api_key: Optional[str]
    memory_budget_tokens: int
    sync_interval_seconds: int
    created_at: str
    archived: bool = False


@dataclass
class AgentMetadata:
    """Agent registered in tenant."""
    agent_id: str
    agent_name: str
    role: str
    company_id: str
    status: str
    budget_monthly_cents: int
    spent_monthly_cents: int
    context_mode: str  # thin | fat
    last_heartbeat: Optional[str]


@dataclass
class ContextPayload:
    """Context prepared for agent."""
    agent_id: str
    timestamp: str
    facts: List[Dict]
    total_tokens: int
    source_mode: str  # surface_only | hybrid | retriever_only
    metadata: Dict


class TenantMemoryBridge:
    """Bridge between Paperclip and Memory Engine."""
    
    def __init__(
        self,
        api_base: str = "http://localhost:3100",
        memory_db_path: Path = None
    ):
        self.api_base = api_base.rstrip('/')
        self.memory_db_path = memory_db_path or DB_PATH
        self.conn = None
        self._connect()
        self._ensure_tenant_tables()
    
    def _connect(self):
        """Connect to memory database."""
        try:
            self.conn = sqlite3.connect(str(self.memory_db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info(f"TenantBridge connected to {self.memory_db_path}")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def _ensure_tenant_tables(self):
        """Create tenant-specific tables."""
        cursor = self.conn.cursor()
        
        # Company tenants
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenant_companies (
                id INTEGER PRIMARY KEY,
                company_id TEXT UNIQUE NOT NULL,
                company_name TEXT NOT NULL,
                api_key TEXT,
                memory_budget_tokens INTEGER DEFAULT 10000,
                sync_interval_seconds INTEGER DEFAULT 3600,
                created_at TEXT NOT NULL,
                archived BOOLEAN DEFAULT 0
            )
        """)
        
        # Registered agents per tenant
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenant_agents (
                id INTEGER PRIMARY KEY,
                agent_id TEXT UNIQUE NOT NULL,
                agent_name TEXT NOT NULL,
                role TEXT NOT NULL,
                company_id TEXT NOT NULL,
                status TEXT,
                budget_monthly_cents INTEGER,
                spent_monthly_cents INTEGER,
                context_mode TEXT DEFAULT 'thin',
                last_heartbeat TEXT,
                registered_at TEXT NOT NULL,
                FOREIGN KEY(company_id) REFERENCES tenant_companies(company_id),
                UNIQUE(company_id, agent_id)
            )
        """)
        
        # Cost events per agent
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenant_cost_events (
                id INTEGER PRIMARY KEY,
                agent_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                tokens_used INTEGER,
                cost_cents INTEGER,
                model TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES tenant_agents(agent_id),
                FOREIGN KEY(company_id) REFERENCES tenant_companies(company_id)
            )
        """)
        
        # Context delivery log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenant_context_deliveries (
                id INTEGER PRIMARY KEY,
                agent_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                query TEXT,
                facts_count INTEGER,
                tokens_used INTEGER,
                source_mode TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES tenant_agents(agent_id),
                FOREIGN KEY(company_id) REFERENCES tenant_companies(company_id)
            )
        """)
        
        # Sync state (for heartbeat coordination)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenant_sync_state (
                id INTEGER PRIMARY KEY,
                company_id TEXT UNIQUE NOT NULL,
                last_sync_at TEXT,
                agents_count INTEGER DEFAULT 0,
                facts_count INTEGER DEFAULT 0,
                total_costs_cents INTEGER DEFAULT 0,
                FOREIGN KEY(company_id) REFERENCES tenant_companies(company_id)
            )
        """)
        
        self.conn.commit()
        logger_obj.info("Tenant tables ensured")
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    # ─────────────────────────────────────────────────────────────────
    # Company (Tenant) Management
    # ─────────────────────────────────────────────────────────────────
    
    def register_company(
        self,
        company_id: str,
        company_name: str,
        api_key: Optional[str] = None,
        memory_budget_tokens: int = 10000,
        sync_interval_seconds: int = 3600
    ) -> bool:
        """
        Register a company as a tenant.
        
        Args:
            company_id: Paperclip company UUID
            company_name: Display name
            api_key: Optional API key for auth
            memory_budget_tokens: Token budget for this tenant's context
            sync_interval_seconds: How often to sync with Paperclip
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO tenant_companies
                (company_id, company_name, api_key, memory_budget_tokens,
                 sync_interval_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id, company_name, api_key,
                memory_budget_tokens, sync_interval_seconds,
                datetime.now().isoformat()
            ))
            
            # Initialize sync state
            cursor.execute("""
                INSERT OR IGNORE INTO tenant_sync_state
                (company_id, last_sync_at)
                VALUES (?, ?)
            """, (company_id, datetime.now().isoformat()))
            
            self.conn.commit()
            logger_obj.info(f"Registered company: {company_id} ({company_name})")
            return True
        
        except Exception as e:
            logger_obj.error(f"Failed to register company: {e}")
            return False
    
    def get_company(self, company_id: str) -> Optional[TenantConfig]:
        """Get company configuration."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tenant_companies WHERE company_id = ?", (company_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return TenantConfig(
            company_id=row['company_id'],
            company_name=row['company_name'],
            api_key=row['api_key'],
            memory_budget_tokens=row['memory_budget_tokens'],
            sync_interval_seconds=row['sync_interval_seconds'],
            created_at=row['created_at'],
            archived=bool(row['archived'])
        )
    
    def list_companies(self, archived: bool = False) -> List[TenantConfig]:
        """List all companies."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tenant_companies WHERE archived = ? ORDER BY created_at DESC",
            (1 if archived else 0,)
        )
        
        return [TenantConfig(
            company_id=row['company_id'],
            company_name=row['company_name'],
            api_key=row['api_key'],
            memory_budget_tokens=row['memory_budget_tokens'],
            sync_interval_seconds=row['sync_interval_seconds'],
            created_at=row['created_at'],
            archived=bool(row['archived'])
        ) for row in cursor.fetchall()]
    
    # ─────────────────────────────────────────────────────────────────
    # Agent Management
    # ─────────────────────────────────────────────────────────────────
    
    def register_agent(
        self,
        agent_id: str,
        agent_name: str,
        role: str,
        company_id: str,
        status: str = "active",
        budget_monthly_cents: int = 0,
        context_mode: str = "thin"
    ) -> bool:
        """Register an agent in the tenant."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO tenant_agents
                (agent_id, agent_name, role, company_id, status,
                 budget_monthly_cents, context_mode, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agent_id, agent_name, role, company_id, status,
                budget_monthly_cents, context_mode,
                datetime.now().isoformat()
            ))
            
            self.conn.commit()
            logger_obj.info(f"Registered agent: {agent_name} in {company_id}")
            return True
        
        except Exception as e:
            logger_obj.error(f"Failed to register agent: {e}")
            return False
    
    def get_agent(self, agent_id: str) -> Optional[AgentMetadata]:
        """Get agent metadata."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tenant_agents WHERE agent_id = ?", (agent_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return AgentMetadata(
            agent_id=row['agent_id'],
            agent_name=row['agent_name'],
            role=row['role'],
            company_id=row['company_id'],
            status=row['status'],
            budget_monthly_cents=row['budget_monthly_cents'],
            spent_monthly_cents=row['spent_monthly_cents'],
            context_mode=row['context_mode'],
            last_heartbeat=row['last_heartbeat']
        )
    
    def list_company_agents(self, company_id: str) -> List[AgentMetadata]:
        """List all agents in a company."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tenant_agents WHERE company_id = ? ORDER BY role",
            (company_id,)
        )
        
        return [AgentMetadata(
            agent_id=row['agent_id'],
            agent_name=row['agent_name'],
            role=row['role'],
            company_id=row['company_id'],
            status=row['status'],
            budget_monthly_cents=row['budget_monthly_cents'],
            spent_monthly_cents=row['spent_monthly_cents'],
            context_mode=row['context_mode'],
            last_heartbeat=row['last_heartbeat']
        ) for row in cursor.fetchall()]
    
    # ─────────────────────────────────────────────────────────────────
    # Context Delivery
    # ─────────────────────────────────────────────────────────────────
    
    def get_agent_context(
        self,
        agent_id: str,
        query: str,
        max_tokens: int = 3000
    ) -> ContextPayload:
        """
        Get context for an agent (scoped to their company).
        
        Integrates with Memory Engine to deliver company-scoped facts.
        
        Args:
            agent_id: Agent requesting context
            query: Query string
            max_tokens: Token budget for this call
        
        Returns:
            ContextPayload with facts + metadata
        """
        agent = self.get_agent(agent_id)
        if not agent:
            logger_obj.warning(f"Agent not found: {agent_id}")
            return ContextPayload(
                agent_id=agent_id,
                timestamp=datetime.now().isoformat(),
                facts=[],
                total_tokens=0,
                source_mode="retriever_only",
                metadata={"error": "agent_not_found"}
            )
        
        # Get facts from Memory Engine (company-scoped)
        # This would call the Memory Engine with company_id filter
        facts = self._query_company_facts(agent.company_id, query, max_tokens)
        
        total_tokens = sum(f.get('tokens', 50) for f in facts)
        
        # Log delivery
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO tenant_context_deliveries
            (agent_id, company_id, query, facts_count, tokens_used, source_mode, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            agent_id,
            agent.company_id,
            query,
            len(facts),
            total_tokens,
            "hybrid",
            datetime.now().isoformat()
        ))
        self.conn.commit()
        
        return ContextPayload(
            agent_id=agent_id,
            timestamp=datetime.now().isoformat(),
            facts=facts,
            total_tokens=total_tokens,
            source_mode="hybrid",
            metadata={
                "company_id": agent.company_id,
                "agent_role": agent.role,
                "context_mode": agent.context_mode
            }
        )
    
    def _query_company_facts(
        self,
        company_id: str,
        query: str,
        max_tokens: int
    ) -> List[Dict]:
        """
        Query facts scoped to company_id.
        
        In full implementation, would call Memory Engine's hybrid_retriever
        with company_id filter.
        """
        # Placeholder: would integrate with actual Memory Engine
        # For now, return empty (assumes Memory Engine is called separately)
        return []
    
    # ─────────────────────────────────────────────────────────────────
    # Cost Tracking
    # ─────────────────────────────────────────────────────────────────
    
    def record_agent_cost(
        self,
        agent_id: str,
        tokens_used: int,
        cost_cents: int,
        model: str = "claude-haiku"
    ) -> bool:
        """
        Record token usage and cost for an agent.
        
        Args:
            agent_id: Agent UUID
            tokens_used: Number of tokens consumed
            cost_cents: Cost in cents
            model: Model used
        """
        agent = self.get_agent(agent_id)
        if not agent:
            logger_obj.warning(f"Agent not found for cost event: {agent_id}")
            return False
        
        cursor = self.conn.cursor()
        
        try:
            # Record cost event
            cursor.execute("""
                INSERT INTO tenant_cost_events
                (agent_id, company_id, tokens_used, cost_cents, model, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                agent_id,
                agent.company_id,
                tokens_used,
                cost_cents,
                model,
                datetime.now().isoformat()
            ))
            
            # Update agent's monthly spent (simplified)
            cursor.execute("""
                UPDATE tenant_agents
                SET spent_monthly_cents = spent_monthly_cents + ?
                WHERE agent_id = ?
            """, (cost_cents, agent_id))
            
            # Update sync state
            cursor.execute("""
                UPDATE tenant_sync_state
                SET total_costs_cents = total_costs_cents + ?
                WHERE company_id = ?
            """, (cost_cents, agent.company_id))
            
            self.conn.commit()
            
            logger_obj.info(f"Cost recorded for {agent_id}: {tokens_used} tokens, {cost_cents}¢")
            
            # Check if over budget and sync to Paperclip
            self._check_budget_and_sync(agent_id, agent.company_id)
            
            return True
        
        except Exception as e:
            logger_obj.error(f"Failed to record cost: {e}")
            return False
    
    def _check_budget_and_sync(self, agent_id: str, company_id: str):
        """Check if agent is over budget and sync to Paperclip."""
        agent = self.get_agent(agent_id)
        if not agent:
            return
        
        # Check monthly budget
        if agent.budget_monthly_cents > 0:
            over_budget = agent.spent_monthly_cents > agent.budget_monthly_cents
            
            if over_budget:
                logger_obj.warning(
                    f"Agent {agent_id} OVER BUDGET: "
                    f"{agent.spent_monthly_cents}¢ / {agent.budget_monthly_cents}¢"
                )
                # Would call Paperclip API to pause agent
                self._sync_to_paperclip_pause(agent_id)
        
        # Sync costs to Paperclip
        self._sync_costs_to_paperclip(agent_id, company_id)
    
    def _sync_to_paperclip_pause(self, agent_id: str):
        """Sync pause request to Paperclip (budget exceeded)."""
        try:
            # PUT /api/agents/{agent_id} { status: "paused" }
            response = requests.put(
                f"{self.api_base}/api/agents/{agent_id}",
                json={"status": "paused"},
                timeout=5
            )
            if response.status_code == 200:
                logger_obj.info(f"Paused agent {agent_id} in Paperclip")
            else:
                logger_obj.error(f"Failed to pause agent: {response.status_code}")
        except Exception as e:
            logger_obj.error(f"Failed to sync pause to Paperclip: {e}")
    
    def _sync_costs_to_paperclip(self, agent_id: str, company_id: str):
        """Sync cost events to Paperclip."""
        try:
            # GET costs for this agent since last sync
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT SUM(tokens_used) as total_tokens, SUM(cost_cents) as total_cost
                FROM tenant_cost_events
                WHERE agent_id = ?
                AND timestamp > datetime('now', '-1 hour')
            """, (agent_id,))
            
            row = cursor.fetchone()
            if row and row['total_cost']:
                # POST /api/cost-events
                response = requests.post(
                    f"{self.api_base}/api/cost-events",
                    json={
                        "agent_id": agent_id,
                        "company_id": company_id,
                        "tokens": row['total_tokens'],
                        "cost_cents": row['total_cost']
                    },
                    timeout=5
                )
                if response.status_code == 201:
                    logger_obj.info(f"Synced costs for {agent_id} to Paperclip")
        except Exception as e:
            logger_obj.error(f"Failed to sync costs to Paperclip: {e}")
    
    # ─────────────────────────────────────────────────────────────────
    # Health & Sync
    # ─────────────────────────────────────────────────────────────────
    
    def get_company_stats(self, company_id: str) -> Dict:
        """Get company-level statistics."""
        cursor = self.conn.cursor()
        
        # Company info
        company = self.get_company(company_id)
        if not company:
            return {}
        
        # Agent count
        cursor.execute(
            "SELECT COUNT(*) as count FROM tenant_agents WHERE company_id = ?",
            (company_id,)
        )
        agents_count = cursor.fetchone()['count']
        
        # Total costs
        cursor.execute(
            "SELECT SUM(cost_cents) as total FROM tenant_cost_events WHERE company_id = ?",
            (company_id,)
        )
        total_costs = cursor.fetchone()['total'] or 0
        
        # Context deliveries
        cursor.execute(
            "SELECT COUNT(*) as count FROM tenant_context_deliveries WHERE company_id = ?",
            (company_id,)
        )
        context_deliveries = cursor.fetchone()['count']
        
        return {
            'company_id': company_id,
            'company_name': company.company_name,
            'agents_count': agents_count,
            'total_costs_cents': total_costs,
            'context_deliveries': context_deliveries,
            'memory_budget_tokens': company.memory_budget_tokens
        }
    
    def sync_from_paperclip(self, company_id: str) -> bool:
        """
        Sync company agents and tasks from Paperclip API.
        
        Pulls current state and updates local registration.
        """
        company = self.get_company(company_id)
        if not company:
            logger_obj.warning(f"Company not found: {company_id}")
            return False
        
        try:
            # GET /api/companies/{company_id}/agents
            response = requests.get(
                f"{self.api_base}/api/companies/{company_id}/agents",
                headers={"X-API-Key": company.api_key} if company.api_key else {},
                timeout=10
            )
            
            if response.status_code != 200:
                logger_obj.error(f"Failed to fetch agents: {response.status_code}")
                return False
            
            agents = response.json().get('data', [])
            
            # Register/update all agents
            for agent_data in agents:
                self.register_agent(
                    agent_id=agent_data['id'],
                    agent_name=agent_data['name'],
                    role=agent_data.get('role', 'unknown'),
                    company_id=company_id,
                    status=agent_data.get('status', 'active'),
                    budget_monthly_cents=agent_data.get('budget_monthly_cents', 0),
                    context_mode=agent_data.get('context_mode', 'thin')
                )
            
            # Update sync state
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE tenant_sync_state
                SET last_sync_at = ?, agents_count = ?
                WHERE company_id = ?
            """, (datetime.now().isoformat(), len(agents), company_id))
            self.conn.commit()
            
            logger_obj.info(f"Synced {len(agents)} agents from Paperclip for {company_id}")
            return True
        
        except Exception as e:
            logger_obj.error(f"Failed to sync from Paperclip: {e}")
            return False


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Paperclip Tenant Memory Bridge")
    parser.add_argument('--api', default='http://localhost:3100', help='Paperclip API base URL')
    
    subparsers = parser.add_subparsers(dest='command')
    
    # Company commands
    company_parser = subparsers.add_parser('company')
    company_subparsers = company_parser.add_subparsers(dest='subcommand')
    
    register_parser = company_subparsers.add_parser('register')
    register_parser.add_argument('--id', required=True, help='Company ID')
    register_parser.add_argument('--name', required=True, help='Company name')
    register_parser.add_argument('--budget', type=int, default=10000, help='Memory budget')
    
    list_parser = company_subparsers.add_parser('list')
    
    stats_parser = company_subparsers.add_parser('stats')
    stats_parser.add_argument('--id', required=True, help='Company ID')
    
    # Agent commands
    agent_parser = subparsers.add_parser('agent')
    agent_subparsers = agent_parser.add_subparsers(dest='subcommand')
    
    register_agent_parser = agent_subparsers.add_parser('register')
    register_agent_parser.add_argument('--id', required=True, help='Agent ID')
    register_agent_parser.add_argument('--name', required=True, help='Agent name')
    register_agent_parser.add_argument('--role', required=True, help='Agent role')
    register_agent_parser.add_argument('--company', required=True, help='Company ID')
    
    list_agents_parser = agent_subparsers.add_parser('list')
    list_agents_parser.add_argument('--company', required=True, help='Company ID')
    
    # Cost commands
    cost_parser = subparsers.add_parser('cost')
    cost_subparsers = cost_parser.add_subparsers(dest='subcommand')
    
    record_parser = cost_subparsers.add_parser('record')
    record_parser.add_argument('--agent', required=True, help='Agent ID')
    record_parser.add_argument('--tokens', type=int, required=True, help='Tokens used')
    record_parser.add_argument('--cents', type=int, required=True, help='Cost in cents')
    
    args = parser.parse_args()
    
    bridge = TenantMemoryBridge(api_base=args.api)
    
    try:
        if args.command == 'company':
            if args.subcommand == 'register':
                bridge.register_company(args.id, args.name, memory_budget_tokens=args.budget)
                print(f"✓ Registered company: {args.name}")
            
            elif args.subcommand == 'list':
                companies = bridge.list_companies()
                print(f"\n✓ Companies ({len(companies)}):")
                for c in companies:
                    print(f"  • {c.company_id}: {c.company_name}")
            
            elif args.subcommand == 'stats':
                stats = bridge.get_company_stats(args.id)
                print(f"\n✓ Company Stats: {args.id}")
                for k, v in stats.items():
                    print(f"  {k}: {v}")
        
        elif args.command == 'agent':
            if args.subcommand == 'register':
                bridge.register_agent(
                    args.id, args.name, args.role, args.company
                )
                print(f"✓ Registered agent: {args.name}")
            
            elif args.subcommand == 'list':
                agents = bridge.list_company_agents(args.company)
                print(f"\n✓ Agents in {args.company} ({len(agents)}):")
                for a in agents:
                    print(f"  • {a.agent_name} ({a.role})")
        
        elif args.command == 'cost':
            if args.subcommand == 'record':
                bridge.record_agent_cost(args.agent, args.tokens, args.cents)
                print(f"✓ Recorded cost for {args.agent}")
    
    finally:
        bridge.close()


if __name__ == '__main__':
    main()
