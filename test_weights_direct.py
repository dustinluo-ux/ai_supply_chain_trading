"""
Direct test to verify weights are actually different and producing different scores
"""
import sys
sys.path.insert(0, '.')

from src.signals.signal_combiner import SignalCombiner
import numpy as np

print("=" * 60)
print("TESTING WEIGHT APPLICATION")
print("=" * 60)

# Same technical signals for all tests
tech_signals = {
    'momentum_score': 0.1,
    'volume_score': 1.5,
    'rsi_score': 0.7
}

# News signals (all zero - typical case)
news_signals = {
    'supply_chain_score': 0.0,
    'sentiment_score': 0.0,
    'confidence': 0.0
}

combiner = SignalCombiner()

# Test 1: Technical-only weights
print("\nTEST 1: Technical-Only")
print("-" * 60)
# Simulate what happens in technical-only mode
momentum = tech_signals['momentum_score']
rsi = tech_signals['rsi_score']
momentum_weight = 0.5
rsi_weight = 0.2
volume_weight = 0.3
total_tech = momentum_weight + rsi_weight + volume_weight
momentum_weight_norm = momentum_weight / total_tech  # 0.5
rsi_weight_norm = rsi_weight / total_tech  # 0.2
volume_weight_norm = volume_weight / total_tech  # 0.3
combined_momentum = (momentum * momentum_weight_norm + rsi * rsi_weight_norm) / (momentum_weight_norm + rsi_weight_norm)
tech_1 = {
    'momentum_score': combined_momentum,
    'volume_score': tech_signals['volume_score'],
    'rsi_score': 0.5
}
weights_1 = {
    'supply_chain': 0.0,
    'sentiment': 0.0,
    'momentum': momentum_weight_norm + rsi_weight_norm,  # 0.7
    'volume': volume_weight_norm  # 0.3
}
score1 = combiner.combine_signals_direct(tech_1, news_signals, weights_1)
print(f"Tech signals: {tech_1}")
print(f"Weights: {weights_1}")
print(f"Score: {score1:.6f}")
print()

# Test 2: News-only weights
print("TEST 2: News-Only")
print("-" * 60)
weights_2 = {
    'supply_chain': 0.5,
    'sentiment': 0.5,
    'momentum': 0.0,
    'volume': 0.0
}
score2 = combiner.combine_signals_direct(tech_signals, news_signals, weights_2)
print(f"Tech signals: {tech_signals}")
print(f"Weights: {weights_2}")
print(f"Score: {score2:.6f}")
print()

# Test 3: Combined weights
print("TEST 3: Combined")
print("-" * 60)
weights_3 = {
    'supply_chain': 0.4,
    'sentiment': 0.3,
    'momentum': 0.2,
    'volume': 0.1
}
score3 = combiner.combine_signals_direct(tech_signals, news_signals, weights_3)
print(f"Tech signals: {tech_signals}")
print(f"Weights: {weights_3}")
print(f"Score: {score3:.6f}")
print()

print("=" * 60)
print("RESULTS")
print("=" * 60)
print(f"Technical-only: {score1:.6f}")
print(f"News-only:      {score2:.6f}")
print(f"Combined:       {score3:.6f}")
print()

if abs(score1 - score2) < 0.0001:
    print("ERROR: Scores 1 and 2 are identical!")
elif abs(score1 - score3) < 0.0001:
    print("ERROR: Scores 1 and 3 are identical!")
elif abs(score2 - score3) < 0.0001:
    print("ERROR: Scores 2 and 3 are identical!")
else:
    print("SUCCESS: All scores are different!")
