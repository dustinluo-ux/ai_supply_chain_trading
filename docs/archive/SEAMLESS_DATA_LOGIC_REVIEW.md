# Seamless Data Logic Self-Review

**Date:** 2026-01-28  
**Reviewer:** AI Assistant  
**Purpose:** Verify implementation against seamless data logic requirements

---

## EXECUTIVE SUMMARY

**Status:** ⚠️ **PARTIAL IMPLEMENTATION** - Core functionality exists but missing critical features for seamless live trading.

**Critical Gaps:**
1. ❌ No automatic warm-up period (14-30 days) before live inference
2. ❌ No gap-filling logic between last CSV entry and current moment
3. ⚠️ Schema standardization exists but not enforced via Standardizer class
4. ⚠️ Normalization consistency needs verification
5. ✅ Self-healing storage implemented
6. ✅ Continuous loop partially implemented (append to historical)

---

## 1. THE 'WARM-UP' CHECK

### Requirement
Does `get_data()` automatically pull enough 'recent-historical' data (last 14-30 days) to calculate indicators before starting live inference?

### Current Implementation
**Status:** ❌ **NOT IMPLEMENTED**

**Current Behavior:**
- `get_data()` requires explicit `start_date` and `end_date` parameters
- No automatic warm-up period calculation
- No logic to fetch recent historical data before live inference

**Code Location:** `src/data/multi_source_factory.py:586-627`

```python
def get_data(
    ticker: str,
    start_date: str,  # REQUIRED - no auto-calculation
    end_date: str,    # REQUIRED - no auto-calculation
    include_news: bool = True,
    use_ibkr_for_intraday: bool = False,
) -> pd.DataFrame:
```

**Missing Logic:**
- No automatic calculation of warm-up period (14-30 days before `end_date`)
- No check for minimum data points required for technical indicators
- No automatic extension of `start_date` to ensure sufficient history

**Recommendation:**
```python
def get_data(
    ticker: str,
    start_date: Optional[str] = None,  # Auto-calculate if None
    end_date: Optional[str] = None,   # Default to today if None
    include_news: bool = True,
    use_ibkr_for_intraday: bool = False,
    warmup_days: int = 30,  # NEW: Warm-up period
) -> pd.DataFrame:
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if start_date is None:
        # Auto-calculate start_date to include warm-up period
        end_dt = pd.to_datetime(end_date)
        start_dt = end_dt - pd.Timedelta(days=warmup_days)
        start_date = start_dt.strftime("%Y-%m-%d")
    
    # ... rest of implementation
```

---

## 2. SOURCE CONTINUITY

### Requirement
Ensure data schema (column names, date formats, sentiment scales) is identical whether data comes from local historical folder, Tiingo, or IBKR.

### Current Implementation
**Status:** ⚠️ **PARTIALLY IMPLEMENTED** - Schema standardization exists but not enforced via Standardizer class

**Current Behavior:**
- All sources return standardized columns: `[timestamp, ticker, price, volume, sentiment_score, source_origin]`
- Date format: `pd.Timestamp` (timezone-naive)
- Sentiment scale: `-1.0 to 1.0` (normalized via `normalize_sentiment()`)
- Price: `close` renamed to `price`
- Volume: Standardized (IBKR applies x100 multiplier)

**Code Locations:**
- Price standardization: `src/data/multi_source_factory.py:303-326` (yfinance), `342-398` (IBKR)
- News standardization: `src/data/multi_source_factory.py:426-491`
- Sentiment normalization: `src/data/multi_source_factory.py:267-280`
- Merge logic: `src/data/multi_source_factory.py:498-549`

**Issues:**
1. **No Standardizer Class:** Schema standardization is scattered across multiple functions
2. **No Validation:** No explicit validation that all sources return identical schemas
3. **Inconsistent Column Handling:** Some sources may return additional columns that are dropped

**Recommendation:**
Create `DataStandardizer` class:

