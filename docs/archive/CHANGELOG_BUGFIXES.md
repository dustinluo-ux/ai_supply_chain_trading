# Changelog and Bug Fixes

**Last Updated:** 2026-01-29

---

## 2026-01-29: Multi-Source Quant Pipeline Build

### Added

- **Warm-Up and self-healing:** `src/data/warmup.py` — `warm_up()` loads historical from `data/prices/`, fetches last 30 days from yfinance, merges; `heal_append()` appends new bars to historical store.
- **Client ID rotation:** `src/utils/client_id_rotation.py` — IBKR client IDs start at `IBKR_CLIENT_ID_START` (default 99), rotate 99, 100, 101, …; used by `IBDataProvider`.
- **yfinance cache init:** `src/utils/yfinance_cache_init.py` — `init_yfinance_cache()` to avoid SQLite issues; called from run scripts.
- **IBKR real-time volume:** `IBDataProvider.get_realtime_volume(ticker)` — reqMktData Tick 8, x100 multiplier for US equities.
- **Tiingo news source:** `src/data/news_sources/tiingo_source.py` — TiingoSource (TIINGO_API_KEY); registered in NewsFetcherFactory.
- **Dual-stream news:** `src/data/news_aggregator.py` — DualStreamNewsAggregator (Marketaux + Tiingo); config source `dual_stream`.
- **Position manager:** `src/portfolio/position_manager.py` — PositionManager(provider or executor), get_current_positions, get_account_value, calculate_delta_trades.
- **Weekly rebalance runner:** `run_weekly_rebalance.py` — Composite score → top N → delta trades → BUY/SELL/HOLD; dry-run or --live.
- **E2E pipeline test:** `run_e2e_pipeline.py` — Warm-up (optional) → signals → weekly rebalance dry-run; logs to `logs/`.
- **Docs:** `docs/INDEX.md` (entry point), `docs/ARCHITECTURE.md` (target architecture); DATA.md updated with Warm-Up/self-healing; README updated with weekly rebalance and E2E.

### Changed

- `IBDataProvider`: client_id defaults to `next_client_id()` (rotation) instead of randint(100, 999).
- `.env.example`: already had TIINGO_API_KEY, MARKETAUX_API_KEY, GOOGLE_API_KEY, IBKR_CLIENT_ID_START.

---

## 2026-01-25: Supply Chain Scoring Fixes

### Issue: False Positive AI Relevance

**Problem:** Non-AI companies (AAL, AEM, ADM) ranking higher than actual AI companies due to:
1. Substring matching bug: "AAL" contains "ai"
2. Generic "supply chain" keyword matching (not AI-specific)
3. Scoring formula didn't penalize lack of relationships

**Fixes:**

**FIX 1: Post-Processing Filter**
- **File:** `src/signals/supply_chain_scanner.py` (lines 54-63)
- **Change:** Set `ai_related=False` if no supplier/customer relationships extracted
- **Impact:** Prevents false positives from keyword matching

**FIX 2: Keyword Matching**
- **File:** `src/signals/llm_analyzer.py` (lines 150-175)
- **Change:** Use word boundary regex for "ai" (`\b(ai|artificial intelligence)\b`)
- **Change:** Require AI-specific context for "supply chain" keyword
- **Impact:** Prevents "AAL" from matching "ai", requires AI context for supply chain

**FIX 3: Scoring Formula Adjustment**
- **File:** `src/signals/supply_chain_scanner.py` (lines 161-194)
- **Change:** Reduce AI weight (40% → 20%) if no relationships exist
- **Change:** Cap score at 0.5 for cases with no relationships
- **Impact:** Prevents false positives from scoring >0.5

**Result:** AAL and AEM scores reduced from ~0.5 to <0.3

---

## 2026-01-25: Gemini-Based Supply Chain Ranking

### Issue: Universe Selection Using FinBERT Instead of Gemini

**Problem:** `UniverseLoader` was using default FinBERT for supply chain ranking, which:
- Couldn't extract supplier/customer relationships
- Had false positives from keyword matching
- Produced inaccurate rankings

**Fix:**
- **File:** `src/data/universe_loader.py` (line 478)
- **Change:** Explicitly initialize `SupplyChainScanner` with `llm_provider="gemini", llm_model="gemini-2.5-flash-lite"`
- **Impact:** Universe ranking now uses Gemini for accurate relationship extraction

