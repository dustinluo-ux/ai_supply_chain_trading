"""
Direct test of signal combination logic to verify weights are working
"""
import sys
sys.path.insert(0, '.')

from src.signals.signal_combiner import SignalCombiner

# Test with sample signals
tech_signals = {
    'momentum_score': 0.1,  # Positive momentum
    'volume_score': 1.5,     # High volume
    'rsi_score': 0.7         # High RSI
}

news_signals = {
    'supply_chain_score': 0.8,  # High supply chain relevance
    'sentiment_score': 0.5,      # Positive sentiment
    'confidence': 0.9
}

combiner = SignalCombiner()

# Test 1: Technical-only weights
print("=" * 60)
print("TEST 1: Technical-Only Weights")
print("=" * 60)
weights_tech = {'supply_chain': 0.0, 'sentiment': 0.0, 'momentum': 0.5, 'volume': 0.3, 'rsi': 0.2}
# RSI needs to be combined with momentum first
momentum_combined = (tech_signals['momentum_score'] * 0.5 + tech_signals['rsi_score'] * 0.2) / 0.7
tech_for_combiner = {
    'momentum_score': momentum_combined,
    'volume_score': tech_signals['volume_score'],
    'rsi_score': 0.5
}
combiner_weights = {'supply_chain': 0.0, 'sentiment': 0.0, 'momentum': 0.7, 'volume': 0.3}
score1 = combiner.combine_signals_direct(tech_for_combiner, news_signals, combiner_weights)
print(f"Weights: {combiner_weights}")
print(f"Score: {score1:.6f}")
print()

# Test 2: News-only weights
print("=" * 60)
print("TEST 2: News-Only Weights")
print("=" * 60)
weights_news = {'supply_chain': 0.5, 'sentiment': 0.5, 'momentum': 0.0, 'volume': 0.0}
score2 = combiner.combine_signals_direct(tech_signals, news_signals, weights_news)
print(f"Weights: {weights_news}")
print(f"Score: {score2:.6f}")
print()

# Test 3: Combined weights
print("=" * 60)
print("TEST 3: Combined Weights")
print("=" * 60)
weights_combined = {'supply_chain': 0.4, 'sentiment': 0.3, 'momentum': 0.2, 'volume': 0.1}
score3 = combiner.combine_signals_direct(tech_signals, news_signals, weights_combined)
print(f"Weights: {weights_combined}")
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
elif abs(score1 - score3) < 0.0001:
    print("ERROR: Technical-only and Combined scores are identical!")
elif abs(score2 - score3) < 0.0001:
    print("ERROR: News-only and Combined scores are identical!")
else:
    print("SUCCESS: All three scores are different!")
