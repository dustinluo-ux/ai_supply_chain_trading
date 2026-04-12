# PROJECT STATUS — Current State & Readiness Assessment

**Last Updated:** 2026-04-12
**Project:** AI Supply Chain Quantitative Trading System
**Phase:** MVP Complete — Autonomous E2E Pipeline Operational

---

## Executive Summary

**Autonomous quantitative trading pipeline** — dynamically imports price + news data, trains a rolling ML model, runs OOS backtest, constructs a portfolio with risk controls, and self-optimizes parameters on a weekly schedule without manual intervention.

**Current status:** MVP operational. The full chain from raw data to promoted config runs unattended:
`run_optimizer.py` → random search → `run_e2e_pipeline.py` (5 stages) → `run_promoter.py` → `strategy_params.yaml` → Windows Task Scheduler re-arms for next week.

**OOS backtest result (smoke test, 2-trial run):** Sharpe ~0.44–0.47, composite score ~0.71–0.82. Trials completed with STATUS: PASS.

**Operating mode:** MVP Phase — optimization loop is live; paper/live IBKR execution is next gate.

---

## What Works ✅

### Core Research Infrastructure

**Canonical workflow (fully implemented):**
1. ✅ Load & validate data (prices, news, SPY benchmark)
2. ✅ Build signals (Master Score via `technical_library.py`)
3. ✅ News overlay (FinBERT + spacy EventDetector, 4 strategies)
4. ✅ Regime detection (3-state HMM: BULL/BEAR/SIDEWAYS)
5. ✅ Policy gates (CASH_OUT, sideways scaling, daily exits)
6. ✅ Portfolio construction (inverse-volatility sizing)
7. ✅ Execution simulation (Next-Day Open, 15 bps friction)
8. ✅ Performance metrics (Sharpe, total return, max drawdown)

**Entry points:**
- ✅ `scripts/run_e2e_pipeline.py` — canonical single-run E2E (5 stages: data→factory→backtest→execute→summary)
- ✅ `scripts/run_optimizer.py` — autonomous random-search optimizer (N trials → promote → schedule)
- ✅ `scripts/run_promoter.py` — atomic config promotion (winner → strategy_params.yaml)
- ✅ `scripts/run_factory.py` — ML model factory with rolling window patch
- ✅ `scripts/backtest_technical_library.py` — standalone OOS backtest engine
- ✅ `scripts/run_execution.py` — portfolio execution (mock/paper/live); supports --no-hedge
- ✅ `scripts/run_weekly_rebalance.py` — standalone weekly rebalance (legacy entry point)

**E2E Pipeline + Optimizer — COMPLETE.** Full chain from data refresh to config promotion runs autonomously. Optimizer composite scoring: `0.5×Sharpe + 0.3×CAGR + 0.2×(1 - |maxDD|)`. Winner params written atomically to `strategy_params.yaml`; schtasks registers next weekly run.

**Execution Bridge: Mock Verification — COMPLETE.** Spine produces validated orders (BUY/SELL with non-zero quantities) using last-close price injection. Implementation: `scripts/run_execution.py` builds a last-close Series from `prices_dict` and passes it as `prices` into `PositionManager.calculate_delta_trades` (see DECISIONS.md D018).

**Dynamic weighting modes:**
- ✅ Fixed (static category weights)
- ✅ Regime (HMM-based: BULL_WEIGHTS/DEFENSIVE_WEIGHTS/SIDEWAYS_WEIGHTS)
- ✅ Rolling (PyPortfolioOpt: max_sharpe or HRP)
- ✅ ML (Scikit-Learn RF + TimeSeriesSplit CV)

### Data Layer

**Price data:**
- ✅ Historical CSV files in `data/stock_market_data/{nasdaq,sp500,nyse,forbes2000}/csv/`
- ✅ Multi-source support: FNSPID/Polygon (legacy), Tiingo/yfinance/Marketaux (new)
- ✅ Self-healing: `warmup.py` merges historical + last 30 days, appends new data

**News data:**
- ✅ JSON files in `data/news/{ticker}_news.json`
- ✅ Dual-stream: Marketaux + Tiingo
- ✅ Deduplication: Levenshtein fuzzy matching (ratio > 0.85)

