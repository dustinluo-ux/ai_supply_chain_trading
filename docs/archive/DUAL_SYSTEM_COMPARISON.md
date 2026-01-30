# Dual System Comparison

Side-by-side overview of System 1 (AI Supply Chain Backtest) and System 2 (Multi-Source Quant Pipeline).  
**Verification date:** 2026-01-29  

---

| Aspect | System 1 (AI Supply Chain) | System 2 (Multi-Source) |
|--------|----------------------------|--------------------------|
| **Purpose** | Historical backtesting of AI supply chain stock selection | Live/recent data trading with multiple data sources |
| **Entry point** | `test_signals.py` | `run_weekly_rebalance.py`, `run_e2e_pipeline.py` |
| **Data sources** | Historical CSVs (`data/stock_market_data/`), cached news (`data/news/`), Gemini cache | Historical parquet (`data/prices/`), yfinance, IBKR, Tiingo, Marketaux |
| **Signal type** | Gemini AI supply chain + technical + news (combined ranking) | Generic quant signals (technical-only or full_with_news via SignalCombiner) |
| **Universe** | 45 stocks → top 15 AI (supply chain ranking via UniverseLoader) | Configurable (warm-up ticker list + SignalCombiner top N) |
| **News analysis** | Gemini (cached), FNSPID-style news JSON | Tiingo + Marketaux (dual-stream), live or cached |
| **Execution** | Backtest only (inline in test_signals.py) | Can trade live (IBKR) or dry-run (mock) |
| **Use case** | Strategy validation, research, November 2022 (or configurable) backtest | Production-style weekly rebalance, E2E pipeline test |
| **Config** | `config/data_config.yaml` | `config/config.yaml`, `config/trading_config.yaml` |
| **Log/output** | `outputs/backtest_log_*.txt` | `logs/ai_supply_chain_*.log`, `data/signals/` |
| **Price storage** | Read-only CSVs in `data/stock_market_data/` | `data/prices/*.parquet` (read/write via warmup/heal) |

---

## Quick Reference

- **Run System 1:** `python test_signals.py --universe-size 15 --top-n 10`
- **Run System 2 (dry-run):** `python run_weekly_rebalance.py --dry-run` or `python run_e2e_pipeline.py`
- **Run System 2 (live):** Set `trading_config.yaml` → `executor: ib`, then `python run_weekly_rebalance.py --live`

Both systems can coexist; they use different data dirs and entry points and do not overwrite each other.
