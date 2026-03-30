#!/usr/bin/env python3
"""
Phase 11: Agent Adapter
Wrapper para que agentes soliciten contexto y reporten costos.

Propósito:
- Abstracción para agentes (Falcon/Katsumi/LEO/NOVA/ARIA)
- Solicita contexto a Paperclip Memory API
- Reporta tokens y costos después de ejecución
- Maneja re-intentos y fallbacks

Uso por agent:
    adapter = AgentAdapter(
        agent_id="uuid",
        company_id="uuid",
        api_base="http://paperclip:3100"
    )
    
    # Solicita contexto
    context = adapter.get_context("campaign strategy")
    
    # Usa context en tu lógica
    response = my_agent_logic(context.facts)
    
    # Reporta cost
    adapter.report_cost(
        tokens_used=response.tokens,
        cost_cents=response.cost_cents
    )

Integración:
    • Falcon (director) → solicita contexto macro
    • Katsumi (hub) → coordina contexto multi-agent
    • LEO (center) → contexto operativo
    • NOVA/ARIA (support) → contexto específico de domain

Flujo de resiliencia:
    1. Intenta GET /api/agents/{id}/context?query=X
    2. Si falla → usar cache local
    3. Si cache vacío → usar minimal context
    4. Reporta falla a telemetría
"""

import requests
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import sqlite3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/agent-adapter.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)


@dataclass
class ContextFact:
    """A single fact from Memory Engine."""
    id: str
    content: str
    source: str
    score: float
    tokens: int


@dataclass
class MemoryContext:
    """Context delivered by Memory Engine."""
    agent_id: str
    timestamp: str
    facts: List[ContextFact]
    total_tokens: int
    source_mode: str  # surface_only | hybrid | retriever_only
    metadata: Dict[str, Any]
    
    def __post_init__(self):
        # Convert dict facts to ContextFact objects
        if self.facts and isinstance(self.facts[0], dict):
            self.facts = [ContextFact(**f) for f in self.facts]


@dataclass
class CostReport:
    """Cost report from agent execution."""
    agent_id: str
    company_id: str
    tokens_used: int
    cost_cents: int
    model: str
    execution_time_seconds: float
    success: bool


