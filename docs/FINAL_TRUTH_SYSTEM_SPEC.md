# Final Truth System — Design Specification (Absolute vs Residual vs Hedged)

**Role:** Architect — design and specification only. No implementation code.  
**Audience:** Engineer implementing interfaces and workflows.  
**Evidence discipline:** Every claim cites file and line or is labeled ASSUMPTION/UNKNOWN.

---

## Verified Facts (Repo Audit)

| Fact | Evidence |
|------|----------|
| Backtest calls `SignalEngine` | `scripts/backtest_technical_library.py` line 189: `signal_engine = SignalEngine()`; scoring via `target_weight_pipeline` which uses `model_path` from config |
| Model path source | `config/model_config.yaml` line 33: `model_path: ...ridge_optimized_20260227_230227.pkl` |
| Residual vs absolute = config only | `src/models/train_pipeline.py` lines 68–96: `residual_target` in `training` controls whether `forward_return = forward_return - (beta * smh_fwd)`; backtest just loads whatever .pkl is at `model_path` |
| Backtest CLI | `scripts/backtest_technical_library.py` lines 586–598: `--out-json`, `--no-llm` exist |
| 46-ticker universe, SSNLF excluded | `config/data_config.yaml` watchlist (lines 31–74); `scripts/backtest_technical_library.py` lines 40–42, 669–673: `BACKTEST_EXCLUDE = {"SSNLF"}` |
| Train period | `config/model_config.yaml` lines 23–26: `train_start: '2022-01-01'`, `train_end: '2023-12-31'` → 2022–2023 in-sample; 2024 out-of-sample per `test_start`/`test_end` |
| Backtest result keys for JSON | `scripts/backtest_technical_library.py` lines 556–568 (return dict), 717–721 (`_json_subset`): `sharpe`, `total_return`, `max_drawdown`, `n_rebalances`, `period_start`, `period_end`, `tickers`, `weekly_returns` |

---

## 1. Interface Contract: `src/core/hedger.py`

### 1.1 Class and Constructor

**Class name:** `Hedger`

**Location:** `src/core/hedger.py`

**`__init__` signature:**

```text
__init__(
    self,
    hedge_ratio: float = 1.0,
    annual_borrow_rate: float = 0.05,
    periods_per_year: int = 52,
) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hedge_ratio` | float | 1.0 | Fraction of portfolio beta to hedge (0 = no hedge, 1 = full). |
| `annual_borrow_rate` | float | 0.05 | Annual cost of borrowing (e.g. 0.05 = 5%). |
| `periods_per_year` | int | 52 | Periods per year for cost annualization (52 = weekly). |

No raises in `__init__`; invalid values (e.g. negative) may be rejected in `apply_hedge()` or documented as undefined behavior.

---

### 1.2 Method: `apply_hedge`

**Signature:**

```text
def apply_hedge(
    self,
    portfolio_returns: Union[pd.Series, np.ndarray],
    smh_returns: Union[pd.Series, np.ndarray],
    portfolio_beta: Optional[float] = None,
) -> HedgeResult
```

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `portfolio_returns` | pd.Series or np.ndarray | Period returns of the portfolio (e.g. weekly). Index/dates must align if Series. |
| `smh_returns` | pd.Series or np.ndarray | Period returns of SMH (hedge instrument) over the same period. |
| `portfolio_beta` | float or None | Portfolio beta to SMH. If None, use 1.0. |

**Output:** Instance of `HedgeResult` (see §1.3).

**Raises:**

- `ValueError`: If `portfolio_returns` or `smh_returns` is empty after alignment.
- `ValueError`: If, after alignment, the two return series have different lengths and alignment by index is not possible (see §1.5 edge cases).

No other exceptions required; document that NaN/inf in inputs produce NaN in outputs or are left to implementation policy.

---

### 1.3 Dataclass: `HedgeResult`

**Fields (all required, types exact):**

| Field | Type | Description |
|-------|------|-------------|
| `hedged_returns` | np.ndarray | Aligned time series of hedged period returns (same length as aligned inputs). |
| `sharpe` | float | Annualized Sharpe of `hedged_returns` (see §1.4). |
| `total_return` | float | Total compounded return (1 + r).cumprod()[-1] - 1. |
| `max_drawdown` | float | Maximum drawdown from cumulative wealth (see §1.4). |
| `n_periods` | int | Length of `hedged_returns`. |
| `portfolio_beta_used` | float | Beta actually used (input or default 1.0). |

