#!/usr/bin/env python3
"""
Paperclip Control Plane Bridge

Connects Hermes Memory Engine to Paperclip for agent coordination.

Provides:
  1. Agent Status Monitoring — check what agents are doing
  2. Action Logging — log memory decisions to control plane
  3. Agent Coordination — synchronize state with Hermes hub
  4. Configuration Sync — pull agent configs from Paperclip

Architecture:
  Hermes Memory (SQLite)
    ↓
  Paperclip Bridge (REST client)
    ↓
  Paperclip Control Plane API (Express/Node)
    ↓
  Agent Registry + Activity Log
"""

import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import requests
from urllib.parse import urljoin

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"

# Paperclip API endpoints
PAPERCLIP_BASE = os.getenv("PAPERCLIP_BASE_URL", "http://localhost:3100")
PAPERCLIP_API = urljoin(PAPERCLIP_BASE, "/api/")

# Company & Agent IDs
COMPANY_ID = os.getenv("PAPERCLIP_COMPANY_ID", "hermes-company")
HERMES_AGENT_ID = os.getenv("HERMES_AGENT_ID", "hermes-memory-engine")
HERMES_AGENT_ID = os.getenv("HERMES_HUB_ID", "hermes_agent-hub")

# Auth
API_KEY = os.getenv("PAPERCLIP_API_KEY", "")


@dataclass
class AgentStatus:
    """Agent status from Paperclip."""
    
    agent_id: str
    name: str
    status: str  # active, idle, paused, error
    last_activity: str
    current_task: Optional[str] = None
    metadata: Dict = None


@dataclass
class MemoryAction:
    """Action taken by Hermes memory system."""
    
    action_id: str
    action_type: str  # activate, predict, schedule, archive
    agent_id: str
    facts_affected: int
    domains: List[str]
    confidence: float
    reason: str
    timestamp: str


