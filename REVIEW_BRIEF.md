# REVIEW_BRIEF — Codex Audit Context

**Prepared:** 2026-04-27
**Audit Type:** External security/code review (no business logic changes)

---

## Project Purpose

AI quantitative trading system for AI/semiconductor supply chain equities. Fully autonomous end-to-end pipeline: data refresh → signal generation → ML model training → backtesting → portfolio optimization → execution (mock/paper/live IBKR).

**Universe:** 54 tickers (NVDA, TSM, ASML, AMD, QCOM, etc.)
**Current Phase:** Paper trading active (IBKR account DUM879076)
**Tech Stack:** Python 3.11, CatBoost ML, HRP portfolio optimization, IBKR ib_insync

---

## Architecture Summary

### Core Engines (Single Spine)

1. **SignalEngine** (`src/core/signal_engine.py`) — Technical signals + Master Score
2. **PolicyEngine** (`src/core/policy_engine.py`) — Regime gates, policy filters
3. **PortfolioEngine** (`src/core/portfolio_engine.py`) — HRP + Alpha Tilt, position sizing

### Layered Signal Architecture (Three Layers)

- **L1 (Quality):** Fundamental quality metrics, audit flags
- **L2 (Valuation):** FCFF, R&D capitalization, cross-sectional ranks
- **L3 (Technical):** Master Score (momentum, trend, volatility)

### Key Modules

| Directory | Purpose |
|-----------|---------|
| `src/core/` | Engines, Intent, state management |
| `src/signals/` | Technical library, layered signal engine, LLM bridge |
| `src/execution/` | IBKR integration, risk overlay, position management |
| `src/agents/` | Advisory agents (Taleb, Damodaran, Bull/Bear debate) |
| `src/fundamentals/` | Semi-valuation, quality metrics |
| `scripts/` | Entry points for pipeline stages |
| `config/` | YAML configurations (machine-written except optimizer_config.yaml) |

---

## Key Files/Directories

### Entry Points

- `scripts/run_e2e_pipeline.py` — Full pipeline orchestration
- `scripts/run_weekly_rebalance.py` — Production weekly run
- `scripts/run_execution.py` — IBKR order submission
- `scripts/run_optimizer.py` — Random search hyperparameter tuning

### Core Logic

- `src/core/portfolio_engine.py` — HRP + Alpha Tilt, max weight cap enforcement
- `src/signals/layered_signal_engine.py` — Three-layer signal combination
- `src/execution/risk_manager.py` — RiskOverlay, VIX/SPY regime checks
- `src/agents/skeptic_gate.py` — Bear-flag detection, concentration alerts

### Configuration

- `config/optimizer_config.yaml` — Master tuning manifest (search_space, fixed_params)
- `config/strategy_params.yaml` — Promoted winner params (machine-written)
- `config/trading_config.yaml` — Execution settings, IBKR client IDs
- `config/universe.yaml` — 54-ticker watchlist

---

## Known Risks

### Technical Debt

1. **Lint/format issues:** 50+ files need black formatting; flake8 shows E402, F401, F841 violations
2. **Failing tests:** 2 of 153 tests fail:
   - `test_ibkr_live_provider.py::TestGetAccountSummary::test_returns_float_fields` — mock assertion
   - `test_skeptic_gate.py::test_fail_two_flags_fatal_ticker` — verdict mismatch (PASS vs FAIL)
3. **Unused imports/variables:** Multiple F401/F841 in `backtest_technical_library.py`, `run_execution.py`
4. **Undefined name:** `DataQualityReport` in `run_execution.py:501`

### Security Concerns

1. **API keys in `.env`** — TIINGO, MARKETAUX, GOOGLE_API, FMP_API_KEY, EDGAR_IDENTITY
2. **IBKR credentials** — Paper account DUM879076 referenced in config
3. **Decimal math enforcement** — Critical for monetary calculations; verify no `float` for money

### Architecture Concerns

1. **ExecutorFactory redefinition** — `run_execution.py:779` redefines from line 651
2. **Stale subprocess calls** — `risk_manager.py:55-100` has deprecated subprocess patterns
3. **Research scripts in production tree** — `scripts/research/` contains experimental code

---

## Recent Changes (Last 10 Commits)

1. `9351871` — Wire execution gaps, TES integration, portfolio beta, BAU orchestration
2. `4b50fbd` — Two-Lane architecture (decouple Alpha from Risk/Execution)
3. `2d9e348` — Activate three-layer engine + consolidate benchmark downloads
4. `6216833` — Remove dead AlphaVantage, Finnhub, NewsAPI integrations
5. `0fdf015` — Fix sys.path.insert ordering
6. `03f649f` — Add 5 quality metrics (FCF Yield, ROIC, etc.)
7. `90a8e0a` — Complete three-layer signal engine
8. `b9be036` — Update docs for D024
9. `fe43214` — Three-layer signal engine + EODHD fundamental fetcher
10. `2e60192` — Move research scripts to scripts/research/

---

## What Must NOT Be Changed

### Immutable Business Logic

1. **Signal formulas** in `docs/STRATEGY_MATH.md` — Authoritative math definitions
2. **Master Score calculation** in `src/signals/technical_library.py` — Do not modify weights
3. **HRP + Alpha Tilt** in `src/core/portfolio_engine.py` — Core allocation algorithm
4. **Risk overlay thresholds** — Values from `config/strategy_params.yaml`
5. **Decimal precision** — All monetary calculations must use `decimal.Decimal`

### Config Files

1. `config/strategy_params.yaml` — Machine-written by `run_promoter.py`
2. `config/model_config.yaml` — Machine-written by rolling window patch
3. `docs/ARCHITECTURE.md`, `docs/STRATEGY_MATH.md` — Require Proposal Review for changes

### Pipeline Behavior

1. **Skeptic Gate** — `WEIGHT_TRIGGER=0.15`, 2+ flags = FAIL
2. **Max single position cap** — Enforced at 40% (configurable in trading_config.yaml)
3. **Rolling training window** — 4-year train, 1-year test, formula-driven dates

---

## Review Focus Areas

### High Priority

1. **Input validation** — User inputs, API responses, config values
2. **Decimal math** — Verify no `float` for monetary values
3. **IBKR integration** — Order submission, position management, error handling
4. **Error handling** — Fail-loudly vs silent degradation patterns
5. **Secrets management** — No hardcoded credentials, proper .env usage

### Medium Priority

1. **Test coverage** — Assess gaps in `tests/`
2. **Code quality** — Unused imports, dead code, type hints
3. **Logging** — Sensitive data exposure in logs
4. **Atomic writes** — Verify `.tmp` → rename pattern for critical files

### Low Priority

1. **Documentation accuracy** — Sync between docs and code
2. **Performance bottlenecks** — Not critical for correctness
3. **Research scripts** — Experimental code, lower bar

---

## Constraints for Reviewer

- **No business logic changes** — Only report issues, do not fix signal formulas or allocation logic
- **No config value changes** — Thresholds are intentional; report but do not modify
- **Preserve determinism** — Random seeds, reproducible outputs must remain
- **Maintain Decimal strictness** — Any `float` for money is a finding

---

## Expected Deliverables

1. Security findings (OWASP Top 10, secrets exposure, injection risks)
2. Code quality issues (unused code, type safety, error handling)
3. Architecture observations (coupling, cohesion, dead code)
4. Test coverage gaps
5. Recommendations (prioritized by severity)
