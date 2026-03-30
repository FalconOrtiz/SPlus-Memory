#!/usr/bin/env python3
"""
Cross-Agent Inference Engine — Phase 5

Query all agents simultaneously and synthesize unified answers.

Process:
1. Parse user query
2. Route to all agents (Falcon, Katsumi, LEO)
3. Each agent searches memory independently
4. Combine results with weighted ranking
5. Synthesize unified answer with confidence score

Agent specialization:
- Falcon: Technical facts, implementation details, system architecture
- Katsumi: Patterns, relationships, temporal context, memories
- LEO: External validation, external data sources, outreach context

Usage:
    inferencer = CrossAgentInferencer()
    
    # Query all agents
    result = inferencer.query("What is the memory system architecture?")
    
    # Result includes:
    # - unified_answer: synthesized response
    # - confidence: combined confidence score
    # - agent_results: individual agent responses
    # - sources: which agents contributed most
    # - reasoning: how answer was synthesized

Example output:
    {
        "query": "memory system architecture",
        "unified_answer": "The memory system uses hybrid ranking (BM25 + 
                           semantic + temporal) with contextual windowing...",
        "confidence": 0.91,
        "agent_results": {
            "falcon": [score, score, score, ...],
            "katsumi": [score, score, score, ...],
            "leo": [score, score, score, ...]
        },
        "combined_ranking": [top_1_from_falcon, top_2_from_katsumi, ...],
        "synthesis_method": "weighted_fusion",
        "timestamp": "2026-03-24T18:30:00"
    }
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/inference.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'

# Agent specialization weights
AGENT_SPECIALIZATION = {
    'falcon': {
        'technical': 0.95,
        'architecture': 0.95,
        'implementation': 0.90,
        'system': 0.90,
        'performance': 0.85,
        'optimization': 0.80,
        'default': 0.75
    },
    'katsumi': {
        'pattern': 0.95,
        'relationship': 0.92,
        'temporal': 0.90,
        'context': 0.90,
        'integration': 0.85,
        'coordination': 0.80,
        'default': 0.80
    },
    'leo': {
        'external': 0.95,
        'outreach': 0.90,
        'validation': 0.85,
        'communication': 0.80,
        'social': 0.75,
        'integration': 0.70,
        'default': 0.70
    }
}


@dataclass
class AgentResult:
    """Result from single agent query."""
    agent_id: str
    query: str
    results: List[Dict]           # Top results from agent
    confidence: float             # Agent's confidence in results
    relevance: float              # Query relevance score
    summary: str                  # Agent's summary
    search_time_ms: float         # Query latency


@dataclass
class InferenceResult:
    """Combined inference result."""
    query: str
    unified_answer: str           # Synthesized answer
    confidence: float             # Combined confidence (0.0-1.0)
    agent_results: Dict[str, AgentResult]
    combined_ranking: List[Dict]  # Merged/ranked results
    sources: Dict[str, float]     # {agent_id: contribution_score}
    synthesis_method: str         # How answer was created
    query_time_ms: float          # Total latency


class CrossAgentInferencer:
    """Query all agents and synthesize answers."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        self.agents = ['falcon', 'katsumi', 'leo']
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info("Inference engine connected")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def _get_agent_specialization_weight(
        self,
        agent_id: str,
        query: str
    ) -> float:
        """
        Calculate specialization weight based on query content.
        
        Analyzes query keywords and matches to agent expertise.
        """
        spec = AGENT_SPECIALIZATION.get(agent_id, {})
        
        query_lower = query.lower()
        best_weight = spec.get('default', 0.75)
        
        for keyword, weight in spec.items():
            if keyword != 'default' and keyword in query_lower:
                best_weight = max(best_weight, weight)
        
        return best_weight
    
    def _query_agent(
        self,
        agent_id: str,
        query: str,
        limit: int = 5
    ) -> AgentResult:
        """
        Query a single agent's memory.
        
        Simulates agent query by searching memory facts
        associated with that agent.
        
        Args:
            agent_id: Agent to query
            query: Search query
            limit: Max results to return
        
        Returns:
            AgentResult with search results
        """
        cursor = self.conn.cursor()
        import time
        start = time.time()
        
        try:
            # Search facts associated with agent
            cursor.execute("""
                SELECT id, content, confidence, agent_id, created_at
                FROM memory_facts
                WHERE agent_id IN (?, 'shared')
                AND (content LIKE ? OR content LIKE ?)
                ORDER BY confidence DESC, created_at DESC
                LIMIT ?
            """, (agent_id, f"%{query}%", f"%{query.split()[0]}%", limit))
            
            results = [dict(row) for row in cursor.fetchall()]
            
            # Calculate metrics
            confidence = sum(r['confidence'] for r in results) / len(results) if results else 0.0
            relevance = self._get_agent_specialization_weight(agent_id, query)
            
            summary = f"Found {len(results)} relevant facts"
            if results:
                summary += f" (avg confidence: {confidence:.2f})"
            
            elapsed = (time.time() - start) * 1000  # ms
            
            return AgentResult(
                agent_id=agent_id,
                query=query,
                results=results,
                confidence=confidence,
                relevance=relevance,
                summary=summary,
                search_time_ms=elapsed
            )
            
        except Exception as e:
            logger_obj.error(f"Agent {agent_id} query failed: {e}")
            return AgentResult(
                agent_id=agent_id,
                query=query,
                results=[],
                confidence=0.0,
                relevance=0.0,
                summary=f"Query failed: {str(e)}",
                search_time_ms=0.0
            )
    
    def _merge_and_rank(
        self,
        agent_results: Dict[str, AgentResult]
    ) -> Tuple[List[Dict], Dict[str, float]]:
        """
        Merge results from all agents into unified ranking.
        
        Uses Borda count (ranked voting) combined with:
        - Confidence scores
        - Relevance weights
        - Deduplication
        
        Args:
            agent_results: Results from all agents
        
        Returns:
            (merged_ranking, agent_contribution_scores)
        """
        # Deduplicate by fact_id, keeping highest confidence
        fact_scores = {}
        fact_data = {}
        
        for agent_id, result in agent_results.items():
            agent_weight = result.relevance  # Specialization weight
            
            for idx, fact in enumerate(result.results):
                fact_id = fact['id']
                
                # Score = (confidence * agent_weight) + (position_bonus)
                position_bonus = (1.0 / (idx + 1)) * 0.2  # Diminishing with position
                score = (fact['confidence'] * agent_weight) + position_bonus
                
                if fact_id not in fact_scores:
                    fact_scores[fact_id] = score
                    fact_data[fact_id] = fact
                else:
                    # Keep highest score
                    if score > fact_scores[fact_id]:
                        fact_scores[fact_id] = score
                        fact_data[fact_id] = fact
        
        # Rank by combined score
        ranked = sorted(
            fact_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        merged_ranking = [
            {**fact_data[fact_id], 'combined_score': score}
            for fact_id, score in ranked
        ]
        
        # Calculate agent contribution
        agent_contributions = {}
        for agent_id, result in agent_results.items():
            agent_facts = sum(1 for f in result.results)
            contribution = agent_facts * result.relevance / len(agent_results)
            agent_contributions[agent_id] = round(contribution, 4)
        
        return merged_ranking, agent_contributions
    
    def _synthesize_answer(
        self,
        query: str,
        merged_ranking: List[Dict],
        agent_results: Dict[str, AgentResult]
    ) -> Tuple[str, float]:
        """
        Synthesize unified answer from all results.
        
        Combines top facts into a coherent answer.
        
        Args:
            query: Original query
            merged_ranking: Combined ranked results
            agent_results: Individual agent results
        
        Returns:
            (synthesized_answer, confidence)
        """
        if not merged_ranking:
            return "No information found.", 0.0
        
        # Calculate overall confidence
        avg_confidence = sum(
            r.get('confidence', 0.0)
            for r in merged_ranking[:3]
        ) / min(3, len(merged_ranking))
        
        # Build answer from top facts
        top_facts = merged_ranking[:3]
        sources = [f['agent_id'] for f in top_facts]
        
        answer_parts = [
            f"Query: {query}\n",
            f"Based on {len([r for r in agent_results.values() if r.results])} agent(s):\n\n"
        ]
        
        for i, fact in enumerate(top_facts, 1):
            agent = fact['agent_id']
            conf = fact.get('confidence', 0.0)
            content = fact.get('content', '')[:100]
            answer_parts.append(f"{i}. ({agent}, confidence={conf:.2f}) {content}...\n")
        
        synthesized = "".join(answer_parts)
        
        logger_obj.info(f"Synthesized answer (confidence={avg_confidence:.2f})")
        return synthesized, avg_confidence
    
    def query(self, query: str) -> InferenceResult:
        """
        Query all agents and synthesize answer.
        
        Args:
            query: User query
        
        Returns:
            InferenceResult with unified answer
        """
        import time
        start = time.time()
        
        logger_obj.info(f"Starting cross-agent query: {query}")
        
        # Step 1: Query all agents
        agent_results = {}
        for agent_id in self.agents:
            result = self._query_agent(agent_id, query)
            agent_results[agent_id] = result
        
        # Step 2: Merge and rank results
        merged_ranking, agent_contributions = self._merge_and_rank(agent_results)
        
        # Step 3: Synthesize answer
        answer, confidence = self._synthesize_answer(query, merged_ranking, agent_results)
        
        elapsed = (time.time() - start) * 1000  # ms
        
        result = InferenceResult(
            query=query,
            unified_answer=answer,
            confidence=confidence,
            agent_results=agent_results,
            combined_ranking=merged_ranking[:5],  # Top 5
            sources=agent_contributions,
            synthesis_method='weighted_fusion',
            query_time_ms=elapsed
        )
        
        logger_obj.info(f"Query complete: {elapsed:.2f}ms, confidence={confidence:.2f}")
        
        return result
    
    def to_dict(self, result: InferenceResult) -> Dict:
        """Convert result to dictionary."""
        return {
            'query': result.query,
            'unified_answer': result.unified_answer,
            'confidence': round(result.confidence, 4),
            'agent_results': {
                agent_id: {
                    'confidence': round(r.confidence, 4),
                    'relevance': round(r.relevance, 4),
                    'results_count': len(r.results),
                    'summary': r.summary,
                    'search_time_ms': round(r.search_time_ms, 2)
                }
                for agent_id, r in result.agent_results.items()
            },
            'combined_ranking': [
                {
                    'id': f.get('id', ''),
                    'content': f.get('content', '')[:80],
                    'agent': f.get('agent_id', ''),
                    'confidence': round(f.get('confidence', 0.0), 4),
                    'score': round(f.get('combined_score', 0.0), 4)
                }
                for f in result.combined_ranking
            ],
            'sources': result.sources,
            'query_time_ms': round(result.query_time_ms, 2),
            'timestamp': datetime.now().isoformat()
        }


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cross-Agent Inferencer")
    parser.add_argument('query', help='Query to send to all agents')
    parser.add_argument('--verbose', action='store_true',
                        help='Show detailed output')
    
    args = parser.parse_args()
    
    inferencer = CrossAgentInferencer()
    
    try:
        result = inferencer.query(args.query)
        output = inferencer.to_dict(result)
        
        print(f"\n✓ Cross-Agent Inference Results:")
        print(f"  Query: {output['query']}")
        print(f"  Confidence: {output['confidence']}")
        print(f"  Time: {output['query_time_ms']}ms")
        print(f"\n✓ Unified Answer:")
        print(f"  {output['unified_answer']}")
        print(f"\n✓ Agent Contributions:")
        for agent, contrib in output['sources'].items():
            print(f"  {agent}: {contrib}")
        
        if args.verbose:
            print(f"\n✓ Combined Ranking:")
            for fact in output['combined_ranking']:
                print(f"  • {fact['id']}: {fact['content']} ({fact['score']})")
    
    finally:
        inferencer.close()


if __name__ == '__main__':
    main()
