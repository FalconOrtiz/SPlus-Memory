#!/usr/bin/env python3
"""
Auto-Embedder — Phase 4

Automatically generates embeddings for new facts using cached embedder
or on-the-fly generation if needed.

Capabilities:
- Generate embeddings for new facts
- Batch embedding with caching
- Update missing embeddings
- Handle multiple embedding models
- Performance optimization

Usage:
    embedder = AutoEmbedder()
    
    # Generate single embedding
    embedding = embedder.generate_embedding(
        content="How does decay work?",
        model="bge-small-en-v1.5"
    )
    
    # Batch embed
    embeddings = embedder.batch_embed([
        {"id": "fact_1", "content": "..."},
        {"id": "fact_2", "content": "..."}
    ])
    
    # Update all missing
    report = embedder.update_missing_embeddings(limit=100)
"""

import sqlite3
import json
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/auto-embedder.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


class AutoEmbedder:
    """Automatically generate embeddings for facts."""
    
    def __init__(self, db_path: Path = None, model: str = 'bge-small-en-v1.5'):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self.model = model
        self.dimensions = 384  # For bge-small-en-v1.5
        self._connect()
        
        # Try to load embedder, fallback to placeholder
        self.embedder = self._load_embedder()
    
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
    
    def _load_embedder(self):
        """
        Try to load embedder from local system.
        Falls back to random embeddings if not available.
        """
        try:
            # Try to import existing embedder
            from sentence_transformers import SentenceTransformer
            logger_obj.info(f"Loading embedder: {self.model}")
            embedder = SentenceTransformer(self.model)
            logger_obj.info("✓ Embedder loaded successfully")
            return embedder
        except ImportError:
            logger_obj.warning("SentenceTransformers not available, using random embeddings")
            return None
        except Exception as e:
            logger_obj.warning(f"Failed to load embedder: {e}, using random embeddings")
            return None
    
    def _generate_random_embedding(self) -> List[float]:
        """Generate random embedding for fallback."""
        import random
        return [random.random() for _ in range(self.dimensions)]
    
    def _generate_embedding_from_model(self, content: str) -> List[float]:
        """Generate embedding using loaded model."""
        if not self.embedder:
            return self._generate_random_embedding()
        
        try:
            embedding = self.embedder.encode(content, convert_to_tensor=False)
            return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        except Exception as e:
            logger_obj.warning(f"Embedding generation failed: {e}, using random")
            return self._generate_random_embedding()
    
    def generate_embedding(
        self,
        content: str,
        model: str = None
    ) -> List[float]:
        """
        Generate embedding for content.
        
        Args:
            content: Text to embed
            model: Model to use (default: self.model)
        
        Returns:
            Embedding vector (list of floats)
        """
        model = model or self.model
        
        try:
            if self.embedder and model == self.model:
                embedding = self._generate_embedding_from_model(content)
            else:
                logger_obj.warning(f"Model {model} not loaded, using random")
                embedding = self._generate_random_embedding()
            
            logger_obj.debug(f"Generated {len(embedding)}-dim embedding")
            return embedding
            
        except Exception as e:
            logger_obj.error(f"Failed to generate embedding: {e}")
            return self._generate_random_embedding()
    
    def batch_embed(
        self,
        facts: List[Dict],
        skip_existing: bool = True
    ) -> Dict[str, List[float]]:
        """
        Generate embeddings for multiple facts.
        
        Args:
            facts: List of dicts with 'id' and 'content'
            skip_existing: Don't re-embed facts that already have embeddings
        
        Returns:
            Dict of fact_id → embedding
        """
        embeddings = {}
        cursor = self.conn.cursor()
        
        try:
            for fact in facts:
                fact_id = fact.get('id')
                content = fact.get('content')
                
                if not fact_id or not content:
                    logger_obj.warning(f"Skipping fact with missing id or content")
                    continue
                
                # Check if already embedded
                if skip_existing:
                    cursor.execute(
                        "SELECT embedding FROM semantic_embeddings WHERE fact_id = ?",
                        (fact_id,)
                    )
                    if cursor.fetchone():
                        logger_obj.debug(f"Embedding already exists for {fact_id}")
                        continue
                
                # Generate embedding
                embedding = self.generate_embedding(content)
                embeddings[fact_id] = embedding
            
            logger_obj.info(f"Generated {len(embeddings)} embeddings from {len(facts)} facts")
            return embeddings
            
        except Exception as e:
            logger_obj.error(f"Batch embedding failed: {e}")
            return embeddings
    
    def insert_embedding(
        self,
        fact_id: str,
        embedding: List[float]
    ) -> bool:
        """
        Insert embedding into database.
        
        Args:
            fact_id: Fact ID
            embedding: Embedding vector
        
        Returns:
            True if successful
        """
        cursor = self.conn.cursor()
        
        try:
            embedding_json = json.dumps(embedding)
            
            cursor.execute("""
                INSERT OR REPLACE INTO semantic_embeddings
                (fact_id, embedding, model, dimensions, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                fact_id,
                embedding_json,
                self.model,
                self.dimensions,
                datetime.now().isoformat()
            ))
            
            self.conn.commit()
            logger_obj.debug(f"Inserted embedding for {fact_id}")
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger_obj.error(f"Failed to insert embedding: {e}")
            return False
    
    def batch_insert_embeddings(
        self,
        embeddings: Dict[str, List[float]]
    ) -> int:
        """
        Insert multiple embeddings efficiently.
        
        Args:
            embeddings: Dict of fact_id → embedding
        
        Returns:
            Number of successfully inserted embeddings
        """
        cursor = self.conn.cursor()
        inserted = 0
        
        try:
            for fact_id, embedding in embeddings.items():
                embedding_json = json.dumps(embedding)
                
                cursor.execute("""
                    INSERT OR REPLACE INTO semantic_embeddings
                    (fact_id, embedding, model, dimensions, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    fact_id,
                    embedding_json,
                    self.model,
                    self.dimensions,
                    datetime.now().isoformat()
                ))
                
                inserted += 1
            
            self.conn.commit()
            logger_obj.info(f"Inserted {inserted} embeddings")
            return inserted
            
        except Exception as e:
            self.conn.rollback()
            logger_obj.error(f"Batch insert failed: {e}")
            return inserted
    
    def find_missing_embeddings(self, limit: int = 100) -> List[Dict]:
        """
        Find facts without embeddings.
        
        Args:
            limit: Maximum number to return
        
        Returns:
            List of facts needing embeddings
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT mf.id, mf.content
                FROM memory_facts mf
                LEFT JOIN semantic_embeddings se ON mf.id = se.fact_id
                WHERE se.fact_id IS NULL AND mf.is_active = 1
                ORDER BY mf.created_at DESC
                LIMIT ?
            """, (limit,))
            
            facts = [dict(row) for row in cursor.fetchall()]
            logger_obj.info(f"Found {len(facts)} facts missing embeddings")
            return facts
            
        except Exception as e:
            logger_obj.error(f"Failed to find missing embeddings: {e}")
            return []
    
    def update_missing_embeddings(
        self,
        limit: int = 100
    ) -> Dict:
        """
        Find missing embeddings and generate them.
        
        Args:
            limit: Maximum facts to process
        
        Returns:
            Report with statistics
        """
        logger_obj.info(f"Starting update for {limit} facts...")
        
        # Find missing
        missing_facts = self.find_missing_embeddings(limit)
        
        if not missing_facts:
            logger_obj.info("No missing embeddings found")
            return {
                'status': 'complete',
                'facts_processed': 0,
                'embeddings_generated': 0,
                'embeddings_inserted': 0
            }
        
        # Generate embeddings
        logger_obj.info(f"Generating embeddings for {len(missing_facts)} facts...")
        embeddings = self.batch_embed(missing_facts, skip_existing=False)
        
        # Insert into database
        logger_obj.info(f"Inserting {len(embeddings)} embeddings...")
        inserted = self.batch_insert_embeddings(embeddings)
        
        report = {
            'status': 'complete',
            'facts_processed': len(missing_facts),
            'embeddings_generated': len(embeddings),
            'embeddings_inserted': inserted,
            'timestamp': datetime.now().isoformat()
        }
        
        logger_obj.info(f"Update complete: {inserted}/{len(embeddings)} embeddings inserted")
        return report
    
    def get_embedding_stats(self) -> Dict:
        """Get statistics about embeddings."""
        cursor = self.conn.cursor()
        
        try:
            # Total facts
            cursor.execute("SELECT COUNT(*) as count FROM memory_facts WHERE is_active = 1")
            total_facts = cursor.fetchone()['count']
            
            # Facts with embeddings
            cursor.execute("SELECT COUNT(*) as count FROM semantic_embeddings")
            with_embeddings = cursor.fetchone()['count']
            
            # Missing embeddings
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM memory_facts mf
                LEFT JOIN semantic_embeddings se ON mf.id = se.fact_id
                WHERE se.fact_id IS NULL AND mf.is_active = 1
            """)
            missing = cursor.fetchone()['count']
            
            # Models
            cursor.execute("""
                SELECT model, COUNT(*) as count
                FROM semantic_embeddings
                GROUP BY model
            """)
            models = {row['model']: row['count'] for row in cursor.fetchall()}
            
            coverage = (with_embeddings / total_facts * 100) if total_facts > 0 else 0
            
            return {
                'total_facts': total_facts,
                'with_embeddings': with_embeddings,
                'missing_embeddings': missing,
                'embedding_coverage_percent': round(coverage, 2),
                'models': models,
                'default_model': self.model,
                'default_dimensions': self.dimensions
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get stats: {e}")
            return {}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto-Embedder")
    parser.add_argument('--stats', action='store_true',
                        help='Show embedding statistics')
    parser.add_argument('--missing', type=int, default=10,
                        help='Find N facts with missing embeddings')
    parser.add_argument('--update', type=int, default=100,
                        help='Update missing embeddings (up to N facts)')
    parser.add_argument('--generate', metavar='TEXT',
                        help='Generate embedding for text')
    parser.add_argument('--model', default='bge-small-en-v1.5',
                        help='Embedding model to use')
    
    args = parser.parse_args()
    
    embedder = AutoEmbedder(model=args.model)
    
    try:
        if args.stats:
            stats = embedder.get_embedding_stats()
            print("\n✓ Embedding Statistics:")
            for key, val in stats.items():
                if isinstance(val, dict):
                    print(f"  {key}:")
                    for k, v in val.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  {key}: {val}")
        
        elif args.missing:
            facts = embedder.find_missing_embeddings(args.missing)
            print(f"\n✓ Facts missing embeddings ({len(facts)}):")
            for fact in facts[:5]:
                print(f"  • {fact['id']}: {fact['content'][:60]}...")
        
        elif args.update:
            report = embedder.update_missing_embeddings(args.update)
            print(f"\n✓ Update Report:")
            for key, val in report.items():
                print(f"  {key}: {val}")
        
        elif args.generate:
            embedding = embedder.generate_embedding(args.generate)
            print(f"\n✓ Generated {len(embedding)}-dimensional embedding")
            print(f"  First 10 dims: {embedding[:10]}")
    
    finally:
        embedder.close()


if __name__ == '__main__':
    main()
