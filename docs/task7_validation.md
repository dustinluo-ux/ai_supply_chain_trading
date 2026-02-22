# Task 7 Validation — 2026-02-21

**Reference:** INDEX.md; Evidence Discipline.  
**Context:** Task 7 implemented in commit 60b11c2. Three tests: generate_daily_weights summary table, daily_workflow.py, performance_tracker.py.

---

## TEST 1 — generate_daily_weights.py with summary table

**Command run:** `python scripts/generate_daily_weights.py > daily_weights_t7.txt 2>&1`

### Full contents of daily_weights_t7.txt

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


=== Daily Signal Summary: 2026-02-21 ===
Ticker      Score    Vol_20d   VolFilter
------  -----   -------   ---------
NVDA        0.400      0.432   NO       
AMD         0.258      0.889   NO       
TSM         0.691      0.383   NO       
ASML        0.721      0.329   NO       
MU          0.338      0.413   NO       
AMAT        0.663      0.386   NO       
INTC        0.341      0.294   NO       
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) CSV block present (date, ticker, target_weight, latest_close, notional_units) | **PASS** | Header and rows present. |
| (c) "=== Daily Signal Summary" table with Ticker/Score/Vol_20d/VolFilter | **PASS** | Table present with those columns. |
| (d) outputs/daily_signals.csv created or appended; exists and has content | **PASS** | File exists; contains header and 7 data rows (Core 7 tickers). |

**TEST 1:** PASS (all checks)

### Paste of summary table section

```
=== Daily Signal Summary: 2026-02-21 ===
Ticker      Score    Vol_20d   VolFilter
------  -----   -------   ---------
NVDA        0.400      0.432   NO       
AMD         0.258      0.889   NO       
TSM        0.691      0.383   NO       
ASML        0.721      0.329   NO       
MU          0.338      0.413   NO       
AMAT        0.663      0.386   NO       
INTC        0.341      0.294   NO       
```

---

## TEST 2 — daily_workflow.py

**Command run:** `python scripts/daily_workflow.py > workflow_run.txt 2>&1`

### Full contents of workflow_run.txt

```
Update Price Data (yfinance)
  Data dir: C:\ai_supply_chain_trading\trading_data\stock_market_data
  Tickers:  ['NVDA', 'AMD', 'TSM', 'ASML', 'MU', 'AMAT', 'INTC', 'SPY']
  Period:   2015-01-01 to 2026-02-21
  ...
  Done: 8 updated, 0 failed, 8 total
INFO: update_price_data.py exit code: 0
Update News Data
  ...
  Done: 7 ok, 0 failed, 7 total
INFO: update_news_data.py exit code: 0
...
[Pipeline] Loaded config: ...
date,ticker,target_weight,latest_close,notional_units
...
=== Daily Signal Summary: 2026-02-21 ===
Ticker      Score    Vol_20d   VolFilter
...
INFO: generate_daily_weights.py exit code: 0
Daily workflow complete.
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) "Daily workflow complete." appears in output | **PASS** | Last line: `Daily workflow complete.` |
| (b) Exit code 0 | **PASS** | Script exited 0. |
| (c) Each sub-step return code is logged (non-zero acceptable) | **PASS** | `INFO: update_price_data.py exit code: 0`, `INFO: update_news_data.py exit code: 0`, `INFO: generate_daily_weights.py exit code: 0`. |

**TEST 2:** PASS (all checks)

### Paste of workflow_run.txt (full)

```
Update Price Data (yfinance)
  Data dir: C:\ai_supply_chain_trading\trading_data\stock_market_data
  Tickers:  ['NVDA', 'AMD', 'TSM', 'ASML', 'MU', 'AMAT', 'INTC', 'SPY']
  Period:   2015-01-01 to 2026-02-21
  Delay:    1.0s between downloads
============================================================
  [1/8] UPDATE NVDA: ... -> nasdaq\csv\NVDA.csv
  ...
  Done: 8 updated, 0 failed, 8 total