```python
class DataStandardizer:
    """Ensures consistent schema across all data sources"""
    
    REQUIRED_COLUMNS = ["timestamp", "ticker", "price", "volume", "sentiment_score", "source_origin"]
    
    @staticmethod
    def standardize(df: pd.DataFrame, source: str) -> pd.DataFrame:
        """Standardize DataFrame to required schema"""
        # 1. Ensure timestamp is pd.Timestamp (timezone-naive)
        # 2. Rename columns (close -> price, etc.)
        # 3. Ensure all required columns exist
        # 4. Validate data types
        # 5. Sort by timestamp
        # 6. Remove duplicates
        pass
    
    @staticmethod
    def validate(df: pd.DataFrame) -> bool:
        """Validate DataFrame matches required schema"""
        # Check columns, types, ranges
        pass
```

---

## 3. THE 'GAP' LOGIC

### Requirement
Check if script has logic to fill the 'Gap' (time between last entry in CSV and current moment). Should fetch missing data from Tiingo/YFinance and 'heal' the local CSV before proceeding to live mode.

### Current Implementation
**Status:** ❌ **NOT IMPLEMENTED**

**Current Behavior:**
- `_append_to_historical()` appends new data to CSV but doesn't check for gaps
- No logic to detect gap between last CSV entry and current date
- No automatic gap-filling before live inference

**Code Location:** `src/data/multi_source_factory.py:552-579`

**Missing Logic:**
```python
def _append_to_historical(ticker: str, df: pd.DataFrame) -> None:
    # CURRENT: Just appends new data
    # MISSING: Check for gaps and fill them
```

**Recommendation:**
```python
def _fill_gap_and_append(ticker: str, end_date: Optional[str] = None) -> None:
    """Fill gap between last CSV entry and end_date, then append"""
    historical_path = Path("data/historical") / f"{ticker.upper()}.csv"
    
    if historical_path.exists():
        existing = pd.read_csv(historical_path, parse_dates=["timestamp"])
        last_date = existing["timestamp"].max()
        
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        end_dt = pd.to_datetime(end_date)
        
        # Check for gap
        if last_date < end_dt:
            gap_start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            gap_data = get_data(ticker, gap_start, end_date, include_news=True)
            
            if not gap_data.empty:
                combined = pd.concat([existing, gap_data], ignore_index=True)
                combined.drop_duplicates(subset=["timestamp"], keep="last", inplace=True)
                combined.sort_values("timestamp", inplace=True)
                combined.to_csv(historical_path, index=False)
                logger.info(f"Filled gap for {ticker}: {gap_start} to {end_date}")
```

---

## 4. EXISTING CODE REVIEW

### Requirement
Did you find any data-loading or cleaning modules in `wealth_signal_mvp_v1`? If so, list them and confirm they are being utilized.

### Findings
**Status:** ⚠️ **NOT UTILIZED** - Found modules but not integrated

**Modules Found in `wealth_signal_mvp_v1/core/data/`:**
1. `loader_ibkr.py` - IBKR data loader (✅ **ALREADY PORTED** - used in `multi_source_factory.py`)
2. `loader_yahoo.py` - Yahoo Finance loader (⚠️ **NOT USED** - we use `yfinance` directly)
3. `loader_text.py` - Text data loader (❌ **NOT USED**)
4. `load_reddit_data.py` - Reddit data loader (❌ **NOT USED**)
5. `load_twitter_data.py` - Twitter data loader (❌ **NOT USED**)
6. `loader_oecd.py` - OECD data loader (❌ **NOT USED**)
7. `registry.py` - Data loader registry (⚠️ **NOT USED** - could be useful for abstraction)

**Analysis:**
- `loader_ibkr.py` logic was ported to `_fetch_price_ibkr()` in `multi_source_factory.py`
- Other loaders are not relevant for this use case (social media, OECD)
- `registry.py` pattern could be useful but not critical

**Recommendation:**
- ✅ IBKR logic already integrated
- ⚠️ Consider using `registry.py` pattern for future extensibility (low priority)

---

## 5. INFERENCE VS. TRAINING

### Requirement
Ensure Gemini Scorer and Rebalancing Engine use exact same normalization math for both backtesting and live data.

### Current Implementation
**Status:** ⚠️ **NEEDS VERIFICATION**

**Gemini Scorer Normalization:**
- Location: `src/data/multi_source_factory.py:267-280`
- Function: `normalize_sentiment(score: float, source: str) -> float`
- Scale: `-1.0 to 1.0`
- Logic: `max(-1.0, min(1.0, value))`

