#!/usr/bin/env python3
"""
S++ Unified Auto-Configuration Installer
=========================================

One-command installation with:
- PostgreSQL as PRIMARY backend
- Auto-detected APIs
- Auto-discovered Swarm peers
- ReverseDB integration
- Hermes/OpenClaw auto-integration

Usage:
    ./install-splusplus --auto                    # Full auto
    ./install-splusplus --detect                  # Detection only
    ./install-splusplus --interactive             # Interactive mode
    ./install-splusplus --postgresql docker       # Specific options
"""

import os
import sys
import json
import time
import socket
import subprocess
import platform
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class EnvironmentProfile:
    """Complete environment detection profile."""
    # System
    os_type: str = "unknown"
    os_version: str = "unknown"
    python_version: str = "unknown"
    architecture: str = "unknown"
    
    # Existing installations
    has_hermes: bool = False
    hermes_path: Optional[str] = None
    has_openclaw: bool = False
    openclaw_path: Optional[str] = None
    has_reversedb: bool = False
    reversedb_path: Optional[str] = None
    
    # Infrastructure
    has_postgresql: bool = False
    postgresql_version: Optional[str] = None
    has_docker: bool = False
    docker_version: Optional[str] = None
    has_gpu: bool = False
    gpu_type: Optional[str] = None
    
    # Network
    has_tailscale: bool = False
    hostname: str = "unknown"
    
    # APIs
    has_openai_key: bool = False
    has_anthropic_key: bool = False
    has_ollama: bool = False
    
    # Python packages
    packages: Dict[str, bool] = field(default_factory=dict)


