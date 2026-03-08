# Final Truth System — Validation Report

**Date:** 2026-03-01  
**Scope:** All 8 checks per Validator task (config, Track A/B outputs, hedger, generate script, run).  
**Evidence:** Every PASS/FAIL cites file:line.

---

## CHECK 1: Config Final State

**Run first.** Read `config/model_config.yaml`.

- [x] **training.residual_target == true** — **PASS** (`config/model_config.yaml` line 29: `residual_target: true`).
- [x] **training.model_path** ends with **ridge_optimized_20260227_230227.pkl** — **PASS** (line 33: full path ends with `ridge_optimized_20260227_230227.pkl`).
- [x] No other key under `training` differs from the spec — **PASS** (train_start, train_end, smh_benchmark_path, etc. match docs/FINAL_TRUTH_SYSTEM_SPEC.md).

**CHECK 1: PASSED.**

---

## CHECK 2: Track A Output Files

**Files:** `outputs/FINAL_BASELINE_ABS_2022.json`, `_2023.json`, `_2024.json`.

- [ ] Files exist and parse as valid JSON — **BLOCKED**. Files do not exist (Track A training and backtests were not run; training failed with local sklearn build error).
- All other sub-checks (tickers ≥40, no SSNLF, period_start/end, sharpe/total_return/max_drawdown finite, weekly_returns non-empty) — **BLOCKED**.

**CHECK 2: BLOCKED** (missing outputs; run Track A backtests after fixing training).

---

## CHECK 3: Track B Output Files

**Files:** `outputs/FINAL_RESIDUAL_ALPHA_2022.json`, `_2023.json`, `_2024.json`.

- [ ] Same as Check 2 — **BLOCKED** (files do not exist; Track B backtests not run).

**CHECK 3: BLOCKED.**

---

## CHECK 4: Cross-Track Sanity

- [ ] Track A vs Track B same universe, same period, Track A sharpe ≠ Track B sharpe — **BLOCKED** (no Track A/B outputs).

**CHECK 4: BLOCKED.**

---

## CHECK 5: hedger.py — Interface Compliance

**Read `src/core/hedger.py`.**

- [x] **HedgeResult** is a dataclass with exactly: `hedged_returns` (list[float]), `sharpe`, `total_return`, `max_drawdown`, `n_periods`, `portfolio_beta_used` — **PASS** (lines 19–27).
- [x] **Hedger.__init__**(hedge_ratio=1.0, annual_borrow_rate=0.05, periods_per_year=52) — **PASS** (lines 40–46).
- [x] **apply_hedge**(portfolio_returns, smh_returns, portfolio_beta=None) — **PASS** (lines 49–54; accepts list/ndarray per Union).

**CHECK 5: PASSED.**

---

## CHECK 6: hedger.py — Math Verification

**Hedge formula (exact):**

- `effective_beta = portfolio_beta if portfolio_beta is not None else 1.0` — **PASS** (line 75).
- `weekly_borrow_cost = (annual_borrow_rate * hedge_ratio) / periods_per_year` when hedge_ratio ≠ 0 — **PASS** (lines 81–83).
- `hedge_offset = hedge_ratio * effective_beta * sr` — **PASS** (line 84).
- `hedged = pr - hedge_offset - weekly_borrow_cost` — **PASS** (line 86); offset and cost **subtracted**.
- **hedge_ratio == 0:** hedge_offset = 0, weekly_borrow_cost = 0 — **PASS** (lines 77–79).
- **Sharpe:** `(mean_r * periods_per_year) / (std_r * sqrt(periods_per_year))`; std=0 → sharpe=0 — **PASS** (lines 110–117). Matches STRATEGY_MATH.md structure with 52 instead of 252.
- **Total return:** `cumulative = (1 + arr).cumprod()`, `total_return = cumulative[-1] - 1` — **PASS** (lines 101–102).
- **Max drawdown:** `running_max = maximum.accumulate(cumulative)`, `drawdown = (cumulative - running_max)/running_max`, `max_drawdown = min(drawdown)` — **PASS** (lines 104–108); peak-to-trough on cumulative; result ≤ 0 or NaN when divide-by-zero guarded.
- **ValueError** when len(portfolio_returns) ≠ len(smh_returns) — **PASS** (lines 69–73).
- **ValueError** when hedge_ratio &lt; 0 or &gt; 1.0 — **PASS** (lines 63–66).
- **n_periods == len(hedged_returns)**, **portfolio_beta_used == effective_beta** — **PASS** (lines 117–124).
- **Imports:** stdlib (math, dataclasses), numpy, typing — **PASS** (no extra pip deps).

