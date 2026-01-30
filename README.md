# AI Supply Chain Thematic Trading System

A quantitative trading system that uses LLM analysis and technical signals (Master Score) to identify AI supply chain beneficiaries and generate weekly trading signals.

---

## Quick Start

```bash
pip install -r requirements.txt
# Create .env from .env.example; add TIINGO_API_KEY, MARKETAUX_API_KEY, GOOGLE_API_KEY (or GEMINI_API_KEY)
```

**Backtest (Master Score, technical-only):**
```bash
python scripts/backtest_technical_library.py --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3 --start 2022-01-01 --end 2022-12-31
```

**Weekly rebalance (dry-run):**
```bash
python run_weekly_rebalance.py --dry-run
```

**Test signals (Master Score + optional news):**
```bash
python test_signals.py
```

---

## Project Structure

```
ai_supply_chain_trading/
├── config/
│   ├── data_config.yaml          # Data dir, universe, news
│   ├── technical_master_score.yaml  # Master Score category weights, rolling window
│   └── signal_weights.yaml       # Composite (news + technical) weights
├── data/
│   ├── stock_market_data/        # CSV price data (nasdaq/csv, sp500/csv, nyse/csv, forbes2000/csv)
│   ├── news/                     # JSON news per ticker
│   └── cache/                    # Gemini cache, etc.
├── src/
│   ├── signals/
│   │   ├── technical_library.py  # Master Score (calculate_all_indicators, compute_signal_strength)
│   │   ├── signal_combiner.py    # Composite score
│   │   └── ...                   # News, sentiment, supply chain
│   ├── execution/                # IB execution (exists; not in default path)
│   └── ...
├── scripts/
│   └── backtest_technical_library.py  # Master Score backtest (next-day open, inverse-vol, kill-switch)
├── docs/
│   ├── ARCHITECTURE.md           # Data flow, pillars, paths
│   ├── TECHNICAL_SPEC.md         # Master Score, indicator math, signal combination
│   ├── BACKTEST_JOURNAL.md       # Backtest assumptions, safety, results
│   └── archive/                  # Older / redundant docs
├── outputs/                      # Backtest logs
└── logs/                         # Application logs
```

---

## Documentation (Rule-Enforced)

| Doc | Purpose |
|-----|--------|
| **docs/ARCHITECTURE.md** | Target architecture, data flow (ingest → execution), key paths, pillars. |
| **docs/TECHNICAL_SPEC.md** | Master Score (source of truth for technical signals), normalization, category weights, composite/portfolio logic. |
| **docs/BACKTEST_JOURNAL.md** | Execution timing, friction, sizing, kill-switch, safety audits, path-dependency safeguards, how to run, results. |

All other technical notes and assumptions are consolidated into these three files. Older docs are in `docs/archive/`.

---

## Areas to Be Completed

- **Ticker Sensitivity:** Systematic tests across ticker universes and top-N to assess robustness.
- **Weight Optimization:** Tune category weights in `config/technical_master_score.yaml` (and composite weights) with out-of-sample or walk-forward validation.

---

## Status

- ✅ Phase 1: Data infrastructure
- ✅ Phase 2: Signal generation (Master Score + news)
- ✅ Phase 3: Backtesting (Technical Library backtest with friction, next-day open, inverse-vol, kill-switch)
- ⏳ Phase 4: Production & paper trading (IB code exists; not wired in default path)

---

## License

[Your License Here]
