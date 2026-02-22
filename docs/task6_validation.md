# Task 6 Validation — 2026-02-21

**Reference:** INDEX.md; Evidence Discipline.  
**Context:** Task 6 implemented in commit d5f51c3. Three tests: watchlist purge, vol filter, mock execution with clean watchlist.

---

## TEST 1 — Watchlist purge

**Command run:** `python scripts/generate_daily_weights.py > daily_weights.txt 2>&1`

### Full contents of daily_weights.txt

```
WARNING:root:ML model load failed (fail-open): RidgeReturnPredictor.__init__() got an unexpected keyword argument 'model_name'
date,ticker,target_weight,latest_close,notional_units

2026-02-21,NVDA,0.0,184.97000122070312,0

2026-02-21,AMD,0.0,203.0800018310547,0

2026-02-21,TSM,0.3333333333333333,364.2000122070313,91

2026-02-21,ASML,0.3333333333333333,600.35498046875,55

2026-02-21,MU,0.0,53.8650016784668,0

2026-02-21,AMAT,0.3333333333333333,107.4113998413086,310

2026-02-21,INTC,0.0,28.11549949645996,0
```

### Checklist

| Check | Result | Evidence |
|-------|--------|----------|
| (a) No AAPL, MSFT, GOOGL, SPY in ticker column | **PASS** | Ticker column contains only: NVDA, AMD, TSM, ASML, MU, AMAT, INTC. |
| (b) All seven tickers present: NVDA, AMD, TSM, ASML, MU, AMAT, INTC | **PASS** | All seven appear in the CSV. |
| (c) Exit code 0; no traceback | **PASS** | Script exited 0. One WARNING line (ML model load fail-open); no traceback. |

**TEST 1:** PASS

---

## TEST 2 — Vol filter active

**Source:** daily_weights.txt (stdout+stderr) and any stderr from generate_daily_weights.

### [VolFilter] lines or "no triggers today"

No `[VolFilter]` WARNING lines appear in daily_weights.txt. **No triggers today** (vol may not be in top 5% today). No traceback from the vol filter block.

**TEST 2:** PASS

---

## TEST 3 — Mock execution with clean watchlist

**Command run:** `python scripts/run_execution.py --tickers NVDA,AMD,TSM,ASML,MU,AMAT,INTC --mode mock --rebalance > mock_run_t6.txt 2>&1`

### Full contents of mock_run_t6.txt

```
2026-02-21 16:33:05 - ai_supply_chain - INFO - MockExecutor initialized with capital: $100,000.00
--- Canonical execution (mock): rebalance (drift threshold) ---
  As-of:       2026-02-16
  Account:     100,000.00
  Intent:      ['TSM', 'AAPL', 'MSFT']
  Executable:  1
  BUY 91 TSM (delta_w=+33.33% drift=-100.0%)
  (Mock: no orders submitted.)
```

### Checklist

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) Intent list contains only tickers from Core 7 (no AAPL/MSFT/GOOGL/SPY) | **FAIL** | Intent is `['TSM', 'AAPL', 'MSFT']`. AAPL and MSFT appear; they are in the purge list. Core 7 is NVDA, AMD, TSM, ASML, MU, AMAT, INTC. |
| (c) No traceback | **PASS** | No traceback in output. |

**TEST 3:** FAIL (check b)

### Paste of mock_run_t6.txt intent line

```
  Intent:      ['TSM', 'AAPL', 'MSFT']
```

---

## Summary

| Test | Result | Failing check |
|------|--------|----------------|
| TEST 1 — Watchlist purge | PASS | — |
| TEST 2 — Vol filter | PASS | — |
| TEST 3 — Mock execution clean watchlist | FAIL | (b) Intent contains AAPL, MSFT |

---

## Overall verdict

**TASK 6 FAILED**