**Benchmark:**
- ✅ SPY data for regime detection and kill-switch
- ✅ Generators: `download_spy_yfinance.py` (network) or `generate_spy_placeholder.py` (offline)

### Signal Generation

**Technical Master Score:**
- ✅ Module: `src/signals/technical_library.py`
- ✅ Categories: Trend 40%, Momentum 30%, Volume 20%, Volatility 10%
- ✅ Normalization: Bounded (static), Unbounded (rolling 252-day min-max)
- ✅ No look-ahead: Strict enforcement

**News Alpha (4 strategies):**
- ✅ Strategy A: Buzz (volume z-score)
- ✅ Strategy B: Surprise (sentiment delta with 1-day lag baseline)
- ✅ Strategy C: Sector Relative (cross-sectional ranking)
- ✅ Strategy D: Event-Driven (spacy NER + phrase matching)
- ✅ Composite: Weighted average, normalized to [0,1]

**Blending:**
- ✅ Default: 80% technical + 20% news (configurable via `news_weight`)

### Regime & Policy

**3-State Regime (hmmlearn):**
- ✅ States: BULL (high mean, low vol), BEAR (low mean, high vol), SIDEWAYS (mean~0)
- ✅ Mapping: By mean return (highest=BULL, lowest=BEAR, middle=SIDEWAYS)
- ✅ Transition matrix: Fitted via Baum-Welch EM (logged on first Monday)
- ✅ Fallback: SPY vs 200-SMA if HMM fails

**Policy gates:**
- ✅ CASH_OUT: Dual-confirmation (BEAR + SPY < 200-SMA)
- ✅ Sideways scaling: Position × 0.5
- ✅ Daily risk exit: Exit if return ≤ threshold (no reallocation)

### Backtesting

**Execution model:**
- ✅ Weekly rebalance (Mondays)
- ✅ Next-Day Open execution (no look-ahead)
- ✅ Transaction costs: 15 bps per trade
- ✅ Inverse-volatility sizing (ATR from T−1)
- ✅ Mid-week exits without reallocation

**Safety features:**
- ✅ Safety report (signal lag, mid-week exit, benchmark alignment)
- ✅ State logging: `[STATE]` shows Regime/News/Action
- ✅ HMM diagnostics: Transition matrix persistence check
- ✅ No-look-ahead verification

**Determinism & Parity Testing:**
- ✅ Backtest ↔ execution parity guard
  - Tolerance: **1e-12** (strict floating-point equality)
  - Ensures research and execution paths produce identical target weights
  - Test: `python scripts/test_execution_parity.py --date 2024-01-08`
- ✅ Regression snapshot lock
  - Snapshot: `contracts/target_weight_snapshot_2024-01-08.json`
  - First run creates snapshot, subsequent runs assert against it
  - Prevents unintended weight drift
  - Test: `python scripts/test_target_weight_regression.py`
- ✅ Deterministic dependency freeze
  - Pinned: `requirements.txt` with exact versions
  - Regenerate: `pip freeze > requirements.txt`
- ✅ Spine integrity check
  - Pre-commit gate: `./scripts/check_spine_integrity.sh`
  - Ensures canonical backtest produces identical outputs on two runs
  - Exit 0 = PASS, 1 = FAIL (do not merge)

### Configuration & Documentation

**Configs:**
- ✅ `config/optimizer_config.yaml` — **master tuning manifest**: `search_space` (varied per trial), `fixed_params` (all other tunable dimensions consolidated here), `composite_weights` (scoring formula — config-driven, no code edit needed)
- ✅ `config/model_config.yaml` — rolling training window (machine-written by factory patch — do not edit)
- ✅ `config/strategy_params.yaml` — auto-promoted winner params
- ✅ `config/trading_config.yaml` — execution settings (values mirrored in `fixed_params`)
- ✅ `config/technical_master_score.yaml` — indicator definitions; category weights mirrored in `fixed_params`
- ✅ `config/data_config.yaml` — data sources, paths, universe watchlist

