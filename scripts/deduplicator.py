#!/usr/bin/env python3
"""
Fact Deduplicator — Phase 3

Identifies and merges duplicate facts using semantic similarity.

Capabilities:
- Find duplicate groups
- Merge facts intelligently
- Update references
- Log deduplication events
- Run full deduplication pipeline

Usage:
    dedup = FactDeduplicator()
    
    # Find duplicates
    duplicates = dedup.find_duplicates(threshold=0.85)
    
    # Merge a group
    dedup.merge_facts(
        canonical_id='fact_123',
        duplicate_ids=['fact_456', 'fact_789']
    )
    
    # Run full pipeline
    report = dedup.deduplicate_database(threshold=0.85)
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
from collections import defaultdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/deduplicator.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


class FactDeduplicator:
    """Identify and merge duplicate facts."""
    
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
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        try:
            import numpy as np
            v1 = np.array(vec1, dtype=np.float32)
            v2 = np.array(vec2, dtype=np.float32)
            
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return float(dot_product / (norm1 * norm2))
        except Exception as e:
            logger_obj.error(f"Similarity calculation failed: {e}")
            return 0.0
    
    def _parse_embedding(self, embedding_data) -> Optional[List[float]]:
        """Parse embedding from JSON or binary format."""
        try:
            import json
            if isinstance(embedding_data, str):
                return json.loads(embedding_data)
            elif isinstance(embedding_data, bytes):
                return json.loads(embedding_data.decode('utf-8'))
        except Exception as e:
            logger_obj.warning(f"Failed to parse embedding: {e}")
        return None
    
    def find_duplicates(
        self,
        threshold: float = 0.85,
        max_duplicates: int = 1000
    ) -> List[List[str]]:
        """
        Find groups of similar/duplicate facts.
        
        Returns:
            List of duplicate groups, each group is list of fact IDs
        """
        cursor = self.conn.cursor()
        
        try:
            logger_obj.info(f"Finding duplicates with similarity threshold {threshold}")
            
            # Get all facts with embeddings
            cursor.execute("""
                SELECT se.fact_id, se.embedding
                FROM semantic_embeddings se
                ORDER BY se.created_at DESC
            """)
            
            facts_with_embeddings = []
            for row in cursor.fetchall():
                embedding = self._parse_embedding(row['embedding'])
                if embedding:
                    facts_with_embeddings.append((row['fact_id'], embedding))
            
            logger_obj.info(f"Loaded {len(facts_with_embeddings)} facts with embeddings")
            
            # Find duplicate groups
            visited = set()
            duplicate_groups = []
            
            for i, (fact_a_id, embedding_a) in enumerate(facts_with_embeddings):
                if fact_a_id in visited:
                    continue
                
                group = [fact_a_id]
                visited.add(fact_a_id)
                
                # Find all similar facts
                for fact_b_id, embedding_b in facts_with_embeddings[i+1:]:
                    if fact_b_id in visited:
                        continue
                    
                    similarity = self._cosine_similarity(embedding_a, embedding_b)
                    
                    if similarity >= threshold:
                        group.append(fact_b_id)
                        visited.add(fact_b_id)
                
                # Only add if group has duplicates
                if len(group) > 1:
                    duplicate_groups.append(group)
            
            logger_obj.info(f"Found {len(duplicate_groups)} duplicate groups")
            return duplicate_groups
            
        except Exception as e:
            logger_obj.error(f"Failed to find duplicates: {e}")
            return []
    
    def select_canonical(self, group: List[str]) -> str:
        """
        Select the canonical fact from a duplicate group.
        
        Strategy:
        1. Prefer facts with more references
        2. Prefer older facts (original)
        3. Prefer facts with better quality metrics
        """
        cursor = self.conn.cursor()
        
        try:
            placeholders = ','.join(['?' * len(group)])
            cursor.execute(f"""
                SELECT 
                    id,
                    created_at,
                    referenced_count,
                    decay_weight,
                    LENGTH(content) as content_length
                FROM memory_facts
                WHERE id IN ({','.join(['?']*len(group))})
                ORDER BY 
                    referenced_count DESC,
                    created_at ASC,
                    decay_weight DESC
                LIMIT 1
            """, group)
            
            row = cursor.fetchone()
            canonical = row['id'] if row else group[0]
            
            logger_obj.info(f"Selected canonical: {canonical} from group {group}")
            return canonical
            
        except Exception as e:
            logger_obj.error(f"Failed to select canonical: {e}")
            return group[0]
    
    def merge_facts(
        self,
        canonical_id: str,
        duplicate_ids: List[str],
        reason: str = "semantic_similarity"
    ) -> bool:
        """
        Merge duplicate facts into canonical.
        
        Steps:
        1. Update fact_references to point to canonical
        2. Update co_access_patterns
        3. Mark duplicates as inactive
        4. Log merge event
        """
        cursor = self.conn.cursor()
        
        try:
            logger_obj.info(f"Merging {len(duplicate_ids)} facts into {canonical_id}")
            
            # Get canonical fact details
            cursor.execute("SELECT * FROM memory_facts WHERE id = ?", (canonical_id,))
            canonical_fact = cursor.fetchone()
            
            if not canonical_fact:
                logger_obj.error(f"Canonical fact not found: {canonical_id}")
                return False
            
            # Move all references to canonical
            for dup_id in duplicate_ids:
                # Update fact_references
                cursor.execute("""
                    UPDATE fact_references
                    SET fact_id = ?
                    WHERE fact_id = ?
                """, (canonical_id, dup_id))
                
                # Mark duplicate as inactive
                cursor.execute("""
                    UPDATE memory_facts
                    SET is_active = 0,
                        is_archived = 1,
                        canonical_id = ?,
                        metadata = json_set(
                            COALESCE(metadata, '{}'),
                            '$.merged_into',
                            json(?)
                        )
                    WHERE id = ?
                """, (canonical_id, '{"id": "' + canonical_id + '"}', dup_id))
            
            # Log deduplication
            now = datetime.now().isoformat()
            for dup_id in duplicate_ids:
                cursor.execute("""
                    INSERT INTO deduplication_log 
                    (from_id, to_id, reason, merged_at)
                    VALUES (?, ?, ?, ?)
                """, (dup_id, canonical_id, reason, now))
            
            self.conn.commit()
            logger_obj.info(f"✓ Merged {len(duplicate_ids)} facts")
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger_obj.error(f"Merge failed: {e}")
            return False
    
    def deduplicate_database(
        self,
        threshold: float = 0.85,
        dry_run: bool = False
    ) -> Dict:
        """
        Run full deduplication pipeline.
        
        Returns:
            Report with stats
        """
        logger_obj.info(f"Starting deduplication (dry_run={dry_run})")
        
        # Find duplicates
        duplicate_groups = self.find_duplicates(threshold)
        
        report = {
            'threshold': threshold,
            'duplicate_groups_found': len(duplicate_groups),
            'total_duplicates': sum(len(g) - 1 for g in duplicate_groups),
            'merges': [],
            'status': 'dry_run' if dry_run else 'complete'
        }
        
        # Process each group
        for group_idx, group in enumerate(duplicate_groups):
            canonical_id = self.select_canonical(group)
            duplicate_ids = [f for f in group if f != canonical_id]
            
            merge_info = {
                'group_index': group_idx,
                'canonical_id': canonical_id,
                'duplicate_ids': duplicate_ids,
                'count': len(duplicate_ids),
                'merged': False
            }
            
            if not dry_run:
                merge_info['merged'] = self.merge_facts(
                    canonical_id,
                    duplicate_ids,
                    reason='deduplication_pipeline'
                )
            
            report['merges'].append(merge_info)
        
        logger_obj.info(f"Deduplication report: {len(duplicate_groups)} groups processed")
        return report
    
    def get_deduplication_stats(self) -> Dict:
        """Get deduplication statistics."""
        cursor = self.conn.cursor()
        
        try:
            # Get merge count
            cursor.execute("SELECT COUNT(*) as merge_count FROM deduplication_log")
            merges = cursor.fetchone()['merge_count']
            
            # Get inactive facts
            cursor.execute("""
                SELECT COUNT(*) as inactive_count 
                FROM memory_facts 
                WHERE is_active = 0
            """)
            inactive = cursor.fetchone()['inactive_count']
            
            # Get facts with canonical_id set
            cursor.execute("""
                SELECT COUNT(*) as canonical_count 
                FROM memory_facts 
                WHERE canonical_id IS NOT NULL
            """)
            canonical_refs = cursor.fetchone()['canonical_count']
            
            # Total facts
            cursor.execute("SELECT COUNT(*) as total_facts FROM memory_facts")
            total = cursor.fetchone()['total_facts']
            
            return {
                'total_facts': total,
                'inactive_facts': inactive,
                'duplicates_merged': merges,
                'facts_with_canonical_id': canonical_refs,
                'deduplication_rate': (merges / total * 100) if total > 0 else 0
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get deduplication stats: {e}")
            return {}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fact Deduplicator")
    parser.add_argument('--find', action='store_true',
                        help='Find duplicates')
    parser.add_argument('--threshold', type=float, default=0.85,
                        help='Similarity threshold')
    parser.add_argument('--deduplicate', action='store_true',
                        help='Run full deduplication')
    parser.add_argument('--dry-run', action='store_true',
                        help='Dry run (no changes)')
    parser.add_argument('--stats', action='store_true',
                        help='Show deduplication statistics')
    parser.add_argument('--merge', nargs='+', metavar='FACT_ID',
                        help='Merge facts (first is canonical)')
    
    args = parser.parse_args()
    
    dedup = FactDeduplicator()
    
    try:
        if args.stats:
            stats = dedup.get_deduplication_stats()
            print("\n✓ Deduplication Statistics:")
            for key, val in stats.items():
                if isinstance(val, float):
                    print(f"  {key}: {val:.2f}")
                else:
                    print(f"  {key}: {val}")
        
        elif args.find:
            duplicates = dedup.find_duplicates(args.threshold)
            print(f"\n✓ Found {len(duplicates)} duplicate groups (threshold={args.threshold}):")
            for i, group in enumerate(duplicates[:5], 1):
                print(f"  Group {i}: {len(group)} facts")
                for fact_id in group[:3]:
                    print(f"    • {fact_id}")
        
        elif args.deduplicate:
            report = dedup.deduplicate_database(args.threshold, args.dry_run)
            print(f"\n✓ Deduplication Report:")
            print(f"  Groups found: {report['duplicate_groups_found']}")
            print(f"  Total duplicates: {report['total_duplicates']}")
            print(f"  Status: {report['status']}")
        
        elif args.merge and len(args.merge) > 1:
            canonical = args.merge[0]
            duplicates = args.merge[1:]
            success = dedup.merge_facts(canonical, duplicates)
            print(f"\n{'✓' if success else '✗'} Merged {len(duplicates)} facts into {canonical}")
    
    finally:
        dedup.close()


if __name__ == '__main__':
    main()
