#!/usr/bin/env python3
"""
Fact Reference Logger — Contextual Windowing Phase 2

Tracks when facts are used, what context triggers their use, and which facts
appear together in responses. This enables:

1. Co-occurrence tracking (which facts appear together)
2. Context reconstruction (rebuild conversations from fact patterns)
3. Smart windowing (select optimal fact subsets)
4. Reference frequency analysis (popularity metrics)

Usage:
    logger = FactReferenceLogger()
    logger.log_reference(
        fact_ids=['fact_123', 'fact_456'],
        context="User asked about Stripe integration",
        response_tokens=250,
        relevance_scores={'fact_123': 0.95, 'fact_456': 0.78}
    )
    
    # Get facts that co-occur with a given fact
    cooccurrences = logger.get_cooccurrences('fact_123', limit=10)
    
    # Get conversation window around facts
    window = logger.get_context_window('fact_123', depth=3)
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/reference-logger.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


@dataclass
class FactReference:
    """Single fact reference event."""
    fact_id: str
    referenced_at: datetime
    context: str
    response_tokens: int
    relevance_score: float = 0.5
    response_facts: List[str] = None
    
    def to_dict(self):
        d = asdict(self)
        d['referenced_at'] = d['referenced_at'].isoformat()
        return d


@dataclass
class CoOccurrence:
    """Co-occurrence relationship between two facts."""
    fact_id_1: str
    fact_id_2: str
    co_occurrence_count: int
    last_co_occurred: datetime
    avg_relevance_delta: float = 0.0  # difference in relevance scores


class FactReferenceLogger:
    """Track fact references and build co-occurrence graph."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
    
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
    
    def log_reference(
        self,
        fact_ids: List[str],
        context: str,
        response_tokens: int = 0,
        relevance_scores: Dict[str, float] = None
    ) -> bool:
        """
        Log a reference event with multiple facts.
        
        Args:
            fact_ids: List of fact IDs appearing in response
            context: Query/prompt that triggered these facts
            response_tokens: Total tokens used in response (optional)
            relevance_scores: Dict of fact_id → relevance_score (0-1)
        
        Returns:
            True if successful
        """
        if not fact_ids:
            logger_obj.warning("No fact IDs provided")
            return False
        
        relevance_scores = relevance_scores or {}
        now = datetime.now()
        
        cursor = self.conn.cursor()
        
        try:
            # Log each fact reference
            for fact_id in fact_ids:
                relevance = relevance_scores.get(fact_id, 0.5)
                feedback = 'helpful' if relevance > 0.7 else 'partial' if relevance > 0.4 else 'not_helpful'
                
                cursor.execute("""
                    INSERT INTO fact_references 
                    (fact_id, context, relevance_feedback, referenced_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    fact_id,
                    context[:200],  # Truncate to reasonable length
                    feedback,
                    now.isoformat()
                ))
                
                # Update memory_facts counters
                cursor.execute("""
                    UPDATE memory_facts
                    SET referenced_count = referenced_count + 1,
                        last_referenced = ?
                    WHERE id = ?
                """, (now.isoformat(), fact_id))
            
            # Log co-occurrences (pairs)
            for i, fact_a in enumerate(fact_ids):
                for fact_b in fact_ids[i+1:]:
                    score_a = relevance_scores.get(fact_a, 0.5)
                    score_b = relevance_scores.get(fact_b, 0.5)
                    avg_score = (score_a + score_b) / 2
                    
                    # Ensure consistent ordering (alphabetical)
                    if fact_a > fact_b:
                        fact_a, fact_b = fact_b, fact_a
                    
                    cursor.execute("""
                        INSERT OR IGNORE INTO co_access_patterns 
                        (fact_id_a, fact_id_b, co_access_count, strength, first_seen, last_seen)
                        VALUES (?, ?, 1, ?, ?, ?)
                    """, (fact_a, fact_b, avg_score, now.isoformat(), now.isoformat()))
                    
                    # Update if already exists
                    cursor.execute("""
                        UPDATE co_access_patterns
                        SET co_access_count = co_access_count + 1,
                            strength = (strength + ?) / 2,
                            last_seen = ?
                        WHERE fact_id_a = ? AND fact_id_b = ?
                    """, (avg_score, now.isoformat(), fact_a, fact_b))
            
            self.conn.commit()
            logger_obj.info(f"✓ Logged {len(fact_ids)} fact references (context: {context[:60]}...)")
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger_obj.error(f"Failed to log references: {e}")
            return False
    
    def get_cooccurrences(
        self,
        fact_id: str,
        limit: int = 10,
        min_count: int = 1
    ) -> List[Dict]:
        """
        Get facts that co-occur with a given fact.
        
        Returns sorted by frequency (descending).
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN fact_id_a = ? THEN fact_id_b
                        ELSE fact_id_a
                    END as cooccurring_fact,
                    co_access_count,
                    strength,
                    last_seen
                FROM co_access_patterns
                WHERE (fact_id_a = ? OR fact_id_b = ?)
                  AND co_access_count >= ?
                ORDER BY co_access_count DESC
                LIMIT ?
            """, (fact_id, fact_id, fact_id, min_count, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'fact_id': row['cooccurring_fact'],
                    'co_occurrence_count': row['co_access_count'],
                    'strength': row['strength'],
                    'last_co_occurred': row['last_seen']
                })
            
            logger_obj.info(f"Found {len(results)} co-occurrences for {fact_id}")
            return results
            
        except Exception as e:
            logger_obj.error(f"Failed to get co-occurrences: {e}")
            return []
    
    def get_context_window(
        self,
        fact_id: str,
        depth: int = 2,
        max_facts: int = 10
    ) -> Dict:
        """
        Reconstruct context window around a fact.
        
        Finds related facts by:
        1. Direct co-occurrences
        2. Co-occurrences of co-occurrences (depth=2)
        3. Temporal proximity
        
        Returns ordered by relevance.
        """
        cursor = self.conn.cursor()
        
        try:
            # Get the fact
            cursor.execute("""
                SELECT id, content, created_at, decay_weight 
                FROM memory_facts 
                WHERE id = ?
            """, (fact_id,))
            
            fact_row = cursor.fetchone()
            if not fact_row:
                logger_obj.warning(f"Fact not found: {fact_id}")
                return {'error': 'Fact not found'}
            
            center_fact = dict(fact_row)
            
            # Get co-occurrences (depth 1)
            cooccs = self.get_cooccurrences(fact_id, limit=max_facts)
            cooccurring_ids = [c['fact_id'] for c in cooccs]
            
            # Get their details
            cursor.execute(f"""
                SELECT id, content, created_at, decay_weight, referenced_count
                FROM memory_facts
                WHERE id IN ({','.join(['?']*len(cooccurring_ids))})
                ORDER BY referenced_count DESC, decay_weight DESC
                LIMIT ?
            """, cooccurring_ids + [max_facts])
            
            related_facts = [dict(row) for row in cursor.fetchall()]
            
            # Calculate window completeness
            window_size = 1 + len(related_facts)
            
            return {
                'center_fact': center_fact,
                'related_facts': related_facts,
                'window_size': window_size,
                'depth': 1,
                'co_occurrence_count': len(cooccs)
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get context window: {e}")
            return {'error': str(e)}
    
    def get_reference_stats(self, fact_id: str) -> Dict:
        """
        Get reference statistics for a fact.
        
        Returns:
            Count, recency, average context, etc.
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_references,
                    MAX(referenced_at) as last_referenced,
                    COUNT(DISTINCT context) as unique_contexts
                FROM fact_references
                WHERE fact_id = ?
            """, (fact_id,))
            
            row = cursor.fetchone()
            if row:
                # Get feedback stats
                cursor.execute("""
                    SELECT relevance_feedback, COUNT(*) as count
                    FROM fact_references
                    WHERE fact_id = ?
                    GROUP BY relevance_feedback
                """, (fact_id,))
                
                feedback_counts = {row['relevance_feedback']: row['count'] for row in cursor.fetchall()}
                
                return {
                    'total_references': row['total_references'],
                    'last_referenced': row['last_referenced'],
                    'unique_contexts': row['unique_contexts'],
                    'feedback_distribution': feedback_counts
                }
            else:
                return {
                    'total_references': 0,
                    'last_referenced': None,
                    'unique_contexts': 0,
                    'feedback_distribution': {}
                }
            
        except Exception as e:
            logger_obj.error(f"Failed to get reference stats: {e}")
            return {}
    
    def get_top_facts_by_reference(
        self,
        limit: int = 20,
        min_age_hours: int = 0
    ) -> List[Dict]:
        """
        Get most frequently referenced facts.
        
        Args:
            limit: Number of facts to return
            min_age_hours: Only facts older than N hours (to exclude recent)
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute(f"""
                SELECT 
                    mf.id,
                    SUBSTR(mf.content, 1, 80) as content,
                    COUNT(fr.fact_id) as reference_count,
                    AVG(fr.relevance_score) as avg_relevance,
                    mf.freshness_tier
                FROM memory_facts mf
                LEFT JOIN fact_references fr ON mf.id = fr.fact_id
                GROUP BY mf.id
                HAVING reference_count > 0
                ORDER BY reference_count DESC
                LIMIT ?
            """, (limit,))
            
            results = [dict(row) for row in cursor.fetchall()]
            logger_obj.info(f"Top {len(results)} facts by reference count")
            return results
            
        except Exception as e:
            logger_obj.error(f"Failed to get top facts: {e}")
            return []
    
    def get_context_clusters(self, min_cluster_size: int = 3) -> List[List[str]]:
        """
        Find clusters of facts that appear together.
        
        Uses co-occurrence graph to identify fact groups.
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT fact_id_1, fact_id_2, co_occurrence_count
                FROM co_access_patterns
                WHERE co_occurrence_count >= 2
                ORDER BY co_occurrence_count DESC
                LIMIT 100
            """)
            
            # Simple clustering: build adjacency graph
            graph = {}
            for row in cursor.fetchall():
                f1, f2, count = row
                if f1 not in graph:
                    graph[f1] = []
                if f2 not in graph:
                    graph[f2] = []
                graph[f1].append(f2)
                graph[f2].append(f1)
            
            # Find clusters using simple DFS
            clusters = []
            visited = set()
            
            def dfs(node, cluster):
                if node in visited:
                    return
                visited.add(node)
                cluster.append(node)
                for neighbor in graph.get(node, []):
                    dfs(neighbor, cluster)
            
            for node in graph:
                if node not in visited:
                    cluster = []
                    dfs(node, cluster)
                    if len(cluster) >= min_cluster_size:
                        clusters.append(sorted(cluster))
            
            logger_obj.info(f"Found {len(clusters)} fact clusters")
            return clusters
            
        except Exception as e:
            logger_obj.error(f"Failed to get context clusters: {e}")
            return []


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fact Reference Logger")
    parser.add_argument('--log-reference', nargs=3, metavar=('FACT_ID', 'CONTEXT', 'TOKENS'),
                        help='Log a reference')
    parser.add_argument('--get-cooccurrences', metavar='FACT_ID',
                        help='Get co-occurrences')
    parser.add_argument('--get-window', metavar='FACT_ID',
                        help='Get context window')
    parser.add_argument('--get-stats', metavar='FACT_ID',
                        help='Get reference statistics')
    parser.add_argument('--top-facts', type=int, default=10,
                        help='Get top N facts by reference count')
    parser.add_argument('--clusters', action='store_true',
                        help='Find fact clusters')
    
    args = parser.parse_args()
    
    logger = FactReferenceLogger()
    
    try:
        if args.log_reference:
            fact_id, context, tokens = args.log_reference
            success = logger.log_reference([fact_id], context, int(tokens))
            print(f"✓ Reference logged" if success else "✗ Failed to log reference")
        
        elif args.get_cooccurrences:
            cooccs = logger.get_cooccurrences(args.get_cooccurrences, limit=10)
            print(f"\nCo-occurrences for {args.get_cooccurrences}:")
            for cocc in cooccs:
                print(f"  {cocc['fact_id']}: {cocc['co_occurrence_count']} times")
        
        elif args.get_window:
            window = logger.get_context_window(args.get_window)
            print(f"\nContext window for {args.get_window}:")
            print(f"  Center fact: {window['center_fact']['id']}")
            print(f"  Related facts: {len(window['related_facts'])}")
            for fact in window['related_facts'][:3]:
                print(f"    • {fact['id']}: {fact['content'][:60]}...")
        
        elif args.get_stats:
            stats = logger.get_reference_stats(args.get_stats)
            print(f"\nStats for {args.get_stats}:")
            for key, val in stats.items():
                print(f"  {key}: {val}")
        
        elif args.top_facts:
            top = logger.get_top_facts_by_reference(limit=args.top_facts)
            print(f"\nTop {args.top_facts} facts by references:")
            for fact in top:
                print(f"  {fact['id']}: {fact['reference_count']} refs, "
                      f"avg relevance {fact['avg_relevance']:.2f}")
        
        elif args.clusters:
            clusters = logger.get_context_clusters()
            print(f"\nFact clusters ({len(clusters)} found):")
            for i, cluster in enumerate(clusters[:5], 1):
                print(f"  Cluster {i}: {len(cluster)} facts")
                for fact_id in cluster[:3]:
                    print(f"    • {fact_id}")
    
    finally:
        logger.close()


if __name__ == '__main__':
    main()
