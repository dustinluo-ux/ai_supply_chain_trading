# News Analysis System Explained

## Overview

The news analysis system uses Google's Gemini 2.0 Flash AI model to analyze news articles about stocks and extract two key signals:
1. **Supply Chain Relevance Score** (0.0 to 1.0)
2. **Sentiment Score** (-1.0 to +1.0)

These scores are then combined with technical indicators to generate trading signals.

---

## How Gemini Analyzer Works

### 1. Article Loading

The system loads news articles from JSON files in `data/news/`:
- Main file: `{ticker}_news.json`
- Monthly files: `{ticker}_YYYY_MM.json` (e.g., `AMD_2023_01.json`)

**Example:**
```python
# For ticker "NVDA" on date "2023-06-15"
# System looks for:
# - data/news/NVDA_news.json
# - data/news/NVDA_2023_06.json
# - data/news/NVDA_2023_05.json (if lookback_days=7 extends to previous month)
```

**Date Range:**
- Default `lookback_days = 7` (configurable in `config/signal_weights.yaml`)
- For Monday 2023-06-15, system loads articles from 2023-06-08 to 2023-06-15

### 2. Prompt Construction

The system combines all articles into a single prompt sent to Gemini AI.

**Actual Prompt Template:**
```
Analyze these news articles about {ticker}. Extract:

* supply_chain_relevance: Score 0-1 (mentions of AI datacenter suppliers, chip makers, hardware for AI infrastructure)
* sentiment: Score -1 to +1 (negative to positive)
* confidence: Score 0-1 (how reliable is this analysis)

Articles:
{combined_article_texts}

Return ONLY valid JSON with these 3 fields:
{
  "supply_chain_relevance": 0.0-1.0,
  "sentiment": -1.0 to 1.0,
  "confidence": 0.0-1.0
}

Return ONLY the JSON object, nothing else.
```

**Article Text Format:**
Each article is formatted as:
```
Title: {title}
Description: {description}
Content: {content[:500]}  # First 500 chars
```

Articles are separated by `\n\n---\n\n`.

**Truncation:**
- Maximum combined text length: 30,000 characters
- If exceeded, text is truncated with `"..."` appended

### 3. Gemini API Call

**Model:** `gemini-2.0-flash-exp` (default, configurable)

**Generation Config:**
```python
temperature=0.3      # Lower = more deterministic
top_p=0.8            # Nucleus sampling
top_k=40             # Top-k sampling
max_output_tokens=500
response_mime_type="application/json"  # Forces JSON output
```

**Example API Call:**
```python
response = model.generate_content(
    prompt,
    generation_config=genai.types.GenerationConfig(
        temperature=0.3,
        top_p=0.8,
        top_k=40,
        max_output_tokens=500,
        response_mime_type="application/json"
    )
)
```

### 4. Response Parsing

The system expects JSON response:
```json
{
  "supply_chain_relevance": 0.75,
  "sentiment": 0.3,
  "confidence": 0.85
}
```

**Post-processing:**
- Removes markdown code blocks (```json, ```)
- Parses JSON
- Validates ranges:
  - `supply_chain_relevance`: clamped to [0.0, 1.0]
  - `sentiment`: clamped to [-1.0, 1.0]
  - `confidence`: clamped to [0.0, 1.0]

### 5. Score Mapping

The Gemini response is mapped to our internal format:
```python
scores = {
    'supply_chain_score': float(result.get('supply_chain_relevance', 0.0)),
    'sentiment_score': float(result.get('sentiment', 0.0)),
    'confidence': float(result.get('confidence', 0.0))
}
```

---

## Score Ranges and Interpretation

### Supply Chain Score (0.0 to 1.0)

**Range:** `[0.0, 1.0]`

**Interpretation:**
- `0.0`: No mention of AI supply chain relevance
- `0.5`: Some mention (e.g., "company makes chips")
- `1.0`: Strong relevance (e.g., "supplies GPUs to OpenAI datacenters")

**What Gemini Looks For:**
- Mentions of AI datacenter suppliers
- Chip makers (NVIDIA, AMD, Intel)
- Hardware for AI infrastructure (GPUs, storage, networking)
- Relationships with hyperscalers (AWS, Azure, GCP)
- Relationships with AI labs (OpenAI, Anthropic)

**Example Scores:**
- Article: "NVIDIA announces new GPU for AI training" → `0.9`
- Article: "Company reports quarterly earnings" → `0.2`
- Article: "Western Digital supplies storage to Microsoft Azure AI" → `0.85`

### Sentiment Score (-1.0 to +1.0)

**Range:** `[-1.0, +1.0]`

**Interpretation:**
- `-1.0`: Very negative (e.g., "supply chain disruption", "shortage")
- `0.0`: Neutral (e.g., "company announces product")
- `+1.0`: Very positive (e.g., "record orders", "partnership expansion")

**Example Scores:**
- Article: "NVIDIA faces GPU shortage" → `-0.6`
- Article: "AMD reports strong AI chip demand" → `0.7`
- Article: "Company announces quarterly results" → `0.0`

### Confidence Score (0.0 to 1.0)

