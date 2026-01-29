"""
Debug script to identify why all three signal approaches produce identical results
Tests the signal combination logic directly
"""
import sys
sys.path.insert(0, '.')

from src.signals.signal_combiner import SignalCombiner
import numpy as np

print("=" * 60)
print("DEBUGGING SIGNAL COMBINATION ISSUE")
print("=" * 60)

# Create sample signals that should produce different results
tech_signals = {
    'momentum_score': 0.15,  # Positive momentum
    'volume_score': 2.0,     # High volume spike
    'rsi_score': 0.75        # High RSI
}

news_signals = {
    'supply_chain_score': 0.0,  # No news data (typical case)
    'sentiment_score': 0.0,
    'confidence': 0.0
}

combiner = SignalCombiner()

print("\nTest Case: News signals are all 0.0 (no news data)")
print(f"Tech signals: {tech_signals}")
print(f"News signals: {news_signals}")
print()

# Test 1: Technical-only
print("=" * 60)
print("TEST 1: Technical-Only")
print("=" * 60)
# Combine momentum and RSI first (as done in simple_backtest_v2.py)
momentum = tech_signals['momentum_score']
rsi = tech_signals['rsi_score']
momentum_weight = 0.5
rsi_weight = 0.2
volume_weight = 0.3
total_tech = momentum_weight + rsi_weight + volume_weight
momentum_weight_norm = momentum_weight / total_tech
rsi_weight_norm = rsi_weight / total_tech
volume_weight_norm = volume_weight / total_tech
combined_momentum = (momentum * momentum_weight_norm + rsi * rsi_weight_norm) / (momentum_weight_norm + rsi_weight_norm)
tech_for_combiner_1 = {
    'momentum_score': combined_momentum,
    'volume_score': tech_signals['volume_score'],
    'rsi_score': 0.5
}
combiner_weights_1 = {
    'supply_chain': 0.0,
    'sentiment': 0.0,
    'momentum': momentum_weight_norm + rsi_weight_norm,
    'volume': volume_weight_norm
}
score1 = combiner.combine_signals_direct(tech_for_combiner_1, news_signals, combiner_weights_1)
print(f"Tech for combiner: {tech_for_combiner_1}")
print(f"Weights: {combiner_weights_1}")
print(f"Score: {score1:.6f}")
print()

# Test 2: News-only
print("=" * 60)
print("TEST 2: News-Only")
print("=" * 60)
combiner_weights_2 = {
    'supply_chain': 0.5,
    'sentiment': 0.5,
    'momentum': 0.0,
    'volume': 0.0
}
score2 = combiner.combine_signals_direct(tech_signals, news_signals, combiner_weights_2)
print(f"Tech for combiner: {tech_signals}")
print(f"Weights: {combiner_weights_2}")
print(f"Score: {score2:.6f}")
print()

# Test 3: Combined
print("=" * 60)
print("TEST 3: Combined")
print("=" * 60)
combiner_weights_3 = {
    'supply_chain': 0.4,
    'sentiment': 0.3,
    'momentum': 0.2,
    'volume': 0.1
}
score3 = combiner.combine_signals_direct(tech_signals, news_signals, combiner_weights_3)
print(f"Tech for combiner: {tech_signals}")
print(f"Weights: {combiner_weights_3}")
print(f"Score: {score3:.6f}")
print()

# Results
print("=" * 60)
print("RESULTS")
print("=" * 60)
print(f"Technical-only: {score1:.6f}")
print(f"News-only:      {score2:.6f}")
print(f"Combined:       {score3:.6f}")
print()

if abs(score1 - score2) < 0.0001:
    print("ERROR: Technical-only and News-only scores are identical!")
    print("  This is expected if news signals are 0.0 (no news data)")
    print("  News-only should return 0.0 for all stocks in this case")
elif abs(score1 - score3) < 0.0001:
    print("ERROR: Technical-only and Combined scores are identical!")
    print("  This indicates a bug - they should be different!")
elif abs(score2 - score3) < 0.0001:
    print("ERROR: News-only and Combined scores are identical!")
    print("  This is expected if news signals are 0.0")
else:
    print("SUCCESS: All three scores are different!")
    print(f"  Difference 1-2: {abs(score1 - score2):.6f}")
    print(f"  Difference 1-3: {abs(score1 - score3):.6f}")
    print(f"  Difference 2-3: {abs(score2 - score3):.6f}")

print("=" * 60)
