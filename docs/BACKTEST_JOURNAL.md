# Backtest Journal

**Last Updated:** 2026-01-29

Execution and portfolio assumptions, safety audits, path-dependency safeguards, and results for the Technical Library Master Score backtest (`scripts/backtest_technical_library.py`). Indicator math is in `TECHNICAL_SPEC.md`.

---

## 1. Execution Timing

| Setting | Value |
|--------|--------|
| **Execution** | **Next-Day Open** — Orders filled at the Open of the first trading day after the signal (Monday close). No look-ahead. |
| **First-day return** | Open-to-Close: `(Close − Open) / Open` on entry day. |
| **Subsequent days** | Close-to-Close percent change. |

---

## 2. Transaction Costs

| Setting | Value |
|--------|--------|
| **Slippage + Commission** | **0.15% per trade** (15 bps). Deducted from portfolio return on rebalance dates. |
| **Code** | `FRICTION_BPS = 15` in `scripts/backtest_technical_library.py`. |

---

## 3. Position Sizing

| Setting | Value |
|--------|--------|
| **Method** | **Inverse Volatility Weighting** — weight ∝ `1 / (ATR_norm + ε)`; higher risk → smaller allocation. |
| **Volatility proxy** | **ATR_norm** from Technical Library; **ATR from Signal Day − 1** (no same-day volatility leak). |
| **Normalization** | Active positions sum to 100%. |

---

## 4. Systemic Risk & 3-State Regime (Overlay)

| Setting | Value |
|--------|--------|
| **Benchmark** | SPY. |
| **3-State Regime** | hmmlearn Gaussian HMM (n_components=3): **BULL** (high mean, low vol) → BULL_WEIGHTS; **BEAR** (negative mean, high vol) → DEFENSIVE_WEIGHTS; **SIDEWAYS** (mean ~0) → SIDEWAYS_WEIGHTS, position × 0.5. |
| **Bear Rule (CASH_OUT)** | **Strictly enforced:** CASH_OUT only when **Regime == BEAR and SPY &lt; 200-SMA** (dual-confirmation; avoids Volatile Bull shake-out). |
| **Sideways Rule** | When regime = SIDEWAYS, **signals_df × 0.5** to reduce chop risk. |
| **Kill-Switch mode** | `cash` = 100% cash; `half` = 50% position size (when SPY &lt; 200-SMA and not already CASH_OUT from regime). |
| **When SPY missing** | Kill-switch off; regime fallback unavailable. |

---

## 5. Critical Audit (Safety)

- **Signal lag:** Position × return uses **no `.shift(1)`**. `positions_df` = weight at **start of day D**; return = during D. Entry is Next-Day Open — no look-ahead.
- **Mid-week exit:** If single-day return ≤ `DAILY_EXIT_PCT` (e.g. −5%), position set to 0 from that day to end of block. Entry Mondays-only; exit any weekday.
- **Benchmark alignment:** SPY reindexed to universe `all_dates` with ffill; same timezone (tz-naive). No timestamp leakage.

---

## 6. Path Dependency Safeguards

- **ATR sizing lag:** Inverse-volatility uses **ATR_norm from Signal Day − 1** (`row_sizing = ind.iloc[-2]` when `len(ind) >= 2`).
- **Mid-week cash:** Exited weight is **not** reallocated to remaining stocks. Portfolio return = `sum(position_i * return_i)`; sum of positions can drop below 1.0 after exits (no “teleport” of cash).

**2022 stress test:** Full year: `--start 2022-01-01 --end 2022-12-31`. If too heavy, run four quarters and aggregate: `(1 + R_Q1) * (1 + R_Q2) * (1 + R_Q3) * (1 + R_Q4) - 1`.

---

## 7. How to Run