**Canonical documentation (INDEX.md + 11 in docs/):**
- ✅ ARCHITECTURE.md — system design, data flow *(immutable: Proposal Review required before edits)*
- ✅ WORKFLOW.md — execution stages
- ✅ SYSTEM_MAP.md — code mapping (1:1 parity with src/ and canonical scripts)
- ✅ STRATEGY_LOGIC.md — decision rules
- ✅ STRATEGY_MATH.md — signal formulas *(immutable: Proposal Review required before edits)*
- ✅ DECISIONS.md — architectural decisions (ADR)
- ✅ TECHNICAL_SPEC.md — indicator math
- ✅ BACKTEST_JOURNAL.md — execution details, results
- ✅ PROJECT_STATUS.md — current state (this file)
- ✅ Design docs: GEMINI_BRIDGE_DESIGN.md, LIVE_EXECUTION_BRIDGE_DESIGN.md

**Status:** All canonical docs verified; SYSTEM_MAP and PROJECT_STATUS updated 2026-02-15 for Phase 2 and new files.

---

## What Doesn't Work ❌

### Critical Gaps for Production

**Live execution:**
- ✅ Orchestration: `scripts/run_execution.py` and `scripts/run_weekly_rebalance.py` (spine -> Intent -> delta trades -> optional IB paper submit)
- ✅ **Execution Bridge: Mock Verification — COMPLETE.** Spine generates validated BUY/SELL orders in dry-run; `run_execution.py` injects last-close prices from `prices_dict` into `PositionManager.calculate_delta_trades` so share quantities are non-zero and mock matches live path (see DECISIONS.md D018).
- ✅ IBKR: `ib_provider.py`, `ib_executor.py`, `ibkr_bridge.py` (AccountMonitor, OrderDispatcher, CircuitBreaker)
- ⚠️ Remaining: fill verification, order status tracking, scheduling (cron/APScheduler)

**Data feeds:**
- ❌ No real-time price streaming
- ❌ No live news ingestion
- ⚠️ Warm-up/self-healing implemented but not activated in weekly mode

**Risk management:**
- ✅ `max_single_position_weight: 0.40` enforced post-normalization in `portfolio_engine.py` (`hrp_alpha_tilt` + `_build_inverse_atr`)
- ⚠️ `min_order_size`, `max_position_size` in `trading_config.yaml` still not enforced in executor

**Scheduling:**
- ✅ Windows Task Scheduler auto-registered after each optimizer run (AITrading_WeeklyOptimizer, next Mon 06:00)

**Reconciliation:**
- ❌ No fill verification (expected vs actual positions)
- ❌ No order status tracking
- ❌ No duplicate-order guardrails

### Research Completeness

**Backtest coverage:**
- ⚠️ Limited historical validation
  - Full 2022: Completed (Sharpe −0.75, Total Return −33.64%)
  - Oct-Nov 2022: Completed (Sharpe 0.11, Total Return +14.94%)
  - Need: Multi-year validation (2020-2024)

**Statistical validation:**
- ❌ No confidence intervals
- ❌ No p-values or significance tests
- ❌ No Monte Carlo simulation
- ❌ No walk-forward analysis

**Parameter sensitivity:**
- Parameter sweep is implemented in `scripts/research_grid_search.py`. `run_parameter_sensitivity()` never existed in code; the doc reference was incorrect. Sweep is now fully wired: CLI flags, JSON output, and regime_stats (n_weeks, sharpe, max_drawdown per BULL/BEAR/SIDEWAYS) are all populated in `scripts/backtest_technical_library.py`.

### Known Technical Debt

**Memory system:**
- ⚠️ `regime_ledger` intended but not updated by canonical code
- ⚠️ Post-run memory limited to performance CSV and logs

**Phase 3 signal design:**
- ⚠️ Risk: If only `top_stocks_latest.csv` exists, same ranking reused every week (look-ahead)
- ✅ Mitigation: `run_technical_backtest.py` generates weekly signals in memory

**ML pipeline:**
- ⚠️ `src/models/` exists and configured but not wired to `run_phase*` or `run_strategy.py`

---

## Physical Folder Structure

### Top-Level Directories

| Path | Status | Purpose |
|------|--------|---------|
| `config/` | ✅ Present | YAML configurations |
| `data/` | ✅ Present | Prices, news, signals, cache (gitignored) |
| `docs/` | ✅ Present | Canonical + archived documentation |
| `logs/` | ✅ Present | Application logs |
| `outputs/` | ✅ Present | Backtest results |
| `backtests/` | ✅ Present | Backtest analysis |
| `scripts/` | ✅ Present | Utilities and canonical entry points |
| `src/` | ✅ Present | Core library |

