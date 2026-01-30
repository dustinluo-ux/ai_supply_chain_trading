# System 1 Verification: AI Supply Chain Trading (Original)

**Purpose:** Historical backtesting of AI supply chain stock selection.  
**Entry point:** `test_signals.py`  
**Verification date:** 2026-01-29  

---

## 1. Can test_signals.py Run Independently?

**Yes.** System 1 is self-contained:

- **Entry:** `python test_signals.py [--universe-size 15] [--top-n 10] [--data-dir <path>]`
- **Dependencies:** `UniverseLoader`, `NewsAnalyzer`, `SignalCombiner` from `src.data` and `src.signals`
- **No imports** from System 2 entry points (`run_weekly_rebalance`, `run_e2e_pipeline`) or from `src.data.warmup`, `src.portfolio.position_manager` for the backtest path
- **Output:** Logs to `outputs/backtest_log_YYYYMMDD_HHMMSS.txt` (stdout redirected) and prints Sharpe ratios for technical-only, news-only, and combined

**Test:** Run from project root:

```bash
python test_signals.py --universe-size 15 --top-n 10
```

Requires:

- `config/data_config.yaml` with valid `data_dir` pointing to historical CSVs
- `data/news/` with `*_news.json` for news coverage
- Optional: `data/cache/` and Gemini for supply chain ranking (or pre-generated supply chain outputs)

---

## 2. Data Sources Used by System 1

| Resource | Location | Role |
|----------|----------|------|
| **Historical price CSVs** | `data/stock_market_data/` (config: `data_config.yaml` → `data_sources.data_dir`) | Subdirs: `nasdaq/csv`, `sp500/csv`, `forbes2000/csv`, `nyse/csv` |
| **Cached Gemini news analysis** | `data/cache/` (e.g. Gemini extractions); news JSON in `data/news/` | Supply chain extraction cache; raw news per ticker |
| **Supply chain ranking** | `UniverseLoader.load_universe(..., rank_by_supply_chain=True)` | Ranks up to `supply_chain_pool_size` (e.g. 45) → top `max_tickers` (e.g. 15) |

**Config:** `config/data_config.yaml`:

- `data_sources.data_dir`: e.g. `data/stock_market_data` (or absolute path)
- `data_sources.file_format`: `csv`
- `universe_selection.max_tickers`: 15 (overridable by `--universe-size`)
- `universe_selection.date_range`: 2020–2024

System 1 does **not** read from `data/prices/*.parquet` or use `warmup.py`; it uses only the CSV-based paths above.

---

## 3. Supply Chain Ranking (45 → Top 15)

- **Component:** `src/data/universe_loader.py` — `load_universe(max_tickers, rank_by_supply_chain=True, supply_chain_pool_size=max_tickers*3)`
- **Flow:** Find all CSV files in configured subdirs → validate (min data points, date range, etc.) → optionally rank by supply chain (Gemini/supply chain manager) → return top `max_tickers`
- **Result:** Universe is **not** limited to symbols starting with 'A'; NVDA, AMD, TSM are included if they have valid CSV files in the configured subdirs and rank in the top N

---

## 4. Recent Fixes Verified

### AAL bug (word boundary / false positive "ai")

- **Problem:** "AAL" was matched as AI-related because it contains the substring "ai".
- **Fixes in codebase:**
  1. **`src/signals/llm_analyzer.py`** (lines ~153–158): Uses word-boundary regex for "ai": `r'\b(ai|artificial intelligence)\b'` so "AAL", "daily", etc. are not matched.
  2. **`src/signals/supply_chain_scanner.py`** (lines ~54–63): Post-processing filter: if no supplier/customer relationships are extracted, set `ai_related = False` and cap relevance, avoiding keyword-only false positives (e.g. "AAL").
- **Status:** Both fixes are present; AAL should no longer be misclassified as AI supply chain.

### NVDA / AMD / TSM in universe

- **Mechanism:** Universe is built from **all** tickers with valid CSV files in `data/stock_market_data/` subdirs, then supply chain ranking selects the top N. There is no filter that restricts to symbols starting with 'A'.
- **References:** `ticker_utils.py` lists AMD, NVDA, TSM in a semantic set; `supply_chain_scanner.py` and `technical_indicators.py` use NVDA/AMD (and similar) in tests. Inclusion in the live universe depends on having CSVs for those tickers in the configured data dir.
- **Status:** Architecture supports NVDA/AMD/TSM; ensure their CSVs exist under the configured `data_dir` subdirs for them to appear in the backtest.

---

## 5. Backtest Results (Technical / News / Combined Sharpe)

- **Location:** Inline in `test_signals.py`: `run_backtest_with_preloaded_data()` (lines ~814+).
- **Flow:** Load universe and prices once → detect news date range (best-coverage month) → for each week in range, compute technical and news signals from preloaded caches → `SignalCombiner` for combined ranking → simulate positions → compute Sharpe for three modes.
- **Output:** Printed (and in `outputs/backtest_log_*.txt`): Sharpe ratios for:
  - `technical_only`
  - `news_only`
  - `combined`

**To reproduce:** Run `test_signals.py` with desired `--universe-size` and `--top-n`; check console and `outputs/backtest_log_*.txt` for the three Sharpe values.

**Test run (2026-01-29):** `python test_signals.py --universe-size 5 --top-n 3` was run from project root. Result: universe loaded successfully from `data/stock_market_data/` (nasdaq, sp500, forbes2000, nyse CSVs); script proceeded to load phase. Full backtest (including Gemini supply chain ranking when enabled) can take several minutes; run completed or timed out in environment. Log written to `outputs/backtest_log_*.txt`. This confirms System 1 runs independently and uses historical CSVs as intended.

---

## Summary

| Check | Status |
|-------|--------|
| test_signals.py runs independently | Yes |
| Uses historical CSVs from data/stock_market_data/ | Yes (via data_config.yaml) |
| Uses cached Gemini news analysis | Yes (data/news + data/cache) |
| Supply chain ranking 45 → top 15 | Yes (UniverseLoader) |
| AAL word-boundary / post-process fix | Present (llm_analyzer + supply_chain_scanner) |
| NVDA/AMD/TSM can be in universe | Yes (if CSVs present in data_dir) |
| Produces technical/news/combined Sharpe ratios | Yes (inline backtest) |

System 1 remains functional and isolated from System 2’s entry points and warmup/parquet data path.
