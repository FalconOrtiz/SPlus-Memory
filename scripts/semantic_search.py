#!/usr/bin/env python3
"""
Semantic Search — Phase 3

Uses embedding vectors for similarity-based fact retrieval.

Supports:
- Query embedding generation
- Cosine similarity search
- Batch operations
- Performance optimization

Usage:
    searcher = SemanticSearcher()
    
    results = searcher.search(
        query="How does decay work?",
        top_k=10
    )
    
    # Or get raw similarity scores
    scores = searcher.semantic_similarity(
        query_embedding=query_vector,
        top_k=5
    )
"""

import sqlite3
import json
import logging
import math
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/semantic-search.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'


@dataclass
class SemanticResult:
    """Single semantic search result."""
    fact_id: str
    content: str
    similarity_score: float
    model: str
    dimensions: int


class SemanticSearcher:
    """Semantic search using embeddings."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        
        # Embedding parameters
        self.default_model = 'bge-small-en-v1.5'
        self.default_dimensions = 384
    
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
    
    def _parse_embedding(self, embedding_data) -> Optional[List[float]]:
        """Parse embedding from JSON or binary format."""
        try:
            if isinstance(embedding_data, str):
                # JSON format
                return json.loads(embedding_data)
            elif isinstance(embedding_data, bytes):
                # Binary format - try to parse as JSON-encoded bytes
                return json.loads(embedding_data.decode('utf-8'))
            else:
                return None
        except Exception as e:
            logger_obj.warning(f"Failed to parse embedding: {e}")
            return None
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Returns value between -1 and 1 (typically 0 to 1 for embeddings).
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        try:
            # Convert to numpy arrays for efficiency
            v1 = np.array(vec1, dtype=np.float32)
            v2 = np.array(vec2, dtype=np.float32)
            
            # Cosine similarity
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return float(dot_product / (norm1 * norm2))
            
        except Exception as e:
            logger_obj.error(f"Similarity calculation failed: {e}")
            return 0.0
    
    def get_embedding(self, fact_id: str) -> Optional[List[float]]:
        """Get embedding vector for a fact."""
        cursor = self.conn.cursor()
        
        try:
            # Try semantic_embeddings first
            cursor.execute("""
                SELECT embedding, model, dimensions
                FROM semantic_embeddings
                WHERE fact_id = ?
            """, (fact_id,))
            
            row = cursor.fetchone()
            if row:
                embedding = self._parse_embedding(row['embedding'])
                return embedding
            
            # Fallback to fact_embeddings
            cursor.execute("""
                SELECT embedding, model, dimensions
                FROM fact_embeddings
                WHERE fact_id = ?
            """, (fact_id,))
            
            row = cursor.fetchone()
            if row:
                embedding = self._parse_embedding(row['embedding'])
                return embedding
            
            logger_obj.warning(f"No embedding found for {fact_id}")
            return None
            
        except Exception as e:
            logger_obj.error(f"Failed to get embedding: {e}")
            return None
    
    def get_all_embeddings(self) -> Dict[str, Tuple[List[float], str]]:
        """
        Get all embeddings from database.
        
        Returns:
            Dict of fact_id → (embedding, model)
        """
        cursor = self.conn.cursor()
        embeddings = {}
        
        try:
            cursor.execute("""
                SELECT fact_id, embedding, model, dimensions
                FROM semantic_embeddings
                ORDER BY created_at DESC
            """)
            
            for row in cursor.fetchall():
                embedding = self._parse_embedding(row['embedding'])
                if embedding:
                    embeddings[row['fact_id']] = (embedding, row['model'])
            
            logger_obj.info(f"Loaded {len(embeddings)} embeddings from database")
            return embeddings
            
        except Exception as e:
            logger_obj.error(f"Failed to load embeddings: {e}")
            return {}
    
    def semantic_similarity(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        min_similarity: float = 0.3
    ) -> List[Tuple[str, float]]:
        """
        Find facts most similar to query embedding.
        
        Returns:
            List of (fact_id, similarity_score) tuples, sorted by score DESC
        """
        cursor = self.conn.cursor()
        results = []
        
        try:
            # Get all facts with embeddings
            cursor.execute("""
                SELECT se.fact_id, se.embedding, mf.content
                FROM semantic_embeddings se
                JOIN memory_facts mf ON se.fact_id = mf.id
                WHERE se.embedding IS NOT NULL
            """)
            
            for row in cursor.fetchall():
                embedding = self._parse_embedding(row['embedding'])
                if not embedding:
                    continue
                
                similarity = self._cosine_similarity(query_embedding, embedding)
                
                if similarity >= min_similarity:
                    results.append((row['fact_id'], similarity, row['content']))
            
            # Sort by similarity (descending)
            results.sort(key=lambda x: x[1], reverse=True)
            
            # Return top-K
            top_results = [
                (fact_id, score, content)
                for fact_id, score, content in results[:top_k]
            ]
            
            logger_obj.info(f"Semantic search: {len(top_results)}/{len(results)} above threshold")
            return top_results
            
        except Exception as e:
            logger_obj.error(f"Semantic similarity search failed: {e}")
            return []
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10
    ) -> List[Dict]:
        """
        Semantic search with full fact details.
        
        Returns:
            List of dicts with fact_id, content, similarity_score, etc.
        """
        cursor = self.conn.cursor()
        results = []
        
        try:
            # Get all embeddings and facts
            cursor.execute("""
                SELECT 
                    se.fact_id,
                    se.embedding,
                    se.model,
                    se.dimensions,
                    mf.content,
                    mf.decay_weight,
                    mf.freshness_tier,
                    mf.referenced_count
                FROM semantic_embeddings se
                JOIN memory_facts mf ON se.fact_id = mf.id
                WHERE se.embedding IS NOT NULL
            """)
            
            for row in cursor.fetchall():
                embedding = self._parse_embedding(row['embedding'])
                if not embedding:
                    continue
                
                similarity = self._cosine_similarity(query_embedding, embedding)
                
                results.append({
                    'fact_id': row['fact_id'],
                    'content': row['content'][:200],  # Truncate for display
                    'similarity_score': round(similarity, 4),
                    'decay_weight': row['decay_weight'],
                    'freshness_tier': row['freshness_tier'],
                    'referenced_count': row['referenced_count'],
                    'model': row['model'],
                    'dimensions': row['dimensions']
                })
            
            # Sort by similarity
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            logger_obj.info(f"Semantic search: returned {len(results[:top_k])}/{len(results)} results")
            return results[:top_k]
            
        except Exception as e:
            logger_obj.error(f"Semantic search failed: {e}")
            return []
    
    def batch_similarity(
        self,
        query_embeddings: List[List[float]],
        fact_ids: List[str]
    ) -> Dict[str, List[float]]:
        """
        Calculate similarity for multiple queries against specific facts.
        
        Useful for batch operations.
        """
        results = {}
        
        for query_emb in query_embeddings:
            similarities = []
            
            for fact_id in fact_ids:
                fact_emb = self.get_embedding(fact_id)
                if fact_emb:
                    sim = self._cosine_similarity(query_emb, fact_emb)
                    similarities.append(sim)
                else:
                    similarities.append(0.0)
            
            results[str(query_embeddings.index(query_emb))] = similarities
        
        return results
    
    def get_similar_facts(
        self,
        fact_id: str,
        top_k: int = 10,
        min_similarity: float = 0.7
    ) -> List[Dict]:
        """
        Find facts similar to a given fact.
        
        Useful for deduplication detection.
        """
        # Get embedding for the fact
        query_embedding = self.get_embedding(fact_id)
        if not query_embedding:
            logger_obj.warning(f"No embedding for fact {fact_id}")
            return []
        
        # Find similar facts
        cursor = self.conn.cursor()
        results = []
        
        try:
            cursor.execute("""
                SELECT 
                    se.fact_id,
                    se.embedding,
                    mf.content,
                    mf.created_at
                FROM semantic_embeddings se
                JOIN memory_facts mf ON se.fact_id = mf.id
                WHERE se.fact_id != ? AND se.embedding IS NOT NULL
            """, (fact_id,))
            
            for row in cursor.fetchall():
                embedding = self._parse_embedding(row['embedding'])
                if not embedding:
                    continue
                
                similarity = self._cosine_similarity(query_embedding, embedding)
                
                if similarity >= min_similarity:
                    results.append({
                        'fact_id': row['fact_id'],
                        'content': row['content'][:150],
                        'similarity': round(similarity, 4),
                        'created_at': row['created_at']
                    })
            
            results.sort(key=lambda x: x['similarity'], reverse=True)
            
            logger_obj.info(f"Found {len(results[:top_k])} similar facts for {fact_id}")
            return results[:top_k]
            
        except Exception as e:
            logger_obj.error(f"Failed to find similar facts: {e}")
            return []
    
    def embedding_stats(self) -> Dict:
        """Get statistics about embeddings in database."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_embeddings,
                    COUNT(DISTINCT model) as unique_models,
                    AVG(dimensions) as avg_dimensions,
                    MAX(created_at) as latest_embedding
                FROM semantic_embeddings
            """)
            
            row = cursor.fetchone()
            
            # Get model breakdown
            cursor.execute("""
                SELECT model, COUNT(*) as count
                FROM semantic_embeddings
                GROUP BY model
            """)
            
            models = {row['model']: row['count'] for row in cursor.fetchall()}
            
            return {
                'total_embeddings': row['total_embeddings'],
                'unique_models': row['unique_models'],
                'avg_dimensions': row['avg_dimensions'],
                'latest_embedding': row['latest_embedding'],
                'models': models
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get embedding stats: {e}")
            return {}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Semantic Search")
    parser.add_argument('--search', metavar='QUERY',
                        help='Search using embedding')
    parser.add_argument('--embedding-file', metavar='FILE',
                        help='Embedding JSON file for query')
    parser.add_argument('--similar', metavar='FACT_ID',
                        help='Find similar facts')
    parser.add_argument('--top-k', type=int, default=10,
                        help='Number of results')
    parser.add_argument('--min-similarity', type=float, default=0.3,
                        help='Minimum similarity threshold')
    parser.add_argument('--stats', action='store_true',
                        help='Show embedding statistics')
    
    args = parser.parse_args()
    
    searcher = SemanticSearcher()
    
    try:
        if args.stats:
            stats = searcher.embedding_stats()
            print("\n✓ Embedding Statistics:")
            for key, val in stats.items():
                if isinstance(val, dict):
                    print(f"  {key}:")
                    for k, v in val.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  {key}: {val}")
        
        elif args.similar:
            similar = searcher.get_similar_facts(args.similar, args.top_k)
            print(f"\n✓ Similar facts to {args.similar}:")
            for fact in similar:
                print(f"  {fact['fact_id']} ({fact['similarity']:.3f})")
                print(f"    {fact['content'][:80]}...")
        
        elif args.search and args.embedding_file:
            # Load embedding from file
            import json
            with open(args.embedding_file) as f:
                query_embedding = json.load(f)
            
            results = searcher.search(query_embedding, args.top_k)
            print(f"\n✓ Semantic search results:")
            for result in results:
                print(f"  {result['fact_id']} ({result['similarity_score']:.3f})")
                print(f"    {result['content'][:80]}...")
    
    finally:
        searcher.close()


if __name__ == '__main__':
    main()
