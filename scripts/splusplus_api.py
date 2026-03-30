#!/usr/bin/env python3
"""
S++ API Auto-Configuration
===========================

Automatically detects and configures LLM APIs:
- OpenAI API (environment, files)
- Anthropic API (environment, files)
- Ollama (local, auto-model-detection)
- Fallback templates (no-API mode)

Usage:
    python splusplus_api.py --detect
    python splusplus_api.py --configure
    python splusplus_api.py --validate
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict


@dataclass
class APIConfig:
    """LLM API configuration."""
    # OpenAI
    openai_enabled: bool = False
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4-turbo-preview"
    openai_cost_per_1k: float = 0.01  # Input cost
    
    # Anthropic
    anthropic_enabled: bool = False
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-opus-20240229"
    anthropic_cost_per_1k: float = 0.015
    
    # Ollama
    ollama_enabled: bool = False
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_fallback_model: str = "phi3:mini"
    
    # Priority order
    provider_priority: List[str] = field(default_factory=lambda: ["anthropic", "openai", "ollama"])
    
    # Feature flags
    auto_fallback: bool = True
    request_timeout: int = 60
    max_retries: int = 3


class APIDetector:
    """Detects available LLM APIs."""
    
    def __init__(self):
        self.home = Path.home()
        self.splusplus_home = self.home / ".splusplus"
        self.config: Optional[APIConfig] = None
    
    def detect_all(self) -> APIConfig:
        """Detect all available APIs."""
        print("🔍 Detecting LLM APIs...")
        
        self.config = APIConfig()
        
        self._detect_openai()
        self._detect_anthropic()
        self._detect_ollama()
        
        # Determine priority based on availability
        self._set_priority()
        
        return self.config
    
    def _detect_openai(self):
        """Detect OpenAI API key."""
        # Check environment
        api_key = os.getenv("OPENAI_API_KEY")
        
        # Check file
        if not api_key:
            key_file = self.home / ".openai" / "key"
            if key_file.exists():
                api_key = key_file.read_text().strip()
        
        if api_key:
            self.config.openai_enabled = True
            self.config.openai_api_key = api_key
            print("   ✅ OpenAI API key found")
            
            # Validate key
            if self._validate_openai(api_key):
                print("   ✅ OpenAI key validated")
            else:
                print("   ⚠️  OpenAI key validation failed")
        else:
            print("   ○ OpenAI API key not found")
    
    def _detect_anthropic(self):
        """Detect Anthropic API key."""
        # Check environment
        api_key = os.getenv("ANTHROPIC_API_KEY")
        
        # Check file
        if not api_key:
            key_file = self.home / ".anthropic" / "key"
            if key_file.exists():
                api_key = key_file.read_text().strip()
        
        if api_key:
            self.config.anthropic_enabled = True
            self.config.anthropic_api_key = api_key
            print("   ✅ Anthropic API key found")
            
            # Validate key
            if self._validate_anthropic(api_key):
                print("   ✅ Anthropic key validated")
            else:
                print("   ⚠️  Anthropic key validation failed")
        else:
            print("   ○ Anthropic API key not found")
    
    def _detect_ollama(self):
        """Detect Ollama installation."""
        import socket
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex(("localhost", 11434))
            sock.close()
            
            if result == 0:
                self.config.ollama_enabled = True
                print("   ✅ Ollama found on localhost:11434")
                
                # List available models
                models = self._list_ollama_models()
                if models:
                    print(f"   📦 Available models: {', '.join(models[:3])}")
                    # Select best available
                    self._select_ollama_model(models)
            else:
                print("   ○ Ollama not found")
                
        except Exception as e:
            print(f"   ○ Ollama not found: {e}")
    
    def _list_ollama_models(self) -> List[str]:
        """List available Ollama models."""
        try:
            import urllib.request
            import json
            
            req = urllib.request.Request(
                f"{self.config.ollama_host}/api/tags"
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                return [m.get("name", "") for m in data.get("models", [])]
                
        except Exception:
            return []
    
    def _select_ollama_model(self, models: List[str]):
        """Select best available Ollama model."""
        # Priority order for code generation
        preferred = ["codellama", "llama3.1", "mistral", "phi3", "llama2"]
        
        for pref in preferred:
            for model in models:
                if pref in model.lower():
                    self.config.ollama_model = model
                    return
        
        # Fallback to first available
        if models:
            self.config.ollama_model = models[0]
    
    def _validate_openai(self, api_key: str) -> bool:
        """Validate OpenAI API key."""
        try:
            import urllib.request
            import json
            
            req = urllib.request.Request(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
                
        except Exception:
            return False
    
    def _validate_anthropic(self, api_key: str) -> bool:
        """Validate Anthropic API key."""
        try:
            import urllib.request
            import json
            
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                }
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
                
        except Exception:
            return False
    
    def _set_priority(self):
        """Set provider priority based on availability."""
        priority = []
        
        if self.config.anthropic_enabled:
            priority.append("anthropic")
        if self.config.openai_enabled:
            priority.append("openai")
        if self.config.ollama_enabled:
            priority.append("ollama")
        
        if priority:
            self.config.provider_priority = priority
        
        print(f"   📊 Provider priority: {' > '.join(priority) if priority else 'None (fallback mode)'}")


class APIConfigurator:
    """Configures S++ API settings."""
    
    def __init__(self, config: APIConfig):
        self.config = config
        self.home = Path.home()
        self.splusplus_home = self.home / ".splusplus"
    
    def interactive_setup(self) -> APIConfig:
        """Interactive API configuration."""
        print("\n🤖 LLM API Configuration")
        print("="*60)
        
        # OpenAI
        if not self.config.openai_enabled:
            print("\n📡 OpenAI Configuration")
            key = input("   Enter OpenAI API key (or press Enter to skip): ").strip()
            if key:
                self.config.openai_enabled = True
                self.config.openai_api_key = key
                
                model = input("   Model [gpt-4-turbo-preview]: ").strip()
                if model:
                    self.config.openai_model = model
        
        # Anthropic
        if not self.config.anthropic_enabled:
            print("\n📡 Anthropic Configuration")
            key = input("   Enter Anthropic API key (or press Enter to skip): ").strip()
            if key:
                self.config.anthropic_enabled = True
                self.config.anthropic_api_key = key
                
                model = input("   Model [claude-3-opus-20240229]: ").strip()
                if model:
                    self.config.anthropic_model = model
        
        # Ollama
        if not self.config.ollama_enabled:
            print("\n📡 Ollama Configuration")
            host = input("   Ollama host [http://localhost:11434]: ").strip()
            if host:
                self.config.ollama_host = host
                self.config.ollama_enabled = True
            elif input("   Enable Ollama? [y/N]: ").lower() == 'y':
                self.config.ollama_enabled = True
        
        # Priority
        print("\n📊 Provider Priority")
        available = []
        if self.config.openai_enabled:
            available.append("openai")
        if self.config.anthropic_enabled:
            available.append("anthropic")
        if self.config.ollama_enabled:
            available.append("ollama")
        
        if len(available) > 1:
            print(f"   Available: {', '.join(available)}")
            custom = input("   Enter priority order (comma-separated) or Enter for default: ").strip()
            if custom:
                self.config.provider_priority = [p.strip() for p in custom.split(",")]
        
        return self.config
    
    def save_config(self) -> Path:
        """Save API configuration."""
        self.splusplus_home.mkdir(parents=True, exist_ok=True)
        
        config_path = self.splusplus_home / "api_config.json"
        
        # Mask sensitive data
        config_dict = asdict(self.config)
        config_dict['openai_api_key_masked'] = "****" if self.config.openai_api_key else ""
        config_dict['anthropic_api_key_masked'] = "****" if self.config.anthropic_api_key else ""
        config_dict['openai_api_key'] = ""  # Don't store in plain JSON
        config_dict['anthropic_api_key'] = ""
        
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
        
        # Store keys securely
        if self.config.openai_api_key:
            self._secure_store("openai_key", self.config.openai_api_key)
        
        if self.config.anthropic_api_key:
            self._secure_store("anthropic_key", self.config.anthropic_api_key)
        
        print(f"💾 API configuration saved to: {config_path}")
        return config_path
    
    def _secure_store(self, key_name: str, value: str):
        """Securely store API key."""
        key_path = self.splusplus_home / ".keys"
        key_path.mkdir(exist_ok=True)
        
        key_file = key_path / key_name
        key_file.write_text(value)
        key_file.chmod(0o600)  # Owner read/write only


class APIValidator:
    """Validates API connectivity."""
    
    def __init__(self, config: APIConfig):
        self.config = config
    
    def validate_all(self) -> Dict[str, bool]:
        """Validate all configured APIs."""
        print("\n🔍 Validating API connectivity...")
        
        results = {}
        
        if self.config.openai_enabled:
            results['openai'] = self._validate_openai()
        
        if self.config.anthropic_enabled:
            results['anthropic'] = self._validate_anthropic()
        
        if self.config.ollama_enabled:
            results['ollama'] = self._validate_ollama()
        
        return results
    
    def _validate_openai(self) -> bool:
        """Validate OpenAI connectivity."""
        try:
            import urllib.request
            
            req = urllib.request.Request(
                f"{self.config.openai_base_url}/models",
                headers={"Authorization": f"Bearer {self.config.openai_api_key}"}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print("   ✅ OpenAI: Connected")
                    return True
                    
        except Exception as e:
            print(f"   ❌ OpenAI: {e}")
            return False
        
        return False
    
    def _validate_anthropic(self) -> bool:
        """Validate Anthropic connectivity."""
        try:
            import urllib.request
            
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": self.config.anthropic_api_key,
                    "anthropic-version": "2023-06-01"
                }
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print("   ✅ Anthropic: Connected")
                    return True
                    
        except Exception as e:
            print(f"   ❌ Anthropic: {e}")
            return False
        
        return False
    
    def _validate_ollama(self) -> bool:
        """Validate Ollama connectivity."""
        try:
            import urllib.request
            
            req = urllib.request.Request(
                f"{self.config.ollama_host}/api/tags"
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    print("   ✅ Ollama: Connected")
                    return True
                    
        except Exception as e:
            print(f"   ❌ Ollama: {e}")
            return False
        
        return False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="S++ API Configuration")
    parser.add_argument("--detect", action="store_true", help="Detect APIs")
    parser.add_argument("--configure", action="store_true", help="Interactive configuration")
    parser.add_argument("--validate", action="store_true", help="Validate connectivity")
    parser.add_argument("--save", action="store_true", help="Save configuration")
    
    args = parser.parse_args()
    
    if args.detect:
        detector = APIDetector()
        config = detector.detect_all()
        
        print("\n📋 Detection Summary:")
        print(f"   OpenAI: {'✅' if config.openai_enabled else '❌'}")
        print(f"   Anthropic: {'✅' if config.anthropic_enabled else '❌'}")
        print(f"   Ollama: {'✅' if config.ollama_enabled else '❌'}")
        
        if args.save:
            configurator = APIConfigurator(config)
            configurator.save_config()
    
    elif args.configure:
        # Load existing or create new
        detector = APIDetector()
        config = detector.detect_all()
        
        configurator = APIConfigurator(config)
        config = configurator.interactive_setup()
        configurator.save_config()
    
    elif args.validate:
        # Load config
        config_path = Path.home() / ".splusplus" / "api_config.json"
        if not config_path.exists():
            print("❌ No API configuration found. Run --detect first.")
            sys.exit(1)
        
        with open(config_path) as f:
            config_dict = json.load(f)
        
        config = APIConfig(**config_dict)
        
        # Load keys
        keys_path = Path.home() / ".splusplus" / ".keys"
        if (keys_path / "openai_key").exists():
            config.openai_api_key = (keys_path / "openai_key").read_text().strip()
        if (keys_path / "anthropic_key").exists():
            config.anthropic_api_key = (keys_path / "anthropic_key").read_text().strip()
        
        validator = APIValidator(config)
        results = validator.validate_all()
        
        if not any(results.values()):
            print("\n⚠️  No APIs validated - system will use fallback templates")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
