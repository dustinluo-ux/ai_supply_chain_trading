# Data Source Toggle Logic

**Question:** Where does “use historical if available, else download recent” live, and how is it configured?  
**Verification date:** 2026-01-29  

---

## 1. Where the Toggle Exists

There is **no single “UnifiedDataProvider”** in the codebase. Toggle behavior is achieved by **entry point + config + which module loads data**:

| Layer | Location | Role |
|-------|----------|------|
| **System 2 warm-up** | `src/data/warmup.py` | Implements “historical first, then recent, then merge”. |
| **System 1** | `test_signals.py` + `UniverseLoader` + `config/data_config.yaml` | Always uses historical CSVs from `data/stock_market_data/`; no runtime toggle for live. |
| **Config** | `config/data_config.yaml` (System 1), `config/config.yaml` (System 2) | Data dirs and date ranges; no single “use_live” flag. |

So:

- **Warmup (System 2):** `src/data/warmup.py` is where “use historical if available, else download recent” is implemented.
- **UnifiedDataProvider:** Not present; the two systems use different loaders (UniverseLoader + CSV vs warmup + parquet/yfinance).
- **Configurable?** Yes via:
  - **Config files:** `data_config.yaml` (`data_dir`, `date_range`) for System 1; `config.yaml` (`data.date_range`, etc.) for System 2.
  - **Runtime:** `warm_up(..., use_recent=True/False)` in code; `run_e2e_pipeline.py --no-warmup` to skip warm-up.

---

## 2. Warmup Logic (System 2)

Implemented in `src/data/warmup.py`:

1. **`load_historical(tickers, start_date, end_date, data_dir)`**  
   - `data_dir` default: `data/prices`.  
   - Reads `{ticker}.parquet` per ticker; returns only tickers that have a parquet file and valid data in range.  
   - If a ticker has no parquet or empty result, it is simply omitted from the returned dict (no download here).

2. **`fetch_recent_yfinance(tickers, last_n_days)`**  
   - Fetches last N calendar days from yfinance.  
   - Independent of historical; can return data even when historical is missing.

3. **`warm_up(tickers, start_date, end_date, last_n_days=30, data_dir=..., use_recent=True)`**  
   - Calls `load_historical(...)`.  
   - If `use_recent=True`, calls `fetch_recent_yfinance(...)` and then `merge_historical_recent(historical, recent)`.  
   - Per-ticker: if only historical exists → use historical; if only recent exists → use recent; if both → merge (dedupe dates, keep last).  
   - So: **use historical when available, add/fill with recent when requested.**

**Scenario summary:**

- **Scenario A – Historical only (2020–2022):** Put parquet in `data/prices/` and call `warm_up(..., use_recent=False)`. Only historical is used.
- **Scenario B – Recent only (2023+):** No (or empty) parquet; `load_historical` returns nothing for that ticker; `fetch_recent_yfinance` returns data; merged result is recent-only.
- **Scenario C – Gap / bridge:** Historical parquet exists but ends before desired end date; `use_recent=True` fetches last N days and merge fills the gap.

---

## 3. System 1 vs System 2 Data Paths (No Conflict)

| System | Price data location | Format | Writes? |
|--------|----------------------|--------|--------|
| **System 1** | `data/stock_market_data/` (subdirs: nasdaq/csv, sp500/csv, etc.) | CSV | No (read-only in backtest) |
| **System 2** | `data/prices/` | Parquet | Yes (warmup can write via `heal_append`) |

- System 1 does not use `data/prices/`.  
- System 2 does not use `data/stock_market_data/`.  
- No overwrites between the two systems.

---

## 4. Config and Runtime Flags

- **Historical vs recent (System 2):**
  - **Config:** `config/config.yaml` → `data.date_range` (start/end) used by E2E for warm-up range.
  - **Runtime:** `warm_up(..., use_recent=True|False)`; `run_e2e_pipeline.py --no-warmup` skips warm-up entirely.
- **System 1:** No “use live” toggle; it always uses `data_config.yaml` and CSV dir (historical only in practice).

---

## Summary

- **Toggle implementation:** In `src/data/warmup.py` (load historical → optionally fetch recent → merge).  
- **UnifiedDataProvider:** Does not exist; each system uses its own data path and loader.  
- **Config:** Separate YAML files per system; warm-up behavior further controlled by `use_recent` and `--no-warmup`.  
- **Conflict:** None; System 1 uses CSVs in `data/stock_market_data/`, System 2 uses `data/prices/*.parquet` and live APIs.
