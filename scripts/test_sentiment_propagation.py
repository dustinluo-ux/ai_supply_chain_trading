"""
Test script for Supply Chain Sentiment Propagation Engine.

Tests propagation from AAPL to Foxconn (HON.TW) and other suppliers.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.signals.sentiment_propagator import SentimentPropagator, NewsItem, PropagatedSignal
import json
from datetime import datetime

def test_aapl_to_foxconn():
    """Test propagation from AAPL to Foxconn."""
    
    print("=" * 70)
    print("SUPPLY CHAIN SENTIMENT PROPAGATION TEST")
    print("=" * 70)
    print("\nScenario: Positive news about AAPL")
    print("Expected: Sentiment propagates to suppliers (Foxconn, TSMC, etc.)")
    print()
    
    # Initialize propagator
    propagator = SentimentPropagator(
        db_path='data/supply_chain_relationships.json',
        tier1_weight=0.5,
        tier2_weight=0.2,
        max_degrees=2
    )
    
    # Create test news item for AAPL
    news_item = NewsItem(
        ticker='AAPL',
        sentiment_score=0.8,  # Strong positive sentiment
        supply_chain_score=0.7,  # Positive supply chain health
        confidence=0.9,
        relationship='Buyer',
        reasoning='AAPL announces record iPhone sales, strong demand'
    )
    
    print(f"Primary News Item:")
    print(f"  Ticker: {news_item.ticker}")
    print(f"  Sentiment Score: {news_item.sentiment_score:.2f}")
    print(f"  Supply Chain Score: {news_item.supply_chain_score:.2f}")
    print(f"  Reasoning: {news_item.reasoning}")
    print()
    
    # Propagate sentiment
    print("Propagating sentiment to related companies...")
    print()
    propagated_signals = propagator.propagate(news_item)
    
    # Group by tier and relationship type
    tier1_signals = [s for s in propagated_signals if s.relationship_tier == 1]
    tier2_signals = [s for s in propagated_signals if s.relationship_tier == 2]
    
    suppliers = [s for s in tier1_signals if s.relationship_type == 'supplier']
    customers = [s for s in tier1_signals if s.relationship_type == 'customer']
    competitors = [s for s in tier1_signals if s.relationship_type == 'competitor']
    
    print("=" * 70)
    print("PROPAGATION RESULTS")
    print("=" * 70)
    print(f"\nTotal Propagated Signals: {len(propagated_signals)}")
    print(f"  Tier 1 (Direct): {len(tier1_signals)}")
    print(f"  Tier 2 (Indirect): {len(tier2_signals)}")
    print()
    
    # Show suppliers (Tier 1)
    print("TIER 1 - SUPPLIERS (Direct Relationships):")
    print("-" * 70)
    if suppliers:
        for signal in sorted(suppliers, key=lambda x: abs(x.sentiment_score), reverse=True)[:10]:
            print(f"  {signal.ticker:10s} | "
                  f"Sentiment: {signal.sentiment_score:6.3f} | "
                  f"Weight: {signal.propagation_weight:.3f} | "
                  f"Confidence: {signal.confidence:.2f}")
            
            # Highlight Foxconn
            if 'HON' in signal.ticker or 'Foxconn' in signal.reasoning:
                print(f"    [*] FOXCONN DETECTED: {signal.ticker}")
    else:
        print("  No suppliers found")
    print()
    
    # Show customers (Tier 1)
    print("TIER 1 - CUSTOMERS (Direct Relationships):")
    print("-" * 70)
    if customers:
        for signal in sorted(customers, key=lambda x: abs(x.sentiment_score), reverse=True)[:5]:
            print(f"  {signal.ticker:10s} | "
                  f"Sentiment: {signal.sentiment_score:6.3f} | "
                  f"Weight: {signal.propagation_weight:.3f}")
    else:
        print("  No customers found (AAPL is B2C)")
    print()
    
    # Show competitors (Tier 1)
    print("TIER 1 - COMPETITORS (Direct Relationships):")
    print("-" * 70)
    if competitors:
        for signal in sorted(competitors, key=lambda x: abs(x.sentiment_score), reverse=True)[:5]:
            print(f"  {signal.ticker:10s} | "
                  f"Sentiment: {signal.sentiment_score:6.3f} | "
                  f"Weight: {signal.propagation_weight:.3f}")
    else:
        print("  No competitors found")
    print()
    
    # Show Tier 2 (indirect)
    if tier2_signals:
        print("TIER 2 - INDIRECT RELATIONSHIPS (2 Degrees of Separation):")
        print("-" * 70)
        for signal in sorted(tier2_signals, key=lambda x: abs(x.sentiment_score), reverse=True)[:10]:
            print(f"  {signal.ticker:10s} | "
                  f"Sentiment: {signal.sentiment_score:6.3f} | "
                  f"Weight: {signal.propagation_weight:.3f} | "
                  f"Type: {signal.relationship_type}")
        print()
    
    # Check for Foxconn specifically
    foxconn_signals = [s for s in propagated_signals if 'HON' in s.ticker or 'Foxconn' in s.reasoning]
    if foxconn_signals:
        print("=" * 70)
        print("FOXCONN PROPAGATION DETAILS")
        print("=" * 70)
        for signal in foxconn_signals:
            print(f"\nTicker: {signal.ticker}")
            print(f"Relationship Type: {signal.relationship_type}")
            print(f"Tier: {signal.relationship_tier}")
            print(f"Propagated Sentiment: {signal.sentiment_score:.3f}")
            print(f"Propagation Weight: {signal.propagation_weight:.3f}")
            print(f"Reasoning: {signal.reasoning}")
    else:
        print("\n[!] Foxconn (HON.TW) not found in propagated signals")
        print("   This might be because:")
        print("   1. HON.TW is not in the supply chain database")
        print("   2. The ticker format is different (e.g., 2317.TW)")
        print("   3. The relationship needs to be added to the database")
    
    # Export to JSON for inspection
    output_data = {
        'primary_ticker': news_item.ticker,
        'primary_sentiment': news_item.sentiment_score,
        'primary_supply_chain': news_item.supply_chain_score,
        'propagated_signals': [propagator.to_dict(s) for s in propagated_signals],
        'summary': {
            'total_signals': len(propagated_signals),
            'tier1_count': len(tier1_signals),
            'tier2_count': len(tier2_signals),
            'suppliers_count': len(suppliers),
            'customers_count': len(customers),
            'competitors_count': len(competitors)
        }
    }
    
    output_path = Path('outputs/propagation_test_aapl.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n[OK] Results saved to: {output_path}")
    
    return propagated_signals


def test_negative_news():
    """Test propagation with negative news."""
    
    print("\n" + "=" * 70)
    print("TEST 2: NEGATIVE NEWS PROPAGATION")
    print("=" * 70)
    print("\nScenario: Negative news about AAPL (supply chain disruption)")
    print()
    
    propagator = SentimentPropagator()
    
    news_item = NewsItem(
        ticker='AAPL',
        sentiment_score=-0.6,  # Negative sentiment
        supply_chain_score=-0.5,  # Supply chain disruption
        confidence=0.8,
        relationship='Buyer',
        reasoning='AAPL reports supply chain delays, production cuts'
    )
    
    propagated_signals = propagator.propagate(news_item)
    
    # Show top affected suppliers (most negative)
    suppliers = [s for s in propagated_signals 
                 if s.relationship_type == 'supplier' and s.relationship_tier == 1]
    
    print("Top 5 Most Affected Suppliers (Negative Sentiment):")
    print("-" * 70)
    for signal in sorted(suppliers, key=lambda x: x.sentiment_score)[:5]:
        print(f"  {signal.ticker:10s} | "
              f"Sentiment: {signal.sentiment_score:6.3f} | "
              f"Weight: {signal.propagation_weight:.3f}")
    
    print(f"\n✅ Generated {len(propagated_signals)} propagated signals")


if __name__ == '__main__':
    # Test 1: Positive news (AAPL -> Foxconn)
    signals = test_aapl_to_foxconn()
    
    # Test 2: Negative news
    test_negative_news()
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    print("\nNext Steps:")
    print("1. Review outputs/propagation_test_aapl.json")
    print("2. Integrate propagator into news processing pipeline")
    print("3. Update signal combiner to handle propagated signals")
