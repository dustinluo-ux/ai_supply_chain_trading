# Interface & Monitoring Layer Spec

**Evidence:** Output schemas from `outputs/regime_status.json`, `outputs/portfolio_state.json`, `outputs/last_valid_weights.json`, `outputs/last_signal.json`, `outputs/ic_monitor.json`, `models/factory_winner.json`, and first line of `outputs/fills/fills.jsonl`. Call site for rebalance alert: `scripts/run_weekly_rebalance.py` (after `log_audit_record`, before `return _exit_code`).

---

## A. scripts/dashboard.py — Streamlit dashboard

### A.1 Panel layout (sections, order)

1. **Header** — Title, as_of timestamp from latest data, manual refresh button.
2. **Regime & risk** — Single row: regime badge, SPY vs SMA200, VIX (from `regime_status.json`).
3. **Portfolio summary** — NAV, cash weight, last NAV fetch time (from `portfolio_state.json`).
4. **Target weights & holdings** — Two columns or tabs: target_weights (from `portfolio_state.json`), holdings (shares, avg_cost) with optional last_valid_weights comparison.
5. **P&L vs SMH benchmark** — Chart (see A.4).
6. **ML status** — factory_winner + ic_monitor sparkline (see A.5).
7. **Last signal snapshot** — Subset of `last_signal.json`: tickers with weight > 0 (score, vol_20d, vol_triggered) in a compact table.
8. **Fills table** — From `fills.jsonl` (see A.6).

### A.2 Data refresh strategy

- **Files to poll:**  
  `outputs/regime_status.json`, `outputs/portfolio_state.json`, `outputs/last_valid_weights.json`, `outputs/last_signal.json`, `outputs/ic_monitor.json`, `models/factory_winner.json`, `outputs/fills/fills.jsonl`.
- **Refresh:** Auto-refresh every **30 seconds** via `time.sleep(30)` then `st.rerun()`. Provide a manual refresh button that triggers immediate `st.rerun()`.
- **Helper:** Implement `load_json(path: Path) -> dict | list | None` that returns parsed JSON or None on missing file / parse error (no crash).

### A.3 Metric labels and formatting

| Source | Field | Label | Format |
|--------|--------|--------|--------|
| portfolio_state | last_nav | NAV | SGD with commas (e.g. 1,044,204.13); if currency not in file, use "NAV" and same number format |
| portfolio_state | cash_weight | Cash weight | Percentage, 2 dp (e.g. 0.00%) |
| portfolio_state | last_nav_fetched_at | Last NAV fetch | ISO timestamp, local or UTC as configured |
| portfolio_state | regime | Regime | Colored badge (see A.7) |
| regime_status | regime | Regime | Colored badge |
| regime_status | spy_close | SPY close | 2 dp |
| regime_status | spy_sma200 | SPY 200d SMA | 2 dp |
| regime_status | spy_below_sma | SPY vs SMA | "Above" / "Below" |
| regime_status | vix | VIX | 2 dp |
| ic_monitor | entries | IC history | Sparkline; each entry has date, ic, passed |
| factory_winner | ic | Winner IC | 4 dp |
| factory_winner | model_type | Model | String badge |
| factory_winner | selected_at | Selected at | ISO timestamp |

**Sharpe:** If shown (e.g. from backtest JSONs), format to **4 decimal places**.

### A.4 P&L vs SMH benchmark chart

- **Primary:** Use `portfolio_state.json` → `holdings` and `last_nav` plus any stored series (e.g. daily NAV) if present in that file or a sibling (e.g. `outputs/nav_series.json`). If no time series exists, chart is "NAV as of date" single point or hide chart until backtest/live series is available.
- **Fallback:** If backtest or weekly_returns JSONs exist under `outputs/` (e.g. backtest result with weekly_returns), use portfolio cumulative return vs SMH cumulative return for the chart. Axis: time (x), cumulative return % (y), two lines (portfolio, SMH).
- **Conclusion:** Prefer portfolio_state + any explicit NAV/series artifact; else use backtest output if present. Document in code which source was used.

### A.5 ML status panel

- **factory_winner.json:** Display model_type, ic (4 dp), model_path (short path or filename), selected_at.
- **ic_monitor.json:** Array of `{date, train_end, ic, passed, model_path}`. Show last N entries (e.g. 20) as a **sparkline** of IC over time (x = date, y = ic). Optionally color dot by passed (e.g. green if passed, red if not).

### A.6 Fills table (from fills.jsonl)

