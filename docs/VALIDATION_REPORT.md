# Validation Report — Quality & Validation Engineer

**Date:** 2026-02-21  
**Scope:** Code audit vs TECHNICAL_SPEC.md / ARCHITECTURE.md, T-1 safety, data integrity, configuration, SYSTEM_MAP parity  
**Evidence rule:** All claims cite file path and symbol; missing evidence marked UNKNOWN.

---

## 1. Single Source of Truth Loaded

- **docs/INDEX.md** — Read; canonical docs and entry points confirmed.
- **docs/SYSTEM_MAP.md** — Read; workflow→code mapping and file counts verified against disk.
- **docs/ARCHITECTURE.md** — Read; cross-checked with SYSTEM_MAP and disk.
- **docs/TECHNICAL_SPEC.md** — Read; indicator math, Master Score, and no look-ahead rules used as reference.

---

## 2. Code Audit vs TECHNICAL_SPEC.md and ARCHITECTURE.md

### 2.1 TECHNICAL_SPEC Compliance

| Requirement | Evidence | Status |
|-------------|----------|--------|
| Master Score in `src.signals.technical_library` | `src/signals/technical_library.py` — module exists; `calculate_all_indicators`, `compute_signal_strength` present | **PASS** |
| Normalization: bounded = static; unbounded = rolling 252-day min-max | `src/signals/technical_library.py:65–76` — `_rolling_minmax(series, window=252)`; docstring "Prevents look-ahead bias" | **PASS** |
| ATR for sizing from Signal Day − 1 | `src/signals/signal_engine.py:194–195` — `row = ind.iloc[-1]`, `row_sizing = ind.iloc[-2]`; `ind` from `slice_df = df[df.index <= as_of_date]` so last row = T, second-to-last = T−1 | **PASS** |
| Regime HMM in `src.signals.weight_model` | `src/signals/weight_model.py:135` — `series = close_series[close_series.index <= as_of_date]`; docstring "Fits ... up to as_of_date (no look-ahead)" | **PASS** |
| News composite from `data/news/{ticker}_news.json` | TECHNICAL_SPEC §2; `src/signals/news_engine.py` — `load_ticker_news(news_dir, ticker)`; input source documented in docstring | **PASS** |

### 2.2 ARCHITECTURE vs SYSTEM_MAP vs Disk (Parity / Drift)

| Issue | Evidence | Action |
|-------|----------|--------|
| SignalEngine location | ARCHITECTURE.md L33: "SignalEngine (`src/core/signal_engine.py`)". Actual: `src/signals/signal_engine.py` (SYSTEM_MAP L47, disk) | **FLAG:** ARCHITECTURE out of sync; Architect should correct ARCHITECTURE.md to `src/signals/signal_engine.py`. |
| Regime detection module | ARCHITECTURE L60: "regime.py" under signals/. No `regime.py` on disk; regime in `weight_model.py` (get_regime_hmm) | **FLAG:** ARCHITECTURE doc drift; update to weight_model. |
| Portfolio sizing module | ARCHITECTURE L62: "sizing.py". Disk: `position_sizer.py` (SYSTEM_MAP correct) | **FLAG:** ARCHITECTURE should say position_sizer.py. |
| Execution modules | ARCHITECTURE L64–65: "executors.py", "factory.py". Disk: base_executor, mock_executor, ib_executor, executor_factory | **FLAG:** ARCHITECTURE naming does not match disk; align with SYSTEM_MAP. |

---

## 3. T-1 Safety (No Look-Ahead)

### 3.1 Pass: Price and indicator slicing

- **Signal slice:** `src/signals/signal_engine.py:176` — `slice_df = df[df.index <= as_of_date]` (backtest path).  
- **Regime SPY:** `src/core/target_weight_pipeline.py:83,92` — `spy_close_series.index <= as_of`.  
- **HMM input:** `src/signals/weight_model.py:135` — `close_series[close_series.index <= as_of_date]`.  
- **Sizing row:** `src/signals/signal_engine.py:194–195` — ATR from `iloc[-2]` on slice ≤ as_of_date ⇒ T−1.  
- **Technical normalization:** `src/signals/technical_library.py:71–72` — rolling min/max on series; caller passes pre-sliced `df` ⇒ no future data.  

**Verdict:** Price and technical pipeline respect T−1.

### 3.2 FAIL: News article date filter (potential look-ahead)

- **Evidence:** `src/signals/news_engine.py:517`  
  ```python
  articles = [a for a in articles if ... and cutoff <= d <= as_of]
  ```  
  Articles with `publishedAt == as_of` (signal date T) are **included**. TECHNICAL_SPEC and Validator rule: no signal at date T may use data from T or later.

- **Impact:** For a Monday signal date, news published on Monday is used → look-ahead.

- **Recommendation:** Change to strict T−1: filter with `d < as_of` (or use end-of-day T−1 as cutoff and keep `d <= cutoff`). If product intent is “same-day news allowed,” document explicitly and get Architect/Validator approval to relax the constraint.

**Verdict:** **FAIL** until filter is `d < as_of` or exception is documented and approved.

---

## 4. Data Integrity

### 4.1 Data inputs and cited sources