**Backtest Normalization:**
- Location: `test_signals.py:832` (line 832 shows "Normalize" comment)
- Need to verify actual normalization logic

**Potential Issues:**
1. **Different Normalization Functions:** `multi_source_factory.py` has `normalize_sentiment()`, but backtest may use different logic
2. **Gemini Scorer Output:** Already normalized to `-1.0 to 1.0` in `GeminiScorer.score()` (line 110-111)
3. **Double Normalization Risk:** If both Gemini and backtest normalize, could cause issues

**Code Verification Needed:**
```python
# In multi_source_factory.py:110-111
score = max(-1.0, min(1.0, score))  # Already normalized

# In multi_source_factory.py:466
sentiment = normalize_sentiment(score_obj["score"], art.get("source", "Gemini"))
# This normalizes again - potential double normalization?
```

**Recommendation:**
1. Verify backtest uses same `normalize_sentiment()` function
2. Remove double normalization if present
3. Create shared normalization module: `src/utils/normalization.py`

---

## 6. CONTINUOUS LOOP

### Requirement
Verify system operates as 'Continuous Loop' where today's live data becomes tomorrow's historical data automatically.

### Current Implementation
**Status:** ✅ **PARTIALLY IMPLEMENTED**

**Current Behavior:**
- `_append_to_historical()` appends fetched data to `data/historical/{TICKER}.csv`
- De-duplicates by timestamp
- Sorts by timestamp

**Code Location:** `src/data/multi_source_factory.py:552-579`

**What Works:**
- ✅ Fetched data is automatically appended to historical CSV
- ✅ Duplicates are removed (keep last)
- ✅ Data is sorted chronologically

**What's Missing:**
- ❌ No automatic daily/weekly sync job
- ❌ No scheduled task to fetch latest data
- ❌ No integration with live trading loop

**Recommendation:**
Create scheduled sync job:
```python
def sync_historical_data(tickers: List[str], days_back: int = 1) -> None:
    """Sync historical data for tickers (run daily)"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - pd.Timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    for ticker in tickers:
        get_data(ticker, start_date, end_date, include_news=True)
        # This automatically appends to historical CSV
```

---

## SUMMARY OF GAPS

| Requirement | Status | Priority | Effort |
|------------|--------|----------|--------|
| Warm-Up Check | ❌ Missing | **HIGH** | Medium |
| Source Continuity | ⚠️ Partial | Medium | Low |
| Gap Logic | ❌ Missing | **HIGH** | Medium |
| Existing Code Review | ⚠️ Partial | Low | Low |
| Inference vs Training | ⚠️ Needs Verification | **HIGH** | Low |
| Continuous Loop | ✅ Partial | Medium | Low |

---

## RECOMMENDED FIXES (Priority Order)

### 1. **HIGH PRIORITY: Add Warm-Up Logic**
```python
def get_data_with_warmup(
    ticker: str,
    end_date: Optional[str] = None,
    warmup_days: int = 30,
    include_news: bool = True,
) -> pd.DataFrame:
    """Get data with automatic warm-up period"""
    # Auto-calculate start_date = end_date - warmup_days
    # Fetch data
    # Return
```

### 2. **HIGH PRIORITY: Add Gap-Filling Logic**
```python
def ensure_data_continuity(ticker: str, end_date: Optional[str] = None) -> None:
    """Fill gap between last CSV entry and end_date"""
    # Check last entry in CSV
    # Calculate gap
    # Fetch missing data
    # Append to CSV
```

### 3. **HIGH PRIORITY: Verify Normalization Consistency**
- Create shared `normalization.py` module
- Ensure backtest and live use same functions
- Remove double normalization

### 4. **MEDIUM PRIORITY: Create DataStandardizer Class**
- Centralize schema standardization
- Add validation
- Ensure consistency

### 5. **MEDIUM PRIORITY: Add Scheduled Sync Job**
- Daily/weekly sync to update historical CSVs
- Integration with live trading loop

---

## NEXT STEPS

1. **Immediate:** Implement warm-up and gap-filling logic
2. **Short-term:** Verify and fix normalization consistency
3. **Medium-term:** Create Standardizer class and scheduled sync

**Estimated Effort:** 4-6 hours for high-priority fixes