Use `dataclasses.dataclass` or equivalent; immutable preferred.

---

### 1.4 Hedge Math and Metric Formulas

**Hedged return (per period t):**

```text
hedged_r_t = portfolio_r_t
             - (hedge_ratio × portfolio_beta × smh_r_t)
             - (annual_borrow_rate × hedge_ratio / periods_per_year)
```

- `portfolio_r_t`, `smh_r_t`: aligned period returns.
- Cost term: `(annual_borrow_rate * hedge_ratio / periods_per_year)` is the per-period borrow cost (e.g. weekly if `periods_per_year=52`).

**Metrics from `hedged_returns`** (project convention — see `docs/STRATEGY_MATH.md`):

- **Sharpe (annualized):**  
  `sharpe = (mean(hedged_returns) * periods_per_year) / (std(hedged_returns) * sqrt(periods_per_year))`  
  If `std(hedged_returns) == 0`, then `sharpe = 0.0` (or document: undefined).

- **Total return:**  
  `cumulative = (1 + hedged_returns).cumprod()`  
  `total_return = cumulative[-1] - 1`

- **Max drawdown:**  
  `running_max = cumulative.expanding().max()`  
  `drawdown = (cumulative - running_max) / running_max`  
  `max_drawdown = drawdown.min()`  
  (So `max_drawdown` is non-positive.)

Reference: `docs/STRATEGY_MATH.md` lines 186–209 (Sharpe, total return, max drawdown). Use `periods_per_year` (e.g. 52) in place of 252 where the doc uses daily.

---

### 1.5 Edge Cases

| Case | Required behavior |
|------|-------------------|
| **Different lengths (no index)** | If inputs are raw arrays with different lengths: raise `ValueError` with a message that alignment is impossible; do not truncate silently. |
| **Different lengths (with index)** | If both are `pd.Series` with a common index: align on index; use the intersection of dates; drop NaNs for that intersection. Result length = length of aligned series. If intersection is empty, raise `ValueError`. |
| **hedge_ratio = 0** | Hedged return = portfolio return minus zero cost: `hedged_r_t = portfolio_r_t`. No SMH term, no cost term. |
| **portfolio_beta is None** | Use `portfolio_beta = 1.0` for the hedge term. `portfolio_beta_used` in `HedgeResult` must be 1.0. |
| **All-zero smh_returns** | Hedge term is 0; hedged return = portfolio return minus cost term only. |
| **NaN in inputs** | Document: either propagate NaN in `hedged_returns` and then metrics (e.g. Sharpe) may be NaN, or drop NaN periods before computing metrics; spec prefers explicit drop and document. |

---

## 2. Interface Contract: `scripts/generate_final_truth_table.py`

### 2.1 Purpose

Read six pre-produced backtest JSON files (FINAL_*.json), plus SPY and SMH price data; optionally apply the hedger to the “Hedged” track; produce one machine-readable table and one human-readable report with in-sample/out-of-sample labeling.

### 2.2 Inputs

| Input | Description | Source (evidence) |
|-------|-------------|-------------------|
| 6× FINAL_*.json | Backtest outputs from six runs (see §2.4). | Engineer-defined naming; e.g. `FINAL_absolute.json`, `FINAL_residual.json`, `FINAL_hedged.json` (or equivalent). |
| SPY CSV | Daily (or weekly) OHLCV for SPY. | Path from data config: `config/data_config.yaml` → `data_sources.data_dir`; CLAUDE.md: `DATA_DIR` env or `trading_data/`; SPY under `stock_market_data` (e.g. `sp500/csv/SPY.csv`). Resolve via same logic as backtest: `find_csv_path(data_dir, "SPY")`. |
| SMH CSV | Same for SMH. | `config/model_config.yaml` line 28: `smh_benchmark_path: trading_data/benchmarks/SMH.csv`. If relative, resolve against `DATA_DIR` or project root per existing convention. |

**Data directory resolution (no new invention):** Use the same pattern as `scripts/backtest_technical_library.py` (lines 610–616): `os.getenv("DATA_DIR")`; if unset, load from `config/data_config.yaml` → `data_sources.data_dir`. Then for SPY: `{data_dir}/stock_market_data` + `find_csv_path(..., "SPY")`; for SMH: use `smh_benchmark_path` from `model_config.yaml` (absolute or relative to DATA_DIR/project root).

### 2.3 Outputs

1. **Machine-readable:** `outputs/FINAL_TRUTH_TABLE.json`  
2. **Human-readable:** `outputs/FINAL_TRUTH_REPORT.md`

