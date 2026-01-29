# Supply Chain Sentiment Propagation Engine

**Date:** 2026-01-25  
**Status:** ✅ Implemented and Tested

---

## Overview

The Supply Chain Sentiment Propagation Engine automatically propagates news sentiment from a primary ticker to related companies (suppliers, customers, competitors) based on the curated supply chain database.

**Key Feature:** When news about AAPL is analyzed, the system automatically generates sentiment scores for its suppliers (Foxconn, TSMC, etc.) and customers, creating a comprehensive supply chain-driven news prediction model.

---

## Architecture

### Directed Graph Approach

```
Primary Ticker (Tier 0)
    ↓
Tier 1: Direct Relationships
    ├── Suppliers (e.g., TSMC, Foxconn)
    ├── Customers (e.g., if B2B)
    └── Competitors (e.g., GOOGL, MSFT)
    ↓
Tier 2: Indirect Relationships (2 degrees)
    └── Suppliers of suppliers, etc.
```

### Propagation Formula

```
Propagated_Sentiment = Original_Sentiment × Relationship_Weight × Decay_Factor
```

**Example:**
- AAPL sentiment: +0.8
- Foxconn relationship weight: 0.7 (high confidence)
- Propagated to Foxconn: 0.8 × 0.7 = 0.56

---

## Components

### 1. SentimentPropagator (`src/signals/sentiment_propagator.py`)

**Core Class:** `SentimentPropagator`

**Key Methods:**
- `propagate(news_item)` - Main propagation method
- `propagate_from_news_result(ticker, news_result)` - Integration with news analyzer
- `calculate_relationship_weight(relationship, type)` - Weight calculation

**Features:**
- BFS traversal (Breadth-First Search) for graph traversal
- Cycle detection (prevents infinite loops)
- Relationship strength weighting
- Revenue concentration-based weights (if available)
- Confidence-based weights (high/medium/low)

### 2. Data Structures

**NewsItem:**
```python
@dataclass
class NewsItem:
    ticker: str
    sentiment_score: float  # -1.0 to 1.0
    supply_chain_score: float  # -1.0 to 1.0
    confidence: float
    relationship: str
    reasoning: str
```

**PropagatedSignal:**
```python
@dataclass
class PropagatedSignal:
    ticker: str
    source_ticker: str
    sentiment_score: float
    supply_chain_score: float
    relationship_type: str  # 'supplier', 'customer', 'competitor'
    relationship_tier: int  # 1 = direct, 2 = indirect
    propagation_weight: float
    source_type: str  # 'direct' or 'propagated'
    confidence: float
    reasoning: str
```

### 3. Integration

**Updated NewsAnalyzer** (`src/signals/news_analyzer.py`):
- Added `enable_propagation` parameter
- Added `get_all_signals()` method
- Returns both direct and propagated signals

---

## Relationship Weighting

### Revenue Concentration (If Available)

If customer relationship has `concentration_pct`:
- **≥20% revenue:** Weight = 0.8
- **≥10% revenue:** Weight = 0.5
- **≥5% revenue:** Weight = 0.3
- **<5% revenue:** Weight = 0.2

### Confidence-Based (Default)

If no revenue data:
- **High confidence:** Weight = 0.7
- **Medium confidence:** Weight = 0.5 (default Tier 1)
- **Low confidence:** Weight = 0.3

### Tier Decay

- **Tier 1 (Direct):** Uses relationship weight (0.5-0.8)
- **Tier 2 (Indirect):** Default 0.2 (20% of original)

---

## Usage

### Basic Usage

```python
from src.signals.sentiment_propagator import SentimentPropagator, NewsItem

# Initialize propagator
propagator = SentimentPropagator(
    tier1_weight=0.5,
    tier2_weight=0.2,
    max_degrees=2
)

# Create news item
news_item = NewsItem(
    ticker='AAPL',
    sentiment_score=0.8,
    supply_chain_score=0.7,
    confidence=0.9,
    relationship='Buyer',
    reasoning='Record iPhone sales'
)

# Propagate
propagated_signals = propagator.propagate(news_item)

# Access results
for signal in propagated_signals:
    print(f"{signal.ticker}: {signal.sentiment_score:.3f} (Tier {signal.relationship_tier})")
```

### Integration with News Analyzer