- **Price data:** `config/data_config.yaml` → `data_sources.data_dir` (e.g. `C:/ai_supply_chain_trading/trading_data/stock_market_data`). Code: `src/data/csv_provider.py` — `load_data_config()` reads that path. **PASS.**  
- **News data:** `config/data_config.yaml` → `news_data.directory` (e.g. `data/news`); TECHNICAL_SPEC §2 and news_engine docstring cite `data/news/{ticker}_news.json`. **PASS.**

### 4.2 CSV/Parquet date handling

- **csv_provider:** `src/data/csv_provider.py:65,90` — `pd.read_csv(..., index_col=0, parse_dates=False)` then `pd.to_datetime(df.index, format="mixed", dayfirst=True)`. Handles mixed date formats explicitly. **PASS.**  
- **universe_loader:** `src/data/universe_loader.py:150,162,177` — `parse_dates=True` or explicit index parsing; parquet read. Multiple code paths; no single canonical list. **PASS** (no evidence of raw string index used in time logic).  
- **storage_handler:** `src/utils/storage_handler.py:91` — `pd.read_parquet(path, engine="fastparquet")`. Parquet typically carries datetime dtypes; no mixed-string date logic in this file. **PASS.**

---

## 5. Configuration Check

- **min_order_size / max_position_size:** Enforced in code; not hardcoded as sole source.  
  - `config/trading_config.yaml:32–33` — `min_order_size: 1`, `max_position_size: 10000`.  
  - `src/execution/ibkr_bridge.py:384–385,512–513` — reads from config; `src/execution/ibkr_bridge.py:392–393,526–527,539–541` — enforces.  
  - `scripts/run_execution.py:474–475,573,578` — reads from config.  
  **PASS.**

- **Backtest data_dir override (hardcoded default):**  
  - **Evidence:** `scripts/backtest_technical_library.py:571–573` — `config = load_config()` then `data_dir = ROOT / "data" / "stock_market_data"` (overwrites config).  
  - **Impact:** `data_config.yaml` `data_sources.data_dir` is ignored; backtest fails when data lives elsewhere (e.g. CLAUDE.md `DATA_DIR=C:\ai_supply_chain_trading\trading_data`).  
  **FAIL:** Backtest must use config as single source: e.g. `data_dir = Path(config.get("data_dir", str(ROOT / "data" / "stock_market_data")))` (or equivalent from `load_config()` return).

---

## 6. SYSTEM_MAP Parity (New / Missing Files)

**Rule (SYSTEM_MAP):** Every `.py` under `src/` must be listed.

| Location | On disk, not in SYSTEM_MAP | SYSTEM_MAP says |
|----------|----------------------------|------------------|
| `src/signals/` | `feature_engineering.py`, `llm_bridge.py` | 9 files (missing 2) |
| `src/data/news_sources/` | `tiingo_provider.py` | 6 files (missing 1) |
| `src/utils/` | `data_manager.py`, `audit_logger.py` | 9 files (missing 2) |
| `src/data/` | — | 15 files; disk has 14 (multi_source_factory, news_aggregator, warmup deleted) |

**Action:** Engineer should update SYSTEM_MAP.md to add: `feature_engineering.py`, `llm_bridge.py`, `tiingo_provider.py`, `data_manager.py`, `audit_logger.py`, and adjust data layer count to 14 (or list current files explicitly).

---

## 7. Backtest Validation

- **Command run:**  
  `python scripts/backtest_technical_library.py --tickers NVDA,AMD,TSM --start 2023-01-01 --end 2023-06-30 --no-llm`

- **Result:** Exit code 1. No price data loaded; script looked under `ROOT/data/stock_market_data` (hardcoded), not under `config/data_config.yaml` `data_sources.data_dir` (e.g. `C:/ai_supply_chain_trading/trading_data/stock_market_data`).

- **Verdict:** Backtest did **not** complete; failure cause is the hardcoded `data_dir` (see §5). No strategy or statistical assessment performed. After Engineer fixes data_dir to use config, re-run backtest and then Validator can assess results.

---

## 8. Summary

| Category | Result | Critical issues |
|----------|--------|-----------------|
| TECHNICAL_SPEC | PASS | — |
| ARCHITECTURE vs SYSTEM_MAP/disk | FLAG | ARCHITECTURE.md SignalEngine path and module names out of sync |
| T-1 safety (price/indicators) | PASS | — |
| T-1 safety (news) | **FAIL** | `news_engine.py:517` uses `d <= as_of` → same-day news |
| Data integrity / sources | PASS | — |
| CSV/Parquet dates | PASS | — |
| Config (min/max order) | PASS | — |
| Config (backtest data_dir) | **FAIL** | Hardcoded data_dir in backtest script |
| SYSTEM_MAP parity | FLAG | 5 files on disk not listed; data count stale |
| Backtest run | Not completed | Blocked by data_dir |

**Required before considering validation complete:**

1. **Engineer:** Change news article filter to T−1: `d < as_of` in `src/signals/news_engine.py:517` (or document and get approval for same-day news).  
2. **Engineer:** Use config for backtest `data_dir` in `scripts/backtest_technical_library.py` (e.g. from `load_config()["data_dir"]`).  
3. **Engineer:** Update SYSTEM_MAP.md for new/missing files and data layer count.  
4. **Architect:** Align ARCHITECTURE.md with SYSTEM_MAP and disk (SignalEngine path, regime, sizing, execution module names).

Validator did not change architecture, stacks, or core execution logic; only audited and reported.