Reason: TEST 3(b) failed. Mock execution with `--tickers NVDA,AMD,TSM,ASML,MU,AMAT,INTC` produced Intent `['TSM', 'AAPL', 'MSFT']`, which includes AAPL and MSFT (purged names). Intent is not restricted to Core 7 in this run. Evidence: `scripts/run_execution.py` passes tickers into the spine but Intent is derived from target weights produced by the pipeline; pipeline output included AAPL and MSFT.

---

## Task 6 Bug Diagnoses

**Reference:** INDEX.md; Evidence discipline (file:line). No code changes — document only.

---

### BUG 1 — ML model load failure

**Error:** `RidgeReturnPredictor.__init__() got an unexpected keyword argument 'model_name'`  
**Trigger:** `target_weight_pipeline.py` calls `BaseReturnPredictor.load_model(path)` (via `MODEL_REGISTRY[_active].load_model(...)`).

**Evidence:**

- **src/models/base_predictor.py:204-208** — The `load_model()` classmethod reconstructs the instance by calling `cls(...)` with keyword arguments:
  - **Line 205:** `model_name=save_data['model_name']`
  - **Line 206:** `model_type=save_data['model_type']`
  - **Line 207:** `feature_names=save_data['feature_names']`
  - **Line 208:** `config=save_data['config']`
- **src/models/linear_model.py:44-45** — `RidgeReturnPredictor.__init__(self, feature_names, config=None)` accepts only **positional `feature_names`** and **optional `config`**. It does not accept `model_name` or `model_type`; it passes fixed values to `super().__init__(model_name=f"ridge_alpha...", model_type="Ridge", ...)` (lines 47-51).

**Mismatch:** The base class passes `model_name=` and `model_type=` into the subclass constructor. The subclass (`RidgeReturnPredictor`) does not accept those kwargs — it only has `feature_names` and `config`.

**Exact line where the kwarg is passed:** **src/models/base_predictor.py:205** — `model_name=save_data['model_name']` (and line 206 for `model_type`).

**One-line fix:** In `RidgeReturnPredictor` (and any other concrete predictor that only takes `feature_names, config`), add `**kwargs` to `__init__` and pass through to `super().__init__(...)`, or have `load_model()` in the base class call the subclass with only the kwargs that the subclass accepts (e.g. `feature_names` and `config`) and set `model_name` / `model_type` on the instance after construction. Prefer: subclasses accept `model_name` and `model_type` as optional kwargs and pass them to `super().__init__()` so `load_model()` works without change.

---

### BUG 2 — AAPL/MSFT appear in intent despite Core 7 --tickers

**Observed:** `run_execution.py` called with `--tickers NVDA,AMD,TSM,ASML,MU,AMAT,INTC` but Intent is `['TSM', 'AAPL', 'MSFT']`.

**Evidence:**

- **scripts/run_execution.py:214** — Tickers come only from CLI: `tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]`. No config read for tickers here.
- **scripts/run_execution.py:256-258** — `compute_target_weights(as_of, tickers, prices_dict, data_dir, ...)` is called with that `tickers` list and the `prices_dict` from `load_prices(data_dir, tickers)` (line 221). So the pipeline receives the Core 7 list as the `tickers` parameter.
- **src/core/target_weight_pipeline.py:47, 126, 139** — `compute_target_weights(as_of, tickers, ...)` accepts `tickers` and passes it in `data_context["tickers"]` and later in `portfolio_context["tickers"]` (line 246). So the requested universe is the Core 7 list.
- **src/signals/signal_engine.py:254-309** — In `_generate_backtest()`, `extended_universe` starts as `list(universe)` (line 254). When **propagation** is enabled, `_propagate_sentiments()` returns `propagated_targets`. For each target **not** already in universe (lines 264-266), the engine loads price data from `data_dir` (via `find_csv_path`, `load_prices`), verifies RSI, then **appends the ticker to `extended_universe`** (line 297) and **mutates `prices_dict[ticker_upper] = df`** (line 309). So propagation can add AAPL and MSFT to the scored universe and to `prices_dict`.
- **src/core/target_weight_pipeline.py:251** — After the spine, `universe = list(prices_dict.keys())`. By then `prices_dict` may have been **mutated** by SignalEngine (line 309 above), so it can include AAPL and MSFT. Intent tickers come from **ranking `gated_scores`** (which has keys from the signal engine, i.e. extended_universe); so intent can be top-N from a set that includes propagated tickers.

