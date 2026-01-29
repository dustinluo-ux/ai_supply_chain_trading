# Trading Strategy Summary

**Last Updated:** 2026-01-25  
**Purpose:** High-level overview of strategic choices and assumptions in the trading system.

---

## Stock Universe

- **Size:** 15 stocks (configurable via `--universe-size` or `config/data_config.yaml`)
- **Sources:** NASDAQ, S&P 500, NYSE, Forbes 2000
- **Market Cap:** $500M - $5B (mid-cap focus)
- **Minimum Price:** $1.00 (excludes penny stocks)
- **Selection:** Stocks with both price data and news coverage in the selected period

---

## Time Period & Data Alignment

- **Date Selection:** Automatically finds the month with the most ticker news coverage
- **Alignment:** Prefers news months that align with available price data years
- **Example:** If price data is 2023-2024, system prefers 2023 news months over 2022
- **Warmup Period:** Requires 30 days of price history before first signal (for technical indicators)

---

## Trading Signals

### Technical Signals

- **Momentum:** Compares 5-day price vs 20-day price (short-term vs medium-term trend)
- **Volume Spike:** Current volume vs 30-day average (identifies unusual trading activity)
- **RSI:** 14-day Relative Strength Index (measures overbought/oversold conditions)

### News Signals (AI-Powered)

- **Supply Chain Health Score:** -1.0 to +1.0
  - Negative = supply chain disruptions, shortages, constraints
  - Positive = healthy supply chain, growing capacity, strong partnerships
  - Analyzed using Gemini 2.5 Flash Lite AI model
  
- **Sentiment Score:** -1.0 to +1.0
  - Negative = bad news (losses, delays, problems)
  - Positive = good news (gains, growth, opportunities)
  
- **Lookback Window:** 7 days before each rebalance date
  - Analyzes news from the past week to inform Monday's trading decision
  - Assumes news reflects supply chain conditions 7 days ahead

- **Asymmetric Analysis:** AI considers the ticker's role (Supplier vs Buyer)
  - Example: TSMC raising prices = Neutral for TSMC (supplier), Negative for Apple (buyer)

### Sentiment Propagation (NEW)
- **Automatic Propagation:** News sentiment automatically propagates to related companies
- **Relationships:** Suppliers, customers, and competitors from curated supply chain database
- **Propagation Depth:** Up to 2 degrees of separation (e.g., AAPL → TSMC → ASML)
- **Weighting:** Based on relationship strength (revenue concentration or confidence level)
- **Tier 1 Weight:** 0.5-0.8 (direct relationships)
- **Tier 2 Weight:** 0.2 (indirect relationships)
- **Example:** Positive AAPL news (+0.8) → Foxconn gets +0.56 sentiment (Tier 1, weight 0.7)
- **Enable/Disable:** Configurable via `enable_propagation` in NewsAnalyzer

---

## Signal Combination

### ML Regression Alternative (NEW)
- **Option:** Use ML model predictions instead of weighted signal combination
- **Enable:** Set `use_ml: true` in `config/model_config.yaml`
- **Models:** Linear, Ridge, Lasso, XGBoost (switchable via config)
- **Training:** Automatic on historical data (training period from config)
- **Features:** momentum, volume, RSI, supply_chain, sentiment
- **Target:** Forward 1-week return
- **Fallback:** If ML disabled or prediction fails, uses weighted signals

### Combined Mode (Default - Weighted Signals)
- **Supply Chain:** 40% weight
- **Sentiment:** 30% weight
- **Momentum:** 20% weight
- **Volume:** 10% weight
- **Method:** Fixed weighted average of normalized signals

### ML Model Mode (Alternative)
- **Method:** ML regression predicts forward return from features
- **Ranking:** Stocks ranked by predicted return (higher = better)
- **Models:** Linear (baseline), Ridge, Lasso, XGBoost
- **Training:** Uses historical data from training period (before backtest)
- **Validation:** 20% of training data used for validation

### Alternative Modes (Weighted Signals)
- **Technical-Only:** Momentum 50%, Volume 30%, RSI 20% (no news analysis)
- **News-Only:** Supply Chain 50%, Sentiment 50% (no technical indicators)

### Handling Missing Data
- **No News:** News signals set to 0.0 (neutral), relies on technical signals only
- **No Technical Data:** Uses default neutral values (momentum=0, volume=1.0, RSI=0.5)
- **News-Only Mode:** Skips ticker entirely if no news found (no fallback)

---

## Portfolio Construction

### Stock Selection
- **Method:** Rank all stocks by combined signal score, select top N
- **Default:** Top 10 stocks per week
- **Configurable:** Can change number of stocks (e.g., top 5, top 20)