**Range:** `[0.0, 1.0]`

**Interpretation:**
- `0.0`: Low confidence (ambiguous article, conflicting information)
- `1.0`: High confidence (clear, specific information)

**Note:** Currently, confidence is calculated but not used in signal combination. It's available for future filtering.

---

## Timing and Lookahead Bias

### Critical: No Lookahead Bias

**Timeline Example:**
```
Monday 2023-06-15 (Week N):
  ├─ Calculate signals using:
  │   ├─ Price data: Up to Friday 2023-06-14 (inclusive)
  │   └─ News data: 2023-06-08 to 2023-06-15 (7-day lookback)
  │
  └─ Trade on: Monday 2023-06-15 (same day)
     └─ Hold until: Monday 2023-06-22 (next rebalance)
```

**Key Points:**
1. **Signals calculated on Monday morning** using data up to previous Friday
2. **Trading happens on Monday** (same day as signal calculation)
3. **News lookback window:** 7 days ending on the signal date
4. **No future data used:** All calculations use only historical data

**Code Implementation:**
```python
# In simple_backtest_v2.py
date_str = monday.strftime("%Y-%m-%d")  # Monday 2023-06-15
lookback_start = (monday - timedelta(days=7)).strftime("%Y-%m-%d")  # 2023-06-08

# News analysis uses articles from lookback_start to date_str
news_signals = news_analyzer.analyze_news_for_ticker(
    ticker, 
    lookback_start,  # 2023-06-08
    date_str         # 2023-06-15
)
```

**Verification:**
- Price data is filtered: `df_filtered = df[df.index <= date_dt]`
- News articles are filtered by `publishedAt` date
- No data from future dates is used

---

## Training vs. Zero-Shot

### Zero-Shot Analysis (No Training)

**The system uses zero-shot learning:**
- Gemini 2.0 Flash is a pre-trained model
- No fine-tuning or training on our data
- No labeled examples provided
- The model uses its general knowledge to interpret articles

**Why Zero-Shot:**
- Faster to implement (no training data needed)
- Works immediately with any ticker
- Leverages Gemini's pre-trained understanding of:
  - Financial terminology
  - Supply chain relationships
  - Sentiment analysis

**Limitations:**
- May misinterpret domain-specific jargon
- No customization to our specific use case
- Relies on model's general knowledge

---

## Fallback Behavior

### When Gemini is Unavailable

**Scenarios:**
1. **No API key:** `GEMINI_API_KEY` not set
2. **API error:** Network failure, rate limit, etc.
3. **No articles found:** News file doesn't exist or is empty
4. **Insufficient articles:** Fewer than `min_articles` (default: 1)

### Fallback: Deterministic Pseudo-Random Scores

**Implementation:**
```python
import hashlib
ticker_hash = int(hashlib.md5(f"{ticker}{start_date}".encode()).hexdigest()[:8], 16)

# Map to ranges
supply_chain = 0.3 + (ticker_hash % 400) / 1000.0  # 0.3 to 0.7
sentiment = -0.2 + (ticker_hash % 400) / 1000.0   # -0.2 to 0.2
confidence = 0.5 + (ticker_hash % 200) / 1000.0   # 0.5 to 0.7
```

**Properties:**
- **Deterministic:** Same ticker + date → same score
- **Different per ticker:** Hash ensures different scores for different tickers
- **Different per date:** Date included in hash
- **Ranges:**
  - Supply chain: `[0.3, 0.7]` (moderate relevance)
  - Sentiment: `[-0.2, 0.2]` (slightly positive to slightly negative)
  - Confidence: `[0.5, 0.7]` (moderate confidence)

**Why This Design:**
- Ensures signal differentiation even without real news
- Prevents all stocks from getting identical scores
- Allows backtesting to proceed even without news data

**Current Status:**
Based on debug output, the system is **currently using fallback scores** because:
- Gemini API may not be configured
- News files may be missing
- API calls may be failing

**To Use Real Gemini:**
1. Set `GEMINI_API_KEY` environment variable
2. Ensure news files exist in `data/news/`
3. Check API quota/rate limits

---

## Example: Complete Analysis Flow

### Input

**Ticker:** `NVDA`  
**Date:** `2023-06-15` (Monday)  
**Lookback:** `7 days` (2023-06-08 to 2023-06-15)

**Articles Found:**
```json
[
  {
    "title": "NVIDIA Announces Record GPU Orders from Hyperscalers",
    "description": "NVIDIA reports unprecedented demand for AI training GPUs from AWS, Microsoft Azure, and Google Cloud.",
    "content": "NVIDIA Corporation announced today that it has received record-breaking orders for its H100 GPUs from major hyperscalers including Amazon Web Services, Microsoft Azure, and Google Cloud Platform. The orders are driven by the explosive growth in AI model training and inference workloads...",
    "publishedAt": "2023-06-12T10:00:00Z"
  },
  {
    "title": "NVIDIA Partners with TSMC for Advanced Chip Manufacturing",
    "description": "NVIDIA expands partnership with TSMC to increase production capacity for AI chips.",
    "content": "NVIDIA and Taiwan Semiconductor Manufacturing Company (TSMC) have announced an expanded partnership to meet growing demand for AI accelerators...",
    "publishedAt": "2023-06-10T14:30:00Z"
  }
]
```

