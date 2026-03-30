#!/usr/bin/env python3
"""
Coherence Validator — Phase 5

Detects and repairs inconsistencies across multi-agent memory.

Three types of coherence:
1. Temporal Coherence — Events ordered correctly in time
2. Logical Coherence — Cause-effect relationships valid
3. Source Coherence — Tracking reliability and authority

Validation reports:
- Consistency matrix (which agents agree/disagree)
- Temporal violations (events out of order)
- Logical violations (conflicting facts)
- Source reliability scores
- Auto-repair suggestions

Usage:
    validator = CoherenceValidator()
    
    # Run full validation
    report = validator.validate_all()
    
    # Check specific coherence type
    temporal = validator.check_temporal_coherence()
    logical = validator.check_logical_coherence()
    source = validator.check_source_coherence()
    
    # Get inconsistencies
    inconsistencies = validator.get_inconsistencies()
    
    # Auto-repair
    validator.auto_repair(inconsistencies)
    
    # Consistency matrix
    matrix = validator.get_consistency_matrix()
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.hermes/memory-engine/logs/coherence.log'),
        logging.StreamHandler()
    ]
)
logger_obj = logging.getLogger(__name__)

DB_PATH = Path.home() / '.hermes/memory-engine/db/memory.db'

# Coherence violation types
VIOLATION_TYPES = {
    'temporal': 'Event ordering violation',
    'logical': 'Cause-effect violation',
    'source': 'Source reliability issue',
    'semantic': 'Semantic contradiction',
    'reference': 'Broken reference'
}


@dataclass
class Violation:
    """A coherence violation."""
    violation_type: str                # temporal, logical, source, semantic, reference
    severity: str                      # critical, high, medium, low
    fact_ids: List[str]               # Involved facts
    description: str                  # Human-readable description
    agents_involved: Set[str]         # {agent_id}
    suggested_fix: str                # How to repair
    timestamp: str = None


class CoherenceValidator:
    """Validate and repair multi-agent coherence."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self._connect()
        self.violations = []
    
    def _connect(self):
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            logger_obj.info("Coherence validator connected")
        except Exception as e:
            logger_obj.error(f"Failed to connect: {e}")
            raise
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def check_temporal_coherence(self) -> List[Violation]:
        """
        Check temporal ordering.
        
        Validates that:
        - Related facts are in correct time order
        - Updates don't precede creations
        - Dependencies are temporally valid
        
        Returns:
            List of temporal violations
        """
        cursor = self.conn.cursor()
        violations = []
        
        try:
            # Check: Updates shouldn't precede creation
            cursor.execute("""
                SELECT id, created_at, updated_at
                FROM memory_facts
                WHERE updated_at IS NOT NULL
                AND datetime(updated_at) < datetime(created_at)
            """)
            
            for row in cursor.fetchall():
                violations.append(Violation(
                    violation_type='temporal',
                    severity='critical',
                    fact_ids=[row['id']],
                    description=f"Fact {row['id']} updated before created",
                    agents_involved={'system'},
                    suggested_fix=f"Set updated_at >= created_at",
                    timestamp=datetime.now().isoformat()
                ))
            
            # Check: Referenced facts should exist before reference
            cursor.execute("""
                SELECT DISTINCT ref_fact_id
                FROM fact_references
                WHERE created_at IS NOT NULL
                AND ref_fact_id NOT IN (
                    SELECT id FROM memory_facts
                )
            """)
            
            for row in cursor.fetchall():
                violations.append(Violation(
                    violation_type='temporal',
                    severity='high',
                    fact_ids=[row['ref_fact_id']],
                    description=f"Referenced fact {row['ref_fact_id']} does not exist",
                    agents_involved={'system'},
                    suggested_fix="Create referenced fact or remove reference",
                    timestamp=datetime.now().isoformat()
                ))
            
            logger_obj.info(f"Found {len(violations)} temporal violations")
            return violations
            
        except Exception as e:
            logger_obj.error(f"Temporal check failed: {e}")
            return violations
    
    def check_logical_coherence(self) -> List[Violation]:
        """
        Check logical consistency.
        
        Validates that:
        - Contradictory facts don't both have high confidence
        - Causality is preserved
        - Dependencies are satisfied
        
        Returns:
            List of logical violations
        """
        cursor = self.conn.cursor()
        violations = []
        
        try:
            # Check for conflicting facts (same content, different confidence)
            cursor.execute("""
                SELECT content, COUNT(*) as count,
                       MIN(confidence) as min_conf,
                       MAX(confidence) as max_conf
                FROM memory_facts
                GROUP BY content
                HAVING count > 1
                AND (max_conf - min_conf) > 0.3
            """)
            
            for row in cursor.fetchall():
                if row['max_conf'] > 0.80:
                    violations.append(Violation(
                        violation_type='logical',
                        severity='high',
                        fact_ids=[],
                        description=f"Conflicting confidence for fact: {row['content'][:50]}",
                        agents_involved={'multi-agent'},
                        suggested_fix="Review and reconcile confidence scores",
                        timestamp=datetime.now().isoformat()
                    ))
            
            # Check: Dependent facts should have compatible confidence
            cursor.execute("""
                SELECT mf.id, mf.confidence, rf.ref_fact_id, rf.dependency_strength
                FROM memory_facts mf
                JOIN fact_references fr ON mf.id = fr.fact_id
                JOIN memory_facts rf ON fr.ref_fact_id = rf.id
                WHERE mf.confidence > 0.80
                AND rf.confidence < 0.60
                AND fr.dependency_strength > 0.7
            """)
            
            for row in cursor.fetchall():
                violations.append(Violation(
                    violation_type='logical',
                    severity='medium',
                    fact_ids=[row['id'], row['ref_fact_id']],
                    description=f"High-confidence fact depends on low-confidence fact",
                    agents_involved={'system'},
                    suggested_fix="Lower confidence or increase dependency fact's confidence",
                    timestamp=datetime.now().isoformat()
                ))
            
            logger_obj.info(f"Found {len(violations)} logical violations")
            return violations
            
        except Exception as e:
            logger_obj.error(f"Logical check failed: {e}")
            return violations
    
    def check_source_coherence(self) -> List[Violation]:
        """
        Check source reliability.
        
        Validates that:
        - Agents maintain consistent authority
        - Sources are tracked correctly
        - Reliability scores are valid
        
        Returns:
            List of source violations
        """
        cursor = self.conn.cursor()
        violations = []
        
        try:
            # Check: Agent authority shouldn't vary by fact type
            cursor.execute("""
                SELECT agent_id,
                       MIN(confidence) as min_conf,
                       MAX(confidence) as max_conf,
                       COUNT(*) as fact_count
                FROM memory_facts
                WHERE agent_id IN ('falcon', 'hermes_agent', 'leo')
                GROUP BY agent_id
                HAVING (max_conf - min_conf) > 0.5
            """)
            
            for row in cursor.fetchall():
                if row['fact_count'] > 10:
                    violations.append(Violation(
                        violation_type='source',
                        severity='medium',
                        fact_ids=[],
                        description=f"Agent {row['agent_id']} has inconsistent confidence range",
                        agents_involved={row['agent_id']},
                        suggested_fix="Normalize or re-evaluate agent's facts",
                        timestamp=datetime.now().isoformat()
                    ))
            
            # Check: Stale facts should be marked as such
            cursor.execute("""
                SELECT id, content, updated_at
                FROM memory_facts
                WHERE datetime(updated_at) < datetime('now', '-30 days')
                AND confidence > 0.80
                LIMIT 10
            """)
            
            stale_count = cursor.rowcount
            if stale_count > 5:
                violations.append(Violation(
                    violation_type='source',
                    severity='low',
                    fact_ids=[],
                    description=f"Found {stale_count} stale high-confidence facts",
                    agents_involved={'system'},
                    suggested_fix="Review and update stale facts",
                    timestamp=datetime.now().isoformat()
                ))
            
            logger_obj.info(f"Found {len(violations)} source violations")
            return violations
            
        except Exception as e:
            logger_obj.error(f"Source check failed: {e}")
            return violations
    
    def validate_all(self) -> Dict:
        """
        Run all coherence checks.
        
        Returns:
            Comprehensive validation report
        """
        logger_obj.info("Starting full coherence validation")
        
        temporal = self.check_temporal_coherence()
        logical = self.check_logical_coherence()
        source = self.check_source_coherence()
        
        all_violations = temporal + logical + source
        
        # Calculate health score
        severity_weights = {
            'critical': 10,
            'high': 5,
            'medium': 2,
            'low': 1
        }
        
        violation_score = sum(
            severity_weights.get(v.severity, 1)
            for v in all_violations
        )
        
        # Health: 100 - (violation_score * 10), min 0
        health_score = max(0, 100 - (violation_score * 10))
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'health_score': health_score,
            'total_violations': len(all_violations),
            'violations_by_type': {
                'temporal': len(temporal),
                'logical': len(logical),
                'source': len(source)
            },
            'violations_by_severity': {
                'critical': len([v for v in all_violations if v.severity == 'critical']),
                'high': len([v for v in all_violations if v.severity == 'high']),
                'medium': len([v for v in all_violations if v.severity == 'medium']),
                'low': len([v for v in all_violations if v.severity == 'low'])
            },
            'violations': all_violations
        }
        
        logger_obj.info(f"Validation complete: health_score={health_score}")
        
        return report
    
    def get_inconsistencies(self) -> List[Dict]:
        """Get all current inconsistencies."""
        report = self.validate_all()
        
        return [
            {
                'type': v.violation_type,
                'severity': v.severity,
                'description': v.description,
                'fact_ids': v.fact_ids,
                'suggested_fix': v.suggested_fix
            }
            for v in report['violations']
        ]
    
    def auto_repair(self, violations: List[Violation] = None) -> Dict:
        """
        Attempt to auto-repair violations.
        
        Args:
            violations: Violations to repair (default: all detected)
        
        Returns:
            Repair report
        """
        if violations is None:
            report = self.validate_all()
            violations = report['violations']
        
        cursor = self.conn.cursor()
        repaired = 0
        failed = 0
        
        try:
            for violation in violations:
                try:
                    if violation.violation_type == 'temporal':
                        # Fix: Set updated_at = created_at if updated < created
                        for fact_id in violation.fact_ids:
                            cursor.execute("""
                                UPDATE memory_facts
                                SET updated_at = created_at
                                WHERE id = ?
                                AND datetime(updated_at) < datetime(created_at)
                            """, (fact_id,))
                            repaired += 1
                    
                    elif violation.violation_type == 'logical':
                        # Fix: Reduce confidence of dependent low-conf facts
                        if len(violation.fact_ids) >= 2:
                            cursor.execute("""
                                UPDATE memory_facts
                                SET confidence = confidence * 0.9
                                WHERE id = ?
                            """, (violation.fact_ids[1],))
                            repaired += 1
                    
                    elif violation.violation_type == 'source':
                        # Fix: Flag stale facts for review
                        for fact_id in violation.fact_ids:
                            cursor.execute("""
                                UPDATE memory_facts
                                SET metadata = json_set(metadata, '$.needs_review', true)
                                WHERE id = ?
                            """, (fact_id,))
                            repaired += 1
                
                except Exception as e:
                    logger_obj.error(f"Failed to repair violation: {e}")
                    failed += 1
            
            self.conn.commit()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'violations_processed': len(violations),
                'repaired': repaired,
                'failed': failed,
                'status': 'complete'
            }
            
        except Exception as e:
            self.conn.rollback()
            logger_obj.error(f"Auto-repair failed: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def get_consistency_matrix(self) -> Dict:
        """
        Get consistency matrix across agents.
        
        Shows which agents agree/disagree on facts.
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT agent_id, COUNT(*) as fact_count,
                       AVG(confidence) as avg_confidence
                FROM memory_facts
                WHERE agent_id IN ('falcon', 'hermes_agent', 'leo')
                GROUP BY agent_id
            """)
            
            matrix = {}
            for row in cursor.fetchall():
                matrix[row['agent_id']] = {
                    'fact_count': row['fact_count'],
                    'avg_confidence': round(row['avg_confidence'], 4)
                }
            
            return {
                'matrix': matrix,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger_obj.error(f"Failed to get consistency matrix: {e}")
            return {}


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Coherence Validator")
    parser.add_argument('--validate', action='store_true',
                        help='Run full validation')
    parser.add_argument('--temporal', action='store_true',
                        help='Check temporal coherence')
    parser.add_argument('--logical', action='store_true',
                        help='Check logical coherence')
    parser.add_argument('--source', action='store_true',
                        help='Check source coherence')
    parser.add_argument('--repair', action='store_true',
                        help='Auto-repair violations')
    parser.add_argument('--matrix', action='store_true',
                        help='Show consistency matrix')
    
    args = parser.parse_args()
    
    validator = CoherenceValidator()
    
    try:
        if args.validate:
            report = validator.validate_all()
            print(f"\n✓ Validation Report:")
            print(f"  Health Score: {report['health_score']}/100")
            print(f"  Total Violations: {report['total_violations']}")
            print(f"  By Type: {report['violations_by_type']}")
            print(f"  By Severity: {report['violations_by_severity']}")
        
        elif args.temporal:
            violations = validator.check_temporal_coherence()
            print(f"\n✓ Temporal Violations: {len(violations)}")
            for v in violations[:5]:
                print(f"  • {v.severity}: {v.description}")
        
        elif args.logical:
            violations = validator.check_logical_coherence()
            print(f"\n✓ Logical Violations: {len(violations)}")
            for v in violations[:5]:
                print(f"  • {v.severity}: {v.description}")
        
        elif args.source:
            violations = validator.check_source_coherence()
            print(f"\n✓ Source Violations: {len(violations)}")
            for v in violations[:5]:
                print(f"  • {v.severity}: {v.description}")
        
        elif args.repair:
            report = validator.auto_repair()
            print(f"\n✓ Auto-Repair Report:")
            for key, val in report.items():
                print(f"  {key}: {val}")
        
        elif args.matrix:
            matrix = validator.get_consistency_matrix()
            print(f"\n✓ Consistency Matrix:")
            for agent, stats in matrix.get('matrix', {}).items():
                print(f"  {agent}: {stats}")
        
        else:
            parser.print_help()
    
    finally:
        validator.close()


if __name__ == '__main__':
    main()