Output directory `outputs/` must be created if missing.

---

### 2.4 JSON Schema: `outputs/FINAL_TRUTH_TABLE.json`

Top-level object:

```text
{
  "generated_at": "<ISO8601 datetime>",
  "data_sources": {
    "spy_path": "<resolved path>",
    "smh_path": "<resolved path>",
    "data_dir": "<resolved data_dir>"
  },
  "tracks": [
    {
      "id": "<string: e.g. absolute|residual|hedged>",
      "label": "<human label>",
      "model_type": "absolute" | "residual" | "hedged",
      "in_sample_years": [2022, 2023],
      "out_of_sample_years": [2024],
      "metrics": {
        "sharpe": <float>,
        "total_return": <float>,
        "max_drawdown": <float>,
        "n_rebalances": <int>,
        "period_start": "<date string>",
        "period_end": "<date string>"
      },
      "by_year": {
        "<YYYY>": {
          "sharpe": <float>,
          "total_return": <float>,
          "max_drawdown": <float>,
          "sample_type": "in_sample" | "out_of_sample"
        }
      },
      "source_file": "<basename of FINAL_*.json used>"
    }
  ],
  "universe": {
    "tickers": ["<list of tickers>"],
    "excluded": ["SSNLF"]
  }
}
```

- Each track corresponds to one FINAL_*.json (and for “hedged”, that JSON is the residual run, then hedger is applied; see §2.6).
- `by_year`: optional; if present, yearly metrics must be labeled `in_sample` or `out_of_sample` using `train_start`/`train_end` from model config (2022–2023 = in-sample, 2024 = out-of-sample). **This labeling is mandatory in the report (§2.5).**
- `universe.excluded`: from `BACKTEST_EXCLUDE` (`scripts/backtest_technical_library.py` lines 40–42): `["SSNLF"]`.

---

### 2.5 Markdown Report: `outputs/FINAL_TRUTH_REPORT.md`

**Required structure:**

1. **Title:** e.g. `# Final Truth Table — Absolute vs Residual vs Hedged`
2. **Generated:** ISO8601 timestamp.
3. **Table:** One table with columns:
   - Track (e.g. Absolute, Residual, Hedged)
   - Sharpe
   - Total return (%)
   - Max drawdown (%)
   - N rebalances
   - Period (start–end)
   - In-sample years (e.g. 2022, 2023)
   - Out-of-sample years (e.g. 2024)
4. **Explicit note:** “2022 and 2023 are in-sample (training period 2022-01-01 to 2023-12-31). 2024 is out-of-sample.”
5. **Look-ahead bias notice:** One sentence: “Results for 2022 and 2023 are in-sample; do not use for forward-looking assessment.”

Table layout (example; exact formatting left to implementation):

```text
| Track    | Sharpe  | Total Return | Max DD   | N Rebal | Period      | In-sample | Out-of-sample |
|----------|---------|--------------|----------|---------|-------------|-----------|---------------|
| Absolute | ...     | ...%         | ...%     | ...     | YYYY-MM-DD  | 2022,2023 | 2024          |
| Residual | ...     | ...%         | ...%     | ...     | YYYY-MM-DD  | 2022,2023 | 2024          |
| Hedged   | ...     | ...%         | ...%     | ...     | YYYY-MM-DD  | 2022,2023 | 2024          |
```

---

### 2.6 Hedged Track

- **Input for hedged metrics:** Use the **residual** run’s `weekly_returns` (and same period for SMH weekly returns).
- **Process:** Load SMH prices from `smh_benchmark_path`, compute weekly returns; align with `weekly_returns` by date; call `Hedger(hedge_ratio=1.0, ...).apply_hedge(portfolio_returns=residual_weekly_returns, smh_returns=smh_weekly_returns, portfolio_beta=1.0)` (or beta from config if available). Use `HedgeResult.sharpe`, `total_return`, `max_drawdown` for the Hedged row.
- **Source file:** Still the residual FINAL_*.json; label track as “Hedged” in report.

---

## 3. Retraining Workflow Spec (Absolute vs Residual)

### 3.1 Track A — Absolute Model

**Goal:** Produce a Ridge model trained on **absolute** forward return (no SMH residual).

**Config changes in `config/model_config.yaml`:**

| Key | Change |
|-----|--------|
| `training.residual_target` | Set to `false` |
| (Optional) `training.model_path` | Do **not** change yet; will point to new file after a successful train. |