### Source Code Modules

| Module | Status | Components |
|--------|--------|------------|
| `src/core/` | ✅ Canonical | policy_engine, portfolio_engine, target_weight_pipeline, intent, types (SignalEngine in signals/) |
| `src/signals/` | ✅ Complete | signal_engine, technical_library, news_engine, signal_combiner, weight_model, sentiment_propagator, performance_logger, metrics |
| `src/portfolio/` | ✅ Complete | position_manager, position_sizer |
| `src/execution/` | ✅ Complete | base_executor, mock_executor, ib_executor, executor_factory, **ibkr_bridge** (AccountMonitor, OrderDispatcher, CircuitBreaker, RiskManager, RebalanceLogic) |
| `src/data/` | ✅ Complete | price_fetcher, news_fetcher, ib_provider, warmup, supply_chain_manager, csv_provider, universe_loader, news_sources, etc. |
| `src/models/` | ⚠️ Not wired | train_pipeline, model_factory, predictors |
| `src/backtest/` | ✅ Exists | backtest_engine (non-canonical; canonical backtest in scripts/backtest_technical_library.py) |
| `src/utils/` | ✅ Complete | config_manager, logger, defensive, ticker_utils, etc. |

### Entry Points

**Canonical (production):**
- ✅ `scripts/backtest_technical_library.py`
- ✅ `scripts/research_grid_search.py`
- ✅ `scripts/run_execution.py`
- ✅ `scripts/run_weekly_rebalance.py` (Automated Rebalancing)

**Non-canonical (experimental):** All other run_* and test_* scripts in root or graveyard.

---

## Backtest Results

### Full Year 2022

| Metric | Master Score | SPY (reference) |
|--------|--------------|-----------------|
| Sharpe Ratio | −0.75 | ~−0.72 |
| Total Return | −33.64% | ~−18.1% |
| Max Drawdown | −48.25% | ~−25.3% |

**Configuration:**
- Universe: NVDA, AMD, TSM, AAPL, MSFT
- Selection: Top 3
- Weighting: Inverse volatility
- Friction: 15 bps

**Analysis:** Bear market year; strategy underperformed benchmark.

### October-November 2022

| Metric | Value |
|--------|-------|
| Sharpe Ratio | 0.11 |
| Total Return | +14.94% |
| Max Drawdown | −12.39% |

**Context:** Market rebound period; positive risk-adjusted return.

---

## Readiness Assessment

### MVP (Autonomous E2E Loop): 100% Complete ✅

- ✅ Dynamic data ingestion (price + news refresh)
- ✅ Rolling ML model training (4-year window, auto-patched)
- ✅ OOS backtest with contamination guard (test window from model_config, never hardcoded)
- ✅ Portfolio construction — HRP/inverse-ATR + max single-weight cap (0.40)
- ✅ Mock execution + last_valid_weights.json output
- ✅ E2E pipeline (`run_e2e_pipeline.py`) — 5 stages, single entry point
- ✅ Autonomous optimizer (`run_optimizer.py`) — random search, composite score
- ✅ Config promotion (`run_promoter.py`) — atomic write, .bak preserved
- ✅ Auto-scheduler — schtasks registers next Monday 06:00 after each optimizer run
- ✅ Max single-position cap enforced in portfolio_engine.py

### Paper Trading: 80% Complete ✅

**Completed:**
- ✅ `src/data/ibkr_live_provider.py` — connect, get_live_prices (snapshot + historical fallback), get_account_summary (NAV, margin), get_positions
- ✅ Live prices wired into `run_execution.py --mode paper` — overlaid on last bar of prices_dict; NAV from IBKR replaces hardcoded 100k
- ✅ `src/data/contract_resolver.py` — resolves equity/future/option to typed IB contract; front-month future selection; ATM option selection; roll warning
- ✅ `config/instruments.yaml` — all instrument definitions (NQ×20, MNQ×2, SMH options, allocation limits)
- ✅ `_instrument_type()` helper in `run_execution.py` — routes each ticker to correct contract type via instruments.yaml
- ✅ `Intent.futures_multipliers` — passed through portfolio engine → position_manager; futures quantity = delta_dollars / (price × multiplier)
- ✅ `--confirm-paper` → real order submission via IBExecutor + stop orders
- ✅ Fill ledger (`outputs/fills/fills.jsonl`) + `--check-fills` flag
- ✅ Circuit breaker, AccountMonitor, OrderDispatcher wired

