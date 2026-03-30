#!/usr/bin/env python3
"""
S++ Activation Script for Hermes/OpenClaw
==========================================

This script is called by Gigabrain at session start to activate
S++ cognitive capabilities alongside the standard 8-layer memory.

Usage (from Gigabrain):
    python activate_for_hermes.py --mode active_assistant

Output: Enhanced context JSON for agent system prompt
"""

import sys
import json
import argparse
from pathlib import Path

# Add S++ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from splusplus.integration.hermes_bridge import create_hermes_bridge


def main():
    parser = argparse.ArgumentParser(
        description="Activate S++ for Hermes/OpenClaw session"
    )
    parser.add_argument(
        "--mode",
        choices=["passive", "active_assistant", "full", "disabled"],
        default="active_assistant",
        help="S++ activation mode"
    )
    parser.add_argument(
        "--output",
        choices=["json", "markdown", "system_prompt"],
        default="json",
        help="Output format"
    )
    parser.add_argument(
        "--swarm-peers",
        nargs="*",
        default=[],
        help="WebSocket endpoints for swarm peers"
    )
    
    args = parser.parse_args()
    
    # Set mode via environment (bridge reads from env)
    import os
    os.environ["SPLUSPLUS_MODE"] = args.mode
    
    # Create and activate bridge
    bridge = create_hermes_bridge()
    
    # Activate session
    context = bridge.on_session_start()
    
    # Add swarm peers if provided
    if args.swarm_peers:
        bridge.splusplus_engine.join_swarm(args.swarm_peers)
    
    # Output based on format
    if args.output == "json":
        print(json.dumps(context, indent=2, default=str))
    
    elif args.output == "markdown":
        print("# S++ Session Context\n")
        print("## Gigabrain Layers 1-8")
        print(f"- MEMORY.md: {len(context['gigabrain'].get('memory_md', {}).get('facts', []))} facts")
        print(f"- Daily files: {len(context['gigabrain'].get('daily_files', []))}")
        print(f"- SOUL.md: {'loaded' if context['gigabrain'].get('soul') else 'not found'}")
        print(f"- AGENTS.md: {'loaded' if context['gigabrain'].get('agents') else 'not found'}")
        
        print("\n## S++ Layers 9-13")
        splus = context.get('splusplus', {})
        if splus.get('splusplus_active'):
            print(f"- Quantum Memory: {splus.get('quantum_facts_loaded', 0)} facts")
            print(f"- Procedures: {splus.get('procedures_available', 0)}")
            print(f"- Tools: {splus.get('tools_in_arsenal', 0)}")
            print(f"- Capabilities: {', '.join(splus.get('capabilities', []))}")
        else:
            print("- S++ not activated")
    
    elif args.output == "system_prompt":
        # Output only the system prompt additions
        print(context.get('system_prompt_additions', ''))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
