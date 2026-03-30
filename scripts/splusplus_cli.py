#!/usr/bin/env python3
"""
S++ Unified CLI
===============

Main command-line interface for S++ operations.

Commands:
    splusplus status          - System status
    splusplus health          - Health check
    splusplus solve <problem> - Solve a problem
    splusplus query <sql>     - Execute unified query
    splusplus swarm list      - List swarm agents
    splusplus memory stats    - Memory statistics
    splusplus install check   - Verify installation

Usage:
    splusplus <command> [args...]
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

# Add S++ to path
SPLUSPLUS_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SPLUSPLUS_ROOT))


class SPlusPlusCLI:
    """S++ command-line interface."""
    
    def __init__(self):
        self.home = Path.home()
        self.splusplus_home = self.home / ".splusplus"
        self.config = self._load_config()
    
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
        
        # Fallback to JSON
        config_path = self.splusplus_home / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                return json.load(f)
        
        return {}
    
    def cmd_status(self, args):
        """Show system status."""
        print("🔍 S++ System Status")
        print("="*60)
        
        # Version
        version = self.config.get("version", "unknown")
        print(f"Version: {version}")
        
        # Installation path
        print(f"Config: {self.splusplus_home}")
        
        # PostgreSQL
        try:
            from splusplus.memory.quantum_persistence import QuantumPersistence
            qp = QuantumPersistence()
            stats = qp.get_stats()
            print(f"\n🗄️  PostgreSQL (PRIMARY):")
            print(f"   Mode: {stats.get('mode', 'unknown')}")
            print(f"   Facts: {stats.get('total_facts', 0)}")
            print(f"   States: {stats.get('total_states', 0)}")
            print(f"   Collapses: {stats.get('total_collapses', 0)}")
        except Exception as e:
            print(f"\n🗄️  PostgreSQL: ❌ {e}")
        
        # APIs
        api_config_path = self.splusplus_home / "api_config.json"
        if api_config_path.exists():
            with open(api_config_path) as f:
                api_config = json.load(f)
            
            print(f"\n🤖 LLM APIs:")
            print(f"   OpenAI: {'✅' if api_config.get('openai_enabled') else '❌'}")
            print(f"   Anthropic: {'✅' if api_config.get('anthropic_enabled') else '❌'}")
            print(f"   Ollama: {'✅' if api_config.get('ollama_enabled') else '❌'}")
            print(f"   Priority: {' > '.join(api_config.get('provider_priority', []))}")
        else:
            print(f"\n🤖 LLM APIs: ❌ Not configured")
        
        # Swarm
        try:
            from splusplus_swarm import SwarmDiscovery
            discovery = SwarmDiscovery()
            agents = discovery.discover()
            print(f"\n🌐 Swarm: {len(agents)} agent(s)")
        except Exception as e:
            print(f"\n🌐 Swarm: ⚠️  {e}")
        
        # ReverseDB
        integration_path = self.splusplus_home / "reversedb_integration.json"
        if integration_path.exists():
            print(f"\n🔌 ReverseDB: ✅ Integrated")
        else:
            print(f"\n🔌 ReverseDB: ○ Not integrated")
    
    def cmd_health(self, args):
        """Run health check."""
        print("🏥 S++ Health Check")
        print("="*60)
        
        checks = []
        
        # Check PostgreSQL
        try:
            from splusplus.memory.quantum_persistence import QuantumPersistence
            qp = QuantumPersistence()
            qp._test_connection()
            checks.append(("PostgreSQL", True, "Connected"))
        except Exception as e:
            checks.append(("PostgreSQL", False, str(e)))
        
        # Check APIs
        try:
            api_config_path = self.splusplus_home / "api_config.json"
            if api_config_path.exists():
                with open(api_config_path) as f:
                    api_config = json.load(f)
                
                if any([
                    api_config.get('openai_enabled'),
                    api_config.get('anthropic_enabled'),
                    api_config.get('ollama_enabled')
                ]):
                    checks.append(("LLM APIs", True, "Configured"))
                else:
                    checks.append(("LLM APIs", False, "No providers"))
            else:
                checks.append(("LLM APIs", False, "Not configured"))
        except Exception as e:
            checks.append(("LLM APIs", False, str(e)))
        
        # Check Swarm
        try:
            from splusplus_swarm import SwarmDiscovery
            discovery = SwarmDiscovery()
            checks.append(("Swarm Discovery", True, "Module available"))
        except Exception as e:
            checks.append(("Swarm Discovery", False, str(e)))
        
        # Print results
        for name, ok, msg in checks:
            status = "✅" if ok else "❌"
            print(f"   {status} {name}: {msg}")
        
        # Summary
        passed = sum(1 for _, ok, _ in checks if ok)
        total = len(checks)
        
        print(f"\nScore: {passed}/{total}")
        
        if passed == total:
            print("🎉 All systems operational!")
            return 0
        else:
            print("⚠️  Some systems need attention")
            return 1
    
    def cmd_solve(self, args):
        """Solve a problem using S++."""
        problem = " ".join(args.problem)
        
        print(f"🧠 S++ Solving")
        print("="*60)
        print(f"Problem: {problem[:100]}...")
        print()
        
        try:
            from splusplus.core.splusplus_engine import SPlusPlusEngine
            
            engine = SPlusPlusEngine()
            result = engine.solve(problem)
            
            print("\n📊 Result:")
            print(json.dumps(result, indent=2, default=str))
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return 1
        
        return 0
    
    def cmd_query(self, args):
        """Execute unified query (S++ + ReverseDB)."""
        sql = " ".join(args.sql)
        
        print(f"🔍 Unified Query")
        print("="*60)
        print(f"SQL: {sql[:80]}...")
        print()
        
        try:
            from splusplus_reversedb import ReverseDBIntegration
            
            integration = ReverseDBIntegration()
            result = integration.execute(sql, use_procedure=args.procedure)
            
            print("\n📊 Result:")
            print(json.dumps(result, indent=2, default=str))
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return 1
        
        return 0
    
    def cmd_swarm(self, args):
        """Swarm management."""
        if args.swarm_command == "list":
            try:
                from splusplus_swarm import SwarmDiscovery
                
                discovery = SwarmDiscovery()
                agents = discovery.discover()
                
                print("🌐 Swarm Agents")
                print("="*60)
                
                if not agents:
                    print("No agents discovered")
                    return 0
                
                for agent in agents:
                    print(f"\n  ID: {agent.agent_id}")
                    print(f"  Role: {agent.role}")
                    print(f"  Capabilities: {', '.join(agent.capabilities)}")
                    print(f"  Endpoint: {agent.endpoint}")
                    print(f"  Reputation: {agent.reputation_score:.2f}")
                    print("-" * 40)
                
            except Exception as e:
                print(f"❌ Error: {e}")
                return 1
        
        elif args.swarm_command == "register":
            try:
                from splusplus_swarm import SwarmDiscovery
                
                discovery = SwarmDiscovery()
                discovery.register(
                    role=args.role or "generalist",
                    capabilities=(args.capabilities or "quantum,procedural").split(",")
                )
                
                print("✅ Agent registered")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                return 1
        
        elif args.swarm_command == "heartbeat":
            try:
                from splusplus_swarm import SwarmDiscovery
                
                discovery = SwarmDiscovery()
                if discovery.heartbeat():
                    print("✅ Heartbeat sent")
                else:
                    print("❌ Heartbeat failed")
                    return 1
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                return 1
        
        return 0
    
    def cmd_memory(self, args):
        """Memory management."""
        if args.memory_command == "stats":
            try:
                from splusplus.memory.quantum_persistence import QuantumPersistence
                
                qp = QuantumPersistence()
                stats = qp.get_stats()
                
                print("🧠 Memory Statistics")
                print("="*60)
                
                for key, value in stats.items():
                    if isinstance(value, dict):
                        print(f"\n{key}:")
                        for k, v in value.items():
                            print(f"   {k}: {v}")
                    else:
                        print(f"{key}: {value}")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                return 1
        
        elif args.memory_command == "vacuum":
            try:
                from splusplus.memory.quantum_persistence import QuantumPersistence
                
                qp = QuantumPersistence()
                qp.vacuum_old_history(days=args.days or 30)
                
                print("✅ Vacuum completed")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                return 1
        
        return 0
    
    def cmd_install(self, args):
        """Installation management."""
        if args.install_command == "check":
            # Run installer health check
            installer_path = SPLUSPLUS_ROOT / "install-splusplus"
            if installer_path.exists():
                import subprocess
                result = subprocess.run(
                    [sys.executable, str(installer_path), "--health"]
                )
                return result.returncode
            else:
                print("❌ Installer not found")
                return 1
        
        return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="S++ Unified CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  splusplus status                    Show system status
  splusplus health                    Run health check
  splusplus solve "Optimize SQL"      Solve a problem
  splusplus query "SELECT * FROM..."  Execute query
  splusplus swarm list                List swarm agents
  splusplus memory stats              Show memory stats
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Status
    subparsers.add_parser("status", help="Show system status")
    
    # Health
    subparsers.add_parser("health", help="Run health check")
    
    # Solve
    solve_parser = subparsers.add_parser("solve", help="Solve a problem")
    solve_parser.add_argument("problem", nargs="+", help="Problem statement")
    
    # Query
    query_parser = subparsers.add_parser("query", help="Execute unified query")
    query_parser.add_argument("sql", nargs="+", help="SQL query")
    query_parser.add_argument("--procedure", action="store_true", 
                              help="Use procedural execution")
    
    # Swarm
    swarm_parser = subparsers.add_parser("swarm", help="Swarm management")
    swarm_sub = swarm_parser.add_subparsers(dest="swarm_command")
    
    swarm_list = swarm_sub.add_parser("list", help="List agents")
    
    swarm_reg = swarm_sub.add_parser("register", help="Register this agent")
    swarm_reg.add_argument("--role", help="Agent role")
    swarm_reg.add_argument("--capabilities", help="Comma-separated capabilities")
    
    swarm_sub.add_parser("heartbeat", help="Send heartbeat")
    
    # Memory
    memory_parser = subparsers.add_parser("memory", help="Memory management")
    memory_sub = memory_parser.add_subparsers(dest="memory_command")
    
    memory_sub.add_parser("stats", help="Show statistics")
    
    memory_vac = memory_sub.add_parser("vacuum", help="Clean old data")
    memory_vac.add_argument("--days", type=int, help="Days to keep")
    
    # Install
    install_parser = subparsers.add_parser("install", help="Installation")
    install_sub = install_parser.add_subparsers(dest="install_command")
    install_sub.add_parser("check", help="Check installation")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    cli = SPlusPlusCLI()
    
    # Route to handler
    handler = getattr(cli, f"cmd_{args.command}", None)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