### Position Weighting
- **Default Method:** Proportional weighting
  - Higher signal score = larger position
  - Weights sum to 100% of portfolio
  
- **Alternative:** Equal weighting
  - All selected stocks get equal weight (1/N)
  - Used as fallback if all scores are zero

### Rebalancing
- **Frequency:** Weekly (every Monday)
- **Holding Period:** Positions held from Monday to next Monday
- **Transaction Costs:** 10 basis points (0.1%) per rebalance
  - Only charged when positions actually change
  - Example: $100,000 portfolio = $100 cost per rebalance

---

## News Analysis System

### AI Model
- **Model:** Google Gemini 2.5 Flash Lite (paid tier)
- **Batching:** Analyzes up to 3 articles per API call (optimizes cost)
- **Caching:** Results cached to avoid redundant API calls for same ticker/date

### Article Requirements
- **Minimum:** 1 article required for analysis
- **Date Range:** Articles must be within 7-day lookback window
- **Source:** News files in `data/news/{ticker}_news.json` format

### Output
- **Supply Chain Health:** -1.0 (disruption) to +1.0 (healthy)
- **Relationship:** Supplier / Buyer / Neutral
- **Reasoning:** 15-word explanation of the score

---

## Performance Measurement

- **Sharpe Ratio:** Annualized risk-adjusted return (252 trading days)
- **Maximum Drawdown:** Largest peak-to-trough decline
- **Total Return:** Cumulative portfolio return
- **Returns Calculation:** Uses next-day prices (avoids lookahead bias)
  - Signals calculated Monday morning
  - Positions set Monday
  - Returns measured from Tuesday's price changes

---

## Key Assumptions & Limitations

### Assumptions
1. **News Lead Time:** News reflects supply chain conditions 7 days ahead
2. **Weekly Rebalancing:** Weekly signals are sufficient (not daily)
3. **Top N Selection:** Holding top 10 stocks captures most opportunity
4. **Proportional Weighting:** Higher signals deserve larger positions
5. **No Shorting:** Only long positions (no negative weights)
6. **Supply Chain Focus:** News about supply chain is predictive of stock performance

### Known Limitations
1. **Date Coverage:** Backtest limited to months with good news coverage
2. **Supply Chain Database Coverage:** Propagation only works for companies in database
3. **Fixed Weights:** Signal weights are fixed (not adaptive to market conditions) - unless using ML
4. **Single Timeframe:** All signals use same lookback periods (not multi-timeframe)
5. **No Risk Management:** No stop-losses, position sizing limits, or volatility filters
6. **News Quality:** Depends on quality and completeness of news data
7. **LLM Reliability:** AI analysis may miss nuances or misinterpret articles
8. **ML Training Period:** Must be before backtest period (no overlap)
9. **Propagation Depth:** Limited to 2 degrees of separation (configurable)

### Data Requirements
- **Price Data:** Minimum 5 days of history required
- **News Data:** At least 1 article in 7-day window
- **Alignment:** Price and news data must overlap in time

---

## Configuration Options

### Easily Changeable
- Number of stocks in portfolio (default: 10)
- Signal weights (via config file)
- News lookback window (default: 7 days)
- Market cap range (default: $500M-$5B)
- Universe size (default: 50 stocks)
- Position weighting method (proportional vs equal)

### Requires Code Changes
- Rebalancing frequency (currently weekly only)
- Technical indicator periods (momentum, volume, RSI windows)
- Transaction cost rate (currently 10 bps)
- News analysis model (currently Gemini 2.5 Flash Lite)
- Date selection algorithm (currently "best coverage")

---

## Quick Reference

**What the strategy does:**
1. Selects 15 mid-cap stocks with news coverage
2. Calculates technical signals (momentum, volume, RSI) weekly
3. Analyzes news for supply chain health and sentiment (7-day window)
4. **Optionally propagates sentiment** to related companies (suppliers, customers, competitors)
5. **Optionally uses ML model** to predict returns (instead of weighted signals)
6. Combines signals: 40% supply chain, 30% sentiment, 20% momentum, 10% volume (if ML disabled)
7. Ranks stocks and buys top 10 with proportional weights
8. Rebalances every Monday
9. Pays 10 bps transaction costs per rebalance

**What affects results:**
- Quality of news data
- Accuracy of AI supply chain analysis
- Supply chain database coverage (for propagation)
- ML model choice and training data quality (if ML enabled)
- Market conditions (bull vs bear)
- News coverage completeness
- Signal weight choices (if using weighted signals)
- Number of stocks held

**What doesn't affect results:**
- Internal normalization formulas
- Cache directory structure
- API rate limiting details
- Data file formats
- Debug mode settings

---

**For technical implementation details, see `MODEL_SPECIFICATION.md`**