---

## 2026-01-25: Cache Management

### Issue: Stale Cache Files Causing Incorrect Scores

**Problem:** Old FinBERT-based cache files (`data/supply_chain_mentions.csv`, `data/*_extractions.json`) contained incorrect scores

**Fix:**
- **Created:** `scripts/backup_cache_files.py`
- **Action:** Moved 46 cache files to `data/cache_backup/`
- **Impact:** Forces fresh Gemini analysis on next run

---

## 2026-01-25: Date Range Alignment

### Issue: Price and News Data Date Mismatch

**Problem:** Backtest failing due to no overlap between price and news data dates

**Fix:**
- **File:** `test_signals.py` (lines 327-544)
- **Change:** Implemented "best coverage" approach - finds month with most tickers having news
- **Change:** Filters to tickers with BOTH price data AND news in that period
- **Impact:** Ensures backtest has valid data overlap

**Limitation:** Uses single month, not full multi-month period (compromise approach)

---

## 2026-01-25: News Analysis Returns None

### Issue: News Analyzer Returning None Without Fallback

**Problem:** If no news found, `NewsAnalyzer` returns `None`, causing errors in signal combination

**Fix:**
- **File:** `test_signals.py` (lines 859-866)
- **Change:** Added default values when news signals are `None`:
  ```python
  news_signals = news_signals_cache.get(ticker, {}).get(date_str, {
      'supply_chain_score': 0.0,
      'sentiment_score': 0.0,
      'confidence': 0.0
  })
  ```
- **Impact:** Backtest continues even if news data missing

---

## 2026-01-25: Supply Chain Database Incremental Updates

### Issue: Database Not Expanding Automatically

**Problem:** Supply chain database only had 5 companies, needed to expand to 20+ core stocks

**Fix:**
- **Created:** `src/data/supply_chain_manager.py` - Manages database with freshness tracking
- **Created:** `scripts/expand_database_core_stocks.py` - Expands database to core stocks
- **Change:** `test_signals.py` checks coverage before backtest and warns if missing
- **Impact:** Database can now expand incrementally as new stocks appear

---

## 2026-01-25: Sentiment Propagation

### Feature: Supply Chain Sentiment Propagation

**Added:**
- **File:** `src/signals/sentiment_propagator.py`
- **Feature:** Propagates news sentiment from primary ticker to related companies (suppliers, customers, competitors)
- **Formula:** `Propagated_Sentiment = Original_Sentiment × Relationship_Weight × Decay_Factor`
- **Impact:** News about AAPL automatically affects sentiment for its suppliers (TSMC, Foxconn, etc.)

**Integration:**
- **File:** `src/signals/news_analyzer.py`
- **Change:** Optional sentiment propagation (enabled by default)
- **Config:** `propagation_tier1_weight: 0.5`, `propagation_tier2_weight: 0.2`

---

## Behavioral Changes

### News Analysis: No Fallback Values

**Before:** News analyzer returned fallback pseudo-random scores if no news found

**After:** Returns `None` if no news found (no fallback)

**Impact:** More honest signal quality - missing news is explicit, not hidden

### Supply Chain Ranking: Gemini Required

**Before:** Used FinBERT by default (couldn't extract relationships)

**After:** Uses Gemini by default (can extract relationships)

**Impact:** More accurate universe ranking

### Date Range: Best Coverage Approach

**Before:** Used union of all available dates (could have gaps)

**After:** Uses single month with best ticker coverage (ensures overlap)

**Impact:** More reliable backtests, but limited to single month

---

## Known Issues

1. **IB Integration Unused:** Code exists but `test_signals.py` doesn't use it
2. **No Position Limits:** Single stock can get 100% weight
3. **No Risk Management:** Risk calculator exists but never called
4. **Single Month Backtest:** Uses best-coverage month, not full period
5. **No Portfolio Optimizer:** Never ported (documentation misleading)

---

## Future Fixes Needed

1. **Integrate IB:** Modify `test_signals.py` to use provider/executor factories
2. **Add Position Limits:** Max 15% per stock
3. **Add Risk Management:** Use risk calculator in backtest
4. **Multi-Month Backtest:** Support full date range, not just best month
5. **Portfolio Optimizer:** Port from old project or create simplified version

---

See `docs/SYSTEM_SPEC.md` for current system status.