```bash
# Full 2022 (5 tickers, top-3)
python scripts/backtest_technical_library.py --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3 --start 2022-01-01 --end 2022-12-31

# Dynamic weighting: regime (HMM), rolling (PyPortfolioOpt), or ml (RF+CV)
python scripts/backtest_technical_library.py --weight-mode regime --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3
python scripts/backtest_technical_library.py --weight-mode rolling --rolling-method max_sharpe --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3
python scripts/backtest_technical_library.py --weight-mode rolling --rolling-method hrp --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3
python scripts/backtest_technical_library.py --weight-mode ml --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3

# News overlay (0.8 Technical + 0.2 News Composite); [STATE] shows News Buzz T/F
python scripts/backtest_technical_library.py --news-dir data/news --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3

# Skip Safety Report
python scripts/backtest_technical_library.py --no-safety-report ...
```

Logs: `outputs/backtest_master_score_YYYYMMDD_HHMMSS.txt`.

---

## 7a. Feature Update: Dynamic Weighting

- **--weight-mode:** `fixed` (default), `regime`, `rolling`, or `ml`. **--rolling-method:** `max_sharpe` (EfficientFrontier) or `hrp` (Hierarchical Risk Parity) when `--weight-mode rolling`. Inverse Volatility Sizing and Next-Day Open execution rules remain strictly enforced regardless of weight mode.
- **Safety:** Weight calculation for signal date T uses only data from T−1 or earlier (no look-ahead). Rolling history and ML training use only data ≤ Monday (signal date).

---

## 7b. Model Validation & Safety Audit

- **[STATE] log:** When `--weight-mode regime` or `--news-dir` is set, the backtest prints per rebalance: `[STATE] {Date} | Regime: B/E/S | News Buzz: T/F/- | Action: Trade/Cash`. **Regime:** B = Bull, E = Bear, S = Sideways. **News Buzz:** T/F only when news data is active (`--news-dir`); otherwise `-`. **Action:** Trade = hold positions (possibly scaled); Cash = 100% cash (CASH_OUT).
- **[HMM TRANSITION MATRIX]:** Logged **on the first Monday** (once per run) when `--weight-mode regime` and verbose. Diagonals printed with note: target &gt; 0.80 for stable regime (Persistence Check).
- **Regime sanity check:** `[REGIME] Date: {monday}, HMM State: {state}, Mean Return: {mu}, Volatility: {sigma}`. Use to verify BEAR has lower mean and higher vol than BULL; SIDEWAYS moderate.
- **Weight floor (rolling mode):** PyPortfolioOpt `weight_bounds=(0.10, 0.50)`; HRP clip then renormalize. No category &lt; 10% or &gt; 50%.
- **ML fallback:** `[ML] CV R²: {value}`; if R² &lt; 0, fallback to fixed weights and log `[ML] Fallback to fixed weights (R² < 0).`
- **Overlay formula:** When `--news-dir` is set, **Final_Score = 0.8 × Technical_Score + 0.2 × News_Composite** (config `news_weight: 0.20`). News composite uses FinBERT + EventDetector + strategies A–D (Buzz, Surprise, Sector Relative, Event-Driven).

---

## 7c. Quant Health Checks (Pre–Backtest)

Before triggering the final 2022 backtest, verify these three checks in code and logs:

| Check | What to verify | Where |
|-------|----------------|--------|
| **1. Persistence (Transition Matrix)** | Logs print the HMM transition matrix **once per run** (on first regime detection). **High diagonals (&gt; 0.80)** = stable regime (e.g. Bull today → Bull tomorrow); **low diagonals** (e.g. ~0.40) = flip-flopping → transaction cost risk. | `scripts/backtest_technical_library.py`: `[HMM TRANSITION MATRIX]` and `Diagonals: [...] (target > 0.80 for stable regime)` when `--weight-mode regime` and verbose. |
| **2. Surprise Lag Rule (Strategy B)** | Strategy B (News Surprise) uses a **1-day lag** for the baseline: **baseline = previous 30 days only**, excluding `as_of`. Compare Monday’s (or recent 7d) sentiment to the average of the **prior** 30 days so today’s news does not “wash out” the surprise. | `src/signals/news_engine.py`: `strategy_surprise` — `baseline_vals` uses `cutoff_baseline <= d < as_of` (strictly before `as_of`). |
| **3. Kill Switch Dual-Confirmation** | CASH_OUT only when **both** (a) regime = **BEAR** and (b) **SPY &lt; 200-SMA**. This avoids being shaken out in a “Volatile Bull” (HMM sees Bear from high vol while trend is still up). | `scripts/backtest_technical_library.py`: `if regime_state == "BEAR" and spy_below_sma200` → CASH_OUT. |

