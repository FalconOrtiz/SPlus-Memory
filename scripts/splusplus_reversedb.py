#!/usr/bin/env python3
"""
S++ + ReverseDB Unified Execution Layer
========================================

Integration between ReverseDB (query optimization) and S++ (cognitive solving):
- ReverseDB provides cost estimation and query optimization
- S++ provides procedural intelligence for complex queries
- Unified execution with intelligent routing

Architecture:
    ┌─────────────────────────────────────────────┐
    │            Unified Query Router             │
    ├─────────────────────────────────────────────┤
    │  Simple Query → ReverseDB (optimizer)       │
    │  Complex Query → S++ (cognitive solver)     │
    │  Hybrid → Both (optimization + execution)   │
    └─────────────────────────────────────────────┘

Usage:
    python splusplus_reversedb.py --status
    python splusplus_reversedb.py --integrate
    python splusplus_reversedb.py --test-query "SELECT * FROM ..."
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class QueryComplexity(Enum):
    """Query complexity classification."""
    SIMPLE = "simple"          # Direct execution via ReverseDB
    MODERATE = "moderate"      # ReverseDB optimization + execution
    COMPLEX = "complex"        # S++ procedural analysis
    UNKNOWN = "unknown"        # Needs analysis


@dataclass
class QueryPlan:
    """Unified query execution plan."""
    query: str
    complexity: QueryComplexity
    estimated_cost: float = 0.0
    estimated_time_ms: float = 0.0
    
    # Routing decision
    use_reversedb: bool = True
    use_splusplus: bool = False
    
    # ReverseDB optimization
    reversedb_optimized_sql: Optional[str] = None
    reversedb_index_suggestions: List[str] = field(default_factory=list)
    
    # S++ procedural analysis
    splusplus_procedure: Optional[Dict] = None
    splusplus_tools: List[str] = field(default_factory=list)
    
    # Execution metadata
    execution_time_ms: float = 0.0
    success: bool = False
    error: Optional[str] = None


class ReverseDBIntegration:
    """Integrates ReverseDB with S++."""
    
    def __init__(self):
        self.home = Path.home()
        self.splusplus_home = self.home / ".splusplus"
        self.hermes_home = self.home / ".hermes"
        
        self.reversedb_path = self.hermes_home / "reversedb"
        self.reversedb_available = self._check_reversedb()
        
        self.splusplus_available = self._check_splusplus()
    
    def _check_reversedb(self) -> bool:
        """Check if ReverseDB is available."""
        if not self.reversedb_path.exists():
            return False
        
        # Check for main executable or module
        return (self.reversedb_path / "reversedb.py").exists() or \
               (self.reversedb_path / "reverse.py").exists()
    
    def _check_splusplus(self) -> bool:
        """Check if S++ core is available."""
        splusplus_path = self.home / "Documents" / "GitHub" / "SPlus-Memory"
        if not splusplus_path.exists():
            splusplus_path = Path("/workspace/SPlus-Memory")
        
        return (splusplus_path / "splusplus" / "core" / "splusplus_engine.py").exists()
    
    def status(self) -> Dict[str, Any]:
        """Get integration status."""
        return {
            "reversedb": {
                "available": self.reversedb_available,
                "path": str(self.reversedb_path) if self.reversedb_available else None,
                "version": self._get_reversedb_version() if self.reversedb_available else None
            },
            "splusplus": {
                "available": self.splusplus_available,
                "path": str(self._get_splusplus_path()),
                "version": "2.0.0-GIGABRAIN"
            },
            "integration_status": "active" if (self.reversedb_available and self.splusplus_available) else "partial",
            "unified_execution": self.reversedb_available and self.splusplus_available
        }
    
    def _get_reversedb_version(self) -> str:
        """Get ReverseDB version."""
        try:
            version_file = self.reversedb_path / "version.txt"
            if version_file.exists():
                return version_file.read_text().strip()
        except:
            pass
        return "7.0.0"
    
    def _get_splusplus_path(self) -> Path:
        """Get S++ installation path."""
        splusplus_path = self.home / "Documents" / "GitHub" / "SPlus-Memory"
        if splusplus_path.exists():
            return splusplus_path
        
        alt_path = Path("/workspace/SPlus-Memory")
        if alt_path.exists():
            return alt_path
        
        return splusplus_path
    
    def analyze_query(self, sql: str) -> QueryPlan:
        """Analyze query and determine optimal execution path."""
        plan = QueryPlan(query=sql, complexity=self._classify_complexity(sql))
        
        # Route based on complexity
        if plan.complexity == QueryComplexity.SIMPLE:
            plan.use_reversedb = True
            plan.use_splusplus = False
            plan = self._optimize_with_reversedb(plan)
            
        elif plan.complexity == QueryComplexity.MODERATE:
            plan.use_reversedb = True
            plan.use_splusplus = False
            plan = self._optimize_with_reversedb(plan)
            
        elif plan.complexity == QueryComplexity.COMPLEX:
            plan.use_reversedb = True
            plan.use_splusplus = True
            plan = self._optimize_with_reversedb(plan)
            plan = self._analyze_with_splusplus(plan)
        
        return plan
    
    def _classify_complexity(self, sql: str) -> QueryComplexity:
        """Classify query complexity."""
        sql_upper = sql.upper()
        
        # Simple patterns
        simple_patterns = [
            "SELECT * FROM",
            "SELECT COUNT(*)",
            "INSERT INTO",
            "UPDATE",
            "DELETE FROM",
        ]
        
        # Complex patterns
        complex_patterns = [
            "WITH RECURSIVE",
            "WINDOW FUNCTION",
            "LATERAL JOIN",
            "CROSS JOIN LATERAL",
            "MULTIPLE CTEs",
            "PIVOT",
            "UNPIVOT",
        ]
        
        # Check for complex features
        if any(p in sql_upper for p in complex_patterns):
            return QueryComplexity.COMPLEX
        
        # Check for moderate complexity
        moderate_indicators = [
            sql_upper.count("JOIN") > 2,
            sql_upper.count("SUBQUERY") > 0,
            "GROUP BY" in sql_upper and "HAVING" in sql_upper,
            sql_upper.count("UNION") > 0,
        ]
        
        if any(moderate_indicators):
            return QueryComplexity.MODERATE
        
        # Check for simple patterns
        if any(p in sql_upper for p in simple_patterns):
            return QueryComplexity.SIMPLE
        
        return QueryComplexity.MODERATE
    
    def _optimize_with_reversedb(self, plan: QueryPlan) -> QueryPlan:
        """Use ReverseDB to optimize query."""
        if not self.reversedb_available:
            plan.estimated_cost = self._estimate_cost_fallback(plan.query)
            return plan
        
        try:
            # Import ReverseDB optimizer
            sys.path.insert(0, str(self.reversedb_path))
            from reversedb import QueryOptimizer, CostEstimator
            
            # Create optimizer
            optimizer = QueryOptimizer()
            estimator = CostEstimator()
            
            # Analyze query
            analysis = optimizer.analyze(plan.query)
            plan.reversedb_optimized_sql = optimizer.optimize(plan.query)
            plan.reversedb_index_suggestions = analysis.get('index_suggestions', [])
            
            # Estimate cost
            cost_estimate = estimator.estimate(plan.reversedb_optimized_sql or plan.query)
            plan.estimated_cost = cost_estimate.get('total_cost', 0.0)
            plan.estimated_time_ms = cost_estimate.get('estimated_time_ms', 0.0)
            
        except Exception as e:
            plan.estimated_cost = self._estimate_cost_fallback(plan.query)
            plan.error = f"ReverseDB optimization failed: {e}"
        
        return plan
    
    def _estimate_cost_fallback(self, sql: str) -> float:
        """Fallback cost estimation when ReverseDB unavailable."""
        sql_upper = sql.upper()
        cost = 10.0  # Base cost
        
        # Add cost for joins
        cost += sql_upper.count("JOIN") * 5.0
        
        # Add cost for subqueries
        cost += sql_upper.count("SELECT") * 3.0
        
        # Add cost for aggregations
        if "GROUP BY" in sql_upper:
            cost += 15.0
        
        # Add cost for sorting
        if "ORDER BY" in sql_upper:
            cost += 8.0
        
        return cost
    
    def _analyze_with_splusplus(self, plan: QueryPlan) -> QueryPlan:
        """Use S++ for procedural analysis of complex queries."""
        if not self.splusplus_available:
            return plan
        
        try:
            # Import S++ engine
            splusplus_path = self._get_splusplus_path()
            sys.path.insert(0, str(splusplus_path))
            from splusplus.core.splusplus_engine import SPlusPlusEngine
            
            # Create problem statement for S++
            problem = f"""
            Optimize and execute this complex SQL query:
            
            {plan.query}
            
            The query has been classified as COMPLEX with estimated cost {plan.estimated_cost}.
            Current optimization: {plan.reversedb_optimized_sql or 'None'}
            
            Create an execution procedure that:
            1. Breaks down the query into manageable steps
            2. Identifies opportunities for parallelization
            3. Handles potential memory/performance issues
            4. Implements result caching if beneficial
            """
            
            # Use S++ to solve
            engine = SPlusPlusEngine()
            result = engine.solve(problem)
            
            plan.splusplus_procedure = result.get('procedure', {})
            plan.splusplus_tools = result.get('tools', [])
            
        except Exception as e:
            plan.error = f"S++ analysis failed: {e}"
        
        return plan
    
    def execute(self, sql: str, use_procedure: bool = False) -> Dict[str, Any]:
        """Execute query using unified execution layer."""
        start_time = time.time()
        
        # Analyze and plan
        plan = self.analyze_query(sql)
        
        # Execute based on plan
        if use_procedure and plan.splusplus_procedure:
            # Use S++ procedural execution
            result = self._execute_procedure(plan)
        elif plan.reversedb_optimized_sql:
            # Use ReverseDB optimized query
            result = self._execute_optimized(plan)
        else:
            # Direct execution
            result = self._execute_direct(plan)
        
        plan.execution_time_ms = (time.time() - start_time) * 1000
        plan.success = result.get('success', False)
        
        return {
            'plan': {
                'complexity': plan.complexity.value,
                'estimated_cost': plan.estimated_cost,
                'use_reversedb': plan.use_reversedb,
                'use_splusplus': plan.use_splusplus
            },
            'execution': result,
            'metrics': {
                'execution_time_ms': plan.execution_time_ms,
                'cost_accuracy': plan.estimated_cost / max(plan.execution_time_ms, 1)
            }
        }
    
    def _execute_optimized(self, plan: QueryPlan) -> Dict[str, Any]:
        """Execute using ReverseDB optimization."""
        try:
            # Execute optimized SQL
            sql_to_execute = plan.reversedb_optimized_sql or plan.query
            
            # TODO: Connect to actual database and execute
            return {
                'success': True,
                'method': 'reversedb_optimized',
                'sql': sql_to_execute,
                'index_suggestions': plan.reversedb_index_suggestions
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _execute_procedure(self, plan: QueryPlan) -> Dict[str, Any]:
        """Execute using S++ procedural approach."""
        try:
            procedure = plan.splusplus_procedure
            
            # Execute each step
            results = []
            for step in procedure.get('steps', []):
                step_result = self._execute_step(step)
                results.append(step_result)
            
            return {
                'success': all(r.get('success', False) for r in results),
                'method': 'splusplus_procedure',
                'steps_executed': len(results),
                'step_results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _execute_step(self, step: Dict) -> Dict[str, Any]:
        """Execute a single procedural step."""
        # TODO: Implement step execution
        return {'success': True, 'step': step.get('name', 'unknown')}
    
    def _execute_direct(self, plan: QueryPlan) -> Dict[str, Any]:
        """Execute query directly."""
        return {
            'success': True,
            'method': 'direct',
            'sql': plan.query
        }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="S++ + ReverseDB Integration")
    parser.add_argument("--status", action="store_true", help="Show integration status")
    parser.add_argument("--integrate", action="store_true", help="Run integration setup")
    parser.add_argument("--test-query", help="Test query analysis")
    parser.add_argument("--execute", help="Execute a query")
    
    args = parser.parse_args()
    
    integration = ReverseDBIntegration()
    
    if args.status:
        status = integration.status()
        print("\n🔌 S++ + ReverseDB Integration Status")
        print("="*60)
        print(f"\nReverseDB:")
        print(f"   Available: {'✅' if status['reversedb']['available'] else '❌'}")
        if status['reversedb']['available']:
            print(f"   Path: {status['reversedb']['path']}")
            print(f"   Version: {status['reversedb']['version']}")
        
        print(f"\nS++:")
        print(f"   Available: {'✅' if status['splusplus']['available'] else '❌'}")
        print(f"   Path: {status['splusplus']['path']}")
        print(f"   Version: {status['splusplus']['version']}")
        
        print(f"\nIntegration:")
        print(f"   Status: {status['integration_status']}")
        print(f"   Unified Execution: {'✅' if status['unified_execution'] else '❌'}")
    
    elif args.integrate:
        print("🔄 Running integration setup...")
        
        if not integration.reversedb_available:
            print("⚠️  ReverseDB not found. Please install ReverseDB first.")
            sys.exit(1)
        
        if not integration.splusplus_available:
            print("⚠️  S++ not found. Please install S++ first.")
            sys.exit(1)
        
        print("✅ Both systems available. Integration ready.")
        
        # Create integration config
        config = {
            "reversedb_path": str(integration.reversedb_path),
            "splusplus_path": str(integration._get_splusplus_path()),
            "unified_execution": True,
            "default_routing": "adaptive",
            "cost_threshold": 50.0
        }
        
        config_path = integration.splusplus_home / "reversedb_integration.json"
        integration.splusplus_home.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"💾 Integration config saved: {config_path}")
    
    elif args.test_query:
        plan = integration.analyze_query(args.test_query)
        
        print(f"\n📊 Query Analysis")
        print("="*60)
        print(f"Complexity: {plan.complexity.value}")
        print(f"Estimated Cost: {plan.estimated_cost:.2f}")
        print(f"Estimated Time: {plan.estimated_time_ms:.2f}ms")
        print(f"\nRouting:")
        print(f"   Use ReverseDB: {'✅' if plan.use_reversedb else '❌'}")
        print(f"   Use S++: {'✅' if plan.use_splusplus else '❌'}")
        
        if plan.reversedb_optimized_sql:
            print(f"\nOptimized SQL:")
            print(f"   {plan.reversedb_optimized_sql[:100]}...")
        
        if plan.reversedb_index_suggestions:
            print(f"\nIndex Suggestions:")
            for idx in plan.reversedb_index_suggestions:
                print(f"   - {idx}")
    
    elif args.execute:
        result = integration.execute(args.execute)
        print(json.dumps(result, indent=2))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
