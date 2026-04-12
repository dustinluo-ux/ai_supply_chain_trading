## Development Environment

- **Python Interpreter**: Always use the Anaconda environment named `wealth`.
- **Environment Path**: `C:\Users\dusro\anaconda3\envs\wealth`
- **Python Executable**: `C:\Users\dusro\anaconda3\envs\wealth\python.exe`
- **Activation Command**: `conda activate wealth`
- **Rule**: When running scripts or installing packages, use the absolute python path above.

---

## Canonical Data Location

All trading data lives **outside the repo** at: `C:\ai_supply_chain_trading\trading_data\`

- Price CSVs: `trading_data\stock_market_data\{nasdaq,sp500,nyse,forbes2000}\csv\`
- News JSON (Marketaux): `trading_data\news\{ticker}_news.json`
- Tiingo parquets: `trading_data\news\tiingo_{YYYY}_{MM}.parquet`
- Env var: `DATA_DIR=C:\ai_supply_chain_trading\trading_data` (set in `.env`)

---

## MVP Architecture (as of 2026-04-12)

The system is an autonomous end-to-end trading pipeline. No manual steps required between data refresh and config promotion.

### Pipeline Chain

```
run_e2e_pipeline.py
  Stage 1: update_price_data + update_news_data       (--skip-data to bypass)
  Stage 2: run_factory  → rolling 4yr training window → factory_winner.json
  Stage 3: OOS backtest → e2e_oos_backtest.json
  Stage 4: run_execution (mock or paper)              → last_valid_weights.json
  Stage 5: ASCII summary + STATUS: PASS/WARN/FAIL + exit code
```

### IBKR Live Integration (paper/live mode)

```
run_execution.py --mode paper --ibkr-port 7497
  1. contract_resolver.resolve(symbol, type, ib)  → typed IB contract
     - equity  → ib_insync.Stock (SMART/USD)
     - future  → front-month Future (NQ multiplier=20, MNQ multiplier=2)
     - option  → nearest-DTE Option (SMH, ATM strike, right=C/P)
  2. ibkr_live_provider.get_live_prices(ib, contracts)
     → snapshot prices; fallback to 1-day historical if market closed
  3. ibkr_live_provider.get_account_summary(ib)
     → net_liquidation, available_funds, maint_margin_req, init_margin_req
  4. Overlay live prices on last bar of prices_dict (keeps history for signals)
  5. Use net_liquidation as portfolio NAV for sizing
  6. Intent.futures_multipliers passed to position_manager
     → quantity = delta_dollars / (price × multiplier) for futures
  7. --confirm-paper submits real orders via IBExecutor
     → fills written to outputs/fills/fills.jsonl
     → --check-fills queries IB for open order status
```

### Instrument Config

`config/instruments.yaml` — all tradeable instrument definitions:
- `equities` — exchange, currency; `use_watchlist: true` pulls from data_config
- `futures` — NQ (×20), MNQ (×2); roll_warning_dte, front_month_offset
- `options` — SMH; expiry_dte_target=30, strike_atm_offset=0 (ATM)
- `allocation_limits` — max_futures_pct: 0.20, max_options_pct: 0.10

### Optimizer Loop

```
run_optimizer.py  (random search over optimizer_config.yaml search_space)
  → N trials of run_e2e_pipeline.py --skip-model
  → composite score: 0.5×Sharpe + 0.3×CAGR + 0.2×(1 - abs(maxDD))
  → optimizer_results.json  (atomic write)
  → run_promoter.py  → strategy_params.yaml  (atomic write, .bak preserved)
  → schtasks  (registers next Monday 06:00 re-run automatically)
```

### Key Config Files

| File | Purpose |
|------|---------|
| `config/optimizer_config.yaml` | **Master tuning manifest** — `search_space` (varied per trial), `fixed_params` (all other tunable dimensions: news_weight, max_single_position_weight, master_score_weights, etc.), `composite_weights` (scoring formula) |
| `config/model_config.yaml` | Training/OOS window (machine-written by rolling patch — do not edit) |
| `config/strategy_params.yaml` | Promoted winner params (written by run_promoter) |
| `config/trading_config.yaml` | Execution settings (values also documented in optimizer_config fixed_params) |
| `config/technical_master_score.yaml` | Indicator definitions and category weights (values also in fixed_params) |

### Rolling Training Window

`run_factory.py` calls `_patch_model_config_training_window(config_path, train_years)` before every factory run.
Formula: `train_start = today − 4yr`, `train_end = today − 365d`, `test_start = train_end`, `test_end = today`.
`model_config.yaml` is machine-written from this point — never edit dates by hand.

### Max Single Position Cap

Hard cap enforced post-normalization in `src/core/portfolio_engine.py`:
- `hrp_alpha_tilt` — `max_single_weight` param (default 0.40)
- `_build_inverse_atr` — same clamp after TES renorm
- Source: `config/trading_config.yaml` → `risk.max_single_position_weight`

### News Data Policy

- **2025-present (live)**: Tiingo via `TiingoProvider` — real publication dates, valid signal
- **Pre-2025 (training)**: No usable historical news. `news_supply` and `news_sentiment` features default to **0.5** (neutral)
- Marketaux flat files remain the operational news source for live weekly rebalance

---

## Workflow Rules (Cursor Agents)

- Cursor does all real code work. Claude Code does planning/Cursor prompts only.
- Three Cursor agents: **Architect** → **Engineer** → **Validator**
- Every Cursor prompt opens with: "Reference INDEX.md and maintain Evidence Discipline for this task."
- Per-repo canon: Pulse/Auditor → `ai_supply_chain_trading/docs/INDEX.md`

---

## Smoke Test

```bash
python scripts/run_optimizer.py --n-trials 2 --skip-data
```

Expected: two trials, optimizer_results.json written, strategy_params.yaml promoted, schtasks registered. Exit 0.
