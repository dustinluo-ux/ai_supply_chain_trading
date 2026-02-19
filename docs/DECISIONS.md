# DECISIONS — Architectural Decision Records

**Last Updated:** 2026-02-19

This file records architectural decisions and their rationale. Implementation details live in other documents. This is the "why" documentation.

---

## Design Principles (Foundational)

These principles guide all architectural decisions:

1. **Guardrails > Speed** — Correctness and safety are more important than performance
2. **Determinism > Cleverness** — Reproducible results trump sophisticated but unpredictable algorithms
3. **Single Canonical Spine > Script Sprawl** — One authoritative execution path, not multiple competing implementations
4. **Explicit State > Implicit Behavior** — All system state must be explicit and observable
5. **Fail Loudly > Silent Degradation** — Missing outputs or violated invariants must terminate execution

These principles are non-negotiable and take precedence over convenience or short-term optimization.

---

## Operating Mode

### P0 Fix Mode (LOCKED DECISION)

**Status:** CLOSED (2026-02-19)

**Definition:** P0 Fix Mode means fixing only what is already documented but broken, missing, unused, or non-observable.

**Explicitly allowed in P0:**
- Wiring existing modules so they actually execute
- Creating outputs that are already declared but missing
- Enforcing invariants and failure-on-missing-output
- Adding logging, manifests, and guards for observability
- Reusing existing logic from `graveyard/` or `wealth_signal_mvp_v1/` as read-only reference

**Explicitly forbidden in P0:**
- Introducing new models, signals, strategies, or metrics
- Changing any public interfaces or function signatures
- Inventing new behavior not described in canon docs
- Expanding scope beyond declared workflow
- Touching components not referenced in WORKFLOW.md or SYSTEM_MAP.md

**Kill-Switch Rule:**
Any run must terminate immediately if:
- A declared output is missing
- A module invariant fails
- The research spine cannot complete end-to-end

**Binding status:** CLOSED 2026-02-19. All P0 gaps resolved or explicitly deferred. Phase 3 now active.

---

### D020 — Phase 2 Closure (2026-02-19)

**Decision:** Phase 2 (Intelligence Expansion + Automated Rebalancing) is formally closed as of 2026-02-19.

**P0 gaps resolved:**
- News pipeline gap: `news_dir` hardcoded None → reads from config
- News loader format-agnostic: flat file + monthly chunk both supported
- News cache tz-aware bug fixed (was burning Marketaux API quota)
- `find_csv_path` returns latest-end-date copy when ticker exists in multiple datasets
- Stale pre-propagated tickers dropped before backtest run
- BEAR weight renorm + non-BEAR assertion relaxed to accept 0.0 (all-propagated top-N edge case)
- Gemini bridge: load_dotenv wired; `--no-llm` flag added for backtests
- `llm_enabled` threaded from config through execution spine
- Fill ledger: persistent JSON-Lines append at `outputs/fills/fills.jsonl`; `--check-fills` CLI flag
- Config limits enforced: `min_order_size` and `max_position_size` now read from config in all execution paths; SELL guard added to prevent accidental shorts

**P0 gaps explicitly deferred (not blocking):**
- News 2025 coverage gap (needs paid source)
- Scheduling automation (no server yet)
- ML pipeline wiring (see D021)

**Backtest baselines at close:**
- 2022: Sharpe -0.2759 | return -17.95% | MDD -20.65%
- 2023: Sharpe +0.3399 | return +78.10% | MDD -19.93%

**Status:** Complete

---

### D021 — ML Pipeline Integration Architecture (Phase 3)

**Decision:** Wire `src/models/` into the signal spine as a third blended signal. Deferred to Phase 3.

**Background:** `src/models/` contains Linear/Ridge/Lasso/XGBoost return predictors with a full training pipeline (`train_pipeline.py`). The `use_ml: false` flag in `config/model_config.yaml` is never read. No trained model artifacts exist.