```python
from src.signals.news_analyzer import NewsAnalyzer

# Initialize with propagation enabled
analyzer = NewsAnalyzer(
    enable_propagation=True,
    propagation_tier1_weight=0.5,
    propagation_tier2_weight=0.2
)

# Analyze news (automatically propagates)
result = analyzer.analyze_news_for_ticker('AAPL', '2023-01-01', '2023-01-07')

# Direct signal
direct_sentiment = result['sentiment_score']

# Propagated signals
propagated = result.get('propagated_signals', [])
for signal in propagated:
    print(f"{signal['ticker']}: {signal['sentiment_score']:.3f}")
```

### Get All Signals

```python
# Get both direct and propagated
direct, propagated = analyzer.get_all_signals('AAPL', '2023-01-01', '2023-01-07')

print(f"Direct: {direct['sentiment_score']:.3f}")
print(f"Propagated: {len(propagated)} signals")
```

---

## Test Results

### AAPL → Foxconn Test

**Input:**
- Ticker: AAPL
- Sentiment: +0.8
- Supply Chain: +0.7

**Output:**
- **Foxconn (HON.TW):** Sentiment = 0.560, Weight = 0.700, Tier = 1
- **TSMC (TSM):** Sentiment = 0.560, Weight = 0.700, Tier = 1
- **Total Propagated:** 31 signals (29 Tier 1, 2 Tier 2)

**Verification:** ✅ Foxconn detected and propagated correctly

---

## Configuration

### Default Weights

```python
propagator = SentimentPropagator(
    tier1_weight=0.5,    # Direct relationships
    tier2_weight=0.2,     # Indirect relationships
    max_degrees=2         # Maximum propagation depth
)
```

### Custom Weights

```python
# More aggressive propagation
propagator = SentimentPropagator(
    tier1_weight=0.7,     # Higher weight for direct
    tier2_weight=0.3,     # Higher weight for indirect
    max_degrees=2
)

# Conservative propagation
propagator = SentimentPropagator(
    tier1_weight=0.3,     # Lower weight
    tier2_weight=0.1,      # Lower weight
    max_degrees=1          # Only direct relationships
)
```

---

## Integration with Backtest

The propagator is automatically integrated into the news processing pipeline:

1. **News Analyzer** analyzes primary ticker
2. **Propagator** generates signals for related companies
3. **Signal Combiner** can use both direct and propagated signals
4. **Portfolio Construction** considers all signals

**Example Flow:**
```
AAPL News → Sentiment: +0.8
    ↓
Propagation Engine
    ├── TSMC: +0.56
    ├── Foxconn: +0.56
    ├── QCOM: +0.56
    └── ... (29 more)
    ↓
Signal Combiner
    ↓
Portfolio Selection
```

---

## Output Format

### Direct Signal

```json
{
  "ticker": "AAPL",
  "source_ticker": "AAPL",
  "sentiment_score": 0.8,
  "supply_chain_score": 0.7,
  "source_type": "direct",
  "confidence": 0.9,
  "relationship": "Buyer",
  "reasoning": "Record iPhone sales"
}
```

### Propagated Signal

```json
{
  "ticker": "HON.TW",
  "source_ticker": "AAPL",
  "sentiment_score": 0.56,
  "supply_chain_score": 0.49,
  "relationship_type": "supplier",
  "relationship_tier": 1,
  "propagation_weight": 0.7,
  "source_type": "propagated",
  "confidence": 0.7,
  "reasoning": "Propagated from AAPL via supplier relationship (Tier 1)"
}
```

---

## Limitations

1. **Database Coverage:** Only propagates to companies in supply chain database
2. **Max Degrees:** Limited to 2 degrees of separation (configurable)
3. **Weight Accuracy:** Uses defaults if revenue concentration data unavailable
4. **Cycle Prevention:** Visited nodes skipped to prevent infinite loops

---

## Future Enhancements

1. **Time Decay:** Older news has lower propagation weight
2. **Relationship Strength:** More granular weighting based on relationship details
3. **Competitor Impact:** Negative sentiment for competitors when primary is positive
4. **Multi-Source Aggregation:** Combine multiple propagated signals for same ticker
5. **Confidence Propagation:** Propagate confidence scores along with sentiment

---

## Files

- `src/signals/sentiment_propagator.py` - Core propagation engine
- `src/signals/news_analyzer.py` - Updated with propagation support
- `scripts/test_sentiment_propagation.py` - Test script
- `outputs/propagation_test_aapl.json` - Test results

---

**Status:** ✅ **PRODUCTION READY**

The propagation engine is fully implemented, tested, and integrated. Enable it by setting `enable_propagation=True` in `NewsAnalyzer`.
