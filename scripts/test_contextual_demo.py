#!/usr/bin/env python3
"""
Contextual Windowing Demo — Real-world scenario

Demonstrates the complete contextual windowing system with realistic data.
"""

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))

from fact_reference_logger import FactReferenceLogger
from session_context_builder import SessionContextBuilder
from context_window_optimizer import ContextWindowOptimizer


def demo():
    """Run complete contextual windowing demo."""
    
    print("\n" + "="*70)
    print(" CONTEXTUAL WINDOWING - LIVE DEMO")
    print("="*70)
    
    logger = FactReferenceLogger()
    builder = SessionContextBuilder()
    optimizer = ContextWindowOptimizer(token_budget=4000)
    
    try:
        # Scenario: User multi-turn conversation about memory system
        print("\nScenario: User conversation about memory architecture")
        print("-" * 70)
        
        # Turn 1: User asks about decay
        print("\n[Turn 1] User: 'How does the decay algorithm work?'")
        facts_t1 = ['fact_03b4456daae2', 'fact_786b5b92217f', 'fact_6318e2dc587c']
        logger.log_reference(
            facts_t1,
            "decay algorithm question",
            relevance_scores={
                facts_t1[0]: 0.95,
                facts_t1[1]: 0.92,
                facts_t1[2]: 0.78
            }
        )
        print(f"  → Selected {len(facts_t1)} facts for response")
        
        # Turn 2: Follow-up on freshness
        print("\n[Turn 2] User: 'What are the freshness tiers?'")
        facts_t2 = ['fact_0463fa4774ba', 'fact_23caf1f332f9']  # Modified facts
        logger.log_reference(
            facts_t2,
            "freshness tiers question",
            relevance_scores={
                facts_t2[0]: 0.98,
                facts_t2[1]: 0.85
            }
        )
        print(f"  → Selected {len(facts_t2)} facts for response")
        
        # Turn 3: Integration question
        print("\n[Turn 3] User: 'How do these integrate with search?'")
        # This combines concepts from both previous turns
        facts_t3 = facts_t1[:2] + facts_t2[:1]  # Re-using some facts
        logger.log_reference(
            facts_t3,
            "integration with search question",
            relevance_scores={
                facts_t3[0]: 0.88,
                facts_t3[1]: 0.91,
                facts_t3[2]: 0.79
            }
        )
        print(f"  → Selected {len(facts_t3)} facts for response")
        
        # Now demonstrate reconstruction
        print("\n" + "-"*70)
        print("Analysis: Building conversation context")
        print("-"*70)
        
        # Get all unique facts
        all_facts = list(set(facts_t1 + facts_t2 + facts_t3))
        print(f"\nTotal unique facts across conversation: {len(all_facts)}")
        
        # Reconstruct in temporal order
        print("\n[1] Temporal reconstruction:")
        context_temporal = builder.reconstruct_from_facts(all_facts, 'temporal')
        for fact in context_temporal['facts'][:3]:
            print(f"    • {fact['id']}: {fact['content'][:60]}...")
        
        # Reconstruct by relevance
        print("\n[2] Relevance-ordered reconstruction:")
        context_relevance = builder.reconstruct_from_facts(all_facts, 'relevance')
        for fact in context_relevance['facts'][:3]:
            print(f"    • {fact['id']}: {fact['content'][:60]}...")
        
        # Estimate tokens needed
        print("\n[3] Token budget analysis:")
        estimate = builder.estimate_context_size(all_facts)
        print(f"    All facts: {estimate['estimated_tokens']} tokens")
        
        # Now optimize for different budgets
        print("\n" + "-"*70)
        print("Optimization: Different token budgets")
        print("-"*70)
        
        budgets = [1000, 2000, 4000]
        for budget in budgets:
            opt = ContextWindowOptimizer(token_budget=budget)
            window = opt.find_optimal_window(
                "Tell me about the memory system",
                all_facts
            )
            print(f"\n  Budget: {budget} tokens")
            print(f"    Selected: {window['count']} facts")
            print(f"    Usage: {window['token_cost']} ({window['percentage_used']:.1f}%)")
            print(f"    Headroom: {window['headroom']} tokens")
            opt.close()
        
        # Co-occurrence analysis
        print("\n" + "-"*70)
        print("Co-occurrence Analysis")
        print("-"*70)
        
        print(f"\nFacts that appear together:")
        for fact_id in all_facts[:2]:
            cooccs = logger.get_cooccurrences(fact_id, limit=5)
            if cooccs:
                print(f"\n  With {fact_id}:")
                for cocc in cooccs:
                    print(f"    • {cocc['fact_id']}: {cocc['co_occurrence_count']} times")
            else:
                print(f"\n  With {fact_id}: no co-occurrences yet")
        
        # Reference statistics
        print("\n" + "-"*70)
        print("Reference Statistics")
        print("-"*70)
        
        print(f"\nPopularity metrics:")
        top_facts = logger.get_top_facts_by_reference(limit=5)
        for fact in top_facts:
            print(f"  {fact['id']}: {fact['reference_count']} references, "
                  f"avg relevance {fact['avg_relevance']:.2f}")
        
        print("\n" + "="*70)
        print(" DEMO COMPLETE")
        print("="*70 + "\n")
        
        return True
    
    except Exception as e:
        print(f"\n✗ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        logger.close()
        builder.close()
        optimizer.close()


if __name__ == '__main__':
    success = demo()
    sys.exit(0 if success else 1)
