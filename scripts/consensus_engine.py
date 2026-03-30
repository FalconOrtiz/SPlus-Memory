#!/usr/bin/env python3
"""
Consensus Engine — Phase 5

Voting mechanism for multi-agent fact validation.

Each agent votes on fact accuracy (0.0-1.0):
- Falcon: 0.95 authority (technical implementation)
- Hermes: 0.90 authority (pattern recognition)
- LEO: 0.75 authority (external validation)

Consensus rules:
- Unanimous (3/3): confidence = min(votes) * authority_avg
- 2/3 agreement: confidence = (sum(top_2_votes) / 2) * 0.85 * authority_avg
- 1/3 or split: requires manual review, confidence = 0.5

Usage:
    voter = ConsensusEngine()
    
    # Register agent votes
    voter.vote('fact_id', 'falcon', 0.95)
    voter.vote('fact_id', 'hermes_agent', 0.92)
    voter.vote('fact_id', 'leo', 0.88)
    
    # Get consensus
    result = voter.get_consensus('fact_id')
    # → {consensus: 0.91, agreement: 3, status: 'approved', agents: {...}}
    
    # Find disputed facts
    disputed = voter.get_disputed_facts(threshold=0.70)
    
    # Audit trail
    audit = voter.get_vote_history('fact_id')
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/consensus.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'

# Agent authority weights
AGENT_AUTHORITY = {
    'falcon': 0.95,
    'hermes_agent': 0.90,
    'leo': 0.75
}


@dataclass
class ConsensusResult:
    """Result of consensus calculation."""
    fact_id: str
    consensus_score: float          # 0.0-1.0
    agreement_count: int            # 0-3 agents agreed
    status: str                      # 'approved', 'disputed', 'pending'
    agent_votes: Dict[str, float]   # {agent_id: confidence}
    authority_weighted: float       # Authority-weighted score
    recommendation: str             # Action to take


class ConsensusEngine:
    """Multi-agent voting and consensus."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info(f"Consensus engine connected to {self.db_path}")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def vote(
        self,
        fact_id: str,
        agent_id: str,
        confidence: float,
        reason: str = None
    ) -> bool:
        """
        Record an agent's vote on a fact.
        
        Args:
            fact_id: Fact being voted on
            agent_id: Agent voting (falcon, hermes_agent, leo)
            confidence: Vote strength (0.0-1.0)
            reason: Optional reason for vote
        
        Returns:
            True if vote recorded
        """
        cursor = self.conn.cursor()
        
        try:
            # Validate inputs
            if not (0.0 <= confidence <= 1.0):
                logger_obj.warning(f"Invalid confidence: {confidence}")
                return False
            
            if agent_id not in AGENT_AUTHORITY:
                logger_obj.warning(f"Unknown agent: {agent_id}")
                return False
            
            # Record vote
            cursor.execute("""
                INSERT INTO agent_votes
                (fact_id, agent_id, confidence, reason, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (fact_id, agent_id, confidence, reason, datetime.now().isoformat()))
            
            self.conn.commit()
            logger_obj.info(f"Vote recorded: {fact_id} by {agent_id} = {confidence}")
            return True
            
        except Exception as e:
            logger_obj.error(f"Failed to record vote: {e}")
            return False
    
    def get_votes(self, fact_id: str) -> Dict[str, float]:
        """Get all votes for a fact."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT agent_id, confidence
                FROM agent_votes
                WHERE fact_id = ?
                ORDER BY timestamp DESC
            """, (fact_id,))
            
            votes = {}
            for row in cursor.fetchall():
                votes[row['agent_id']] = row['confidence']
            
            return votes
            
        except Exception as e:
            logger_obj.error(f"Failed to get votes: {e}")
            return {}
    
    def calculate_consensus(self, fact_id: str) -> ConsensusResult:
        """
        Calculate consensus for a fact.
        
        Algorithm:
        1. Collect all agent votes
        2. Calculate agreement level (0-3 agents)
        3. Apply authority weighting
        4. Determine consensus status
        5. Generate recommendation
        
        Args:
            fact_id: Fact to calculate consensus for
        
        Returns:
            ConsensusResult with detailed breakdown
        """
        votes = self.get_votes(fact_id)
        
        if not votes:
            return ConsensusResult(
                fact_id=fact_id,
                consensus_score=0.0,
                agreement_count=0,
                status='pending',
                agent_votes={},
                authority_weighted=0.0,
                recommendation='No votes yet'
            )
        
        # Calculate authority-weighted average
        total_authority = 0.0
        weighted_sum = 0.0
        
        for agent_id, confidence in votes.items():
            authority = AGENT_AUTHORITY.get(agent_id, 0.5)
            weighted_sum += confidence * authority
            total_authority += authority
        
        authority_weighted = weighted_sum / total_authority if total_authority > 0 else 0.0
        
        # Determine agreement level
        agreement_count = len(votes)
        
        # Calculate consensus score
        if agreement_count == 3:
            # Unanimous: use minimum confidence * authority avg
            min_confidence = min(votes.values())
            authority_avg = sum(AGENT_AUTHORITY.values()) / 3
            consensus_score = min_confidence * authority_avg
            recommendation = "APPROVED - Unanimous consensus"
            status = "approved"
        
        elif agreement_count == 2:
            # Majority: use average of top 2 * discount factor
            sorted_votes = sorted(votes.values(), reverse=True)
            avg_confidence = sum(sorted_votes[:2]) / 2
            consensus_score = avg_confidence * 0.85  # 15% discount for missing vote
            recommendation = "APPROVED - Majority consensus"
            status = "approved"
        
        else:
            # Single vote: requires manual review
            consensus_score = votes[list(votes.keys())[0]] * 0.5
            recommendation = "REQUIRES REVIEW - Only single agent voted"
            status = "disputed"
        
        # Override status if consensus is too low
        if consensus_score < 0.60:
            status = "disputed"
            recommendation = "DISPUTED - Consensus score too low"
        
        return ConsensusResult(
            fact_id=fact_id,
            consensus_score=consensus_score,
            agreement_count=agreement_count,
            status=status,
            agent_votes=votes,
            authority_weighted=authority_weighted,
            recommendation=recommendation
        )
    
    def get_consensus(self, fact_id: str) -> Dict:
        """Get consensus as dictionary."""
        result = self.calculate_consensus(fact_id)
        
        return {
            'fact_id': result.fact_id,
            'consensus_score': round(result.consensus_score, 4),
            'agreement_count': result.agreement_count,
            'status': result.status,
            'agent_votes': {k: round(v, 4) for k, v in result.agent_votes.items()},
            'authority_weighted': round(result.authority_weighted, 4),
            'recommendation': result.recommendation,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_disputed_facts(self, threshold: float = 0.70) -> List[Dict]:
        """
        Find facts with low consensus.
        
        Args:
            threshold: Consensus score threshold (default: 0.70)
        
        Returns:
            List of disputed facts
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT DISTINCT fact_id
                FROM agent_votes
                GROUP BY fact_id
            """)
            
            disputed = []
            for row in cursor.fetchall():
                consensus = self.calculate_consensus(row['fact_id'])
                
                if consensus.consensus_score < threshold:
                    disputed.append(self.get_consensus(row['fact_id']))
            
            logger_obj.info(f"Found {len(disputed)} disputed facts")
            return disputed
            
        except Exception as e:
            logger_obj.error(f"Failed to get disputed facts: {e}")
            return []
    
    def get_vote_history(self, fact_id: str) -> List[Dict]:
        """Get voting history for a fact."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT *
                FROM agent_votes
                WHERE fact_id = ?
                ORDER BY timestamp DESC
            """, (fact_id,))
            
            history = [dict(row) for row in cursor.fetchall()]
            return history
            
        except Exception as e:
            logger_obj.error(f"Failed to get vote history: {e}")
            return []
    
    def get_agent_accuracy(self, agent_id: str) -> Dict:
        """
        Get voting accuracy for an agent.
        
        Compares votes against final consensus to measure accuracy.
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT COUNT(*) as total_votes
                FROM agent_votes
                WHERE agent_id = ?
            """, (agent_id,))
            
            total = cursor.fetchone()['total_votes']
            
            if total == 0:
                return {
                    'agent_id': agent_id,
                    'total_votes': 0,
                    'accuracy': 0.0,
                    'authority': AGENT_AUTHORITY.get(agent_id, 0.5)
                }
            
            # Count agreements with final consensus
            cursor.execute("""
                SELECT COUNT(*) as matching_votes
                FROM agent_votes av
                WHERE av.agent_id = ? AND (
                    SELECT status FROM agent_votes
                    WHERE fact_id = av.fact_id
                    GROUP BY fact_id
                    HAVING COUNT(*) >= 2
                ) IS NOT NULL
            """, (agent_id,))
            
            matching = cursor.fetchone()['matching_votes'] or 0
            accuracy = matching / total if total > 0 else 0.0
            
            return {
                'agent_id': agent_id,
                'total_votes': total,
                'matching_votes': matching,
                'accuracy': round(accuracy, 4),
                'authority': AGENT_AUTHORITY.get(agent_id, 0.5)
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get agent accuracy: {e}")
            return {}
    
    def approve_consensus(
        self,
        fact_id: str,
        approver: str = 'system'
    ) -> bool:
        """
        Mark a consensus as approved and update fact.
        
        Args:
            fact_id: Fact to approve
            approver: Who approved (agent or human)
        
        Returns:
            True if approved
        """
        cursor = self.conn.cursor()
        
        try:
            consensus = self.calculate_consensus(fact_id)
            
            cursor.execute("""
                UPDATE memory_facts
                SET confidence = ?,
                    agent_id = 'shared',
                    updated_at = ?
                WHERE id = ?
            """, (consensus.consensus_score, datetime.now().isoformat(), fact_id))
            
            cursor.execute("""
                INSERT INTO consensus_log
                (fact_id, consensus_score, approver, timestamp)
                VALUES (?, ?, ?, ?)
            """, (fact_id, consensus.consensus_score, approver, datetime.now().isoformat()))
            
            self.conn.commit()
            logger_obj.info(f"Consensus approved: {fact_id} (score={consensus.consensus_score})")
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger_obj.error(f"Failed to approve consensus: {e}")
            return False


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Consensus Engine")
    parser.add_argument('--vote', nargs=3, metavar=('FACT_ID', 'AGENT', 'CONFIDENCE'),
                        help='Record a vote')
    parser.add_argument('--consensus', metavar='FACT_ID',
                        help='Get consensus for fact')
    parser.add_argument('--disputed', type=float, default=0.70,
                        help='Show disputed facts (threshold)')
    parser.add_argument('--history', metavar='FACT_ID',
                        help='Show vote history')
    parser.add_argument('--accuracy', metavar='AGENT',
                        help='Get agent voting accuracy')
    
    args = parser.parse_args()
    
    voter = ConsensusEngine()
    
    try:
        if args.vote:
            fact_id, agent, confidence = args.vote
            result = voter.vote(fact_id, agent, float(confidence))
            print(f"\n✓ Vote recorded: {fact_id} by {agent} = {confidence}")
        
        elif args.consensus:
            result = voter.get_consensus(args.consensus)
            print(f"\n✓ Consensus for {args.consensus}:")
            for key, val in result.items():
                print(f"  {key}: {val}")
        
        elif args.disputed:
            disputed = voter.get_disputed_facts(args.disputed)
            print(f"\n✓ Disputed Facts ({len(disputed)}):")
            for fact in disputed:
                print(f"  • {fact['fact_id']}: {fact['consensus_score']} - {fact['status']}")
        
        elif args.history:
            history = voter.get_vote_history(args.history)
            print(f"\n✓ Vote History for {args.history} ({len(history)} votes):")
            for vote in history:
                print(f"  • {vote['agent_id']}: {vote['confidence']} ({vote['timestamp']})")
        
        elif args.accuracy:
            acc = voter.get_agent_accuracy(args.accuracy)
            print(f"\n✓ Agent Accuracy - {args.accuracy}:")
            for key, val in acc.items():
                print(f"  {key}: {val}")
    
    finally:
        voter.close()


if __name__ == '__main__':
    main()