### Prompt Sent to Gemini

```
Analyze these news articles about NVDA. Extract:

* supply_chain_relevance: Score 0-1 (mentions of AI datacenter suppliers, chip makers, hardware for AI infrastructure)
* sentiment: Score -1 to +1 (negative to positive)
* confidence: Score 0-1 (how reliable is this analysis)

Articles:

Title: NVIDIA Announces Record GPU Orders from Hyperscalers
Description: NVIDIA reports unprecedented demand for AI training GPUs from AWS, Microsoft Azure, and Google Cloud.
Content: NVIDIA Corporation announced today that it has received record-breaking orders for its H100 GPUs from major hyperscalers including Amazon Web Services, Microsoft Azure, and Google Cloud Platform. The orders are driven by the explosive growth in AI model training and inference workloads...

---

Title: NVIDIA Partners with TSMC for Advanced Chip Manufacturing
Description: NVIDIA expands partnership with TSMC to increase production capacity for AI chips.
Content: NVIDIA and Taiwan Semiconductor Manufacturing Company (TSMC) have announced an expanded partnership to meet growing demand for AI accelerators...

Return ONLY valid JSON with these 3 fields:
{
  "supply_chain_relevance": 0.0-1.0,
  "sentiment": -1.0 to 1.0,
  "confidence": 0.0-1.0
}

Return ONLY the JSON object, nothing else.
```

### Gemini Response

```json
{
  "supply_chain_relevance": 0.95,
  "sentiment": 0.8,
  "confidence": 0.9
}
```

### Final Scores

```python
{
    'supply_chain_score': 0.95,  # Very high relevance (GPU supplier to hyperscalers)
    'sentiment_score': 0.8,      # Very positive (record orders, partnerships)
    'confidence': 0.9            # High confidence (clear, specific information)
}
```

---

## Integration with Trading Strategy

### Signal Combination

News scores are combined with technical indicators using weighted average:

```python
# From signal_combiner.py
combined_score = (
    supply_chain_score * w_supply_chain +
    sentiment_norm * w_sentiment +
    momentum_norm * w_momentum +
    volume_norm * w_volume
)
```

**Current Weights (from `config/signal_weights.yaml`):**
- `supply_chain`: 0.40
- `sentiment`: 0.30
- `momentum`: 0.20
- `volume`: 0.10

**Sentiment Normalization:**
```python
# Convert [-1, +1] to [0, 1]
if abs(sentiment) < 0.001:
    sentiment_norm = 0.0  # No news = 0.0 (not 0.5)
else:
    sentiment_norm = (sentiment + 1.0) / 2.0
```

**Example Calculation:**
```python
supply_chain_score = 0.95
sentiment_score = 0.8
sentiment_norm = (0.8 + 1.0) / 2.0 = 0.9
momentum_norm = 0.6  # (from technical analysis)
volume_norm = 0.7    # (from technical analysis)

combined_score = (
    0.95 * 0.40 +  # supply_chain
    0.9 * 0.30 +   # sentiment
    0.6 * 0.20 +   # momentum
    0.7 * 0.10     # volume
) = 0.38 + 0.27 + 0.12 + 0.07 = 0.84
```

---

## Debugging and Verification

### Check if Real Gemini is Being Used

**Look for debug output:**
```
[NEWS DEBUG] NVDA: Calling Gemini API with 5 articles...
[NEWS DEBUG] NVDA: Gemini returned: supply_chain=0.750, sentiment=0.300, confidence=0.850
```

**If using fallback:**
```
[NEWS DEBUG] NVDA: Loaded 0 articles from 2023-06-08 to 2023-06-15
[NEWS DEBUG] NVDA: Using fallback scores (no articles): supply_chain=0.523, sentiment=0.142
```

### Verify News Files Exist

```bash
# Check for news files
ls data/news/*_news.json
ls data/news/*_2023_*.json
```

### Test Gemini API

```python
from src.signals.gemini_analyzer import GeminiAnalyzer

analyzer = GeminiAnalyzer()
test_article = {
    'title': 'NVIDIA Partners with Western Digital for AI Storage',
    'description': 'Partnership announcement',
    'content': 'NVIDIA and Western Digital partner for AI datacenter storage solutions.'
}
result = analyzer.analyze_article(test_article)
print(result)
```

---

## Summary

1. **What Gemini Does:** Analyzes news articles to extract supply chain relevance and sentiment
2. **Prompt:** Structured prompt asking for JSON with 3 scores
3. **Scores:**
   - Supply chain: `[0.0, 1.0]` (relevance to AI supply chain)
   - Sentiment: `[-1.0, +1.0]` (negative to positive)
   - Confidence: `[0.0, 1.0]` (reliability)
4. **Timing:** 7-day lookback ending on signal date (no lookahead bias)
5. **Training:** Zero-shot (no training, uses pre-trained model)
6. **Fallback:** Deterministic pseudo-random scores when Gemini unavailable
7. **Current Status:** Likely using fallback scores (check debug output)
