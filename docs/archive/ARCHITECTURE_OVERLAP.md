# Architecture Overlap: Shared vs Isolated Components

**Purpose:** Clarify what is shared between System 1 (AI Supply Chain Backtest) and System 2 (Multi-Source Quant Pipeline) and what is isolated.  
**Verification date:** 2026-01-29  

---

## 1. Duplicate Components?

**No true duplicates.** Both systems reuse the same libraries where it makes sense; differences are in **entry point, data source, and execution**:

| Concern | System 1 | System 2 | Duplicate? |
|---------|----------|-----------|------------|
| **Data provider** | UniverseLoader + CSV paths from `data_config.yaml` | warmup.py + parquet + yfinance/IBKR/Tiingo | No – different modules and paths |
| **Signal combiner** | SignalCombiner() (default data_dir="data") | SignalCombiner(data_dir="data", output_dir="data/signals") | No – same class, different callers and input data |
| **News** | NewsAnalyzer, Gemini cache, data/news JSON | DualStreamNewsAggregator, Tiingo/Marketaux, live | No – same news analyzer possible, but S2 can use live aggregator |
| **Execution** | Inline backtest (no live orders) | ExecutorFactory + PositionManager, dry-run or live | No – S1 has no executor; S2 has executor layer |

So: one data path for S1 (CSV), one for S2 (parquet + APIs); one SignalCombiner used by both; no second “signal combiner” or “data provider” doing the same job.

---

## 2. Naming and Config Conflicts

- **Config files:**  
  - System 1: `config/data_config.yaml` (data_dir, universe, news dir).  
  - System 2: `config/config.yaml`, `config/trading_config.yaml`.  
  No shared config file that would force one system to override the other.

- **Cache dirs:**  
  - Both may use `data/cache/` (e.g. Gemini, news analyzer).  
  Shared cache is intentional (e.g. reuse Gemini results); no overwrite of each other’s backtest vs live data.

- **Output dirs:**  
  - System 1: backtest log → `outputs/backtest_log_*.txt`.  
  - System 2: `setup_logger()` → `logs/ai_supply_chain_YYYYMMDD.log`; signals under `data/signals/`.  
  Different directories; no conflict.

- **Log files:**  
  - System 1: custom stdout redirect to `outputs/backtest_log_*.txt`.  
  - System 2: `logs/` via `setup_logger()`.  
  Separate; no naming conflict.

---

## 3. Shared vs Isolated Components

**Shared (reused by both):**

- **ML / technical / utils:** e.g. technical indicator code, ML models under `src/models/`, `src/utils/` (logger, ticker_utils, etc.).
- **SignalCombiner:** Same class; S1 uses it inside backtest with preloaded data; S2 uses it with `data/` signal files (technical_indicators.parquet, etc.).
- **News/sentiment building blocks:** e.g. sentiment analyzer, Gemini analyzer; S2 can also use dual-stream news and different data sources.
- **Config:** Shared use of `config/signal_weights.yaml` (or weights in config.yaml) for combiner weights.

**Isolated (per system):**

- **Entry points:** S1 → `test_signals.py`; S2 → `run_weekly_rebalance.py`, `run_e2e_pipeline.py`.
- **Data providers:** S1 → UniverseLoader + CSV dir; S2 → warmup + parquet + IBKR/Tiingo/Marketaux/yfinance.
- **Execution layer:** S1 → inline backtest only; S2 → ExecutorFactory, PositionManager, dry-run/live.
- **Universe building:** S1 → UniverseLoader with supply chain ranking from CSV universe; S2 → typically fixed or config-driven ticker list for warm-up, then SignalCombiner top-N.

---

## 4. Test Independence (Run Order and Conflicts)

- **Run test_signals.py (System 1) only:**  
  Uses `data/stock_market_data/`, `data/news/`, `data/cache/`, writes `outputs/backtest_log_*.txt`.  
  Does not touch `data/prices/`, `run_weekly_rebalance.py`, or `run_e2e_pipeline.py`.  
  **Does not break System 2.**

- **Run run_e2e_pipeline.py or run_weekly_rebalance.py (System 2) only:**  
  Uses `data/prices/`, `data/signals/`, `config/config.yaml`, `config/trading_config.yaml`, writes to `logs/`.  
  Does not modify `data/stock_market_data/` or `test_signals.py` flow.  
  **Does not break System 1.**

- **Separate resources:**
  - **Logs:** S1 → `outputs/backtest_log_*.txt`; S2 → `logs/ai_supply_chain_*.log`.
  - **Cache:** Both can use `data/cache/` (e.g. Gemini); same cache dir, different use cases (backtest vs live prep).
  - **Outputs:** S1 → `outputs/`; S2 → rebalance results in logs and optional execution; signal outputs in `data/signals/`.

So both systems can run **sequentially or in parallel** (e.g. different terminals) without overwriting each other’s data or breaking either flow.

---

## Summary Table

| Component | Shared | Isolated (S1) | Isolated (S2) |
|-----------|--------|----------------|----------------|
| Entry point | — | test_signals.py | run_weekly_rebalance.py, run_e2e_pipeline.py |
| Data loader | — | UniverseLoader + data_config | warmup + config.yaml |
| Price storage | — | data/stock_market_data/*.csv | data/prices/*.parquet |
| SignalCombiner | Yes | — | — |
| Technical/ML/utils | Yes | — | — |
| Execution | — | Inline backtest | ExecutorFactory, PositionManager |
| Logs | — | outputs/backtest_log_*.txt | logs/*.log |
| Config | signal_weights | data_config.yaml | config.yaml, trading_config.yaml |

No architectural redundancy: one combiner, one set of indicators/utils, two clear data and execution paths.