**config/strategy_params.yaml:21-29** — `entity_ticker_map` contains NVIDIA→NVDA, TSM, ASML, MU, AMAT, AMD, SSNLF. It does **not** contain AAPL or MSFT. So the source of AAPL/MSFT is **not** entity_ticker_map; it is **propagation**: the supply chain DB (or news-discovered links) returns AAPL and MSFT as propagation targets, and they are added to `extended_universe` and `prices_dict` after price verification.

**Code path that introduces AAPL/MSFT:** Propagation in **SignalEngine._generate_backtest()** (signal_engine.py:255-309): propagated targets from the supply chain / propagator include AAPL and MSFT; they are price-verified, added to `extended_universe`, and `prices_dict` is mutated (line 309). Scores are computed for them; they can rank in top-N; **PortfolioEngine** builds intent from the top-N of `gated_scores.keys()`, so intent ends up as `['TSM', 'AAPL', 'MSFT']`. The pipeline never restricts intent to the originally requested `tickers` parameter.

**One-line fix:** After `portfolio_engine.build()` in **target_weight_pipeline.py**, restrict intent to the requested universe: set intent tickers and weights to only those in the original `tickers` parameter (e.g. filter `intent.tickers` to `[t for t in intent.tickers if t in tickers]`, and build the returned weights Series over `universe = tickers` instead of `universe = list(prices_dict.keys())` so that only requested tickers appear in the output).

---

## Bug 2 Deep Diagnosis

**Context:** Bug 2 fix was applied to target_weight_pipeline.py (restrict weights to requested universe after portfolio_engine.build()). run_execution.py mock output still shows `Intent: ['TSM', 'AAPL', 'MSFT']` with Core 7 --tickers. Diagnosis below. Evidence discipline: file:line. No code — document only.

---

### 1. run_execution.py — what prints "Intent:" and where that variable is set

- **Line that prints Intent:** **scripts/run_execution.py:389** — `print(f"  Intent:      {intent.tickers}", flush=True)`. The variable printed is **intent.tickers** (the `intent` object’s `tickers` attribute).
- **Where intent is set:** There are two branches.
  - **With --rebalance (lines 241-254):** intent is built from the **cache** (outputs/last_valid_weights.json). **Line 247:** `target_weights_dict = cache.get("weights") or {}`. **Line 253:** `intent_tickers = [t for t, w in target_weights_dict.items() if float(w) > 0]`. **Line 254:** `intent = SimpleNamespace(tickers=intent_tickers, weights=dict(optimal_weights_series))`. So **intent does not come from compute_target_weights() or portfolio_engine.build()** — it comes from the **previously saved weights** in the cache. The list of tickers with positive weight is taken directly from the cache’s keys.
  - **Without --rebalance (lines 255-268):** **Line 256:** `optimal_weights_series = compute_target_weights(...)`. **Line 267:** `intent_tickers = list(optimal_weights_series[optimal_weights_series > 0].index)`. **Line 268:** `intent = SimpleNamespace(tickers=intent_tickers, weights=optimal_weights_series.to_dict())`. So in this branch intent is derived from the **return value** of compute_target_weights() (the Series index of positive-weight entries).

The failing test (TEST 3) was run **with --rebalance** (task6_validation.md: “Command run: … --mode mock **--rebalance**”). So the code path that produced `Intent: ['TSM', 'AAPL', 'MSFT']` is the **--rebalance** branch. intent_tickers is set at **line 253** from the cache; it is **not** set from compute_target_weights() or portfolio_engine.build().

---

### 2. target_weight_pipeline.py — what compute_target_weights returns and where the fix is