**Summary:** (1) Check transition matrix in backtest log; (2) Surprise baseline is lagged in `news_engine.py`; (3) BEAR + SPY &lt; 200-SMA required for cash-out.

---

## 8. Results Summary

| Period | Sharpe | Total return | Max drawdown |
|--------|--------|--------------|--------------|
| Full 2022 (5 tickers, top-3) | −0.75 | −33.64% | −48.25% |
| Oct–Nov 2022 | 0.11 | +14.94% | −12.39% |

Master Score uses category-weighted indicators (Trend 40%, Momentum 30%, Volume 20%, Volatility 10%); legacy technical-only used momentum + volume + RSI. Over 2022 bear, both lost; Master Score had higher return but lower Sharpe in Oct–Nov vs legacy.

---

## 8a. Model vs. Model (Q2 2022)

**Hypothesis:** HRP (Hierarchical Risk Parity) should have **lower Max Drawdown** than max_sharpe (EfficientFrontier) in Q2 2022 because HRP does not overfit to noisy rallies.

**Commands (run locally to populate results):**

```bash
# Q2 2022 — max_sharpe (EfficientFrontier)
python scripts/backtest_technical_library.py --weight-mode rolling --rolling-method max_sharpe --start 2022-04-01 --end 2022-06-30 --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3 --no-safety-report

# Q2 2022 — hrp (Hierarchical Risk Parity)
python scripts/backtest_technical_library.py --weight-mode rolling --rolling-method hrp --start 2022-04-01 --end 2022-06-30 --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3 --no-safety-report
```

**Results (Q2 2022, 5 tickers, top-3, rolling weights with 10%–50% floor):**

| Method       | Sharpe | Total return | Max drawdown |
|-------------|--------|--------------|--------------|
| max_sharpe  | *run above* | *run above* | *run above* |
| hrp         | *run above* | *run above* | *run above* |

After running, fill the table and compare: if HRP shows a less negative max drawdown, the hypothesis is supported.

---

## 9. Autonomous Run: 2022 Regime + News Overlay

**Objective:** Execute full 2022 backtest with 3-State Regime + News Alpha overlay and verify results vs SPY, HMM diagonals, and Cash-Out during Q2/Q4 2022 drawdowns.

**Intended command (Bash/PowerShell):**

```bash
# Bash
python scripts/backtest_technical_library.py --start-date 2022-01-01 --end-date 2022-12-31 --weight-mode regime --news-dir data/news --tickers AAPL,MSFT,NVDA,AMD,GOOGL,TSLA,META --top-n 3

# PowerShell (same; --start-date/--end-date are aliases for --start/--end)
python scripts/backtest_technical_library.py --start 2022-01-01 --end 2022-12-31 --weight-mode regime --news-dir data/news --tickers AAPL,MSFT,NVDA,AMD,TSLA --top-n 3
```

**Notes:**