**Remaining (activate when TWS is running):**
- ❌ First live paper run with TWS — validation deferred
- ❌ `min_order_size` / `max_position_size` enforcement in executor
- ❌ Automated TWS session startup

### Live Trading: 20% Complete ⚠️

**Remaining (beyond paper):**
- ❌ Real-time price feeds
- ❌ Live news ingestion
- ❌ Position reconciliation
- ❌ Duplicate order guardrails
- ❌ Monitoring dashboard

---

## Priority Action Items

### High Priority (Next Gate: Profitability Proof)

| # | Item | Status |
|---|------|--------|
| 1 | Run full backtest 2019–2024, confirm profitable Sharpe | ❌ Deferred (20–40 min run) |
| 2 | Activate TES tilt: `python scripts/refresh_tes_scores.py` | ❌ Deferred (3–5 min) |
| 3 | Verify `run_weekly_rebalance.py --dry-run` produces non-zero weights (ASML/AMAT CSVs now present) | ❌ Not yet verified |

### Medium Priority (Paper Trading Readiness)

| # | Item | Status |
|---|------|--------|
| 4 | Fill reconciliation (expected vs actual positions) | ❌ Not started |
| 5 | Order status tracking | ❌ Not started |
| 6 | Enforce `min_order_size` / `max_position_size` in executor | ❌ Not started |
| 7 | Multi-year statistical validation (confidence intervals) | ❌ Not started |

### Low Priority

| # | Item | Status |
|---|------|--------|
| 8 | Real-time data feeds | ❌ Not started |
| 9 | Live news ingestion pipeline | ❌ Not started |
| 10 | Monitoring dashboard | ❌ Not started |
| 11 | Walk-forward / Monte Carlo simulation | ❌ Not started |

---

## Two-Week Execution Plan

### Week 1: Backtest Integrity & Audit

**Focus:** Research completeness

**Tasks:**
1. Fix Phase 3 to generate weekly signals in memory (avoid look-ahead)
2. Run technical-only backtest end-to-end; confirm metrics
3. Wire audit logging (`log_audit_record()` after runs)
4. (Optional) Wire `ModelTrainingPipeline` into separate "train and score" script

**Deliverable:** Validated backtest with full audit trail

### Week 2: Paper Execution

**Focus:** Trading infrastructure

**Tasks:**
1. Add `run_paper_rebalance.py` (signals → target → executor → submit)
2. One manual paper run with TWS/Gateway; verify orders and positions
3. Add config-based order/position limits and simple fill check
4. Document in README: physical folder layout, how to run paper rebalance

**Deliverable:** Working paper trading capability

---

## Dependencies & Engines

**Core libraries:**
- pandas_ta (technical indicators)
- PyYAML (config)

**Dynamic weighting & regime:**
- PyPortfolioOpt (max_sharpe, HRP)
- hmmlearn (3-state Gaussian HMM)
- Scikit-Learn (Random Forest + TimeSeriesSplit)

**News Alpha:**
- transformers + ProsusAI/finbert (sentiment)
- spacy en_core_web_md (NER, event detection)
- Levenshtein (deduplication)

**Execution:**
- ib_insync (IBKR TWS)

**Installation notes:**
```bash
pip install pandas-ta PyYAML pypfopt hmmlearn scikit-learn transformers spacy python-Levenshtein ib_insync
python -m spacy download en_core_web_md
```

---

## Known Limitations & Risks

### Backtest Limitations

1. **Single year validation:** 2022 only (bear market); need multi-year
2. **No position limits:** Single stock can get 100% weight
3. **Simple transaction costs:** 15 bps fixed; no dynamic slippage
4. **News dependency:** STOP if news ERROR; no technical-only fallback (by design)

### Technical Debt

1. **Phase 3 signal file risk:** If only `top_stocks_latest.csv`, same ranking every week
2. **Regime ledger gap:** Intended but not updated by canonical code
3. **ML pipeline orphan:** Code exists but not wired to main flow
4. **No weekly regime:** Policy engine is passthrough in weekly mode (gates OFF)

### Production Risks

