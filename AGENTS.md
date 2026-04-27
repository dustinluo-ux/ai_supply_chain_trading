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

## Quarterly fundamentals (FMP + semi-valuation + Edgar)

**Source:** `scripts/fetch_quarterly_fundamentals.py` writes `trading_data/fundamentals/quarterly_signals.parquet` (atomic `.tmp` → validate → replace). With `FMP_API_KEY` set, pulls FMP income / balance / cash flow (20 quarters), caches raw JSON per ticker under `fundamentals/fmp_raw_{TICKER}.parquet`, then runs `SemiValuationEngine` (`src/fundamentals/semi_valuation.py`) and optional SEC checks.

**FCFF (engine view):** Layer 2 uses **`fcff_adjusted`** from that parquet (cross-sectionally ranked after forward-fill). Pipeline definition (Decimal math in code): **`fcff_raw`** = after-tax EBIT + D&A + SBC − capex − ΔNWC; **`fcff_adjusted`** = `fcff_raw` + SBC − R&D expense + R&D amortization from a 5-year straight-line schedule on quarterly R&D (treats R&D as investment-like).

**R&D capitalization:** Each quarter’s R&D is amortized over 20 quarters at 1/20 per quarter (20%/year on the cohort). **`rd_cap_variance_pct`** = |`fcff_adjusted` − `fcff_raw`| / |`fcff_raw`| (NaN if `fcff_raw` = 0). High variance flags model uncertainty around R&D treatment.

**When Edgar audit runs:** If any quarter has **`needs_edgar_audit`** (internal to the fetch path) because `rd_cap_variance_pct` > 15%, the script calls `audit_ticker` (`src/data/edgar_audit.py`) for the latest fiscal year and sets **`edgar_audit_flag`** = True only if both R&D and SBC variances vs 10-K XBRL are under 15%; otherwise False (or conservative default on error).

**Layered engine wiring:** `src/signals/layered_signal_engine.py` — L2 includes `fcff_adjusted` and **`rd_cap_variance_pct_neg`** (negative `rd_cap_variance_pct` so higher variance ranks like other “bad is low” inputs). L1 includes **`edgar_audit_flag`**: when the flag is **False** (audit failed or errored), the combined L1 multiplier is scaled by **`quality_audit.edgar_audit_cap`** (default `0.5` in `config/layered_signal_config.yaml`). Missing column defaults to True (no cap). *Note:* if you intended “cap when True”, invert the `l1_edgar_audit_multiplier` line in that module.

**Refresh command (wealth Python):**

```text
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\fetch_quarterly_fundamentals.py
```

Set `EDGAR_IDENTITY` or `EDGAR_EMAIL` in `.env` for SEC user-agent when audits run.

---

## Workflow Rules (Cursor Agents)

- Cursor does all real code work. Codex does planning/Cursor prompts only.
- Three Cursor agents: **Architect** → **Engineer** → **Validator**
- Every Cursor prompt opens with: "Reference INDEX.md and maintain Evidence Discipline for this task."
- Per-repo canon: Pulse/Auditor → `ai_supply_chain_trading/docs/INDEX.md`

---

## Smoke Test

```bash
python scripts/run_optimizer.py --n-trials 2 --skip-data
```

Expected: two trials, optimizer_results.json written, strategy_params.yaml promoted, schtasks registered. Exit 0.
