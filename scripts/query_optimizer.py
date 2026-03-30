#!/usr/bin/env python3
"""
Query Optimizer — Phase 8

ML-based query optimization and learning.

Optimizations:
- Query rewrite rules
- Parameter hints
- Index suggestions
- Caching strategies
- Model selection optimization

Learning:
- Track successful patterns
- Learn optimal parameters
- Build query fingerprints
- Predict best execution path

Usage:
    optimizer = QueryOptimizer()
    
    # Optimize a query
    optimized = optimizer.optimize_query("SELECT * FROM facts...")
    
    # Get execution plan
    plan = optimizer.get_execution_plan(query)
    
    # Learn from successful queries
    optimizer.learn_from_execution(query, duration_ms, result_count)
    
    # Get query stats
    stats = optimizer.get_query_statistics(query_pattern)
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import hashlib

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


@dataclass
class OptimizedQuery:
    """Optimized query with execution plan."""
    original: str
    optimized: str
    fingerprint: str
    estimated_cost: float
    suggested_cache: bool
    suggested_model: str
    hints: List[str]
    confidence: float


class QueryOptimizer:
    """Optimize queries based on ML and historical patterns."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        self._ensure_tables()
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info("Query optimizer connected")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def _ensure_tables(self):
        """Ensure query tracking tables exist."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_fingerprints (
                id INTEGER PRIMARY KEY,
                fingerprint TEXT UNIQUE,
                query_pattern TEXT,
                avg_duration_ms REAL,
                avg_result_count INTEGER,
                execution_count INTEGER,
                last_execution TEXT,
                suggested_cache BOOLEAN,
                suggested_model TEXT,
                confidence REAL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_executions (
                id INTEGER PRIMARY KEY,
                fingerprint TEXT,
                duration_ms REAL,
                result_count INTEGER,
                success BOOLEAN,
                timestamp TEXT,
                FOREIGN KEY(fingerprint) REFERENCES query_fingerprints(fingerprint)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fingerprints ON query_fingerprints(fingerprint)
        """)
        
        self.conn.commit()
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def _get_fingerprint(self, query: str) -> str:
        """
        Get query fingerprint.
        
        Fingerprint is hash of normalized query pattern.
        """
        # Simple normalization: remove parameters, whitespace
        normalized = ' '.join(query.split()).lower()
        # Remove WHERE values
        import re
        pattern = re.sub(r'(WHERE|=|IN|LIKE)\s+[^,);]+', r'\1 ?', normalized)
        
        return hashlib.md5(pattern.encode()).hexdigest()
    
    def optimize_query(self, query: str) -> OptimizedQuery:
        """
        Optimize a query.
        
        Uses learned patterns to suggest optimizations.
        
        Args:
            query: SQL or memory query
        
        Returns:
            Optimized query with hints
        """
        logger_obj.info(f"Optimizing query: {query[:80]}...")
        
        fingerprint = self._get_fingerprint(query)
        
        # Get historical data for this pattern
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT avg_duration_ms, execution_count, suggested_cache, 
                   suggested_model, confidence
            FROM query_fingerprints
            WHERE fingerprint = ?
        """, (fingerprint,))
        
        row = cursor.fetchone()
        
        if row:
            # We've seen this pattern before - use learned optimization
            avg_duration = row['avg_duration_ms']
            exec_count = row['execution_count']
            suggested_cache = row['suggested_cache']
            suggested_model = row['suggested_model']
            confidence = row['confidence']
        else:
            # New pattern - use default heuristics
            avg_duration = 100
            exec_count = 0
            suggested_cache = 'SELECT' in query.upper() and 'COUNT' in query.upper()
            suggested_model = 'sonnet' if len(query) > 500 else 'haiku'
            confidence = 0.5
        
        # Generate optimization hints
        hints = self._generate_hints(query, avg_duration, exec_count)
        
        # Generate optimized query
        optimized = self._rewrite_query(query, hints)
        
        # Estimate cost
        estimated_cost = self._estimate_cost(query)
        
        return OptimizedQuery(
            original=query,
            optimized=optimized,
            fingerprint=fingerprint,
            estimated_cost=estimated_cost,
            suggested_cache=suggested_cache,
            suggested_model=suggested_model,
            hints=hints,
            confidence=confidence
        )
    
    def _generate_hints(self, query: str, avg_duration: float, exec_count: int) -> List[str]:
        """Generate optimization hints."""
        hints = []
        
        # Hint 1: Caching
        if exec_count > 5 and avg_duration > 50:
            hints.append("CACHE: Frequently executed, consider caching")
        
        # Hint 2: Batch processing
        if 'LIMIT' not in query.upper():
            hints.append("BATCH: Consider LIMIT clause for pagination")
        
        # Hint 3: Index usage
        if 'WHERE' in query.upper():
            hints.append("INDEX: Ensure WHERE columns are indexed")
        
        # Hint 4: Join optimization
        if query.count('JOIN') > 2:
            hints.append("JOIN: Multiple joins detected, verify index coverage")
        
        # Hint 5: Model selection
        if avg_duration > 200:
            hints.append("MODEL: Large result set, consider Sonnet model")
        
        return hints
    
    def _rewrite_query(self, query: str, hints: List[str]) -> str:
        """Rewrite query based on hints."""
        optimized = query
        
        # Add LIMIT if not present and query doesn't have aggregates
        if 'LIMIT' not in query.upper() and 'COUNT' not in query.upper():
            optimized += " LIMIT 1000"
        
        # Add index hints if available
        if any('INDEX' in h for h in hints):
            # In practice, would add USING INDEX clauses
            pass
        
        return optimized
    
    def _estimate_cost(self, query: str) -> float:
        """
        Estimate execution cost.
        
        Rough estimate based on query characteristics.
        """
        cost = 1.0  # Base cost
        
        # Longer queries cost more
        cost += len(query) / 1000
        
        # JOINs are expensive
        cost *= (1 + query.count('JOIN') * 0.5)
        
        # Aggregations are expensive
        if 'GROUP BY' in query.upper():
            cost *= 2
        
        return cost
    
    def get_execution_plan(self, query: str) -> Dict:
        """
        Get execution plan for a query.
        
        Includes estimated cost, steps, and optimizations.
        """
        optimized = self.optimize_query(query)
        
        return {
            'original_query': optimized.original,
            'optimized_query': optimized.optimized,
            'fingerprint': optimized.fingerprint,
            'estimated_cost': optimized.estimated_cost,
            'suggested_cache': optimized.suggested_cache,
            'suggested_model': optimized.suggested_model,
            'hints': optimized.hints,
            'confidence': optimized.confidence,
            'steps': [
                {'step': 1, 'operation': 'Parse', 'cost': 0.1},
                {'step': 2, 'operation': 'Optimize', 'cost': 0.1},
                {'step': 3, 'operation': 'Execute', 'cost': optimized.estimated_cost - 0.2}
            ]
        }
    
    def learn_from_execution(
        self,
        query: str,
        duration_ms: float,
        result_count: int,
        success: bool = True
    ) -> bool:
        """
        Learn from query execution.
        
        Updates statistics for pattern matching.
        """
        fingerprint = self._get_fingerprint(query)
        
        cursor = self.conn.cursor()
        
        try:
            # Record execution
            cursor.execute("""
                INSERT INTO query_executions
                (fingerprint, duration_ms, result_count, success, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (fingerprint, duration_ms, result_count, success, datetime.now().isoformat()))
            
            # Update or insert fingerprint stats
            cursor.execute("""
                SELECT COUNT(*) as count, AVG(duration_ms) as avg_duration,
                       AVG(result_count) as avg_results
                FROM query_executions
                WHERE fingerprint = ?
            """, (fingerprint,))
            
            stats = cursor.fetchone()
            
            # Determine caching benefit
            should_cache = stats['count'] > 3 and stats['avg_duration'] > 50
            
            # Determine best model
            best_model = 'sonnet' if stats['avg_results'] > 1000 else 'haiku'
            
            # Confidence increases with execution count
            confidence = min(1.0, stats['count'] / 10)
            
            cursor.execute("""
                INSERT OR REPLACE INTO query_fingerprints
                (fingerprint, query_pattern, avg_duration_ms, avg_result_count,
                 execution_count, last_execution, suggested_cache, suggested_model, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fingerprint, query[:255], stats['avg_duration'],
                stats['avg_results'], stats['count'],
                datetime.now().isoformat(), should_cache, best_model, confidence
            ))
            
            self.conn.commit()
            logger_obj.info(f"Learned from execution: {fingerprint[:8]}... ({duration_ms:.0f}ms)")
            return True
        
        except Exception as e:
            logger_obj.error(f"Failed to learn from execution: {e}")
            return False
    
    def get_query_statistics(self, query_pattern: str = None) -> Dict:
        """Get statistics for a query pattern."""
        cursor = self.conn.cursor()
        
        try:
            if query_pattern:
                cursor.execute("""
                    SELECT *
                    FROM query_fingerprints
                    WHERE query_pattern LIKE ?
                    ORDER BY execution_count DESC
                """, (f"%{query_pattern}%",))
            else:
                cursor.execute("""
                    SELECT *
                    FROM query_fingerprints
                    ORDER BY execution_count DESC
                    LIMIT 10
                """)
            
            stats = []
            for row in cursor.fetchall():
                stats.append({
                    'fingerprint': row['fingerprint'],
                    'pattern': row['query_pattern'],
                    'executions': row['execution_count'],
                    'avg_duration_ms': row['avg_duration_ms'],
                    'avg_results': row['avg_result_count'],
                    'cache_suggested': row['suggested_cache'],
                    'model_suggested': row['suggested_model'],
                    'confidence': row['confidence']
                })
            
            return {
                'timestamp': datetime.now().isoformat(),
                'query_pattern': query_pattern,
                'patterns_found': len(stats),
                'stats': stats
            }
        
        except Exception as e:
            logger_obj.error(f"Failed to get statistics: {e}")
            return {}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Query Optimizer")
    parser.add_argument('--optimize', metavar='QUERY', help='Optimize a query')
    parser.add_argument('--plan', metavar='QUERY', help='Get execution plan')
    parser.add_argument('--learn', nargs=3, metavar=('QUERY', 'DURATION', 'COUNT'),
                        help='Learn from execution')
    parser.add_argument('--stats', metavar='PATTERN', help='Get query statistics')
    
    args = parser.parse_args()
    
    optimizer = QueryOptimizer()
    
    try:
        if args.optimize:
            opt = optimizer.optimize_query(args.optimize)
            print(f"\n✓ Query Optimization:")
            print(f"  Original: {opt.original[:80]}...")
            print(f"  Optimized: {opt.optimized[:80]}...")
            print(f"  Hints: {'; '.join(opt.hints)}")
            print(f"  Cache: {opt.suggested_cache}")
            print(f"  Model: {opt.suggested_model}")
        
        elif args.plan:
            plan = optimizer.get_execution_plan(args.plan)
            print(f"\n✓ Execution Plan:")
            print(f"  Cost: {plan['estimated_cost']:.2f}")
            print(f"  Cache: {plan['suggested_cache']}")
            print(f"  Steps:")
            for step in plan['steps']:
                print(f"    {step['step']}. {step['operation']} (cost={step['cost']:.2f})")
        
        elif args.learn:
            query, duration, count = args.learn
            result = optimizer.learn_from_execution(query, float(duration), int(count))
            print(f"\n✓ Learning complete: {result}")
        
        elif args.stats:
            stats = optimizer.get_query_statistics(args.stats)
            print(f"\n✓ Query Statistics:")
            print(f"  Found: {stats['patterns_found']} patterns")
            for s in stats['stats'][:5]:
                print(f"  • Executions: {s['executions']}, Avg: {s['avg_duration_ms']:.0f}ms")
        
        else:
            parser.print_help()
    
    finally:
        optimizer.close()


if __name__ == '__main__':
    main()
