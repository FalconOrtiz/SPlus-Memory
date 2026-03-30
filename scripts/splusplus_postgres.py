#!/usr/bin/env python3
"""
S++ PostgreSQL Auto-Configuration
=================================

PostgreSQL is the PRIMARY backend - no SQLite fallback.
Auto-installation options:
- Docker container (preferred for local dev)
- System package manager
- Cloud service connection (existing DB)

Usage:
    python splusplus_postgres.py --install docker
    python splusplus_postgres.py --install brew
    python splusplus_postgres.py --install system
    python splusplus_postgres.py --connect postgres://user:pass@host:5432/db
"""

import os
import sys
import json
import time
import subprocess
import socket
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict


@dataclass
class PostgreSQLConfig:
    """PostgreSQL connection configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "splusplus"
    user: str = "splusplus"
    password: str = ""
    sslmode: str = "prefer"
    
    @property
    def dsn(self) -> str:
        """Connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?sslmode={self.sslmode}"
    
    @property
    def dsn_masked(self) -> str:
        """Connection string with masked password."""
        return f"postgresql://{self.user}:****@{self.host}:{self.port}/{self.database}"
    
    @classmethod
    def from_url(cls, url: str) -> "PostgreSQLConfig":
        """Parse from connection URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return cls(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            database=parsed.path.lstrip('/') if parsed.path else "splusplus",
            user=parsed.username or "splusplus",
            password=parsed.password or "",
            sslmode="require" if parsed.scheme == "postgresqls" else "prefer"
        )


class PostgreSQLInstaller:
    """Handles PostgreSQL installation and configuration."""
    
    def __init__(self, config: Optional[PostgreSQLConfig] = None):
        self.config = config or PostgreSQLConfig()
        self.home = Path.home()
        self.splusplus_home = self.home / ".splusplus"
        self.log_file = self.splusplus_home / "postgres_install.log"
    
    def log(self, message: str):
        """Log installation progress."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.splusplus_home.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
        
        print(f"🗄️  {message}")
    
    def check_existing(self) -> bool:
        """Check if PostgreSQL is already running."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.config.host, self.config.port))
            sock.close()
            return result == 0
        except:
            return False
    
    def install_docker(self) -> bool:
        """Install PostgreSQL via Docker."""
        self.log("Installing PostgreSQL via Docker...")
        
        # Check if Docker is available
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10
            )
            if result.returncode != 0:
                self.log("❌ Docker daemon not running")
                return False
        except:
            self.log("❌ Docker not installed")
            return False
        
        # Generate password
        import secrets
        self.config.password = secrets.token_urlsafe(32)
        
        # Create Docker container
        cmd = [
            "docker", "run", "-d",
            "--name", "splusplus-postgres",
            "-p", f"{self.config.port}:5432",
            "-e", f"POSTGRES_DB={self.config.database}",
            "-e", f"POSTGRES_USER={self.config.user}",
            "-e", f"POSTGRES_PASSWORD={self.config.password}",
            "-v", "splusplus-postgres-data:/var/lib/postgresql/data",
            "--restart", "unless-stopped",
            "postgres:16-alpine"
        ]
        
        self.log(f"Creating container 'splusplus-postgres'...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            if "already in use" in result.stderr:
                self.log("Container already exists, starting it...")
                subprocess.run(
                    ["docker", "start", "splusplus-postgres"],
                    capture_output=True
                )
            else:
                self.log(f"❌ Failed to create container: {result.stderr}")
                return False
        
        # Wait for PostgreSQL to be ready
        self.log("Waiting for PostgreSQL to be ready...")
        for i in range(30):
            time.sleep(1)
            if self.check_existing():
                self.log("✅ PostgreSQL is ready!")
                return True
        
        self.log("❌ Timeout waiting for PostgreSQL")
        return False
    
    def install_brew(self) -> bool:
        """Install PostgreSQL via Homebrew."""
        self.log("Installing PostgreSQL via Homebrew...")
        
        # Check for Homebrew
        try:
            result = subprocess.run(
                ["which", "brew"],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                self.log("❌ Homebrew not installed")
                return False
        except:
            self.log("❌ Homebrew not installed")
            return False
        
        # Install PostgreSQL
        result = subprocess.run(
            ["brew", "install", "postgresql@16"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0 and "already installed" not in result.stderr:
            self.log(f"❌ Failed to install PostgreSQL: {result.stderr}")
            return False
        
        # Start PostgreSQL service
        self.log("Starting PostgreSQL service...")
        subprocess.run(
            ["brew", "services", "start", "postgresql@16"],
            capture_output=True
        )
        
        # Wait for it to be ready
        time.sleep(5)
        
        if not self.check_existing():
            self.log("❌ PostgreSQL service not responding")
            return False
        
        # Create database and user
        self._create_database_brew()
        
        self.log("✅ PostgreSQL installed via Homebrew")
        return True
    
    def _create_database_brew(self):
        """Create database and user for Homebrew installation."""
        import secrets
        
        self.config.password = secrets.token_urlsafe(32)
        
        # Create user
        subprocess.run(
            ["createuser", "-s", self.config.user],
            capture_output=True
        )
        
        # Set password
        subprocess.run(
            ["psql", "-c", f"ALTER USER {self.config.user} WITH PASSWORD '{self.config.password}';"],
            capture_output=True
        )
        
        # Create database
        subprocess.run(
            ["createdb", "-O", self.config.user, self.config.database],
            capture_output=True
        )
        
        self.log(f"✅ Created database '{self.config.database}' and user '{self.config.user}'")
    
    def install_system(self) -> bool:
        """Install PostgreSQL via system package manager."""
        self.log("Installing PostgreSQL via system package manager...")
        
        # Detect OS
        if sys.platform == "linux":
            # Check for apt (Debian/Ubuntu)
            if Path("/usr/bin/apt-get").exists():
                return self._install_apt()
            # Check for dnf/yum (Red Hat)
            elif Path("/usr/bin/dnf").exists():
                return self._install_dnf()
        
        self.log("❌ Unsupported system package manager")
        return False
    
    def _install_apt(self) -> bool:
        """Install via apt (Debian/Ubuntu)."""
        cmds = [
            ["sudo", "apt-get", "update"],
            ["sudo", "apt-get", "install", "-y", "postgresql", "postgresql-contrib"],
            ["sudo", "systemctl", "start", "postgresql"],
        ]
        
        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log(f"❌ Command failed: {' '.join(cmd)}")
                return False
        
        time.sleep(3)
        
        # Create user and database
        import secrets
        self.config.password = secrets.token_urlsafe(32)
        
        subprocess.run(
            ["sudo", "-u", "postgres", "createuser", "-s", self.config.user],
            capture_output=True
        )
        
        subprocess.run(
            ["sudo", "-u", "postgres", "createdb", "-O", self.config.user, self.config.database],
            capture_output=True
        )
        
        self.log("✅ PostgreSQL installed via apt")
        return True
    
    def _install_dnf(self) -> bool:
        """Install via dnf (Fedora/RHEL)."""
        cmds = [
            ["sudo", "dnf", "install", "-y", "postgresql-server", "postgresql-contrib"],
            ["sudo", "postgresql-setup", "--initdb"],
            ["sudo", "systemctl", "start", "postgresql"],
            ["sudo", "systemctl", "enable", "postgresql"],
        ]
        
        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log(f"❌ Command failed: {' '.join(cmd)}")
                return False
        
        time.sleep(3)
        
        # Create user and database
        import secrets
        self.config.password = secrets.token_urlsafe(32)
        
        subprocess.run(
            ["sudo", "-u", "postgres", "createuser", "-s", self.config.user],
            capture_output=True
        )
        
        subprocess.run(
            ["sudo", "-u", "postgres", "createdb", "-O", self.config.user, self.config.database],
            capture_output=True
        )
        
        self.log("✅ PostgreSQL installed via dnf")
        return True
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test PostgreSQL connection."""
        self.log("Testing PostgreSQL connection...")
        
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password
            )
            
            cur = conn.cursor()
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            cur.close()
            conn.close()
            
            self.log(f"✅ Connected: {version}")
            return True, version
            
        except ImportError:
            self.log("⚠️  psycopg2 not installed, using basic socket test")
            if self.check_existing():
                return True, "Port open (psycopg2 not available)"
            return False, "Connection failed"
            
        except Exception as e:
            self.log(f"❌ Connection failed: {e}")
            return False, str(e)
    
    def create_schema(self) -> bool:
        """Create S++ database schema."""
        self.log("Creating S++ database schema...")
        
        schema_sql = """
-- S++ v2.0.0 Schema
-- PostgreSQL PRIMARY backend - no SQLite fallback

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Quantum memory facts (superposition-based)
CREATE TABLE IF NOT EXISTS quantum_facts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(255),
    base_embedding VECTOR(1536),  -- Requires pgvector extension
    direction_vectors JSONB,      -- Compressed superposition states
    context_hash VARCHAR(64),
    certainty FLOAT DEFAULT 0.5,
    source VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Collapse history (which context→which state)
CREATE TABLE IF NOT EXISTS collapse_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fact_id UUID REFERENCES quantum_facts(id) ON DELETE CASCADE,
    collapsed_state_idx INTEGER,
    collapsed_embedding VECTOR(1536),
    query_context TEXT,
    certainty FLOAT,
    collapsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Procedural memory (solution patterns)
CREATE TABLE IF NOT EXISTS procedures (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_hash VARCHAR(64) UNIQUE,
    problem_fingerprint TEXT,
    steps JSONB NOT NULL,
    tool_mappings JSONB,
    success_rate FLOAT DEFAULT 0.0,
    execution_count INTEGER DEFAULT 0,
    avg_execution_time FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_executed TIMESTAMP
);

-- Experience replay buffer
CREATE TABLE IF NOT EXISTS experiences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    problem_type VARCHAR(255),
    problem_statement TEXT,
    procedure_id UUID REFERENCES procedures(id),
    success BOOLEAN,
    execution_time FLOAT,
    feedback_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent registry for Swarm
CREATE TABLE IF NOT EXISTS swarm_agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(100) NOT NULL,
    capabilities TEXT[],
    endpoint VARCHAR(255),
    reputation_score FLOAT DEFAULT 1.0,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tailscale_ip VARCHAR(45),
    is_active BOOLEAN DEFAULT TRUE
);

-- Meta-cognitive analysis cache
CREATE TABLE IF NOT EXISTS meta_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    problem_hash VARCHAR(64) UNIQUE,
    analysis_type VARCHAR(50),
    result JSONB,
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_quantum_facts_entity ON quantum_facts(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_quantum_facts_certainty ON quantum_facts(certainty DESC);
CREATE INDEX IF NOT EXISTS idx_collapse_history_fact ON collapse_history(fact_id);
CREATE INDEX IF NOT EXISTS idx_procedures_fingerprint ON procedures USING gin(to_tsvector('english', problem_fingerprint));
CREATE INDEX IF NOT EXISTS idx_procedures_success ON procedures(success_rate DESC);
CREATE INDEX IF NOT EXISTS idx_experiences_type ON experiences(problem_type);
CREATE INDEX IF NOT EXISTS idx_swarm_agents_role ON swarm_agents(role);
CREATE INDEX IF NOT EXISTS idx_swarm_agents_active ON swarm_agents(is_active) WHERE is_active = TRUE;
"""
        
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password
            )
            
            # Enable pgvector
            cur = conn.cursor()
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()
            
            # Create tables
            cur.execute(schema_sql)
            conn.commit()
            cur.close()
            conn.close()
            
            self.log("✅ Schema created successfully")
            return True
            
        except ImportError:
            self.log("⚠️  psycopg2 not installed, skipping schema creation")
            return False
            
        except Exception as e:
            self.log(f"❌ Schema creation failed: {e}")
            return False
    
    def save_config(self) -> Path:
        """Save configuration to file."""
        config_path = self.splusplus_home / "postgres_config.json"
        self.splusplus_home.mkdir(parents=True, exist_ok=True)
        
        config_dict = asdict(self.config)
        config_dict['dsn'] = self.config.dsn
        config_dict['dsn_masked'] = self.config.dsn_masked
        config_dict['installed_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
        
        self.log(f"💾 Configuration saved to: {config_path}")
        return config_path


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="S++ PostgreSQL Setup")
    parser.add_argument("--install", choices=["docker", "brew", "system"],
                        help="Installation method")
    parser.add_argument("--connect", help="Connect to existing PostgreSQL URL")
    parser.add_argument("--test", action="store_true", help="Test connection")
    parser.add_argument("--schema", action="store_true", help="Create schema")
    
    args = parser.parse_args()
    
    if args.connect:
        config = PostgreSQLConfig.from_url(args.connect)
        installer = PostgreSQLInstaller(config)
    else:
        installer = PostgreSQLInstaller()
    
    success = True
    
    if args.install:
        if args.install == "docker":
            success = installer.install_docker()
        elif args.install == "brew":
            success = installer.install_brew()
        elif args.install == "system":
            success = installer.install_system()
        
        if success:
            installer.save_config()
    
    if args.test or (args.install and success):
        ok, msg = installer.test_connection()
        if not ok:
            success = False
    
    if args.schema:
        installer.create_schema()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