**CHECK 6: PASSED.**

---

## CHECK 7: generate_final_truth_table.py — Schema and Logic

**Read `scripts/generate_final_truth_table.py`.**

- [x] Loads 6 FINAL_*.json by **explicit hardcoded filenames** (no glob) — **PASS** (FINAL_ABS_FILES, FINAL_RESIDUAL_FILES lists; lines 28–38).
- [x] SMH path from **config/model_config.yaml** `smh_benchmark_path` — **PASS** (_smh_path(model_config), lines 67–73).
- [x] SPY loaded via **find_csv_path**(data_dir, "SPY") — **PASS** (line 161: `find_csv_path(data_dir_str, "SPY")`).
- [x] Hedger(hedge_ratio=1.0, annual_borrow_rate=0.05, periods_per_year=52) — **PASS** (line 139).
- [x] **FINAL_TRUTH_TABLE.json** schema: generated, universe_size, hedge_params, tracks, by_year with 2022/2023/2024, each with sample_type, absolute, residual, hedged_residual — **PASS** (truth_table dict, lines 148–155).
- [x] sample_type 2022/2023 **in_sample**, 2024 **out_of_sample** — **PASS** (line 144).
- [x] Disclaimer block in Markdown: "⚠ LOOK-AHEAD BIAS NOTICE", "2022–2023 data", "OUT-OF-SAMPLE" — **PASS** (lines 186–191).

**CHECK 7: PASSED.**

---

## CHECK 8: Run generate_final_truth_table.py

- [ ] Exit code 0 — **FAIL**. Script exits 1 when any of the 6 FINAL_*.json files are missing (expected until Track A/B backtests are run).
- [ ] outputs/FINAL_TRUTH_TABLE.json and FINAL_TRUTH_REPORT.md written — **BLOCKED** (script exits before writing when inputs missing).
- [ ] No NaN/Inf/None in numeric fields, disclaimer in report — **BLOCKED**.

**CHECK 8: FAILED** (missing inputs; re-run after producing the 6 backtest JSONs).

---

## FINAL VERDICT

**VALIDATION FAILED.**

- **Blocking:** CHECK 2, 3, 4, 8 — Track A and Track B backtest outputs were not produced because **training failed** (local environment: `ImportError` for sklearn `_check_build`). Until training runs successfully and the six FINAL_*.json files exist, Checks 2, 3, 4 and the full run of Check 8 cannot pass.
- **Passed:** CHECK 1 (config), CHECK 5 (hedger interface), CHECK 6 (hedger math), CHECK 7 (generate script schema and logic).

**Required next steps (Engineer/User):**

1. Fix the `wealth` conda environment (reinstall or repair scikit-learn so `train_ml_model.py` runs).
2. Set `config/model_config.yaml` → `training.residual_target: false`.
3. Run `python scripts/train_ml_model.py --skip-tournament`; if IC ≥ 0.01, update `training.model_path` to the new .pkl.
4. Run Track A backtests (2022, 2023, 2024) with `--no-llm` and `--out-json outputs/FINAL_BASELINE_ABS_YYYY.json`.
5. Restore config: `residual_target: true`, `model_path`: `...ridge_optimized_20260227_230227.pkl`.
6. Run Track B backtests (2022, 2023, 2024) with `--out-json outputs/FINAL_RESIDUAL_ALPHA_YYYY.json`.
7. Run `python scripts/generate_final_truth_table.py` and re-validate Checks 2, 3, 4, 8.

---

*Evidence discipline: all findings cite file:line. No code was modified by the Validator.*