- **CLI:** Script uses `--start` / `--end` (aliases: `--start-date` / `--end-date`). `--news-weight` is in `config/technical_master_score.yaml` (0.20). Kill-switch mode is `KILL_SWITCH_MODE` in script (e.g. `cash`).
- **Data:** Tickers with CSV in repo (as of audit): AAPL, MSFT, NVDA, AMD, TSLA (from sp500/nasdaq/forbes2000/csv). GOOGL, META may be missing; add CSV or drop from list. **SPY:** Run `scripts/download_spy_yfinance.py` (network) or `scripts/generate_spy_placeholder.py` (no network) to create `data/stock_market_data/sp500/csv/SPY.csv`; without it, Kill-Switch and HMM are OFF.
- **News overlay:** With `--news-dir`, FinBERT (ProsusAI/finbert) is loaded on first use; if HuggingFace is unreachable (e.g. proxy), the run can hang. Run without `--news-dir` for regime-only, or ensure network access for full overlay.
- **HMM check:** When SPY data exists and `--weight-mode regime`, logs print `[HMM TRANSITION MATRIX]` on the first Monday. If diagonals are &lt; 0.60, consider adjusting HMM in `weight_model.py` (e.g. `n_iter`, `random_state`, or more history).

**Result verification (run locally and fill):**

| Metric | Strategy (2022) | SPY 2022 (reference) |
|--------|------------------|----------------------|
| Sharpe | *run locally* | ~−0.72 |
| Total return | *run locally* | ~−18.1% |
| Max drawdown | *run locally* | ~−25.3% |

**Cash-Out rule:** Triggered when **Regime == BEAR and SPY &lt; 200-SMA**. With SPY data, expect Cash/CASH_OUT in logs during Q2 2022 and Q4 2022 drawdowns when the HMM is BEAR and SPY is below 200-SMA.

**Autonomous run outcome (environment):** Full 2022 run may time out in CI; run the command above locally. With SPY CSV in place, Kill-Switch and HMM regime are active (see Local Run Audit below).

---

## 9a. Local Run Audit: Environment & Dependencies

**Step 1 — SPY index data**

- **Check:** `data/stock_market_data/sp500/csv/SPY.csv` exists.
- **If missing:** Run once (with network): `python scripts/download_spy_yfinance.py` (downloads SPY 2015-01-01 to 2023-01-01 via yfinance).  
  Or (no network): `python scripts/generate_spy_placeholder.py` (synthetic SPY 2015–2022 for Kill-Switch and HMM; replace with real data when possible).

**Step 2 — FinBERT (news overlay)**

- **Check:** With `--news-dir`, the backtest loads FinBERT on first use. If HuggingFace is unreachable (e.g. proxy), the run can hang or raise after retries.
- **Offline:** Place FinBERT in `./models/finbert` (clone HuggingFace `ProsusAI/finbert` or copy from cache). `news_engine.py` checks this path first and uses `local_files_only=True`.
- **Skip news:** Run without `--news-dir` for regime-only (no FinBERT).

**Local Run Audit confirmation**

| Check | Status |
|-------|--------|
| SPY data used for Kill-Switch | **Yes** when `data/stock_market_data/sp500/csv/SPY.csv` exists. Log shows `Kill-Switch: ON (SPY < 200 SMA -> cash)`. |
| SPY data used for HMM regime | **Yes** when SPY CSV exists. Log shows `[STATE] ... | Regime: B/E/S | ...` (B=Bull, E=Bear, S=Sideways). |
| [HMM TRANSITION MATRIX] in logs | Printed on **first Monday** when `--weight-mode regime` and SPY loaded. Audit diagonals: &lt; 0.5 → High Volatility Warning; &gt; 0.80 → stable. |
| Dual-Confirmation (Action: Cash) | Scan logs for Q2 and Q4 2022: `Action: Cash` when Regime E (Bear) and SPY &lt; 200-SMA. |

**Final results (fill after local run)**

After a full 2022 run, update the table in §9 and add:

- **Sharpe:** *value*
- **Total return:** *value*
- **Max drawdown:** *value*
- **HMM diagonals (first Monday):** *e.g. [0.85, 0.82, 0.79] — stable / or &lt; 0.5 — High Volatility Warning*
- **Cash-Out in Q2 2022:** Yes/No *(list dates if Yes)*
- **Cash-Out in Q4 2022:** Yes/No *(list dates if Yes)*

---

## 10. Safety Report (Terminal)

Run without `--no-safety-report` to print the Safety Report after each backtest (signal lag, mid-week exit, benchmark alignment).