class PaperclipBridge:
    """Client for Paperclip control plane."""

    def __init__(
        self,
        base_url: str = PAPERCLIP_BASE,
        company_id: str = COMPANY_ID,
        api_key: str = API_KEY,
        db_path: Path = None,
    ):
        self.base_url = base_url
        self.company_id = company_id
        self.api_key = api_key
        self.db_path = db_path or DB_PATH
        self.conn = None
        self.session = requests.Session()

        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()
        self.session.close()

    def _request(
        self, method: str, endpoint: str, data: Dict = None, params: Dict = None
    ) -> Optional[Dict]:
        """Make authenticated request to Paperclip API."""
        url = urljoin(self.base_url, f"/api/{endpoint}")

        try:
            if method == "GET":
                resp = self.session.get(url, params=params, timeout=5)
            elif method == "POST":
                resp = self.session.post(url, json=data, timeout=5)
            elif method == "PUT":
                resp = self.session.put(url, json=data, timeout=5)
            else:
                return None

            if resp.status_code in (200, 201):
                return resp.json()
            else:
                print(f"⚠️  Paperclip API error: {resp.status_code} {resp.text}")
                return None

        except requests.RequestException as e:
            print(f"⚠️  Paperclip connection error: {e}")
            return None

    def get_agent_status(self, agent_id: str) -> Optional[AgentStatus]:
        """Get status of an agent from Paperclip."""
        data = self._request(
            "GET",
            f"companies/{self.company_id}/agents/{agent_id}",
        )

        if not data:
            return None

        return AgentStatus(
            agent_id=data.get("id", agent_id),
            name=data.get("name", ""),
            status=data.get("status", "unknown"),
            last_activity=data.get("lastActivity", ""),
            current_task=data.get("currentTask"),
            metadata=data.get("metadata"),
        )

    def list_agents(self) -> List[AgentStatus]:
        """List all agents in the company."""
        data = self._request("GET", f"companies/{self.company_id}/agents")

        if not data:
            return []

        agents = []
        for agent_data in data.get("agents", []):
            agents.append(
                AgentStatus(
                    agent_id=agent_data.get("id"),
                    name=agent_data.get("name"),
                    status=agent_data.get("status"),
                    last_activity=agent_data.get("lastActivity"),
                    current_task=agent_data.get("currentTask"),
                )
            )

        return agents

    def log_action(self, action: MemoryAction) -> bool:
        """Log a memory action to Paperclip activity log."""
        data = self._request(
            "POST",
            f"companies/{self.company_id}/activities",
            {
                "agentId": HERMES_AGENT_ID,
                "type": action.action_type,
                "description": action.reason,
                "payload": {
                    "action_id": action.action_id,
                    "facts_affected": action.facts_affected,
                    "domains": action.domains,
                    "confidence": action.confidence,
                },
                "timestamp": action.timestamp,
            },
        )

        return data is not None

    def sync_memory_state(self) -> Dict:
        """
        Sync Hermes memory state to Paperclip.
        
        Reports:
          • Facts indexed
          • Domains active
          • Recent activations
          • Predictions made
        """
        # Get Hermes stats
        stats = self._get_hermes_stats()

        # Send to Paperclip
        data = self._request(
            "PUT",
            f"companies/{self.company_id}/agents/{HERMES_AGENT_ID}/status",
            {
                "status": "active",
                "lastActivity": datetime.now().isoformat(),
                "metadata": stats,
            },
        )

        return {"synced": data is not None, "stats": stats}

    def _get_hermes_stats(self) -> Dict:
        """Get Hermes memory statistics."""
        try:
            facts = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM quantum_facts WHERE status NOT IN ('abandoned')"
            ).fetchone()["cnt"]

            domains = self.conn.execute(
                "SELECT COUNT(DISTINCT value) as cnt FROM kw_bitmap b JOIN kw_dictionary d ON b.value_id = d.id WHERE b.dimension = 'domain'"
            ).fetchone()["cnt"]

            embeddings = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM fact_embeddings"
            ).fetchone()["cnt"]

            heat_map_slots = 0
            hm_row = self.conn.execute(
                "SELECT value FROM engine_metadata WHERE key = 'prediction_heat_map'"
            ).fetchone()
            if hm_row and hm_row["value"]:
                try:
                    heat_map = json.loads(hm_row["value"])
                    heat_map_slots = len(heat_map)
                except json.JSONDecodeError:
                    pass

            recent_actions = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM evolution_log WHERE created_at > datetime('now', '-1 hour')"
            ).fetchone()["cnt"]

            return {
                "facts_indexed": facts,
                "domains_active": domains,
                "embeddings": embeddings,
                "heat_map_slots": heat_map_slots,
                "recent_actions_1h": recent_actions,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"error": str(e)}

    def coordinate_with_hermes_agent(self, action_type: str, payload: Dict) -> bool:
        """
        Notify Hermes hub of Hermes actions.
        
        Hermes coordinates between:
          • Hermes (memory)
          • LEO (outreach)
          • NOVA (execution)
          • ARIA (analysis)
        """
        action = MemoryAction(
            action_id=f"hermes_{datetime.now().timestamp()}",
            action_type=action_type,
            agent_id=HERMES_AGENT_ID,
            facts_affected=payload.get("facts_affected", 0),
            domains=payload.get("domains", []),
            confidence=payload.get("confidence", 0.5),
            reason=payload.get("reason", ""),
            timestamp=datetime.now().isoformat(),
        )

        logged = self.log_action(action)

        # Notify Hermes
        self._request(
            "POST",
            f"companies/{self.company_id}/agents/{HERMES_AGENT_ID}/messages",
            {
                "from_agent": HERMES_AGENT_ID,
                "action": action_type,
                "payload": asdict(action),
            },
        )

        return logged

    def get_hermes_agent_config(self) -> Optional[Dict]:
        """Get Hermes hub configuration."""
        return self._request(
            "GET",
            f"companies/{self.company_id}/agents/{HERMES_AGENT_ID}/config",
        )

    def get_status(self) -> Dict:
        """Get bridge health status."""
        # Test connection
        health = self._request("GET", "health")
        connected = health is not None

        # Get Hermes status
        hermes_stats = self._get_hermes_stats()

        # Get agent statuses
        agents = self.list_agents()

        return {
            "paperclip_connected": connected,
            "hermes_stats": hermes_stats,
            "agents": [asdict(a) for a in agents],
            "timestamp": datetime.now().isoformat(),
        }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Paperclip Bridge")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Bridge health & sync status")
    sub.add_parser("sync", help="Sync Hermes state to Paperclip")

    p = sub.add_parser("agents", help="List agents in company")

    p = sub.add_parser("log", help="Log action to Paperclip")
    p.add_argument("action_type")
    p.add_argument("--facts", type=int, default=0)
    p.add_argument("--domains", nargs="+", default=[])
    p.add_argument("--reason", default="")

    sub.add_parser("hermes_agent", help="Get Hermes hub config")

    parser.add_argument("--json", action="store_true")
    parser.add_argument("--base-url", default=PAPERCLIP_BASE)
    parser.add_argument("--company", default=COMPANY_ID)
    parser.add_argument("--api-key", default=API_KEY)

    args = parser.parse_args()

    bridge = PaperclipBridge(
        base_url=args.base_url,
        company_id=args.company,
        api_key=args.api_key,
    )
    bridge.connect()

    try:
        if args.command == "status":
            status = bridge.get_status()
            if args.json:
                print(json.dumps(status, indent=2, default=str))
            else:
                print(f"\n  PAPERCLIP BRIDGE STATUS")
                print(f"  {'═' * 50}\n")
                print(f"  Connected:       {status['paperclip_connected']}")
                print(f"\n  HERMES STATS:")
                for k, v in status["hermes_stats"].items():
                    if k != "timestamp":
                        print(f"    {k:25s} {v}")
                print(f"\n  AGENTS ({len(status['agents'])}):")
                for a in status["agents"][:10]:
                    print(f"    {a['name']:20s} {a['status']}")
                print()

        elif args.command == "sync":
            result = bridge.sync_memory_state()
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"\n  SYNC TO PAPERCLIP")
                print(f"  {'═' * 50}\n")
                print(f"  Synced: {result['synced']}")
                for k, v in result["stats"].items():
                    if k != "timestamp":
                        print(f"    {k}: {v}")
                print()

        elif args.command == "agents":
            agents = bridge.list_agents()
            if args.json:
                print(json.dumps([asdict(a) for a in agents], indent=2))
            else:
                print(f"\n  AGENTS IN {args.company}")
                print(f"  {'═' * 50}\n")
                for a in agents:
                    print(f"  {a.name:20s} {a.status:10s} {a.last_activity}")
                print()

        elif args.command == "log":
            action = MemoryAction(
                action_id=f"hermes_{datetime.now().timestamp()}",
                action_type=args.action_type,
                agent_id=HERMES_AGENT_ID,
                facts_affected=args.facts,
                domains=args.domains,
                confidence=0.8,
                reason=args.reason,
                timestamp=datetime.now().isoformat(),
            )
            logged = bridge.log_action(action)
            if args.json:
                print(json.dumps({"logged": logged}, indent=2))
            else:
                print(f"\n  LOGGED ACTION")
                print(f"  {'═' * 50}\n")
                print(f"  Type:    {args.action_type}")
                print(f"  Facts:   {args.facts}")
                print(f"  Domains: {args.domains}")
                print(f"  Status:  {'✓' if logged else '✗'}\n")

        elif args.command == "hermes_agent":
            config = bridge.get_hermes_agent_config()
            if args.json:
                print(json.dumps(config, indent=2, default=str))
            else:
                print(f"\n  HERMES HUB CONFIG")
                print(f"  {'═' * 50}\n")
                if config:
                    print(json.dumps(config, indent=2, default=str))
                else:
                    print("  (not available)\n")

        else:
            parser.print_help()

    finally:
        bridge.close()


if __name__ == "__main__":
    main()
