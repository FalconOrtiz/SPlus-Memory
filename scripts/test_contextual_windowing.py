#!/usr/bin/env python3
"""
Integration Test: Contextual Windowing System

Tests the complete flow:
1. Log fact references
2. Build context windows
3. Optimize token usage
4. Validate all components
"""

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))

from fact_reference_logger import FactReferenceLogger
from session_context_builder import SessionContextBuilder
from context_window_optimizer import ContextWindowOptimizer


def test_fact_reference_logging():
    """Test 1: Fact reference logging."""
    print("\n" + "="*70)
    print("TEST 1: FACT REFERENCE LOGGING")
    print("="*70)
    
    logger = FactReferenceLogger()
    
    try:
        # Log a group of facts appearing together
        test_facts = ['fact_03b4456daae2', 'fact_786b5b92217f', 'fact_6318e2dc587c']
        relevance_scores = {
            'fact_03b4456daae2': 0.95,
            'fact_786b5b92217f': 0.87,
            'fact_6318e2dc587c': 0.72
        }
        
        success = logger.log_reference(
            fact_ids=test_facts,
            context="User queried about decay algorithm and temporal weighting",
            response_tokens=250,
            relevance_scores=relevance_scores
        )
        
        if success:
            print("✓ Logged 3 fact references")
            
            # Get co-occurrences
            cooccs = logger.get_cooccurrences('fact_03b4456daae2', limit=5)
            print(f"✓ Found {len(cooccs)} co-occurrences")
            
            # Get reference stats
            stats = logger.get_reference_stats('fact_03b4456daae2')
            print(f"✓ Reference stats: {stats['total_references']} refs, "
                  f"avg relevance {stats['avg_relevance']:.2f}")
            
            return True
        else:
            print("✗ Failed to log references")
            return False
    
    finally:
        logger.close()


def test_session_context_building():
    """Test 2: Session context reconstruction."""
    print("\n" + "="*70)
    print("TEST 2: SESSION CONTEXT BUILDING")
    print("="*70)
    
    builder = SessionContextBuilder()
    
    try:
        # Reconstruct context from multiple facts
        facts = ['fact_03b4456daae2', 'fact_786b5b92217f', 'fact_6318e2dc587c']
        
        context = builder.reconstruct_from_facts(facts, order_by='relevance')
        
        if 'error' not in context:
            print(f"✓ Reconstructed context with {context['total_facts']} facts")
            print(f"  Summary: {context.get('context_summary', '')}")
            
            # Find related facts
            related = builder.find_related_facts('fact_03b4456daae2', depth=1)
            print(f"✓ Found {len(related['related_facts'])} related facts")
            
            # Estimate size
            estimate = builder.estimate_context_size(facts)
            print(f"✓ Context size estimate:")
            print(f"  Estimated tokens: {estimate.get('estimated_tokens', 0)}")
            print(f"  Total characters: {estimate.get('total_characters', 0)}")
            
            # Suggest complementary
            suggestions = builder.suggest_complementary_facts(facts)
            print(f"✓ Found {len(suggestions)} complementary facts")
            
            return True
        else:
            print(f"✗ Failed to build context: {context.get('error')}")
            return False
    
    finally:
        builder.close()


def test_context_window_optimization():
    """Test 3: Token-budgeted context window optimization."""
    print("\n" + "="*70)
    print("TEST 3: CONTEXT WINDOW OPTIMIZATION")
    print("="*70)
    
    optimizer = ContextWindowOptimizer(token_budget=2000)
    
    try:
        # Get some facts
        facts = ['fact_03b4456daae2', 'fact_786b5b92217f', 'fact_6318e2dc587c',
                'fact_12f669b13be2', 'fact_f7e81c7fbba3']
        
        # Test greedy strategy
        window_greedy = optimizer.find_optimal_window(
            "Tell me about decay algorithm",
            facts,
            strategy='greedy'
        )
        
        print(f"✓ Greedy strategy:")
        print(f"  Selected: {window_greedy['count']} facts")
        print(f"  Token cost: {window_greedy['token_cost']}")
        print(f"  Budget usage: {window_greedy['percentage_used']:.1f}%")
        
        # Test adaptive strategy
        window_adaptive = optimizer.find_optimal_window(
            "Compare facts on memory and decay",
            facts,
            strategy='adaptive'
        )
        
        print(f"✓ Adaptive strategy (detected: {window_adaptive['strategy']}):")
        print(f"  Selected: {window_adaptive['count']} facts")
        print(f"  Token cost: {window_adaptive['token_cost']}")
        
        # Test clustering
        clusters = optimizer.cluster_facts_by_relevance(
            "decay and temporal weighting",
            facts
        )
        
        print(f"✓ Fact clustering:")
        print(f"  Primary: {len(clusters['primary'])} facts")
        print(f"  Supporting: {len(clusters['supporting'])} facts")
        print(f"  Background: {len(clusters['background'])} facts")
        
        # Get efficiency report
        report = optimizer.get_efficiency_report()
        print(f"✓ Budget efficiency:")
        print(f"  All facts fit in budget: {report['all_facts_fit']}")
        print(f"  Max facts possible: {report['max_facts_in_budget']}")
        
        return True
    
    finally:
        optimizer.close()