- **Does it call portfolio_engine.build() and return its output?** **Yes**, but only indirectly. **src/core/target_weight_pipeline.py:249** — `intent = portfolio_engine.build(as_of, gated_scores, portfolio_context)`. The function does **not** return the intent object. It uses intent only to build the **weights**: lines 253-264 build a `weights` dict restricted to `requested_set` (the `tickers` parameter), renormalize, and **line 264:** `return pd.Series(weights).reindex(list(tickers), fill_value=0.0)`. So compute_target_weights() returns a **pd.Series of weights** indexed by the requested tickers only. It does **not** return the raw Intent; the caller (run_execution) never sees intent.tickers from the pipeline.
- **Where the universe-restriction fix is:** **target_weight_pipeline.py:251-264.** The fix filters the **weights** to `requested_set` (line 254: `weights = {t: intent.weights.get(t, 0.0) for t in requested_set}`) and returns a Series indexed by `list(tickers)` (line 264). So the **returned Series** is restricted to the requested universe.
- **Is it filtering the correct object?** It filters the **weights** that are returned. That is correct for the **non-rebalance** path in run_execution: when run_execution calls compute_target_weights() (line 256), it then sets `intent_tickers = list(optimal_weights_series[optimal_weights_series > 0].index)` (line 267). Since optimal_weights_series is now indexed only by requested tickers, intent_tickers can only contain requested tickers. So the pipeline fix **is** on the correct code path for the **non-rebalance** path. It does **not** run when **--rebalance** is used, because with --rebalance run_execution **does not call** compute_target_weights() at all (see lines 241-254).

---

### 3. run_execution.py does not call portfolio_engine.build() directly

run_execution.py does **not** call portfolio_engine.build() directly. It either (a) calls compute_target_weights() (non-rebalance) or (b) reads the cache (rebalance). The issue is that in case (b), the **intent** is built in run_execution itself from the cache (lines 253-254), and the cache can contain tickers from an older run (e.g. TSM, AAPL, MSFT). No pipeline code runs in that branch, so the universe filter in target_weight_pipeline never applies.

---

### Summary and correct fix location

| Item | Detail |
|------|--------|
| **Exact file:line that produces the Intent variable in mock output** | **scripts/run_execution.py:253** — `intent_tickers = [t for t, w in target_weights_dict.items() if float(w) > 0]` (when --rebalance). That list is assigned to intent.tickers at line 254 and printed at line 389. |
| **Is the universe filter in compute_target_weights() on the correct code path?** | **Only for the non-rebalance path.** For the path that actually failed (--rebalance), compute_target_weights() is **not** called; intent is built from the cache in run_execution.py, so the pipeline filter never runs. |
| **Correct location for the filter that affects the Intent printed by run_execution.py** | **scripts/run_execution.py**, in the **--rebalance** block. After building intent_tickers from the cache (line 253), restrict it to the requested universe: **line 253** (or a new line immediately after) — filter intent_tickers so that only tickers in the `tickers` variable (the requested Core 7 list from --tickers) are included. E.g. intent_tickers = [t for t, w in target_weights_dict.items() if float(w) > 0 **and t in tickers**], or intent_tickers = [t for t in intent_tickers if t in tickers] after line 253. |
| **One-line fix description** | In **run_execution.py** in the --rebalance branch, when building intent_tickers from the cache (line 253), restrict to the requested tickers list (e.g. intersect with `tickers`) so that intent.tickers and the printed Intent contain only tickers from --tickers, not stale tickers from the cache. |

---

## Task 6 Fix Validation — 2026-02-21

**Context:** Two fixes applied in commit fbea950. Re-run of TEST 1 (ML model load) and TEST 2 (Intent restricted to requested universe) from task6_validation.md.

### TEST 1 — ML model loads (was failing with model_name kwarg error)

**Command run:** `python scripts/generate_daily_weights.py > daily_weights2.txt 2>&1`

#### Full contents of daily_weights2.txt