class EnvironmentDetector:
    """Detects environment for S++ installation."""
    
    def __init__(self):
        self.home = Path.home()
    
    def detect_all(self) -> EnvironmentProfile:
        """Run complete environment detection."""
        print("🔍 Detecting environment...")
        
        profile = EnvironmentProfile()
        
        # System detection
        profile.os_type = platform.system().lower()
        profile.os_version = platform.version()
        profile.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        profile.architecture = platform.machine()
        profile.hostname = socket.gethostname()
        
        # Existing agent installations
        self._detect_hermes(profile)
        self._detect_openclaw(profile)
        self._detect_reversedb(profile)
        
        # Infrastructure
        self._detect_postgresql(profile)
        self._detect_docker(profile)
        self._detect_gpu(profile)
        self._detect_tailscale(profile)
        
        # APIs
        self._detect_api_keys(profile)
        self._detect_ollama(profile)
        
        # Python packages
        self._detect_packages(profile)
        
        return profile
    
    def _detect_hermes(self, profile: EnvironmentProfile):
        """Detect Hermes installation."""
        hermes_paths = [
            self.home / ".hermes",
            self.home / "hermes",
        ]
        
        for path in hermes_paths:
            if path.exists() and (path / "workspace" / "memory").exists():
                profile.has_hermes = True
                profile.hermes_path = str(path)
                print(f"   ✅ Hermes found: {path}")
                return
        
        print("   ○ Hermes not found")
    
    def _detect_openclaw(self, profile: EnvironmentProfile):
        """Detect OpenClaw installation."""
        openclaw_paths = [
            self.home / ".openclaw",
            self.home / "openclaw",
        ]
        
        for path in openclaw_paths:
            if path.exists():
                profile.has_openclaw = True
                profile.openclaw_path = str(path)
                print(f"   ✅ OpenClaw found: {path}")
                return
        
        print("   ○ OpenClaw not found")
    
    def _detect_reversedb(self, profile: EnvironmentProfile):
        """Detect ReverseDB installation."""
        reversedb_path = self.home / ".hermes" / "reversedb"
        
        if reversedb_path.exists():
            profile.has_reversedb = True
            profile.reversedb_path = str(reversedb_path)
            print(f"   ✅ ReverseDB found: {reversedb_path}")
        else:
            print("   ○ ReverseDB not found")
    
    def _detect_postgresql(self, profile: EnvironmentProfile):
        """Detect PostgreSQL installation."""
        # Check for pg_config or psql
        pg_commands = ["pg_config", "psql"]
        
        for cmd in pg_commands:
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    profile.has_postgresql = True
                    profile.postgresql_version = result.stdout.strip()
                    print(f"   ✅ PostgreSQL found: {result.stdout.strip()}")
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        
        # Check if PostgreSQL is running
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(("localhost", 5432))
            sock.close()
            
            if result == 0:
                profile.has_postgresql = True
                profile.postgresql_version = "running (version unknown)"
                print("   ✅ PostgreSQL found: running on localhost:5432")
                return
        except:
            pass
        
        print("   ○ PostgreSQL not found")
    
    def _detect_docker(self, profile: EnvironmentProfile):
        """Detect Docker installation."""
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                profile.has_docker = True
                profile.docker_version = result.stdout.strip()
                print(f"   ✅ Docker found: {result.stdout.strip()}")
                
                # Check if docker is running
                result2 = subprocess.run(
                    ["docker", "info"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result2.returncode == 0:
                    print("   ✅ Docker daemon running")
                else:
                    print("   ⚠️  Docker installed but daemon not running")
                return
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        print("   ○ Docker not found")
    
    def _detect_gpu(self, profile: EnvironmentProfile):
        """Detect GPU availability."""
        # Check for CUDA (NVIDIA)
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                profile.has_gpu = True
                profile.gpu_type = "NVIDIA CUDA"
                print("   ✅ NVIDIA GPU found")
                return
        except:
            pass
        
        # Check for Metal (macOS)
        if profile.os_type == "darwin":
            try:
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if "Metal" in result.stdout:
                    profile.has_gpu = True
                    profile.gpu_type = "Apple Metal"
                    print("   ✅ Apple Metal GPU found")
                    return
            except:
                pass
        
        print("   ○ No GPU detected (CPU-only mode)")
    
    def _detect_tailscale(self, profile: EnvironmentProfile):
        """Detect Tailscale."""
        try:
            result = subprocess.run(
                ["tailscale", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                profile.has_tailscale = True
                print("   ✅ Tailscale found")
                return
        except:
            pass
        
        print("   ○ Tailscale not found")
    
    def _detect_api_keys(self, profile: EnvironmentProfile):
        """Detect API keys."""
        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            profile.has_openai_key = True
            print("   ✅ OpenAI API key found (env)")
        elif (self.home / ".openai" / "key").exists():
            profile.has_openai_key = True
            print("   ✅ OpenAI API key found (file)")
        else:
            print("   ○ OpenAI API key not found")
        
        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            profile.has_anthropic_key = True
            print("   ✅ Anthropic API key found (env)")
        else:
            print("   ○ Anthropic API key not found")
    
    def _detect_ollama(self, profile: EnvironmentProfile):
        """Detect Ollama."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(("localhost", 11434))
            sock.close()
            
            if result == 0:
                profile.has_ollama = True
                print("   ✅ Ollama found on localhost:11434")
                return
        except:
            pass
        
        print("   ○ Ollama not found")
    
    def _detect_packages(self, profile: EnvironmentProfile):
        """Detect Python packages."""
        packages = [
            "numpy",
            "psycopg2",
            "openai",
            "anthropic",
            "websockets",
        ]
        
        for pkg in packages:
            try:
                __import__(pkg)
                profile.packages[pkg] = True
            except ImportError:
                profile.packages[pkg] = False
        
        installed = sum(profile.packages.values())
        print(f"   📦 Python packages: {installed}/{len(packages)} installed")


def print_detection_report(profile: EnvironmentProfile):
    """Print formatted detection report."""
    print("\n" + "="*60)
    print("  ENVIRONMENT DETECTION REPORT")
    print("="*60)
    
    print(f"\n🖥️  System:")
    print(f"   OS: {profile.os_type} {profile.os_version}")
    print(f"   Python: {profile.python_version}")
    print(f"   Architecture: {profile.architecture}")
    print(f"   Hostname: {profile.hostname}")
    
    print(f"\n🤖 Agent Installations:")
    print(f"   Hermes: {'✅' if profile.has_hermes else '❌'}")
    if profile.has_hermes:
        print(f"      Path: {profile.hermes_path}")
    print(f"   OpenClaw: {'✅' if profile.has_openclaw else '❌'}")
    print(f"   ReverseDB: {'✅' if profile.has_reversedb else '❌'}")
    
    print(f"\n🗄️  Infrastructure:")
    print(f"   PostgreSQL: {'✅' if profile.has_postgresql else '❌'}")
    if profile.has_postgresql:
        print(f"      Version: {profile.postgresql_version}")
    print(f"   Docker: {'✅' if profile.has_docker else '❌'}")
    print(f"   GPU: {'✅' if profile.has_gpu else '❌'}")
    if profile.has_gpu:
        print(f"      Type: {profile.gpu_type}")
    print(f"   Tailscale: {'✅' if profile.has_tailscale else '❌'}")
    
    print(f"\n🤖 LLM Providers:")
    print(f"   OpenAI: {'✅' if profile.has_openai_key else '❌'}")
    print(f"   Anthropic: {'✅' if profile.has_anthropic_key else '❌'}")
    print(f"   Ollama: {'✅' if profile.has_ollama else '❌'}")
    
    print("\n" + "="*60)


def main():
    """Main entry point for detection."""
    import argparse
    
    parser = argparse.ArgumentParser(description="S++ Environment Detection")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    detector = EnvironmentDetector()
    profile = detector.detect_all()
    
    if args.json:
        print(json.dumps(asdict(profile), indent=2))
    else:
        print_detection_report(profile)
    
    # Save to file
    output_file = Path("environment_profile.json")
    with open(output_file, 'w') as f:
        json.dump(asdict(profile), f, indent=2)
    
    print(f"\n📄 Profile saved to: {output_file}")


if __name__ == "__main__":
    main()