class AgentAdapter:
    """
    Adapter for agents to interact with Memory Engine via Paperclip API.
    
    Handles:
    - Context retrieval with retries and fallback
    - Cost reporting
    - Local cache for offline operation
    - Telemetry and error reporting
    """
    
    def __init__(
        self,
        agent_id: str,
        company_id: str,
        api_base: str = "http://localhost:3100",
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        timeout_seconds: int = 10,
        retry_attempts: int = 3,
        retry_delay_seconds: float = 0.5
    ):
        self.agent_id = agent_id
        self.company_id = company_id
        self.api_base = api_base.rstrip('/')
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.retry_delay_seconds = retry_delay_seconds
        
        # Cache directory
        self.cache_dir = cache_dir or Path.home() / '.hermes/memory-engine/agent-cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Metrics
        self.context_requests_total = 0
        self.context_requests_succeeded = 0
        self.context_requests_failed = 0
        self.total_tokens_received = 0
        self.total_costs_reported_cents = 0
        
        logger_obj.info(f"AgentAdapter initialized for {agent_id}")
    
    def get_context(
        self,
        query: str,
        max_tokens: int = 3000,
        use_cache: bool = True,
        fallback_to_cache: bool = True
    ) -> MemoryContext:
        """
        Get context from Memory Engine.
        
        Args:
            query: Query string
            max_tokens: Token budget
            use_cache: Whether to save to local cache
            fallback_to_cache: Fall back to cache if API fails
        
        Returns:
            MemoryContext with facts
        """
        self.context_requests_total += 1
        
        # Try API first
        try:
            context = self._fetch_context_from_api(query, max_tokens)
            self.context_requests_succeeded += 1
            self.total_tokens_received += context.total_tokens
            
            # Cache successful response
            if use_cache:
                self._cache_context(query, context)
            
            logger_obj.info(
                f"Got context for '{query}': "
                f"{len(context.facts)} facts, {context.total_tokens} tokens"
            )
            return context
        
        except Exception as e:
            self.context_requests_failed += 1
            logger_obj.warning(f"Failed to fetch context: {e}")
            
            # Fall back to cache
            if fallback_to_cache:
                cached = self._load_cached_context(query)
                if cached:
                    logger_obj.info(f"Using cached context for '{query}'")
                    return cached
            
            # Last resort: empty context
            logger_obj.error(f"No context available for '{query}'")
            return MemoryContext(
                agent_id=self.agent_id,
                timestamp=datetime.now().isoformat(),
                facts=[],
                total_tokens=0,
                source_mode="retriever_only",
                metadata={"error": "no_context_available"}
            )
    
    def _fetch_context_from_api(
        self,
        query: str,
        max_tokens: int
    ) -> MemoryContext:
        """Fetch context from Paperclip API with retries."""
        
        for attempt in range(self.retry_attempts):
            try:
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                response = requests.get(
                    f"{self.api_base}/api/agents/{self.agent_id}/context",
                    params={
                        'query': query,
                        'maxTokens': max_tokens
                    },
                    headers=headers,
                    timeout=self.timeout_seconds
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return MemoryContext(
                        agent_id=data['agentId'],
                        timestamp=data['timestamp'],
                        facts=data['facts'],
                        total_tokens=data['totalTokens'],
                        source_mode=data['sourceMode'],
                        metadata=data['metadata']
                    )
                
                elif response.status_code == 404:
                    raise ValueError(f"Agent not found: {self.agent_id}")
                
                elif response.status_code == 403:
                    raise PermissionError(f"Access denied to context")
                
                else:
                    raise RuntimeError(
                        f"API error {response.status_code}: {response.text}"
                    )
            
            except requests.Timeout:
                if attempt < self.retry_attempts - 1:
                    logger_obj.debug(f"Timeout (attempt {attempt + 1}), retrying...")
                    time.sleep(self.retry_delay_seconds * (attempt + 1))
                else:
                    raise
            
            except requests.RequestException as e:
                if attempt < self.retry_attempts - 1:
                    logger_obj.debug(f"Request error (attempt {attempt + 1}), retrying...")
                    time.sleep(self.retry_delay_seconds * (attempt + 1))
                else:
                    raise
        
        raise RuntimeError("All retry attempts failed")
    
    def acknowledge_context(
        self,
        context_id: str,
        useful: bool,
        facts_used: List[str] = None
    ) -> bool:
        """
        Send feedback about context usefulness.
        Used by Evolution Engine to improve rankings.
        """
        try:
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            
            response = requests.post(
                f"{self.api_base}/api/agents/{self.agent_id}/context/acknowledge",
                json={
                    'contextId': context_id,
                    'useful': useful,
                    'factsUsed': facts_used or []
                },
                headers=headers,
                timeout=self.timeout_seconds
            )
            
            if response.status_code == 200:
                logger_obj.info(f"Acknowledged context {context_id}")
                return True
            else:
                logger_obj.warning(f"Failed to acknowledge context: {response.status_code}")
                return False
        
        except Exception as e:
            logger_obj.error(f"Error acknowledging context: {e}")
            return False
    
    def report_cost(
        self,
        tokens_used: int,
        cost_cents: int,
        model: str = "claude-haiku",
        execution_time_seconds: float = 0.0,
        success: bool = True
    ) -> bool:
        """
        Report token usage and cost.
        
        Args:
            tokens_used: Tokens consumed
            cost_cents: Cost in cents
            model: Model used
            execution_time_seconds: How long execution took
            success: Whether execution was successful
        
        Returns:
            True if reported successfully
        """
        self.total_costs_reported_cents += cost_cents
        
        try:
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            
            response = requests.post(
                f"{self.api_base}/api/cost-events",
                json={
                    'agentId': self.agent_id,
                    'companyId': self.company_id,
                    'tokensUsed': tokens_used,
                    'costCents': cost_cents,
                    'model': model
                },
                headers=headers,
                timeout=self.timeout_seconds
            )
            
            if response.status_code == 201:
                logger_obj.info(
                    f"Reported cost: {tokens_used} tokens, {cost_cents}¢ "
                    f"(exec time: {execution_time_seconds:.2f}s)"
                )
                return True
            else:
                logger_obj.error(f"Failed to report cost: {response.status_code}")
                # Still return True to not block agent
                return True
        
        except Exception as e:
            logger_obj.error(f"Error reporting cost: {e}")
            # Still return True to not block agent
            return True
    
    # ─────────────────────────────────────────────────────────────────
    # Caching
    # ─────────────────────────────────────────────────────────────────
    
    def _cache_context(self, query: str, context: MemoryContext) -> None:
        """Cache context to disk."""
        try:
            query_hash = hash(query) & 0x7fffffff  # Positive hash
            cache_file = self.cache_dir / f"context_{query_hash}.json"
            
            cache_data = {
                'query': query,
                'timestamp': context.timestamp,
                'facts': [asdict(f) for f in context.facts],
                'total_tokens': context.total_tokens,
                'source_mode': context.source_mode,
                'metadata': context.metadata
            }
            
            cache_file.write_text(json.dumps(cache_data, indent=2))
            logger_obj.debug(f"Cached context to {cache_file}")
        
        except Exception as e:
            logger_obj.warning(f"Failed to cache context: {e}")
    
    def _load_cached_context(self, query: str) -> Optional[MemoryContext]:
        """Load context from cache."""
        try:
            query_hash = hash(query) & 0x7fffffff
            cache_file = self.cache_dir / f"context_{query_hash}.json"
            
            if not cache_file.exists():
                return None
            
            # Check age (use if < 24h old)
            age_seconds = time.time() - cache_file.stat().st_mtime
            if age_seconds > 86400:  # 24 hours
                logger_obj.debug(f"Cache too old: {age_seconds}s")
                return None
            
            cache_data = json.loads(cache_file.read_text())
            return MemoryContext(
                agent_id=self.agent_id,
                timestamp=cache_data['timestamp'],
                facts=cache_data['facts'],
                total_tokens=cache_data['total_tokens'],
                source_mode=cache_data['source_mode'],
                metadata=cache_data['metadata']
            )
        
        except Exception as e:
            logger_obj.debug(f"Failed to load cache: {e}")
            return None
    
    # ─────────────────────────────────────────────────────────────────
    # Metrics & Health
    # ─────────────────────────────────────────────────────────────────
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get adapter metrics."""
        return {
            'agent_id': self.agent_id,
            'context_requests': {
                'total': self.context_requests_total,
                'succeeded': self.context_requests_succeeded,
                'failed': self.context_requests_failed,
                'success_rate': (
                    self.context_requests_succeeded / max(self.context_requests_total, 1)
                )
            },
            'tokens': {
                'total_received': self.total_tokens_received,
                'average_per_request': (
                    self.total_tokens_received / max(self.context_requests_succeeded, 1)
                )
            },
            'costs': {
                'total_reported_cents': self.total_costs_reported_cents,
                'total_reported_dollars': self.total_costs_reported_cents / 100.0
            }
        }
    
    def health_check(self) -> bool:
        """Quick health check."""
        try:
            response = requests.get(
                f"{self.api_base}/api/health",
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False


def main():
    """Demo usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Agent Adapter")
    parser.add_argument('--agent-id', required=True, help='Agent UUID')
    parser.add_argument('--company-id', required=True, help='Company UUID')
    parser.add_argument('--api', default='http://localhost:3100', help='API base URL')
    
    subparsers = parser.add_subparsers(dest='command')
    
    # Get context
    context_parser = subparsers.add_parser('context')
    context_parser.add_argument('--query', required=True, help='Query string')
    context_parser.add_argument('--max-tokens', type=int, default=3000)
    
    # Report cost
    cost_parser = subparsers.add_parser('cost')
    cost_parser.add_argument('--tokens', type=int, required=True)
    cost_parser.add_argument('--cents', type=int, required=True)
    cost_parser.add_argument('--model', default='claude-haiku')
    
    # Health
    health_parser = subparsers.add_parser('health')
    
    # Metrics
    metrics_parser = subparsers.add_parser('metrics')
    
    args = parser.parse_args()
    
    adapter = AgentAdapter(
        agent_id=args.agent_id,
        company_id=args.company_id,
        api_base=args.api
    )
    
    try:
        if args.command == 'context':
            context = adapter.get_context(args.query, args.max_tokens)
            print(f"\n✓ Context for '{args.query}':")
            print(f"  Facts: {len(context.facts)}")
            print(f"  Tokens: {context.total_tokens}")
            print(f"  Mode: {context.source_mode}")
            for fact in context.facts[:3]:
                print(f"    • {fact.content[:60]}... (score={fact.score:.2f})")
        
        elif args.command == 'cost':
            success = adapter.report_cost(args.tokens, args.cents, args.model)
            print(f"\n✓ Cost reported: {args.tokens} tokens, {args.cents}¢")
        
        elif args.command == 'health':
            healthy = adapter.health_check()
            print(f"\n✓ Health: {'OK' if healthy else 'FAIL'}")
        
        elif args.command == 'metrics':
            metrics = adapter.get_metrics()
            print(f"\n✓ Metrics:")
            print(json.dumps(metrics, indent=2))
    
    finally:
        metrics = adapter.get_metrics()
        logger_obj.info(f"Session metrics: {json.dumps(metrics)}")


if __name__ == '__main__':
    main()