```
[Pipeline] Loaded config: C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\config\model_config.yaml
[Pipeline] Active model: ridge
date,ticker,target_weight,latest_close,notional_units

2026-02-21,NVDA,0.0,184.97000122070312,0

2026-02-21,AMD,0.0,203.0800018310547,0

2026-02-21,TSM,0.3333333333333333,364.2000122070313,91

2026-02-21,ASML,0.3333333333333333,600.35498046875,55

2026-02-21,MU,0.0,53.8650016784668,0

2026-02-21,AMAT,0.3333333333333333,107.4113998413086,310

2026-02-21,INTC,0.0,28.11549949645996,0
```

#### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) No "ML model load failed" warning in output | **PASS** | Output has `[Pipeline] Loaded config` and `[Pipeline] Active model: ridge`; no "ML model load failed" line. |
| (b) CSV table present with Core 7 tickers | **PASS** | CSV has tickers: NVDA, AMD, TSM, ASML, MU, AMAT, INTC. |
| (c) Exit code 0 | **PASS** | Script exited 0. |

**TEST 1:** PASS (all checks)

---

### TEST 2 — Intent restricted to requested universe (was returning AAPL/MSFT)

**Command run:** `python scripts/run_execution.py --tickers NVDA,AMD,TSM,ASML,MU,AMAT,INTC --mode mock --rebalance > mock_run_t6b.txt 2>&1`

#### Full contents of mock_run_t6b.txt

```
2026-02-21 17:12:47 - ai_supply_chain - INFO - MockExecutor initialized with capital: $100,000.00
--- Canonical execution (mock): rebalance (drift threshold) ---
  As-of:       2026-02-16
  Account:     100,000.00
  Intent:      ['TSM', 'AAPL', 'MSFT']
  Executable:  1
  BUY 91 TSM (delta_w=+33.33% drift=-100.0%)
  (Mock: no orders submitted.)
```

#### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) Intent list contains only tickers from Core 7 — no AAPL, MSFT, GOOGL, SPY | **FAIL** | Intent line: `Intent:      ['TSM', 'AAPL', 'MSFT']`. AAPL and MSFT appear. |
| (c) No traceback | **PASS** | No traceback in output. |

**TEST 2:** FAIL (check b)

#### Intent line (paste)

```
  Intent:      ['TSM', 'AAPL', 'MSFT']
```

---

### Overall verdict

**Overall verdict:** Not all fixes confirmed. **Failed:** TEST 2(b) — Intent list still contains AAPL and MSFT; not restricted to Core 7. **Confirmed:** TEST 1 (ML model load) — no "ML model load failed" warning; CSV with Core 7; exit 0.

---

## Task 6 Final Validation — 2026-02-21

**Context:** Final fix applied in commit bcbdb03 to `scripts/run_execution.py` line 253. Re-run of TEST 2 only (TEST 1 already confirmed).

**Command run:** `python scripts/run_execution.py --tickers NVDA,AMD,TSM,ASML,MU,AMAT,INTC --mode mock --rebalance > mock_run_t6c.txt 2>&1`

### Full contents of mock_run_t6c.txt

```
2026-02-21 17:33:22 - ai_supply_chain - INFO - MockExecutor initialized with capital: $100,000.00
--- Canonical execution (mock): rebalance (drift threshold) ---
  As-of:       2026-02-16
  Account:     100,000.00
  Intent:      ['TSM']
  Executable:  1
  BUY 91 TSM (delta_w=+33.33% drift=-100.0%)
  (Mock: no orders submitted.)
```

### TEST 2 result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) Intent list contains only tickers from Core 7 — no AAPL, MSFT, GOOGL, SPY | **PASS** | Intent: `['TSM']`. Only TSM; all from Core 7 (NVDA, AMD, TSM, ASML, MU, AMAT, INTC). |
| (c) No traceback | **PASS** | No traceback in output. |

### Intent line from output

```
  Intent:      ['TSM']
```

### Overall verdict

**TASK 6 FULLY CONFIRMED**
