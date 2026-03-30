#!/usr/bin/env python3
"""
Context Window Optimizer — Contextual Windowing Phase 2

Smart token-budgeted context selection.

Given a query and a token budget, selects the optimal subset of facts
to include in the LLM context window.

Algorithms:
1. Greedy: Highest scored facts until budget full
2. Diverse: Mix of categories to avoid redundancy
3. Clustered: Related facts grouped for context
4. Adaptive: Auto-detects query type and adjusts strategy

Usage:
    optimizer = ContextWindowOptimizer(token_budget=4000)
    
    # Find optimal window
    window = optimizer.find_optimal_window(
        query="How do I fix Stripe integration?",
        available_facts=['fact_1', 'fact_2', ...],
        strategy='adaptive'
    )
    
    # Estimate cost
    cost = optimizer.estimate_token_cost(['fact_1', 'fact_2'])
    
    # Cluster facts
    clusters = optimizer.cluster_facts_by_relevance(query, facts)
"""

import sqlite3
import json
import logging
import math
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/optimizer.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


class ContextWindowOptimizer:
    """Optimize fact selection for token-budgeted context windows."""
    
    def __init__(self, db_path: Path = None, token_budget: int = 4000):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        
        self.token_budget = token_budget
        self.headroom_ratio = 0.1  # Keep 10% headroom
        self.available_tokens = int(token_budget * (1 - self.headroom_ratio))
        
        # Token estimation
        self.avg_tokens_per_fact = 80
        self.overhead_tokens = 150  # System prompt, formatting, etc
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def estimate_token_cost(self, fact_ids: List[str]) -> int:
        """Estimate tokens needed for a set of facts."""
        cursor = self.conn.cursor()
        
        try:
            placeholders = ','.join(['?' * len(fact_ids)])
            cursor.execute(f"""
                SELECT SUM(LENGTH(content)) as total_chars
                FROM memory_facts
                WHERE id IN ({','.join(['?']*len(fact_ids))})
            """, fact_ids)
            
            row = cursor.fetchone()
            total_chars = row['total_chars'] or 0
            
            # Estimate: 1 token ≈ 4 chars + overhead
            estimated = (total_chars // 4) + (len(fact_ids) * 10) + self.overhead_tokens
            return estimated
            
        except Exception as e:
            logger_obj.error(f"Failed to estimate tokens: {e}")
            return self.avg_tokens_per_fact * len(fact_ids)
    
    def find_optimal_window(
        self,
        query: str,
        available_facts: List[str],
        strategy: str = 'adaptive'
    ) -> Dict:
        """
        Find optimal fact subset for query within token budget.
        
        Strategies:
        - 'greedy': Highest scored facts until budget full
        - 'diverse': Mix of categories
        - 'clustered': Related fact groups
        - 'adaptive': Auto-select based on query
        
        Returns:
            Dict with selected_facts, token_cost, strategy_used, etc
        """
        if not available_facts:
            return {
                'selected_facts': [],
                'token_cost': 0,
                'available_tokens': self.available_tokens,
                'strategy': strategy,
                'status': 'empty'
            }
        
        try:
            if strategy == 'adaptive':
                # Detect query type and pick strategy
                strategy = self._detect_strategy(query)
                logger_obj.info(f"Adaptive strategy selected: {strategy}")
            
            if strategy == 'greedy':
                selected = self._greedy_selection(available_facts)
            elif strategy == 'diverse':
                selected = self._diverse_selection(available_facts)
            elif strategy == 'clustered':
                selected = self._clustered_selection(available_facts)
            else:
                selected = self._greedy_selection(available_facts)
            
            token_cost = self.estimate_token_cost(selected)
            
            # If over budget, prune
            while len(selected) > 0 and token_cost > self.available_tokens:
                selected = selected[:-1]
                token_cost = self.estimate_token_cost(selected)
            
            return {
                'selected_facts': selected,
                'token_cost': token_cost,
                'token_budget': self.token_budget,
                'available_tokens': self.available_tokens,
                'headroom': self.available_tokens - token_cost,
                'percentage_used': (token_cost / self.available_tokens) * 100,
                'strategy': strategy,
                'count': len(selected),
                'status': 'optimal' if token_cost <= self.available_tokens else 'pruned'
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to find optimal window: {e}")
            return {
                'error': str(e),
                'selected_facts': [],
                'token_cost': 0,
                'status': 'error'
            }
    
    def _detect_strategy(self, query: str) -> str:
        """Auto-detect best strategy based on query."""
        query_lower = query.lower()
        
        # Check for multi-topic queries
        if any(word in query_lower for word in ['vs', 'compare', 'difference', 'both']):
            return 'diverse'
        
        # Check for contextual/story queries
        if any(word in query_lower for word in ['why', 'what happened', 'history', 'flow']):
            return 'clustered'
        
        # Default: greedy (most relevant)
        return 'greedy'
    
    def _greedy_selection(self, fact_ids: List[str]) -> List[str]:
        """Select facts greedily by relevance score."""
        cursor = self.conn.cursor()
        
        try:
            # Score each fact
            placeholders = ','.join(['?' * len(fact_ids)])
            cursor.execute(f"""
                SELECT 
                    id,
                    decay_weight,
                    referenced_count,
                    (decay_weight * (1 + LOG(MAX(1, referenced_count)))) as score
                FROM memory_facts
                WHERE id IN ({','.join(['?']*len(fact_ids))})
                ORDER BY score DESC
            """, fact_ids)
            
            scored = [(row['id'], row['score']) for row in cursor.fetchall()]
            
            selected = []
            cost = 0
            
            for fact_id, score in scored:
                fact_tokens = self.estimate_token_cost([fact_id])
                if cost + fact_tokens <= self.available_tokens:
                    selected.append(fact_id)
                    cost += fact_tokens
            
            logger_obj.info(f"Greedy selection: {len(selected)} facts")
            return selected
            
        except Exception as e:
            logger_obj.error(f"Greedy selection failed: {e}")
            return fact_ids[:5]  # Fallback
    
    def _diverse_selection(self, fact_ids: List[str]) -> List[str]:
        """Select diverse facts from different categories."""
        cursor = self.conn.cursor()
        
        try:
            # Group by category
            placeholders = ','.join(['?' * len(fact_ids)])
            cursor.execute(f"""
                SELECT 
                    category,
                    id,
                    decay_weight * (1 + LOG(MAX(1, referenced_count))) as score
                FROM memory_facts
                WHERE id IN ({','.join(['?']*len(fact_ids))})
                ORDER BY category, score DESC
            """, fact_ids)
            
            # Group by category
            by_category = defaultdict(list)
            for row in cursor.fetchall():
                by_category[row['category'] or 'uncategorized'].append(row['id'])
            
            # Select top from each category
            selected = []
            cost = 0
            max_per_category = max(1, len(fact_ids) // len(by_category))
            
            for category, facts in sorted(by_category.items()):
                for i, fact_id in enumerate(facts[:max_per_category]):
                    fact_tokens = self.estimate_token_cost([fact_id])
                    if cost + fact_tokens <= self.available_tokens:
                        selected.append(fact_id)
                        cost += fact_tokens
            
            logger_obj.info(f"Diverse selection: {len(selected)} facts from {len(by_category)} categories")
            return selected
            
        except Exception as e:
            logger_obj.error(f"Diverse selection failed: {e}")
            return fact_ids[:5]
    
    def _clustered_selection(self, fact_ids: List[str]) -> List[str]:
        """Select clustered facts that appear together."""
        cursor = self.conn.cursor()
        
        try:
            # Build co-occurrence graph
            graph = defaultdict(list)
            for fact_id in fact_ids:
                cursor.execute("""
                    SELECT 
                        CASE 
                            WHEN fact_id_1 = ? THEN fact_id_2
                            ELSE fact_id_1
                        END as other_fact,
                        co_occurrence_count
                    FROM co_access_patterns
                    WHERE (fact_id_1 = ? OR fact_id_2 = ?)
                    ORDER BY co_occurrence_count DESC
                    LIMIT 3
                """, (fact_id, fact_id, fact_id))
                
                for row in cursor.fetchall():
                    if row['other_fact'] in fact_ids:
                        graph[fact_id].append(row['other_fact'])
            
            # Find clusters using greedy grouping
            visited = set()
            clusters = []
            
            for start_fact in fact_ids:
                if start_fact in visited:
                    continue
                
                cluster = [start_fact]
                visited.add(start_fact)
                to_explore = list(graph[start_fact])
                
                while to_explore and len(cluster) < 4:
                    next_fact = to_explore.pop(0)
                    if next_fact not in visited:
                        cluster.append(next_fact)
                        visited.add(next_fact)
                        to_explore.extend(graph[next_fact])
                
                clusters.append(cluster)
            
            # Select clusters that fit budget
            selected = []
            cost = 0
            
            for cluster in clusters:
                cluster_cost = self.estimate_token_cost(cluster)
                if cost + cluster_cost <= self.available_tokens:
                    selected.extend(cluster)
                    cost += cluster_cost
            
            logger_obj.info(f"Clustered selection: {len(selected)} facts in {len(clusters)} clusters")
            return selected
            
        except Exception as e:
            logger_obj.error(f"Clustered selection failed: {e}")
            return fact_ids[:5]
    
    def cluster_facts_by_relevance(
        self,
        query: str,
        facts: List[str]
    ) -> Dict:
        """
        Cluster facts by relevance to query.
        
        Returns:
            Dict with 'primary', 'supporting', 'background' clusters
        """
        cursor = self.conn.cursor()
        
        try:
            # Get reference stats for each fact
            placeholders = ','.join(['?' * len(facts)])
            cursor.execute(f"""
                SELECT 
                    mf.id,
                    mf.decay_weight,
                    COUNT(fr.fact_id) as ref_count,
                    AVG(fr.relevance_score) as avg_relevance
                FROM memory_facts mf
                LEFT JOIN fact_references fr ON mf.id = fr.fact_id
                WHERE mf.id IN ({','.join(['?']*len(facts))})
                GROUP BY mf.id
                ORDER BY mf.decay_weight DESC
            """, facts)
            
            scored_facts = [
                {
                    'id': row['id'],
                    'decay': row['decay_weight'],
                    'ref_count': row['ref_count'] or 0,
                    'avg_relevance': row['avg_relevance'] or 0.5
                }
                for row in cursor.fetchall()
            ]
            
            # Cluster by relevance score
            total = len(scored_facts)
            primary_count = max(1, total // 3)
            supporting_count = max(1, total // 3)
            
            primary = [f['id'] for f in scored_facts[:primary_count]]
            supporting = [f['id'] for f in scored_facts[primary_count:primary_count+supporting_count]]
            background = [f['id'] for f in scored_facts[primary_count+supporting_count:]]
            
            return {
                'query': query,
                'primary': primary,
                'supporting': supporting,
                'background': background,
                'total': len(scored_facts)
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to cluster facts: {e}")
            return {
                'error': str(e),
                'primary': [],
                'supporting': [],
                'background': []
            }
    
    def get_efficiency_report(self) -> Dict:
        """Get report on token budget efficiency."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_facts,
                    SUM(LENGTH(content)) as total_chars,
                    AVG(LENGTH(content)) as avg_chars,
                    MIN(decay_weight) as min_decay,
                    MAX(decay_weight) as max_decay,
                    AVG(decay_weight) as avg_decay
                FROM memory_facts
            """)
            
            row = cursor.fetchone()
            
            total_chars = row['total_chars'] or 0
            avg_fact_chars = row['avg_chars'] or 0
            total_facts = row['total_facts'] or 0
            
            # Estimate if all facts fit
            all_facts_tokens = (total_chars // 4) + (total_facts * 10)
            fits_in_budget = all_facts_tokens <= self.available_tokens
            
            return {
                'total_facts': total_facts,
                'total_characters': total_chars,
                'average_fact_chars': avg_fact_chars,
                'average_fact_tokens': self.avg_tokens_per_fact,
                'all_facts_estimated_tokens': all_facts_tokens,
                'available_tokens': self.available_tokens,
                'all_facts_fit': fits_in_budget,
                'max_facts_in_budget': self.available_tokens // self.avg_tokens_per_fact,
                'efficiency_percent': (all_facts_tokens / self.available_tokens * 100) if self.available_tokens else 0
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get efficiency report: {e}")
            return {}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Context Window Optimizer")
    parser.add_argument('--optimize', metavar='QUERY',
                        help='Optimize context for query')
    parser.add_argument('--facts', nargs='+', metavar='FACT_ID',
                        help='Available facts')
    parser.add_argument('--budget', type=int, default=4000,
                        help='Token budget (default: 4000)')
    parser.add_argument('--strategy', choices=['greedy', 'diverse', 'clustered', 'adaptive'],
                        default='adaptive', help='Selection strategy')
    parser.add_argument('--estimate', nargs='+', metavar='FACT_ID',
                        help='Estimate token cost')
    parser.add_argument('--cluster', metavar='QUERY',
                        help='Cluster facts by relevance')
    parser.add_argument('--report', action='store_true',
                        help='Get efficiency report')
    
    args = parser.parse_args()
    
    optimizer = ContextWindowOptimizer(token_budget=args.budget)
    
    try:
        if args.optimize and args.facts:
            window = optimizer.find_optimal_window(args.optimize, args.facts, args.strategy)
            print(f"\n✓ Optimized context window:")
            print(f"  Strategy: {window['strategy']}")
            print(f"  Selected: {window['count']} facts")
            print(f"  Token cost: {window['token_cost']} / {window['available_tokens']}")
            print(f"  Usage: {window['percentage_used']:.1f}%")
            print(f"  Status: {window['status']}")
        
        elif args.estimate:
            cost = optimizer.estimate_token_cost(args.estimate)
            print(f"\n✓ Token cost estimate:")
            print(f"  Facts: {len(args.estimate)}")
            print(f"  Estimated tokens: {cost}")
        
        elif args.cluster and args.facts:
            clusters = optimizer.cluster_facts_by_relevance(args.cluster, args.facts)
            print(f"\n✓ Fact clusters by relevance:")
            print(f"  Primary ({len(clusters['primary'])}): {', '.join(clusters['primary'][:3])}...")
            print(f"  Supporting ({len(clusters['supporting'])}): {', '.join(clusters['supporting'][:3])}...")
            print(f"  Background ({len(clusters['background'])}): {', '.join(clusters['background'][:3])}...")
        
        elif args.report:
            report = optimizer.get_efficiency_report()
            print(f"\n✓ Token budget efficiency report:")
            for key, val in report.items():
                print(f"  {key}: {val}")
    
    finally:
        optimizer.close()


if __name__ == '__main__':
    main()