**Steps:**

1. Set `residual_target: false`.
2. Run: `python scripts/train_ml_model.py` (or equivalent with project Python).
3. If IC gate passes: script saves new .pkl to `models/saved/ridge_<timestamp>.pkl` and exits 0. If IC gate fails: script does **not** save, exits 1 (see §4).
4. Manually (or via a separate “promote” step) update `training.model_path` to the new absolute model path for running the absolute backtest. Do **not** leave `model_config.yaml` pointing at the absolute model after the Final Truth run (see §3.3).

**Success criteria:**

- `train_ml_model.py` exit code 0.
- New .pkl exists under `model_save_dir`.
- IC ≥ 0.01 (see §4).

---

### 3.2 Track B — Residual Model (Restore Baseline)

**Goal:** Restore the current production setup (residual target, existing residual model).

**Config changes in `config/model_config.yaml`:**

| Key | Value |
|-----|--------|
| `training.residual_target` | `true` |
| `training.model_path` | Restore to current residual model path, e.g. `.../ridge_optimized_20260227_230227.pkl` |

**Success criteria:**

- Backtest and truth-table scripts use the residual model when `model_path` points to this file.
- No permanent switch to the absolute model path in the committed config.

---

### 3.3 Config State Management

- **After all Final Truth runs:** `config/model_config.yaml` must be restored so that:
  - `training.residual_target` is `true`
  - `training.model_path` points to the **residual** model path (current production).
- Engineer must not commit a state where `model_path` points to the absolute model as the default.

---

### 3.4 Look-Ahead Bias and Reporting

- **Training period:** 2022-01-01 to 2023-12-31 (`config/model_config.yaml` lines 23–24).
- **Implication:** Any backtest that includes 2022 or 2023 is **in-sample**; 2024 is **out-of-sample**.
- **Requirement:** All Final Truth outputs (JSON table and Markdown report) must label years explicitly as in-sample (2022, 2023) or out-of-sample (2024). The report must include the look-ahead bias notice in §2.5.

---

## 4. Risk Flags for the Engineer

### 4.1 Do Not Change

- **`scripts/backtest_technical_library.py`:** Do not modify backtest logic, result dict shape, or CLI (`--out-json`, `--no-llm`). Only add calls to the hedger or truth-table script if a separate task explicitly requests it.
- **`config/data_config.yaml`:** Do not change watchlist, benchmark, or data_dir for the Final Truth workflow. Universe and paths stay as-is (46 effective tickers, SSNLF excluded).

### 4.2 Config State

- **End state of `config/model_config.yaml`:** Must be **residual**: `residual_target: true`, `model_path` = residual model. Document in runbook or script comment that “Final Truth” runs must not leave the repo in absolute-model default.

### 4.3 IC Gate (0.01) in `train_ml_model.py`

- **Evidence:** `scripts/train_ml_model.py` line 36: `IC_GATE = 0.01`; lines 98–100: `passed = ic >= IC_GATE`, then print PASS/FAIL and exit 0 or 1; lines 103–110: model is saved only if `passed`.
- **If the absolute model fails the IC gate:** The script must **not** save the model and must exit with non-zero. Engineer must **not** silence this or override the gate to “continue anyway.”
- **Required behavior:** On IC &lt; 0.01, print FAIL and exit 1; do not update `model_path` to a new absolute model. Document in runbook: “If absolute run fails IC gate, do not use that model for Final Truth; report failure and keep residual as baseline.”

---

## 5. Summary

| Component | Deliverable |
|-----------|-------------|
| **hedger** | `src/core/hedger.py`: class `Hedger`, method `apply_hedge`, dataclass `HedgeResult`; hedge formula and metric formulas as above; edge cases as above. |
| **Truth table script** | `scripts/generate_final_truth_table.py`: reads 6× FINAL_*.json + SPY + SMH; writes `outputs/FINAL_TRUTH_TABLE.json` (schema §2.4) and `outputs/FINAL_TRUTH_REPORT.md` (layout §2.5); in-sample/out-of-sample and look-ahead notice mandatory. |
| **Retraining** | Track A: set `residual_target: false`, run train, use new .pkl for absolute backtest only; Track B: restore `residual_target: true` and residual `model_path`. Config must end in residual state. |
| **Risks** | Do not change backtest script or data_config; do not bypass IC gate; do not leave `model_config` pointing at absolute model. |

---

*Spec version: 1.0. Evidence from repo as of 2026-03-01.*
