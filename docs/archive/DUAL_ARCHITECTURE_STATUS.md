# Dual Architecture Status (Master)

**Purpose:** Single place to answer whether both systems coexist, whether System 1 is still intact, how data toggling works, and what the recommended usage is.  
**Verification date:** 2026-01-29  

---

## Can both systems coexist without conflicts?

**Yes.**  

- **Data:** System 1 uses `data/stock_market_data/*.csv` (read-only in backtest). System 2 uses `data/prices/*.parquet` and live APIs. No shared write target; no overwrites.
- **Entry points:** System 1 = `test_signals.py`; System 2 = `run_weekly_rebalance.py`, `run_e2e_pipeline.py`. Different scripts, different configs.
- **Logs:** System 1 → `outputs/backtest_log_*.txt`; System 2 → `logs/ai_supply_chain_*.log`. Separate dirs.
- **Cache:** Both can use `data/cache/` (e.g. Gemini); shared read is fine; no conflict.

You can run System 1 and System 2 sequentially or in parallel (e.g. different terminals) without breaking either.

---

## Is System 1 (AI supply chain) still functional after System 2 additions?

**Yes.**  

- **Entry point:** `test_signals.py` still runs independently; it does not import System 2 entry points or warmup.
- **Data:** Still uses `config/data_config.yaml` and `data/stock_market_data/` (CSVs) and `data/news/`; no dependency on `data/prices/` or warmup.
- **Supply chain ranking:** UniverseLoader with `rank_by_supply_chain=True` and supply_chain_pool_size is unchanged; 45 → top 15 flow is intact.
- **Fixes:** AAL word-boundary fix in `llm_analyzer.py` and post-process filter in `supply_chain_scanner.py` are present. NVDA/AMD/TSM can be in the universe if their CSVs exist in the configured data dir.
- **Backtest:** Inline backtest in test_signals.py still produces technical_only, news_only, and combined Sharpe ratios.

Adding System 2 did not remove or break System 1’s flow.

---

## How do you toggle between historical and live data?

- **System 1:** No toggle; it always uses historical CSVs and cached news (backtest only).
- **System 2:**  
  - **Historical:** Parquet in `data/prices/`; optionally `warm_up(..., use_recent=False)` or E2E with `--no-warmup` if you only need pre-built signals.  
  - **Recent/live:** `warm_up(..., use_recent=True)` (default in E2E) pulls last N days from yfinance; for live trading set `trading_config.yaml` → `executor: ib` and run `run_weekly_rebalance.py --live`.

So: “historical vs live” is **only** in System 2, via warmup flags and executor config; System 1 is always historical.

---

## Are there any architectural issues or redundancies?

**No major issues.**  

- **No duplicate “data provider” or “signal combiner”:** One SignalCombiner used by both; different data loaders (UniverseLoader vs warmup) for different paths.
- **Config:** Separate files per system; shared only where intended (e.g. signal weights). No naming conflicts.
- **Redundancy:** Some shared code (SignalCombiner, technical/ML utils) is intentional reuse, not redundancy.

---

## What’s the recommended usage pattern?

- **Strategy research / backtest (AI supply chain, 2020–2022 style):**  
  Use **System 1:** `python test_signals.py --universe-size 15 --top-n 10`. Ensure `data/stock_market_data/` and `data/news/` are populated; use `data_config.yaml` for data dir and universe.

- **Weekly rebalance / live or recent data:**  
  Use **System 2:**  
  - Ensure `data/prices/` has parquet (or let warm-up fetch recent via yfinance).  
  - Ensure `data/signals/` has technical (and optionally sentiment/supply chain) inputs for SignalCombiner.  
  - Dry-run: `python run_weekly_rebalance.py --dry-run` or `python run_e2e_pipeline.py`.  
  - Live: set `trading_config.yaml` → `executor: ib`, then `python run_weekly_rebalance.py --live`.

- **Running both:** Safe to run `test_signals.py` and `run_weekly_rebalance.py` (or E2E) in the same repo; use different terminals or schedules. They do not overwrite each other’s data or logs.

---

## Critical questions answered

| # | Question | Answer |
|---|----------|--------|
| 1 | Did adding System 2 break System 1’s AI supply chain ranking? | No. System 1 still uses UniverseLoader, supply chain ranking, and CSV/news data. |
| 2 | Is NVDA/AMD/TSM fix still intact in System 1? | Yes. Universe is built from all valid CSVs in data_dir; no “A-only” filter. AAL fix (word boundary + post-process) is in llm_analyzer and supply_chain_scanner. |
| 3 | Can System 1 still run backtests independently? | Yes. `python test_signals.py --universe-size 15 --top-n 10` runs without System 2. |
| 4 | Does the data toggle work as described (historical first, then recent)? | Yes, in System 2: `warmup.warm_up()` loads historical from parquet, then optionally fetches recent from yfinance and merges. |
| 5 | Are there any naming conflicts or data overwrites? | No. Different data dirs (stock_market_data vs prices), different log dirs (outputs vs logs), shared cache is read-friendly. |
| 6 | Can both systems use the same ML models and technical indicators? | Yes. They share `src/signals` (e.g. SignalCombiner, technical indicators) and `src/utils`; only data source and entry point differ. |

---

## Reference docs

- **System 1:** [SYSTEM1_VERIFICATION.md](SYSTEM1_VERIFICATION.md)  
- **System 2:** [SYSTEM2_VERIFICATION.md](SYSTEM2_VERIFICATION.md)  
- **Data toggle:** [DATA_TOGGLE_LOGIC.md](DATA_TOGGLE_LOGIC.md)  
- **Overlap:** [ARCHITECTURE_OVERLAP.md](ARCHITECTURE_OVERLAP.md)  
- **Config:** [SYSTEM_TOGGLE_CONFIG.md](SYSTEM_TOGGLE_CONFIG.md)  
- **Comparison:** [DUAL_SYSTEM_COMPARISON.md](DUAL_SYSTEM_COMPARISON.md)  

**Status:** Both systems are verified to coexist; System 1 remains functional; data toggle and config are documented; no architectural conflicts or redundancies identified. Recommended usage is System 1 for backtest, System 2 for weekly rebalance and live/recent data.
