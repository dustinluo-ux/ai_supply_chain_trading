# Health Check Validation — 2026-02-21

**Reference:** INDEX.md; Evidence Discipline.  
**Command run:** `python scripts/daily_workflow.py > health_check.txt 2>&1`

---

## Full paste of health_check.txt

```
Update Price Data (yfinance)
  Data dir: C:\ai_supply_chain_trading\trading_data\stock_market_data
  Tickers:  ['NVDA', 'AMD', 'TSM', 'ASML', 'MU', 'AMAT', 'INTC', 'SPY']
  Period:   2015-01-01 to 2026-02-21
  Delay:    1.0s between downloads
============================================================
  [1/8] UPDATE NVDA: 6812 existing + 2800 new -> 6812 total (1999-01-22 to 2026-02-20) -> nasdaq\csv\NVDA.csv
  [2/8] UPDATE AMD: 11577 existing + 2800 new -> 11577 total (1980-03-17 to 2026-02-20) -> forbes2000\csv\AMD.csv
  [3/8] UPDATE TSM: 7135 existing + 2800 new -> 7135 total (1997-10-09 to 2026-02-20) -> nyse\csv\TSM.csv
  [4/8] UPDATE ASML: 7786 existing + 2800 new -> 7786 total (1995-03-15 to 2026-02-20) -> forbes2000\csv\ASML.csv
  [5/8] UPDATE MU: 10512 existing + 2800 new -> 10512 total (1984-06-01 to 2026-02-20) -> forbes2000\csv\MU.csv
  [6/8] UPDATE AMAT: 11577 existing + 2800 new -> 11577 total (1980-03-17 to 2026-02-20) -> forbes2000\csv\AMAT.csv
  [7/8] UPDATE INTC: 11577 existing + 2800 new -> 11577 total (1980-03-17 to 2026-02-20) -> nasdaq\csv\INTC.csv
  [8/8] UPDATE SPY: 2872 existing + 2800 new -> 2872 total (2015-01-02 to 2026-02-20) -> sp500\csv\SPY.csv
============================================================
  Done: 8 updated, 0 failed, 8 total
INFO: update_price_data.py exit code: 0
Update News Data
  News dir: data/news
  Tickers:  ['NVDA', 'AMD', 'TSM', 'ASML', 'MU', 'AMAT', 'INTC']
  Period:   2026-02-14 to 2026-02-21
  ...
  Done: 7 ok, 0 failed, 7 total
INFO: update_news_data.py exit code: 0
...
[Pipeline] Loaded config: ...\config\model_config.yaml
[Pipeline] Active model: ridge
date,ticker,target_weight,latest_close,notional_units
...
=== Daily Signal Summary: 2026-02-21 ===
Ticker      Score    Vol_20d   VolFilter
------  -----   -------   ---------
NVDA        0.434      0.391   NO       
AMD         0.260      0.835   NO       
TSM         0.635      0.349   NO       
ASML        0.629      0.360   NO       
MU          0.609      0.727   NO       
AMAT        0.759      0.565   NO       
INTC        0.328      0.910   NO       
INFO: generate_daily_weights.py exit code: 0
                     System Health - 2026-02-21                     
+------------------------------------------------------------------+
| Ticker | ML_Score | VolFilter | Final_Weight | Top_News_Headline |
|--------+----------+-----------+--------------+-------------------|
| NVDA   | 0.434    | NO        | 0.0%         | -                 |
| AMD    | 0.260    | NO        | 0.0%         | -                 |
| TSM    | 0.635    | NO        | 33.3%        | -                 |
| ASML   | 0.629    | NO        | 33.3%        | -                 |
| MU     | 0.609    | NO        | 0.0%         | -                 |
| AMAT   | 0.759    | NO        | 33.3%        | -                 |
| INTC   | 0.328    | NO        | 0.0%         | -                 |
+------------------------------------------------------------------+
Daily workflow complete.
```

*(Abbreviated middle sections; full 83-line output in health_check.txt.)*

---

## PASS/FAIL per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) "Daily workflow complete." present — exit code 0 | **PASS** | Last line: `Daily workflow complete.`; script exited 0. |
| (b) "System Health" table (or fallback) with all 5 columns: Ticker, ML_Score, VolFilter, Final_Weight, Top_News_Headline | **PASS** | Table "System Health - 2026-02-21" with header row and columns Ticker, ML_Score, VolFilter, Final_Weight, Top_News_Headline. |
| (c) All 7 Core tickers appear in the table | **PASS** | NVDA, AMD, TSM, ASML, MU, AMAT, INTC all present. |
| (d) No traceback | **PASS** | No traceback in output. |
| (e) WARNING lines for stale news (note tickers or "none today") | **PASS** | No WARNING lines for stale news in health_check.txt — **none today**. |
| (f) outputs/last_signal.json exists and is valid JSON; key list | **PASS** | File exists; `json.load(open('outputs/last_signal.json'))` succeeds. Key list below. |

---

## last_signal.json key list

**Command run:** `python -c "import json; d=json.load(open('outputs/last_signal.json')); print(list(d.keys()))"`

**Output (top-level keys):**  
`['NVDA', 'AMD', 'TSM', 'ASML', 'MU', 'AMAT', 'INTC']`

*(Evidence: file read; valid JSON; top-level keys are the seven Core tickers.)*

---

## Overall verdict

**HEALTH CHECK CONFIRMED**
