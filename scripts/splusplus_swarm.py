#!/usr/bin/env python3
"""
S++ Swarm Auto-Discovery
=========================

Automatic peer discovery for S++ Swarm coordination:
- mDNS (local network) - preferred for LAN
- Tailscale (VPN network) - for distributed nodes
- PostgreSQL registry (shared DB) - fallback for cloud

Usage:
    python splusplus_swarm.py --discover
    python splusplus_swarm.py --register
    python splusplus_swarm.py --list
"""

import os
import sys
import json
import time
import socket
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class SwarmAgent:
    """Swarm agent registration."""
    agent_id: str
    role: str
    capabilities: List[str] = field(default_factory=list)
    endpoint: str = ""
    tailscale_ip: str = ""
    hostname: str = ""
    reputation_score: float = 1.0
    last_seen: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SwarmAgent":
        return cls(**data)


class SwarmDiscovery:
    """Multi-method swarm peer discovery."""
    
    DISCOVERY_METHODS = ["mdns", "tailscale", "postgresql"]
    
    def __init__(self, agent_id: Optional[str] = None):
        self.agent_id = agent_id or self._generate_agent_id()
        self.hostname = socket.gethostname()
        self.home = Path.home()
        self.splusplus_home = self.home / ".splusplus"
        
        # Load config
        self.config = self._load_config()
    
    def _generate_agent_id(self) -> str:
        """Generate unique agent ID."""
        import uuid
        return f"splusplus-{uuid.uuid4().hex[:8]}"
    
    def _load_config(self) -> Dict[str, Any]:
        """Load S++ configuration."""
        config_path = self.splusplus_home / "config.yaml"
        
        if config_path.exists():
            try:
                import yaml
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
            except:
                pass
        
        return {}
    
    def discover(self) -> List[SwarmAgent]:
        """Discover swarm agents using all available methods."""
        print("🔍 Discovering S++ Swarm agents...")
        
        agents = []
        
        # Method 1: mDNS (local network)
        mdns_agents = self._discover_mdns()
        agents.extend(mdns_agents)
        
        # Method 2: Tailscale
        tailscale_agents = self._discover_tailscale()
        agents.extend(tailscale_agents)
        
        # Method 3: PostgreSQL registry
        pg_agents = self._discover_postgresql()
        agents.extend(pg_agents)
        
        # Remove duplicates (same agent_id)
        seen = set()
        unique_agents = []
        for agent in agents:
            if agent.agent_id not in seen:
                seen.add(agent.agent_id)
                unique_agents.append(agent)
        
        print(f"\n✅ Found {len(unique_agents)} unique agent(s)")
        return unique_agents
    
    def _discover_mdns(self) -> List[SwarmAgent]:
        """Discover via mDNS/Zeroconf."""
        agents = []
        
        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
            
            class SPlusPlusListener(ServiceListener):
                def __init__(self):
                    self.agents = []
                
                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if info:
                        agent = SwarmAgent(
                            agent_id=name.replace("._splusplus._tcp.local.", ""),
                            role=info.properties.get(b"role", b"generalist").decode(),
                            capabilities=info.properties.get(b"caps", b"").decode().split(","),
                            endpoint=f"{socket.inet_ntoa(info.addresses[0])}:{info.port}" if info.addresses else "",
                            hostname=info.server
                        )
                        self.agents.append(agent)
                
                def remove_service(self, zc, type_, name):
                    pass
                
                def update_service(self, zc, type_, name):
                    pass
            
            print("   🔍 Scanning via mDNS...")
            zeroconf = Zeroconf()
            listener = SPlusPlusListener()
            browser = ServiceBrowser(zeroconf, "_splusplus._tcp.local.", listener)
            
            # Wait for discovery
            time.sleep(3)
            
            agents = listener.agents
            zeroconf.close()
            
            if agents:
                print(f"   ✅ Found {len(agents)} via mDNS")
            else:
                print("   ○ No mDNS agents found")
                
        except ImportError:
            print("   ⚠️  zeroconf not installed, skipping mDNS")
        except Exception as e:
            print(f"   ⚠️  mDNS error: {e}")
        
        return agents
    
    def _discover_tailscale(self) -> List[SwarmAgent]:
        """Discover via Tailscale."""
        agents = []
        
        try:
            # Check if Tailscale is running
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                print("   ○ Tailscale not running")
                return agents
            
            status = json.loads(result.stdout)
            
            print("   🔍 Scanning Tailscale network...")
            
            for peer in status.get("Peer", {}).values():
                host = peer.get("HostName", "")
                
                # Look for S++ agents
                if "splusplus" in host.lower() or self._is_splusplus_node(peer):
                    agent = SwarmAgent(
                        agent_id=f"splusplus-{host}",
                        role="generalist",
                        tailscale_ip=peer.get("TailscaleIPs", [""])[0],
                        hostname=host,
                        endpoint=f"{peer.get('TailscaleIPs', [''])[0]}:9876"
                    )
                    agents.append(agent)
            
            if agents:
                print(f"   ✅ Found {len(agents)} via Tailscale")
            else:
                print("   ○ No Tailscale agents found")
                
        except FileNotFoundError:
            print("   ○ Tailscale not installed")
        except Exception as e:
            print(f"   ⚠️  Tailscale error: {e}")
        
        return agents
    
    def _is_splusplus_node(self, peer: Dict) -> bool:
        """Check if a Tailscale peer is an S++ node."""
        tags = peer.get("Tags", [])
        return any("splusplus" in tag.lower() for tag in tags)
    
    def _discover_postgresql(self) -> List[SwarmAgent]:
        """Discover via PostgreSQL registry."""
        agents = []
        
        try:
            import psycopg2
            
            # Load PostgreSQL config
            pg_config_path = self.splusplus_home / "postgres_config.json"
            if not pg_config_path.exists():
                print("   ○ PostgreSQL config not found")
                return agents
            
            with open(pg_config_path) as f:
                pg_config = json.load(f)
            
            conn = psycopg2.connect(pg_config['dsn'])
            cur = conn.cursor()
            
            # Query swarm_agents table
            cur.execute("""
                SELECT agent_id, role, capabilities, endpoint, 
                       tailscale_ip, reputation_score, last_seen
                FROM swarm_agents
                WHERE is_active = TRUE 
                  AND last_seen > NOW() - INTERVAL '1 hour'
            """)
            
            for row in cur.fetchall():
                agent = SwarmAgent(
                    agent_id=row[0],
                    role=row[1],
                    capabilities=row[2] or [],
                    endpoint=row[3] or "",
                    tailscale_ip=row[4] or "",
                    reputation_score=row[5] or 1.0,
                    last_seen=str(row[6]) if row[6] else ""
                )
                agents.append(agent)
            
            cur.close()
            conn.close()
            
            if agents:
                print(f"   ✅ Found {len(agents)} via PostgreSQL")
            else:
                print("   ○ No PostgreSQL registry agents found")
                
        except ImportError:
            print("   ⚠️  psycopg2 not installed, skipping PostgreSQL")
        except Exception as e:
            print(f"   ⚠️  PostgreSQL error: {e}")
        
        return agents
    
    def register(self, role: str = "generalist", capabilities: List[str] = None,
                 tailscale_ip: str = "", port: int = 9876) -> bool:
        """Register this agent in the swarm."""
        print(f"📝 Registering agent '{self.agent_id}'...")
        
        if capabilities is None:
            capabilities = ["quantum_memory", "procedural_learning"]
        
        # Register in PostgreSQL
        pg_success = self._register_postgresql(role, capabilities, tailscale_ip, port)
        
        # Register via mDNS
        mdns_success = self._register_mdns(role, capabilities, port)
        
        return pg_success or mdns_success
    
    def _register_postgresql(self, role: str, capabilities: List[str],
                             tailscale_ip: str, port: int) -> bool:
        """Register in PostgreSQL registry."""
        try:
            import psycopg2
            
            pg_config_path = self.splusplus_home / "postgres_config.json"
            if not pg_config_path.exists():
                return False
            
            with open(pg_config_path) as f:
                pg_config = json.load(f)
            
            conn = psycopg2.connect(pg_config['dsn'])
            cur = conn.cursor()
            
            # Upsert agent
            cur.execute("""
                INSERT INTO swarm_agents 
                    (agent_id, role, capabilities, endpoint, tailscale_ip, last_seen)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (agent_id) 
                DO UPDATE SET
                    role = EXCLUDED.role,
                    capabilities = EXCLUDED.capabilities,
                    endpoint = EXCLUDED.endpoint,
                    tailscale_ip = EXCLUDED.tailscale_ip,
                    last_seen = NOW(),
                    is_active = TRUE
            """, (self.agent_id, role, capabilities, 
                  f"{self.hostname}:{port}", tailscale_ip))
            
            conn.commit()
            cur.close()
            conn.close()
            
            print(f"   ✅ Registered in PostgreSQL")
            return True
            
        except Exception as e:
            print(f"   ⚠️  PostgreSQL registration failed: {e}")
            return False
    
    def _register_mdns(self, role: str, capabilities: List[str], port: int) -> bool:
        """Register via mDNS."""
        try:
            from zeroconf import Zeroconf, ServiceInfo
            
            zeroconf = Zeroconf()
            
            info = ServiceInfo(
                type_="_splusplus._tcp.local.",
                name=f"{self.agent_id}._splusplus._tcp.local.",
                addresses=[socket.inet_aton(self._get_local_ip())],
                port=port,
                properties={
                    b"role": role.encode(),
                    b"caps": ",".join(capabilities).encode()
                }
            )
            
            zeroconf.register_service(info)
            
            print(f"   ✅ Registered via mDNS on port {port}")
            
            # Keep registered (or we could store zeroconf instance)
            import atexit
            atexit.register(zeroconf.unregister_service, info)
            atexit.register(zeroconf.close)
            
            return True
            
        except ImportError:
            print("   ⚠️  zeroconf not installed, skipping mDNS")
            return False
        except Exception as e:
            print(f"   ⚠️  mDNS registration failed: {e}")
            return False
    
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def heartbeat(self) -> bool:
        """Update last_seen timestamp."""
        try:
            import psycopg2
            
            pg_config_path = self.splusplus_home / "postgres_config.json"
            if not pg_config_path.exists():
                return False
            
            with open(pg_config_path) as f:
                pg_config = json.load(f)
            
            conn = psycopg2.connect(pg_config['dsn'])
            cur = conn.cursor()
            
            cur.execute("""
                UPDATE swarm_agents 
                SET last_seen = NOW()
                WHERE agent_id = %s
            """, (self.agent_id,))
            
            conn.commit()
            cur.close()
            conn.close()
            
            return True
            
        except:
            return False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="S++ Swarm Discovery")
    parser.add_argument("--discover", action="store_true", help="Discover agents")
    parser.add_argument("--register", action="store_true", help="Register this agent")
    parser.add_argument("--list", action="store_true", help="List discovered agents")
    parser.add_argument("--role", default="generalist", help="Agent role")
    parser.add_argument("--capabilities", default="quantum,procedural", 
                        help="Comma-separated capabilities")
    parser.add_argument("--heartbeat", action="store_true", help="Send heartbeat")
    
    args = parser.parse_args()
    
    discovery = SwarmDiscovery()
    
    if args.discover or args.list:
        agents = discovery.discover()
        
        print("\n📋 Discovered Agents:")
        print("-" * 80)
        for agent in agents:
            print(f"  ID: {agent.agent_id}")
            print(f"  Role: {agent.role}")
            print(f"  Caps: {', '.join(agent.capabilities)}")
            print(f"  Endpoint: {agent.endpoint}")
            print(f"  Tailscale: {agent.tailscale_ip or 'N/A'}")
            print(f"  Reputation: {agent.reputation_score:.2f}")
            print("-" * 80)
    
    if args.register:
        caps = args.capabilities.split(",")
        discovery.register(role=args.role, capabilities=caps)
    
    if args.heartbeat:
        discovery.heartbeat()


if __name__ == "__main__":
    main()