INFO: update_price_data.py exit code: 0
Update News Data
  ...
  Done: 7 ok, 0 failed, 7 total
INFO: update_news_data.py exit code: 0
...
[Pipeline] Loaded config: ...
date,ticker,target_weight,latest_close,notional_units
...
=== Daily Signal Summary: 2026-02-21 ===
Ticker      Score    Vol_20d   VolFilter
...
INFO: generate_daily_weights.py exit code: 0
Daily workflow complete.
```

---

## TEST 3 — performance_tracker.py

**Command run:** Inline `python -c "from src.evaluation.performance_tracker import ...; result = pt.run(...); print(result)" > tracker_run.txt 2>&1`

### Full contents of tracker_run.txt

```
=== Performance Summary ===
Traceback (most recent call last):
  File "<string>", line 8, in <module>
    result = pt.run('outputs/daily_signals.csv', data_dir)
  File "C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\src\evaluation\performance_tracker.py", line 137, in run
    print(f"Period:        {first_str} \u2192 {last_str}  ({n_days} trading days)")
  File "C:\Users\dusro\anaconda3\Lib\encodings\cp1252.py", line 19, in encode
    return codecs.charmap_encode(input,self.errors,encoding_table)[0]
UnicodeEncodeError: 'charmap' codec can't encode character '\u2192' in position 26: character maps to <undefined>
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) No traceback (n_days=0/1 with note acceptable) | **FAIL** | UnicodeEncodeError in performance_tracker.py line 137 (arrow `\u2192` not encodable in cp1252). |
| (b) Performance Summary block or "insufficient data" message | **PARTIAL** | "=== Performance Summary ===" printed then crash before full block. |
| (c) Exit code 0 | **FAIL** | Exit code 1. |

**TEST 3:** FAIL (checks a, c; traceback and non-zero exit)

### Paste of tracker_run.txt

*(As above.)*

---

## Summary

| Test | Result | Failing checks |
|------|--------|----------------|
| TEST 1 — generate_daily_weights + summary | PASS | — |
| TEST 2 — daily_workflow.py | PASS | — |
| TEST 3 — performance_tracker.py | FAIL | (a) traceback, (c) exit 1 |

---

## Overall verdict

**Remaining failures:** TEST 3 — PerformanceTracker run raised `UnicodeEncodeError` when printing a Unicode arrow (`\u2192`) on Windows cp1252; traceback at `src/evaluation/performance_tracker.py` line 137; exit code 1. TEST 1 and TEST 2 are **confirmed**.

**Verdict:** Task 7 **not fully confirmed**; list remaining failure: TEST 3 (traceback and exit code in performance_tracker run).

---

## Task 7 Final Validation

**Context:** Unicode fix applied to `src/evaluation/performance_tracker.py`. Re-run of TEST 3 only (Tests 1 and 2 already confirmed).

**Command run:** Inline `python -c "from src.evaluation.performance_tracker import ...; pt.run(...); print(result)" > tracker_run2.txt 2>&1`

### Full contents of tracker_run2.txt

```
=== Performance Summary ===
Period:        2026-02-21 -> 2026-02-21  (1 trading days)
Total Return:  0.00%
SPY Return:    0.00%
Alpha vs SPY:  +0.00%
Max Drawdown:  0.00%
Sharpe Ratio:  0.00
{'total_return': 0.0, 'spy_return': 0.0, 'alpha_vs_spy': 0.0, 'max_drawdown': 0.0, 'sharpe_ratio': 0.0, 'n_days': 1}
```

### TEST 3 result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) No traceback | **PASS** | No traceback in output. |
| (b) Performance Summary block or clear message (one date acceptable) | **PASS** | Full "=== Performance Summary ===" block printed; Period 2026-02-21 -> 2026-02-21 (1 trading days); one date is acceptable per instructions. |
| (c) Exit code 0 | **PASS** | Script exited 0. |

### Overall verdict

**TASK 7 CONFIRMED**
