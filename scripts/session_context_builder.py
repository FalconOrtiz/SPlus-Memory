#!/usr/bin/env python3
"""
Session Context Builder — Contextual Windowing Phase 2

Reconstructs conversation context from fact clusters.

Capabilities:
1. Reconstruct multi-fact conversations
2. Build coherent fact orderings (topic flow)
3. Identify context gaps
4. Estimate token costs for fact sets
5. Suggest complementary facts

Usage:
    builder = SessionContextBuilder()
    
    # Reconstruct from facts
    context = builder.reconstruct_from_facts([
        'fact_123',
        'fact_456',
        'fact_789'
    ])
    
    # Find related facts
    related = builder.find_related_facts('fact_123', depth=2)
    
    # Estimate context size
    cost = builder.estimate_context_size(['fact_123', 'fact_456'])
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/context-builder.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


class SessionContextBuilder:
    """Build coherent context from fact clusters."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        
        # Token estimation parameters
        self.avg_tokens_per_fact = 80  # Average tokens per fact
        self.separator_tokens = 20  # Tokens for separators/formatting
    
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
    
    def get_fact_details(self, fact_id: str) -> Optional[Dict]:
        """Get full details for a fact."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    id, content, source, created_at, decay_weight,
                    freshness_tier, referenced_count, category, fact_type
                FROM memory_facts
                WHERE id = ?
            """, (fact_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
            
        except Exception as e:
            logger_obj.error(f"Failed to get fact details: {e}")
            return None
    
    def reconstruct_from_facts(
        self,
        fact_ids: List[str],
        order_by: str = 'relevance'
    ) -> Dict:
        """
        Reconstruct conversation context from facts.
        
        Orders facts by:
        - 'relevance': freshness + decay weight
        - 'temporal': creation time
        - 'frequency': how often referenced together
        - 'topical': semantic clustering
        
        Returns:
            Ordered facts with context metadata
        """
        cursor = self.conn.cursor()
        
        try:
            # Get all fact details
            facts = []
            for fact_id in fact_ids:
                detail = self.get_fact_details(fact_id)
                if detail:
                    facts.append(detail)
            
            if not facts:
                logger_obj.warning(f"No facts found in {fact_ids}")
                return {'error': 'No facts found', 'facts': []}
            
            # Order facts based on strategy
            if order_by == 'temporal':
                facts.sort(key=lambda f: f['created_at'])
            elif order_by == 'frequency':
                # Get reference counts
                fact_ids_str = ','.join([f"'{f['id']}'" for f in facts])
                cursor.execute(f"""
                    SELECT fact_id, COUNT(*) as ref_count
                    FROM fact_references
                    WHERE fact_id IN ({fact_ids_str})
                    GROUP BY fact_id
                """)
                ref_counts = {row['fact_id']: row['ref_count'] for row in cursor.fetchall()}
                facts.sort(key=lambda f: ref_counts.get(f['id'], 0), reverse=True)
            else:  # 'relevance' (default)
                facts.sort(key=lambda f: (
                    f['decay_weight'],
                    f['referenced_count']
                ), reverse=True)
            
            # Build context
            context = {
                'facts': facts,
                'total_facts': len(facts),
                'order_by': order_by,
                'timestamp': datetime.now().isoformat(),
                'context_summary': self._generate_summary(facts)
            }
            
            logger_obj.info(f"Reconstructed context from {len(facts)} facts (order: {order_by})")
            return context
            
        except Exception as e:
            logger_obj.error(f"Failed to reconstruct context: {e}")
            return {'error': str(e), 'facts': []}
    
    def _generate_summary(self, facts: List[Dict]) -> str:
        """Generate brief summary of fact cluster."""
        if not facts:
            return ""
        
        # Get categories
        categories = [f.get('category', 'general') for f in facts]
        unique_categories = set(categories)
        
        # Get sources
        sources = set(f.get('source', 'unknown') for f in facts)
        
        summary = f"{len(facts)} facts from {len(unique_categories)} categories"
        if len(sources) <= 3:
            summary += f" (sources: {', '.join(sources)})"
        
        return summary
    
    def find_related_facts(
        self,
        fact_id: str,
        depth: int = 2,
        max_facts: int = 10
    ) -> Dict:
        """
        Find facts related to a given fact.
        
        Explores:
        1. Direct co-occurrences (depth 1)
        2. Co-occurrences of co-occurrences (depth 2)
        3. Temporal neighbors
        
        Returns:
            Dict with fact_id, related_facts (ordered by relevance), depth_reached
        """
        cursor = self.conn.cursor()
        visited = set()
        results_by_depth = defaultdict(list)
        current_level = {fact_id}
        
        try:
            for current_depth in range(depth):
                next_level = set()
                
                for fid in current_level:
                    if fid in visited:
                        continue
                    visited.add(fid)
                    
                    # Get co-occurrences
                    cursor.execute("""
                        SELECT 
                            CASE 
                                WHEN fact_id_1 = ? THEN fact_id_2
                                ELSE fact_id_1
                            END as related_fact,
                            co_occurrence_count
                        FROM co_access_patterns
                        WHERE (fact_id_1 = ? OR fact_id_2 = ?)
                        ORDER BY co_occurrence_count DESC
                        LIMIT ?
                    """, (fid, fid, fid, max_facts // (current_depth + 1)))
                    
                    for row in cursor.fetchall():
                        related_id = row['related_fact']
                        if related_id not in visited:
                            detail = self.get_fact_details(related_id)
                            if detail:
                                results_by_depth[current_depth + 1].append({
                                    'fact': detail,
                                    'co_occurrence_count': row['co_occurrence_count'],
                                    'depth': current_depth + 1
                                })
                                next_level.add(related_id)
                
                current_level = next_level
                if not current_level:
                    break
            
            # Flatten and sort by relevance
            all_related = []
            for depth_results in results_by_depth.values():
                all_related.extend(depth_results)
            
            all_related.sort(key=lambda x: (
                x['depth'],
                -x['co_occurrence_count']
            ))
            
            return {
                'fact_id': fact_id,
                'related_facts': all_related[:max_facts],
                'total_found': len(all_related),
                'depth_reached': max(results_by_depth.keys()) if results_by_depth else 0
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to find related facts: {e}")
            return {
                'fact_id': fact_id,
                'related_facts': [],
                'error': str(e)
            }
    
    def estimate_context_size(
        self,
        fact_ids: List[str],
        estimate_type: str = 'tokens'
    ) -> Dict:
        """
        Estimate size of context for fact set.
        
        Args:
            fact_ids: Facts to estimate
            estimate_type: 'tokens', 'chars', 'lines'
        
        Returns:
            Size estimate with breakdown
        """
        cursor = self.conn.cursor()
        
        try:
            # Get content for all facts
            placeholders = ','.join(['?' * len(fact_ids)])
            cursor.execute(f"""
                SELECT id, content
                FROM memory_facts
                WHERE id IN ({','.join(['?']*len(fact_ids))})
            """, fact_ids)
            
            total_chars = 0
            total_lines = 0
            found_facts = 0
            
            for row in cursor.fetchall():
                content = row['content'] or ""
                total_chars += len(content)
                total_lines += content.count('\n') + 1
                found_facts += 1
            
            # Estimate tokens (rough: 1 token ≈ 4 chars)
            estimated_tokens = (total_chars // 4) + (found_facts * self.separator_tokens)
            
            estimates = {
                'estimate_type': estimate_type,
                'total_facts': len(fact_ids),
                'found_facts': found_facts,
                'total_characters': total_chars,
                'total_lines': total_lines,
            }
            
            if estimate_type == 'tokens' or estimate_type == 'all':
                estimates['estimated_tokens'] = estimated_tokens
            
            logger_obj.info(f"Estimated {estimated_tokens} tokens for {len(fact_ids)} facts")
            return estimates
            
        except Exception as e:
            logger_obj.error(f"Failed to estimate context size: {e}")
            return {
                'error': str(e),
                'total_facts': len(fact_ids),
                'found_facts': 0
            }
    
    def suggest_complementary_facts(
        self,
        fact_ids: List[str],
        gap_threshold: float = 0.5
    ) -> List[Dict]:
        """
        Suggest facts that would fill gaps in a context.
        
        Identifies topics covered by current facts and suggests
        facts from complementary categories.
        """
        cursor = self.conn.cursor()
        
        try:
            # Get categories of current facts
            placeholders = ','.join(['?' * len(fact_ids)])
            cursor.execute(f"""
                SELECT DISTINCT category
                FROM memory_facts
                WHERE id IN ({','.join(['?']*len(fact_ids))})
            """, fact_ids)
            
            current_categories = {row['category'] for row in cursor.fetchall() if row['category']}
            
            # Find complementary categories
            cursor.execute("""
                SELECT DISTINCT category
                FROM memory_facts
                WHERE category IS NOT NULL
                LIMIT 10
            """)
            
            all_categories = {row['category'] for row in cursor.fetchall()}
            missing_categories = all_categories - current_categories
            
            # Get top facts from missing categories
            suggestions = []
            for category in missing_categories:
                cursor.execute("""
                    SELECT id, content, decay_weight, referenced_count
                    FROM memory_facts
                    WHERE category = ?
                    ORDER BY decay_weight * referenced_count DESC
                    LIMIT 1
                """, (category,))
                
                row = cursor.fetchone()
                if row:
                    suggestions.append({
                        'fact_id': row['id'],
                        'content': row['content'][:100],
                        'category': category,
                        'relevance': row['decay_weight']
                    })
            
            logger_obj.info(f"Suggested {len(suggestions)} complementary facts")
            return suggestions
            
        except Exception as e:
            logger_obj.error(f"Failed to suggest complementary facts: {e}")
            return []
    
    def build_conversation_flow(
        self,
        fact_ids: List[str]
    ) -> Dict:
        """
        Build coherent conversation flow from facts.
        
        Arranges facts to tell a story/follow logical progression.
        """
        # Reconstruct with different strategies
        by_relevance = self.reconstruct_from_facts(fact_ids, 'relevance')
        by_temporal = self.reconstruct_from_facts(fact_ids, 'temporal')
        by_frequency = self.reconstruct_from_facts(fact_ids, 'frequency')
        
        return {
            'fact_count': len(fact_ids),
            'strategies': {
                'relevance_order': by_relevance['facts'],
                'temporal_order': by_temporal['facts'],
                'frequency_order': by_frequency['facts']
            },
            'recommended': by_relevance['facts'],  # Default recommendation
            'timestamp': datetime.now().isoformat()
        }


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Session Context Builder")
    parser.add_argument('--reconstruct', nargs='+', metavar='FACT_ID',
                        help='Reconstruct context from facts')
    parser.add_argument('--order-by', choices=['relevance', 'temporal', 'frequency'],
                        default='relevance', help='Ordering strategy')
    parser.add_argument('--find-related', metavar='FACT_ID',
                        help='Find related facts')
    parser.add_argument('--depth', type=int, default=2,
                        help='Relationship depth')
    parser.add_argument('--estimate', nargs='+', metavar='FACT_ID',
                        help='Estimate context size')
    parser.add_argument('--suggest', nargs='+', metavar='FACT_ID',
                        help='Suggest complementary facts')
    
    args = parser.parse_args()
    
    builder = SessionContextBuilder()
    
    try:
        if args.reconstruct:
            context = builder.reconstruct_from_facts(args.reconstruct, args.order_by)
            print(f"\n✓ Reconstructed context ({args.order_by}):")
            print(f"  Facts: {context['total_facts']}")
            print(f"  Summary: {context.get('context_summary', '')}")
            for fact in context['facts'][:3]:
                print(f"    • {fact['id']}: {fact['content'][:60]}...")
        
        elif args.find_related:
            related = builder.find_related_facts(args.find_related, args.depth)
            print(f"\n✓ Related facts for {args.find_related}:")
            print(f"  Found: {len(related['related_facts'])}")
            for rel in related['related_facts'][:5]:
                print(f"    • {rel['fact']['id']} (depth {rel['depth']}): "
                      f"{rel['fact']['content'][:50]}...")
        
        elif args.estimate:
            estimate = builder.estimate_context_size(args.estimate)
            print(f"\n✓ Context size estimate:")
            for key, val in estimate.items():
                print(f"  {key}: {val}")
        
        elif args.suggest:
            suggestions = builder.suggest_complementary_facts(args.suggest)
            print(f"\n✓ Suggested complementary facts:")
            for sugg in suggestions:
                print(f"  • {sugg['category']}: {sugg['fact_id']}")
                print(f"    {sugg['content']}")
    
    finally:
        builder.close()


if __name__ == '__main__':
    main()