- **Source:** `outputs/fills/fills.jsonl` — one JSON object per line.
- **Columns to display:** run_id, timestamp, ticker, side, qty_requested, qty_filled, avg_fill_price, status, fill_check_passed, fill_check_reason. Optionally order_id, stop_order_id.
- **Sort:** Most recent first (by timestamp or run_id).
- **Format:** qty as integer; avg_fill_price as 2 dp or "—" if null; status as badge (full / partial / failed / mock).

### A.7 Color coding conventions

- **BULL** → green badge.
- **BEAR** → red badge.
- **NORMAL / SIDEWAYS / NEUTRAL** (or any other regime) → amber/orange badge.

### A.8 HNWI-appropriate styling

- **Page config:** `st.set_page_config(page_title="Wealth Dashboard", layout="wide", initial_sidebar_state="collapsed")`. Prefer **dark theme** if available (e.g. Streamlit dark theme via user settings or `st.set_page_config` + custom CSS).
- **Layout:** Wide layout; use columns for side-by-side blocks (regime + portfolio; weights + holdings).
- **Typography:** Clear headings, sufficient contrast; avoid playful fonts.

---

## B. src/monitoring/telegram_alerts.py

### B.1 Alert types and triggers

| Alert type | Trigger | Data source |
|------------|--------|--------------|
| **regime_change** | Cached last regime ≠ current regime (e.g. BULL→BEAR or BEAR→BULL). Compare `outputs/regime_status.json` → `regime` vs in-memory or file-cached previous value. | regime_status.json |
| **rebalance_complete** | Emitted by `run_weekly_rebalance.py` at end of run (after execution and audit log). | Passed in payload (run_id, mode, tickers, exit_code). |
| **fill_miss** | Any fill record in `outputs/fills/fills.jsonl` with `qty_filled < qty_requested` (or status in ["partial","failed"]). Can be checked by a separate job or after run. | fills.jsonl |
| **ic_degradation** | Last entry in `outputs/ic_monitor.json` has `ic < 0.01` (or `passed == false`). | ic_monitor.json |

### B.2 Message format (Markdown; include key numbers)

- **regime_change:**  
  `"Regime change: {old_regime} → {new_regime}. As of {as_of}. SPY: {spy_close}, VIX: {vix}."`
- **rebalance_complete:**  
  `"Rebalance complete. Run: {run_id}. Mode: {mode}. Tickers: {tickers}. Exit code: {exit_code}."`
- **fill_miss:**  
  `"Fill miss: {ticker} {side} requested {qty_requested}, filled {qty_filled}. Run: {run_id}. Reason: {fill_check_reason}."`
- **ic_degradation:**  
  `"IC degradation: last IC = {ic:.4f} (threshold 0.01). Date: {date}. Passed: {passed}."`

### B.3 Config

- **Bot token:** `.env` key `TELEGRAM_BOT_TOKEN`.
- **Chat ID:** `.env` key `TELEGRAM_CHAT_ID`.
- If either missing, `send_alert` no-ops or logs and returns (no raise).

### B.4 Public function signature

```python
def send_alert(alert_type: str, payload: dict) -> None
```

- **alert_type:** One of `"regime_change"`, `"rebalance_complete"`, `"fill_miss"`, `"ic_degradation"`.
- **payload:** Dict with fields needed for the message (e.g. old_regime, new_regime, as_of, run_id, ic, date).
- **Side effect:** Send Telegram message to TELEGRAM_CHAT_ID; on missing config or API error, log and return (no exception).

### B.5 Where to call send_alert in run_weekly_rebalance.py

- **rebalance_complete:** Call `send_alert("rebalance_complete", {...})` **after** `log_audit_record(...)` (line 122) and **before** `return _exit_code` (line 124). Payload: run_id=_run_id, mode=_rebalance_config["mode"], tickers=tickers, exit_code=_exit_code.

---

## C. File structure (stubs only)

| File | Content |
|------|--------|
| **scripts/dashboard.py** | Imports (streamlit, pathlib, json, time); `st.set_page_config`; section comments for A.1; `load_json(path)` helper stub; no full implementation. |
| **src/monitoring/__init__.py** | Empty (or export names for telegram_alerts, regime_watcher). |
| **src/monitoring/telegram_alerts.py** | Imports; `send_alert(alert_type: str, payload: dict) -> None` with docstring describing B.1–B.4; no implementation. |
| **src/monitoring/regime_watcher.py** | Imports; stub that polls `outputs/regime_status.json`, detects change vs cached regime, calls `send_alert("regime_change", ...)`; no implementation. |

---

**End of spec.**