**Rationale for deferral:**
- The models output predicted forward returns (%), not a normalized 0–1 score — unit mismatch with existing Master Score prevents drop-in integration
- No saved artifacts exist; model must be trained and IC-validated before production use
- Introducing an untrained model into a working system violates "Determinism > Cleverness" (D-principle #2)

**Approved architecture for Phase 3 (from expert review 2026-02-19):**

1. **Pooled training:** Train one model on all tickers combined (not separate per-ticker). ~150 rows × 8 tickers ≈ 1200 samples — sufficient for regularized regression.
2. **Normalization:** Convert ML predicted return to 0–1 score using rolling Z-score (3–6 month window) passed through a min-max clipper. Preserves relative magnitude unlike percentile ranking.
3. **Blend:** `Final Score = 0.7 × Baseline + 0.3 × ML_Score` as starting point. Baseline = current Technical + News blend.
4. **Sanity check:** If ML predicts negative return but Baseline is bullish, reduce position size by 50% rather than ignoring the disagreement.
5. **Gate before wiring:** Measure IC (Spearman rank correlation of predictions vs actual returns) on anchored walk-forward. Require IC ≥ 0.02 before integrating into live system. If IC < 0.02, discard.
6. **Validation:** Run two backtests — (1) Technical + News only, (2) Technical + News + ML — and require ≥10% Sharpe improvement before promoting to production.
7. **Pitfall mitigations:** Use purged cross-validation to prevent look-ahead leakage; use sector-neutral features (e.g. stock RSI minus SOXX RSI) to reduce high-correlation noise in concentrated semiconductor universe.

**Features (unchanged from existing train_pipeline.py):** momentum_20d, volume_ratio_30d, rsi_14d, news_supply_chain, news_sentiment.

**Status:** Deferred — architecture approved, implementation blocked on IC validation gate.

## Core Architectural Decisions

### D001 — Separate Research vs Execution

**Decision:** Maintain strict separation between research/backtest code and live execution code.

**Rationale:** 
- Prevents research logic from leaking into live trading
- Allows aggressive research experimentation without production risk
- Enables independent testing and validation of each path

**Implementation:**
- Research: `scripts/backtest_technical_library.py`, `scripts/research_grid_search.py`
- Execution: (Planned) `run_weekly_rebalance.py`, IBKR integration

**Status:** Implemented

---

### D002 — Enforce Invariants Centrally

**Decision:** Invariants must fail fast and be centrally enforced.

**Rationale:**
- Distributed invariant checks lead to inconsistency
- Silent failures corrupt downstream results
- Central enforcement enables better error messages

**Current state (v1):** 
- Invariants enforced locally within canonical entry points
- Examples: `ensure_ohlcv`, row count validation, date slice checks in backtest

**Future state (v2 goal):**
- Central invariant layer
- Single source of truth for all validation rules
- Standardized error handling

**Status:** Partial implementation (v1 complete, v2 planned)

---

### D003 — Regime as Structured State

**Decision:** Market regime must be represented as structured state with confidence and provenance.

**Rationale:**
- Downstream logic needs to know confidence level
- Debugging requires understanding regime source
- Historical regime tracking enables strategy refinement

**Structure:**
```python
RegimeState {
    label: 'BULL' | 'BEAR' | 'SIDEWAYS',
    confidence: float,
    source: 'hmm' | 'sma_fallback',
    metadata: {
        mean_return: float,
        volatility: float,
        transition_matrix: ndarray
    }
}
```

**Status:** Implemented

---

### D004 — Strategy Selector is Advisory

**Decision:** Strategy parameter selector provides recommendations, not mandates.

**Rationale:**
- Governance layer can override for risk management
- Safety checks must validate all parameters
- Human oversight on critical decisions

**Implementation:**
- Selector suggests parameters based on memory/performance
- Policy layer can veto or modify
- All overrides logged

**Status:** Implemented

---

### D005 — Memory Updated Post-Run Only

**Decision:** System memory (ledgers, performance history) updated only after run completes.

**Rationale:**
- Prevents partial-run corruption
- Ensures atomic updates
- Enables rollback on failure

**Memory scope (explicit list of what gets updated post-run):**

| Artifact | Path | Updated By | Frequency | Status |
|----------|------|-----------|-----------|--------|
| **Performance CSV** | `--performance-csv` arg | `performance_logger.append_row()` | Per run | Optional |
| **Log files** | `outputs/backtest_master_score_*.txt` | Backtest script | Per run | Always |
| **Run manifest** | `outputs/run_manifest_*.json` | Backtest script | Per run | Always |
| **Regime ledger** | `data/logs/regime_ledger.csv` | `performance_logger.update_regime_ledger()` | Per week | **Gap: not called** |

**Known gaps:**
- `regime_ledger.csv` intended as system memory but **not yet updated** by canonical backtest code
- Function exists (`update_regime_ledger()`) but no call site in canonical entry points
- Strategy Selector depends on regime_ledger for winning profile lookup
- Post-run artifacts currently limited to performance CSV, logs, and manifest

**Kill-switch guard:**
- PolicyEngine does NOT apply kill-switch when `regime_state` is None
- Kill-switch applies only when regime is detected AND criteria met (BEAR + SPY < 200-SMA)
- Explicit guard: `if regime_state is not None and <conditions>`

**Future work:**
- Wire `update_regime_ledger()` call in backtest loop (see PROJECT_STATUS.md action items)
- Add signal history tracking
- Implement audit trail with run-level snapshots

**Status:** Partial implementation

---

### D006 — News is First-Class Input

**Decision:** Every research or execution run MUST include news context.

**News states:**

| State | Definition | Action |
|-------|------------|--------|
| `PRESENT` | News files exist and readable | Compute news_score |
| `EMPTY` | News files exist but yield no usable signal | news_score = 0 (valid) |
| `ERROR` | News files missing, unreadable, or malformed | **STOP execution** |

**Prohibitions:**
- No silent fallback to "technical-only"
- No implicit defaults when news is missing
- No degradation without explicit configuration

**Rationale:**
- Absence of news is information (market quiet period)
- Silent downgrade causes invisible regime drift
- Explicit state tracking improves diagnostics

**Status:** Implemented

---

### D007 — Macro Regime Scope (Price-Only for Now)

**Decision:** Use price-derived regime signals only; defer external macro data.

**Current approach:**
- HMM on SPY returns
- 200-day SMA fallback
- No external macro series (FRED rates, CPI, PMI)

**Rationale:**
1. Price already aggregates macro information
2. Most macro series are lagged and add complexity without clear incremental signal
3. Simpler regime logic is more robust during early system validation

**Future extensions:**
- Macro data integration must be implemented behind dedicated interface/switch
- No ad-hoc macro logic permitted
- Must demonstrate incremental value in backtest before production

**Deferred scope:**
- Interest rate regime detection
- Economic cycle classification
- Inflation regime tracking

**Status:** Implemented (price-only), macro deferred

---

## Phase and Convergence Decisions

### D008 — Phased Backend Convergence

**Decision:** Phase 1 allows two signal backends under one interface; convergence to single backend is Phase 2/3 scope.

**Phase 1 (current):**
- Backtest: `technical_library` + `news_engine`
- Weekly: `SignalCombiner` (precomputed)
- Same `SignalEngine` interface

**Phase 2/3 (planned):**
- Converge to single backend
- Unified signal computation
- Remove precomputation requirement

**Rationale:**
- Allows immediate progress on research spine
- Defers complexity of real-time signal generation
- Validates architecture before optimization

**Status:** Phase 1 complete

---

### D009 — Full Workflow Parity (Deferred)

**Decision:** Full parity of research workflow across all stages is planned but not required for current correctness.

**Current phase focus:** 
- Validate research spine end-to-end in backtest
- Ensure all declared outputs exist
- Verify no look-ahead violations

**Deferred activations:**
- Full parity across prices, news, normalization, regime, policy gating, and portfolio intent
- Extension to weekly and execution modes

**Rationale:**
- Current phase focuses on research validation
- Production execution activation comes after research confidence
- Reduces scope creep during P0 fix mode

**Status:** Partial implementation

---

## Audit and Quality Decisions

### D010 — Code vs Docs Audit

**Decision:** Periodic audit of code against canonical documentation.

**Audit completed:** 2026-01

**Audit scope:**
- Verify canon docs match executable code
- Document mismatches in `docs/CODE_VS_DOCS_AUDIT.md`
- Track technical debt

**Findings location:** See audit document for details

**Cadence:** 
- After major feature additions
- Before production releases
- Quarterly minimum

**Status:** Initial audit complete

---

## Feature Flags and Toggles

### D011 — Feature Activation via Configuration

**Decision:** New features activated via explicit configuration, not code changes.

**Examples:**
- `--weight-mode regime` enables HMM regime detection
- `--news-dir data/news` enables news overlay
- `--no-safety-report` skips safety validation output

**Rationale:**
- Enables A/B testing
- Reduces deployment risk
- Allows gradual rollout

**Status:** Implemented

---

## Safety and Risk Management

### D012 — Fail-Fast on Missing Data

**Decision:** Missing or corrupt data terminates execution immediately.

**No silent degradation:**
- Missing ticker data → stop
- Missing news when required → stop
- Invalid date range → stop
- Insufficient history → stop

**Error handling:**
- Clear error messages
- Diagnostic information logged
- Guidance on resolution

**Rationale:**
- Silent failures lead to incorrect results
- Better to halt than produce unreliable signals
- Forces data quality discipline

**Status:** Implemented

---

### D013 — Dual-Confirmation Kill-Switch

**Decision:** CASH_OUT requires both regime and trend confirmation.

**Rule:** Trigger only when:
- Regime = BEAR (from HMM), AND
- SPY < 200-SMA (trend confirmation)

**Rationale:**
- Prevents false signals during volatile bull markets
- HMM may classify high-volatility bull as BEAR
- Trend filter adds robustness

**Alternative approaches rejected:**
- HMM alone (too sensitive to volatility)
- SMA alone (too slow to react)
- Confidence threshold (hard to calibrate)

**Status:** Implemented

---

## Data and Integration Decisions

### D014 — Multi-Source Data Strategy

**Decision:** Support multiple data sources with unified interface.

**Supported sources:**
- Legacy: FNSPID, Polygon
- New: Tiingo, yfinance, Marketaux

**Requirements:**
- Unified schema for all sources
- Source selection via configuration
- Seamless switching without code changes

**Rationale:**
- Reduces vendor lock-in
- Enables cost optimization
- Provides redundancy

**Status:** Implemented

---

### D015 — Self-Healing Historical Data

**Decision:** Live fetches automatically update historical store.

**Process:**
1. Fetch new bars from live source
2. Append to historical parquet files
3. Deduplicate by timestamp
4. Maintain continuous time series

**Rationale:**
- Reduces reliance on batch downloads
- Keeps historical data current
- Simplifies data management

**Module:** `src/data/warmup.py` → `heal_append()`

**Status:** Implemented

---

## Testing and Validation Decisions

### D016 — Mandatory Safety Report

**Decision:** Every backtest generates safety report unless explicitly skipped.

**Report contents:**
- Signal lag verification (no look-ahead)
- Mid-week exit validation
- Benchmark alignment checks
- Data quality metrics

**Override:** `--no-safety-report` flag

**Rationale:**
- Catches look-ahead bugs early
- Documents backtest assumptions
- Builds confidence in results

**Status:** Implemented

---

### D017 — Model Validation via State Logging

**Decision:** When regime or news active, log state at each rebalance.

**Format:**
```
[STATE] {Date} | Regime: B/E/S | News Buzz: T/F/- | Action: Trade/Cash
```

**Legend:**
- Regime: B=Bull, E=Bear, S=Sideways
- News Buzz: T/F when news active, - otherwise
- Action: Trade or Cash (CASH_OUT)

**Additional logging:**
```
[REGIME] Date: {monday}, HMM State: {state}, Mean Return: {mu}, Volatility: {sigma}
[HMM TRANSITION MATRIX] (printed on first Monday)
```

**Rationale:**
- Enables strategy validation
- Supports debugging
- Provides audit trail

**Status:** Implemented

---

### D018 — Dry-Run Price Injection for Execution Parity

**Decision:** During dry-run/mock execution, inject last-close prices from the loaded `prices_dict` into the execution spine so that `PositionManager.calculate_delta_trades` receives a non-null `prices` argument and computes correct share quantities.

**Rationale:**
- Without prices, `current_price` in position logic is missing; quantity becomes zero and no executable orders are produced in mock mode.
- Live/paper execution has real prices; mock must behave the same for validation and testing.
- Single code path (spine → Intent → delta trades) must produce identical structure of orders whether mock or live; only the execution backend (mock vs IB) differs.

**Implementation:**
- In `scripts/run_execution.py` (non–rebalance path): before calling `position_manager.calculate_delta_trades(...)`, build a last-close price Series from `prices_dict` as of the rebalance date (`as_of`) and pass it as the `prices` argument.
- `src/portfolio/position_manager.py` uses this for `current_price` and thus computes non-zero quantities and executable orders in dry-run.

**Status:** Implemented. (Gemini Intelligence Bridge separately transitioned Fallback→Active 2026-02-17; see D019.)

---

### D019 — Gemini Bridge: Fallback to Active (2026-02-17)

**Decision:** The Gemini Intelligence Bridge (Phase B activation per docs/GEMINI_ACTIVATION_PLAN.md) successfully transitioned from **Fallback** (no API/key or parse failure) to **Active** mode on 2026-02-17.

**Rationale:**
- Dependencies (google-genai, pydantic) and API keys (GOOGLE_API_KEY / GEMINI_API_KEY) were verified via `scripts/verify_environment.py` as "Gemini API ready."
- First intelligence-driven backtest was run for the August 2022 window (NVDA, AAPL, MSFT; `scripts/backtest_technical_library.py` with `--news-dir data/news`).
- When the LLM gate fires (supply_chain_keyword or surprise > trigger_threshold), `src/signals/news_engine.py` calls the bridge; successful Gemini responses yield `new_network_links` passed to the sentiment propagator (signal_engine), blending LLM-derived supply chain intelligence into the capital decision spine.

**Evidence:**
- Observability: `logger.info("LLM Triggered: ...", reason, ticker)` and `logger.info("LLM deep_analyze: category=%s sentiment=%.2f links=%d", ...)` in `src/signals/news_engine.py` (L532, L557).
- Safety fallback: `logger.warning("LLM gate failed (skipping): ...", exc)` (L560) when API/auth or parse fails.

**Status:** Verified 2026-02-17 (environment and first backtest); bridge Active when key set and gate fires.

---

## Governance Process

### Decision Lifecycle

1. **Proposal:** Document problem and proposed solution
2. **Review:** Technical review by stakeholders
3. **Decision:** Formal decision recorded here
4. **Implementation:** Code changes to align with decision
5. **Validation:** Testing and verification
6. **Audit:** Periodic review of decision impact

### Decision Modification

**Minor changes:** Update rationale and status inline

**Major changes:** 
- Create new decision record
- Reference superseded decision
- Document migration path

### Decision Status Values

- **Proposed:** Under consideration
- **Implemented:** In production code
- **Partial:** Some aspects complete, others pending
- **Deferred:** Accepted but implementation delayed
- **Superseded:** Replaced by newer decision
- **Rejected:** Considered and declined

---

## Document Maintenance

**Update triggers:**
- New architectural decision
- Major feature addition
- Significant refactoring
- Audit findings

**Review cadence:**
- Monthly: Status updates
- Quarterly: Full review
- Release: Pre-release validation

---

This document is the authoritative record of "why" decisions were made. Implementation details belong in other canonical documents (ARCHITECTURE, WORKFLOW, SYSTEM_MAP, STRATEGY_LOGIC, TECHNICAL_SPEC, BACKTEST_JOURNAL).