1. **No real-time feeds:** Historical data only
2. **No fill verification:** Orders submitted but not reconciled
3. **No safety limits:** Config exists but not enforced
4. **Manual scheduling:** No automation

---

## Governance & Operating Mode

**Current mode:** **Phase 2 Active**

**Allowed:**
- Fix documented but broken features
- Wire existing modules (Automated Rebalancing, Live Execution Bridge)
- Add observability (logging, manifests)
- Implement approved designs (e.g. Gemini bridge after Proposal Review)

**Immutability (mandatory):**
- **ARCHITECTURE.md** and **STRATEGY_MATH.md** must not be modified without a **Proposal Review** from the user first.

**Governance:** Interface changes and scope expansion require explicit approval per AI_RULES.md.

---

## Historical Roadmap (From Early Planning)

**Note:** This 5-phase roadmap reflects early project planning. Phase 1 is complete; subsequent phases are partially implemented or deferred.

### Phase 1: Infrastructure Institutionalization ✅ COMPLETE

1. ✅ Canonical spine consolidation
2. ✅ Execution parity enforcement (1e-12 tolerance)
3. ✅ Regression snapshot guard
4. ✅ Environment freeze (pinned requirements)
5. ✅ Paper IB execution path (components exist)

### Phase 2: Intelligence Expansion ✅ ACTIVE

6. ✅ Integrate news score into Master Score — **DONE** (News Alpha overlay in news_engine.py)
7. ✅ Supply-chain propagation — **DONE** (sentiment_propagator.py wired in signal_engine; optional enable_propagation)
8. ✅ Multi-indicator technical architecture — **DONE** (Master Score with 4 categories in technical_library.py)
9. ⚠️ Diagnostic transparency (feature contribution logging) — **NOT STARTED**
10. ⚠️ Explainability outputs per rebalance — **NOT STARTED**
11. ✅ Automated Rebalancing — **DONE** (scripts/run_weekly_rebalance.py; delegates to run_execution)
12. ✅ Live Execution Bridge (IBKR) — **DONE** (src/execution/ibkr_bridge.py; design: docs/LIVE_EXECUTION_BRIDGE_DESIGN.md)
12a. ✅ **Execution Bridge: Mock Verification — COMPLETE** (run_weekly_rebalance.py --dry-run produces validated BUY/SELL orders; last-close prices from prices_dict injected in run_execution.py so PositionManager receives non-null prices and computes correct quantities; execution parity per DECISIONS.md D018)
13. ✅ Gemini/LLM deep analysis — **IN PROGRESS: Gemini Bridge Verified** (docs/GEMINI_BRIDGE_DESIGN.md; first intelligence-driven backtest Aug 2022 window; Fallback→Active 2026-02-17 per DECISIONS.md D019)

### Phase 3: Statistical Validation ❌ NOT STARTED

11. ❌ Multi-month forward-walk validation
12. ❌ Regime robustness analysis
13. ❌ Parameter stability grid validation
14. ❌ Turnover & slippage modeling
15. ❌ Capacity stress testing

### Phase 4: Controlled Capital Deployment ❌ NOT STARTED

16. ❌ Small-capital live IB deployment
17. ❌ Execution slippage audit
18. ❌ Operational monitoring layer
19. ❌ Automated failure alerts

### Phase 5: Strategic Productization ❌ NOT STARTED

20. ❌ Wealth-management packaging layer
21. ❌ Client reporting framework
22. ❌ Risk dashboard
23. ❌ Documentation for allocators

**Current phase:** Phase 2 active. See "Priority Action Items" above for near-term execution plan. Design docs: GEMINI_BRIDGE_DESIGN.md, LIVE_EXECUTION_BRIDGE_DESIGN.md (in docs/).

---

## Conclusion

**System status:** Production-ready for research/backtest; 30% ready for live trading.

**Strengths:**
- Solid canonical workflow
- Comprehensive signal generation (technical + news + regime)
- Validated backtest infrastructure
- Complete documentation

**Next steps:**
1. Complete Week 1 plan (backtest integrity)
2. Complete Week 2 plan (paper trading)
3. Multi-year validation
4. Statistical significance testing

**Estimated time to paper trading:** 2 weeks (following execution plan)

**Estimated time to live trading:** 4-6 weeks (after paper trading validation)