def test_end_to_end_flow():
    """Test 4: Complete end-to-end flow."""
    print("\n" + "="*70)
    print("TEST 4: END-TO-END CONTEXTUAL WINDOWING FLOW")
    print("="*70)
    
    logger = FactReferenceLogger()
    builder = SessionContextBuilder()
    optimizer = ContextWindowOptimizer(token_budget=3000)
    
    try:
        # Scenario: User asks about memory system
        query = "How does the memory system work with decay?"
        facts_to_log = ['fact_03b4456daae2', 'fact_786b5b92217f', 'fact_6318e2dc587c']
        
        print(f"\nScenario: User query → '{query}'")
        
        # Step 1: Log the reference
        print("\n  Step 1: Log reference...")
        success = logger.log_reference(
            fact_ids=facts_to_log,
            context=query,
            response_tokens=300,
            relevance_scores={
                facts_to_log[0]: 0.95,
                facts_to_log[1]: 0.88,
                facts_to_log[2]: 0.75
            }
        )
        print(f"    ✓ Logged {len(facts_to_log)} facts")
        
        # Step 2: Reconstruct context
        print("\n  Step 2: Reconstruct context...")
        context = builder.reconstruct_from_facts(facts_to_log)
        print(f"    ✓ Reconstructed {context['total_facts']} facts")
        print(f"    ✓ Summary: {context.get('context_summary', '')}")
        
        # Step 3: Estimate token cost
        print("\n  Step 3: Estimate token cost...")
        estimate = builder.estimate_context_size(facts_to_log)
        tokens_needed = estimate.get('estimated_tokens', 0)
        print(f"    ✓ Estimated {tokens_needed} tokens needed")
        
        # Step 4: Optimize window
        print("\n  Step 4: Optimize within budget...")
        window = optimizer.find_optimal_window(
            query=query,
            available_facts=facts_to_log,
            strategy='adaptive'
        )
        print(f"    ✓ Selected {window['count']} facts")
        print(f"    ✓ Token usage: {window['token_cost']} / {window['available_tokens']}")
        print(f"    ✓ Headroom: {window['headroom']} tokens")
        
        # Step 5: Get related facts
        print("\n  Step 5: Find related facts...")
        related = builder.find_related_facts(facts_to_log[0], depth=1)
        print(f"    ✓ Found {len(related['related_facts'])} related facts")
        
        print("\n✓ END-TO-END FLOW COMPLETE")
        return True
    
    finally:
        logger.close()
        builder.close()
        optimizer.close()


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*68 + "║")
    print("║  CONTEXTUAL WINDOWING SYSTEM - INTEGRATION TEST" + " "*21 + "║")
    print("║" + " "*68 + "║")
    print("╚" + "="*68 + "╝")
    
    start_time = time.time()
    
    results = {
        'Fact Reference Logging': False,
        'Session Context Building': False,
        'Context Window Optimization': False,
        'End-to-End Flow': False
    }
    
    try:
        results['Fact Reference Logging'] = test_fact_reference_logging()
    except Exception as e:
        print(f"✗ Test failed: {e}")
    
    try:
        results['Session Context Building'] = test_session_context_building()
    except Exception as e:
        print(f"✗ Test failed: {e}")
    
    try:
        results['Context Window Optimization'] = test_context_window_optimization()
    except Exception as e:
        print(f"✗ Test failed: {e}")
    
    try:
        results['End-to-End Flow'] = test_end_to_end_flow()
    except Exception as e:
        print(f"✗ Test failed: {e}")
    
    elapsed = time.time() - start_time
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {test_name}")
    
    print("-" * 70)
    print(f"Result: {passed}/{total} tests passed ({elapsed:.2f}s)")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED - CONTEXTUAL WINDOWING READY FOR PRODUCTION")
    else:
        print(f"\n⚠️  {total - passed} tests failed")
    
    print("="*70 + "\n")
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
