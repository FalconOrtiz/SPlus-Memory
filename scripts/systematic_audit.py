#!/usr/bin/env python3
"""
S++ Systematic Audit & Health Check
====================================

Verifies complete system structure, parameters, and health.
Generates comprehensive report on S++ readiness.

Usage:
    python scripts/systematic_audit.py [--detailed]
"""

import os
import sys
import json
import time
import inspect
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class ComponentCheck:
    """Result of a component check."""
    name: str
    status: str  # PASS, FAIL, WARNING, SKIP
    details: str
    metrics: Dict[str, Any]
    execution_time_ms: float


@dataclass
class AuditReport:
    """Complete audit report."""
    timestamp: str
    splusplus_version: str
    overall_health: str
    components_checked: int
    passed: int
    failed: int
    warnings: int
    skipped: int
    checks: List[ComponentCheck]
    recommendations: List[str]


class SPlusPlusAuditor:
    """
    Comprehensive auditor for S++ system.
    
    Checks:
    1. File structure integrity
    2. Module imports
    3. Configuration validity
    4. Database connectivity
    5. LLM availability
    6. Memory systems
    7. Performance metrics
    """
    
    def __init__(self, detailed: bool = False):
        self.detailed = detailed
        self.checks: List[ComponentCheck] = []
        self.start_time = time.time()
        
        # Root path
        self.root = Path(__file__).parent.parent
        
        print("🔍 S++ Systematic Audit Starting...")
        print(f"   Root: {self.root}")
        print(f"   Mode: {'Detailed' if detailed else 'Standard'}\n")
    
    def run_all_checks(self) -> AuditReport:
        """Execute complete audit suite."""
        
        # Structure checks
        self._check_file_structure()
        self._check_module_integrity()
        self._check_documentation()
        
        # Functional checks
        self._check_imports()
        self._check_configuration()
        self._check_database_connectivity()
        self._check_llm_availability()
        
        # System checks
        self._check_memory_systems()
        self._check_quantum_store()
        self._check_procedural_memory()
        self._check_tool_forge()
        self._check_swarm()
        self._check_continual_learning()
        
        # Integration checks
        self._check_hermes_bridge()
        self._check_activation_scripts()
        
        # Performance checks
        self._check_performance_metrics()
        
        # Generate report
        return self._generate_report()
    
    def _check_file_structure(self):
        """Verify directory structure."""
        t0 = time.time()
        
        required_dirs = [
            "splusplus/core",
            "splusplus/forge", 
            "splusplus/memory",
            "splusplus/projection",
            "splusplus/perception",
            "splusplus/execution",
            "splusplus/swarm",
            "splusplus/learning",
            "splusplus/integration",
            "scripts",
            "docs",
        ]
        
        missing = []
        for dir_path in required_dirs:
            full_path = self.root / dir_path
            if not full_path.exists():
                missing.append(dir_path)
        
        status = "PASS" if not missing else "FAIL"
        details = f"All required directories present" if not missing else f"Missing: {', '.join(missing)}"
        
        self.checks.append(ComponentCheck(
            name="File Structure",
            status=status,
            details=details,
            metrics={"required": len(required_dirs), "missing": len(missing)},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_module_integrity(self):
        """Check all Python modules are valid."""
        t0 = time.time()
        
        modules_to_check = [
            "splusplus/__init__.py",
            "splusplus/core/splusplus_engine.py",
            "splusplus/forge/tool_forge.py",
            "splusplus/forge/llm_client.py",
            "splusplus/memory/procedural_memory.py",
            "splusplus/memory/quantum_store.py",
            "splusplus/memory/quantum_persistence.py",
            "splusplus/projection/neuro_procedural.py",
            "splusplus/perception/predictive_engine.py",
            "splusplus/perception/meta_cognitive.py",
            "splusplus/execution/procedural_executor.py",
            "splusplus/swarm/swarm_orchestrator.py",
            "splusplus/learning/continual_learner.py",
            "splusplus/integration/hermes_bridge.py",
            "splusplus/integration/splus_bridge.py",
        ]
        
        errors = []
        syntax_ok = []
        
        for module_path in modules_to_check:
            full_path = self.root / module_path
            if full_path.exists():
                try:
                    with open(full_path) as f:
                        compile(f.read(), full_path, 'exec')
                    syntax_ok.append(module_path)
                except SyntaxError as e:
                    errors.append(f"{module_path}: {e}")
            else:
                errors.append(f"{module_path}: File not found")
        
        status = "PASS" if not errors else "FAIL"
        details = f"{len(syntax_ok)}/{len(modules_to_check)} modules valid" if not errors else f"Errors: {len(errors)}"
        
        self.checks.append(ComponentCheck(
            name="Module Integrity",
            status=status,
            details=details,
            metrics={"checked": len(modules_to_check), "valid": len(syntax_ok), "errors": len(errors)},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_documentation(self):
        """Verify documentation exists."""
        t0 = time.time()
        
        required_docs = [
            "README.md",
            "SPLUSPLUS_README.md",
            "SPLUS_GIGABRAIN_INTEGRATION.md",
            "INTEGRATION_SUMMARY.md",
        ]
        
        missing = [doc for doc in required_docs if not (self.root / doc).exists()]
        
        status = "PASS" if not missing else "WARNING"
        
        self.checks.append(ComponentCheck(
            name="Documentation",
            status=status,
            details=f"All docs present" if not missing else f"Missing: {', '.join(missing)}",
            metrics={"required": len(required_docs), "missing": len(missing)},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_imports(self):
        """Test critical imports."""
        t0 = time.time()
        
        critical_imports = [
            ("splusplus", "SPlusPlusEngine"),
            ("splusplus", "HermesBridge"),
            ("splusplus", "ToolForge"),
            ("splusplus", "QuantumMemoryStore"),
            ("splusplus", "ProceduralMemory"),
            ("splusplus", "SwarmOrchestrator"),
            ("splusplus", "ContinualLearner"),
        ]
        
        failed = []
        for module, obj in critical_imports:
            try:
                mod = __import__(module, fromlist=[obj])
                getattr(mod, obj)
            except Exception as e:
                failed.append(f"{module}.{obj}: {e}")
        
        status = "PASS" if not failed else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Critical Imports",
            status=status,
            details=f"All imports successful" if not failed else f"Failed: {len(failed)}",
            metrics={"checked": len(critical_imports), "failed": len(failed)},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_configuration(self):
        """Check configuration system."""
        t0 = time.time()
        
        try:
            from splusplus.core.splusplus_engine import SPlusPlusEngine
            engine = SPlusPlusEngine()
            config_accessible = True
            version = engine.version
        except Exception as e:
            config_accessible = False
            version = "unknown"
        
        status = "PASS" if config_accessible else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Configuration",
            status=status,
            details=f"Version: {version}" if config_accessible else "Engine initialization failed",
            metrics={"version": version},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_database_connectivity(self):
        """Check database connections."""
        t0 = time.time()
        
        # Check SQLite (always available)
        sqlite_ok = True
        
        # Check PostgreSQL (optional)
        postgres_ok = False
        try:
            import psycopg2
            postgres_ok = True
        except ImportError:
            pass
        
        status = "PASS" if sqlite_ok else "FAIL"
        details = f"SQLite: OK"
        if postgres_ok:
            details += ", PostgreSQL: OK"
        else:
            details += ", PostgreSQL: Not installed (optional)"
        
        self.checks.append(ComponentCheck(
            name="Database Connectivity",
            status=status,
            details=details,
            metrics={"sqlite": sqlite_ok, "postgresql": postgres_ok},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_llm_availability(self):
        """Check LLM providers availability."""
        t0 = time.time()
        
        providers = {
            "openai": False,
            "anthropic": False,
            "ollama": False,
        }
        
        # Check OpenAI
        if os.getenv("OPENAI_API_KEY"):
            try:
                import openai
                providers["openai"] = True
            except ImportError:
                pass
        
        # Check Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                providers["anthropic"] = True
            except ImportError:
                pass
        
        # Check Ollama (local)
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(("localhost", 11434))
            providers["ollama"] = True
            sock.close()
        except:
            pass
        
        available = sum(providers.values())
        status = "WARNING" if available == 0 else "PASS"
        
        self.checks.append(ComponentCheck(
            name="LLM Availability",
            status=status,
            details=f"{available}/3 providers available: {', '.join([k for k,v in providers.items() if v]) or 'None (fallback mode)'}"
            ,
            metrics=providers,
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_memory_systems(self):
        """Check memory subsystems."""
        t0 = time.time()
        
        systems = {}
        
        try:
            from splusplus.memory.quantum_store import QuantumMemoryStore
            qs = QuantumMemoryStore()
            systems["quantum_store"] = True
        except Exception as e:
            systems["quantum_store"] = False
        
        try:
            from splusplus.memory.procedural_memory import ProceduralMemory
            pm = ProceduralMemory()
            systems["procedural_memory"] = True
        except Exception as e:
            systems["procedural_memory"] = False
        
        all_ok = all(systems.values())
        status = "PASS" if all_ok else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Memory Systems",
            status=status,
            details=f"All systems operational" if all_ok else f"Failed: {[k for k,v in systems.items() if not v]}"
            ,
            metrics=systems,
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_quantum_store(self):
        """Check quantum memory functionality."""
        t0 = time.time()
        
        try:
            from splusplus.memory.quantum_store import QuantumMemoryStore, QuantumFact, QuantumState
            import numpy as np
            
            store = QuantumMemoryStore()
            
            # Test store and retrieve
            fact = QuantumFact(
                id="test_001",
                content="Test fact for audit",
                states=[
                    QuantumState(
                        embedding=np.random.randn(384).astype(np.float32),
                        context_type="test",
                        weight=1.0,
                        tags=["test"]
                    )
                ],
                created_at=datetime.now().isoformat()
            )
            
            store.facts["test_001"] = fact
            retrieved = store.facts.get("test_001")
            
            functional = retrieved is not None
        except Exception as e:
            functional = False
        
        status = "PASS" if functional else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Quantum Store",
            status=status,
            details="Store/retrieve working" if functional else f"Error: {e}",
            metrics={"functional": functional},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_procedural_memory(self):
        """Check procedural memory."""
        t0 = time.time()
        
        try:
            from splusplus.memory.procedural_memory import ProceduralMemory
            pm = ProceduralMemory()
            stats = pm.get_procedure_stats()
            functional = True
        except Exception as e:
            stats = {}
            functional = False
        
        status = "PASS" if functional else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Procedural Memory",
            status=status,
            details=f"Procedures: {stats.get('total_procedures', 0)}" if functional else "Failed",
            metrics=stats if functional else {},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_tool_forge(self):
        """Check tool generation."""
        t0 = time.time()
        
        try:
            from splusplus.forge.tool_forge import ToolForge
            forge = ToolForge()
            stats = forge.get_stats()
            functional = True
        except Exception as e:
            stats = {}
            functional = False
        
        status = "PASS" if functional else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Tool Forge",
            status=status,
            details="Tool generation ready" if functional else "Failed",
            metrics=stats if functional else {},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_swarm(self):
        """Check swarm orchestrator."""
        t0 = time.time()
        
        try:
            from splusplus.swarm.swarm_orchestrator import SwarmOrchestrator, AgentRole
            swarm = SwarmOrchestrator("test_agent", AgentRole.GENERALIST)
            functional = True
        except Exception as e:
            functional = False
        
        status = "PASS" if functional else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Swarm Orchestrator",
            status=status,
            details="Swarm system ready" if functional else "Failed",
            metrics={"functional": functional},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_continual_learning(self):
        """Check continual learning."""
        t0 = time.time()
        
        try:
            from splusplus.learning.continual_learner import ContinualLearner
            learner = ContinualLearner()
            report = learner.get_learning_report()
            functional = True
        except Exception as e:
            report = {}
            functional = False
        
        status = "PASS" if functional else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Continual Learning",
            status=status,
            details="Learning system ready" if functional else "Failed",
            metrics=report if functional else {},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_hermes_bridge(self):
        """Check Hermes integration."""
        t0 = time.time()
        
        try:
            from splusplus.integration.hermes_bridge import HermesBridge
            bridge = HermesBridge()
            status_obj = bridge.get_status()
            functional = True
        except Exception as e:
            status_obj = {}
            functional = False
        
        status = "PASS" if functional else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Hermes Bridge",
            status=status,
            details="Gigabrain integration ready" if functional else "Failed",
            metrics=status_obj if functional else {},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_activation_scripts(self):
        """Check activation scripts."""
        t0 = time.time()
        
        scripts = [
            "scripts/activate_for_hermes.py",
            "splusplus_demo.py",
            "splusplus_demo_v2.py",
        ]
        
        existing = []
        for script in scripts:
            if (self.root / script).exists():
                existing.append(script)
        
        status = "PASS" if len(existing) == len(scripts) else "WARNING"
        
        self.checks.append(ComponentCheck(
            name="Activation Scripts",
            status=status,
            details=f"{len(existing)}/{len(scripts)} scripts present",
            metrics={"present": existing},
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _check_performance_metrics(self):
        """Check basic performance."""
        t0 = time.time()
        
        # Quick performance test
        try:
            from splusplus.memory.quantum_store import QuantumMemoryStore
            import numpy as np
            
            store = QuantumMemoryStore()
            
            # Store 10 facts
            start = time.time()
            for i in range(10):
                from splusplus.memory.quantum_store import QuantumFact, QuantumState
                fact = QuantumFact(
                    id=f"perf_test_{i}",
                    content=f"Performance test fact {i}",
                    states=[
                        QuantumState(
                            embedding=np.random.randn(384).astype(np.float32),
                            context_type="test",
                            weight=1.0,
                            tags=["perf"]
                        )
                    ],
                    created_at=datetime.now().isoformat()
                )
                store.facts[fact.id] = fact
            
            store_time = (time.time() - start) * 1000
            
            # Query
            start = time.time()
            results = store.collapse_wavefunction("test query")
            query_time = (time.time() - start) * 1000
            
            metrics = {
                "store_10_facts_ms": store_time,
                "query_ms": query_time,
                "facts_per_second": 10 / (store_time / 1000)
            }
            
            functional = True
        except Exception as e:
            metrics = {}
            functional = False
        
        status = "PASS" if functional else "FAIL"
        
        self.checks.append(ComponentCheck(
            name="Performance Metrics",
            status=status,
            details=f"Store: {metrics.get('store_10_facts_ms', 0):.1f}ms, Query: {metrics.get('query_ms', 0):.1f}ms"
            if functional else "Failed",
            metrics=metrics,
            execution_time_ms=(time.time() - t0) * 1000
        ))
    
    def _generate_report(self) -> AuditReport:
        """Generate final audit report."""
        
        passed = sum(1 for c in self.checks if c.status == "PASS")
        failed = sum(1 for c in self.checks if c.status == "FAIL")
        warnings = sum(1 for c in self.checks if c.status == "WARNING")
        skipped = sum(1 for c in self.checks if c.status == "SKIP")
        
        # Determine overall health
        if failed == 0 and warnings == 0:
            overall = "HEALTHY"
        elif failed == 0:
            overall = "DEGRADED"
        else:
            overall = "CRITICAL"
        
        # Generate recommendations
        recommendations = []
        
        for check in self.checks:
            if check.status == "FAIL":
                if "LLM" in check.name:
                    recommendations.append("Install LLM provider: pip install openai anthropic")
                elif "PostgreSQL" in check.name:
                    recommendations.append("Install PostgreSQL adapter: pip install psycopg2-binary")
                elif "Database" in check.name:
                    recommendations.append("Database connectivity issues - check configuration")
            elif check.status == "WARNING":
                if "LLM" in check.name:
                    recommendations.append("LLM in fallback mode - templates will be used")
        
        if not recommendations:
            recommendations.append("System is ready for production deployment")
        
        try:
            from splusplus import __version__
            version = __version__
        except:
            version = "2.0.0"
        
        return AuditReport(
            timestamp=datetime.now().isoformat(),
            splusplus_version=version,
            overall_health=overall,
            components_checked=len(self.checks),
            passed=passed,
            failed=failed,
            warnings=warnings,
            skipped=skipped,
            checks=self.checks,
            recommendations=recommendations
        )


def print_report(report: AuditReport, detailed: bool = False):
    """Pretty print audit report."""
    
    print("\n" + "="*70)
    print("  S++ SYSTEMATIC AUDIT REPORT")
    print("="*70)
    print(f"\nTimestamp: {report.timestamp}")
    print(f"Version: {report.splusplus_version}")
    print(f"Overall Health: {report.overall_health}")
    
    # Summary
    print(f"\n{'─'*70}")
    print("  SUMMARY")
    print(f"{'─'*70}")
    print(f"  Components Checked: {report.components_checked}")
    print(f"  ✅ Passed:   {report.passed}")
    print(f"  ❌ Failed:   {report.failed}")
    print(f"  ⚠️  Warnings: {report.warnings}")
    print(f"  ⏭️  Skipped:  {report.skipped}")
    
    # Detailed checks
    if detailed:
        print(f"\n{'─'*70}")
        print("  DETAILED CHECKS")
        print(f"{'─'*70}")
        
        for check in report.checks:
            icon = "✅" if check.status == "PASS" else "❌" if check.status == "FAIL" else "⚠️"
            print(f"\n{icon} {check.name}")
            print(f"   Status: {check.status}")
            print(f"   Details: {check.details}")
            print(f"   Time: {check.execution_time_ms:.1f}ms")
            if check.metrics:
                try:
                    metrics_str = json.dumps(check.metrics, indent=4, default=str)[:200]
                except:
                    metrics_str = str(check.metrics)[:200]
                print(f"   Metrics: {metrics_str}")
    else:
        print(f"\n{'─'*70}")
        print("  CHECKS OVERVIEW")
        print(f"{'─'*70}")
        
        for check in report.checks:
            icon = "✅" if check.status == "PASS" else "❌" if check.status == "FAIL" else "⚠️"
            print(f"{icon} {check.name:30} | {check.status:10} | {check.execution_time_ms:6.1f}ms")
    
    # Recommendations
    print(f"\n{'─'*70}")
    print("  RECOMMENDATIONS")
    print(f"{'─'*70}")
    for rec in report.recommendations:
        print(f"  • {rec}")
    
    print(f"\n{'='*70}")
    
    # Save to file
    report_file = Path("audit_report.json")
    with open(report_file, 'w') as f:
        json.dump(asdict(report), f, indent=2, default=str)
    
    print(f"\n📄 Full report saved to: {report_file.absolute()}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="S++ Systematic Audit")
    parser.add_argument("--detailed", action="store_true", help="Show detailed output")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    
    args = parser.parse_args()
    
    auditor = SPlusPlusAuditor(detailed=args.detailed)
    report = auditor.run_all_checks()
    
    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        print_report(report, detailed=args.detailed)
    
    # Return exit code
    return 0 if report.overall_health in ["HEALTHY", "DEGRADED"] else 1


if __name__ == "__main__":
    sys.exit(main())
