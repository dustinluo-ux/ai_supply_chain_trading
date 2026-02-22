# Global Universe Validation — AI Trade Global

**Reference:** INDEX.md; Evidence Discipline.  
**Context:** The AI trade is now global. Validation only; no code changes.

---

## TEST 1 — sync_universe.py (47 tickers + global_equities dir)

**Command run:** `python scripts/sync_universe.py > sync_run3.txt 2>&1`

### Full paste of sync_run3.txt

```
Directory ensured: C:\ai_supply_chain_trading\trading_data\news\raw_bulk
Directory ensured: C:\ai_supply_chain_trading\trading_data\news\historical_archives
Directory ensured: C:\ai_supply_chain_trading\trading_data\news\global_equities
Synced 47 tickers to data_config.yaml
0700.HK, 1810.HK, 6758.T, 6861.T, 9988.HK, ALAB, AMD, AMZN, ANET, ARM, ASML, AVGO, BEP, CCJ, CDNS, CEG, CLS, CRDO, EME, FIX, GEV, GOOGL, INTC, ISRG, LEU, LITE, META, MOD, MRVL, MSFT, NEP, NVDA, NVT, OKLO, ORCL, ORSTED.CO, PATH, PLTR, SAP.DE, SMR, SNPS, TEAM, TER, TSM, UUUU, VRT, VST
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) "Synced 47 tickers to data_config.yaml" line present | **PASS** | Line 4. |
| (c) "Directory ensured: ...global_equities" line present | **PASS** | Line 3. |
| (d) All three directory lines present (raw_bulk, historical_archives, global_equities) | **PASS** | Lines 1–3. |

**TEST 1:** PASS (all checks)

### data_config.yaml verification

**Command run:**  
`python -c "import yaml; with open('config/data_config.yaml') as f: cfg = yaml.safe_load(f); wl = cfg['universe_selection']['watchlist']; mt = cfg['universe_selection']['max_tickers']; global_tickers = [t for t in wl if '.' in t]; print(f'max_tickers={mt}, watchlist_count={len(wl)}'); print('Global tickers in watchlist:', global_tickers); print('SPY in watchlist:', 'SPY' in wl)"`

**Output:**

```
max_tickers=47, watchlist_count=47
Global tickers in watchlist: ['0700.HK', '1810.HK', '6758.T', '6861.T', '9988.HK', 'ORSTED.CO', 'SAP.DE']
SPY in watchlist: False
```

**Confirm:** max_tickers=47 — **PASS**; watchlist_count=47 — **PASS**; global tickers present (7) — **PASS**; SPY absent — **PASS**.

---

## TEST 2 — ingest_historical_news.py (empty archive graceful exit)

**Command run:** `python scripts/ingest_historical_news.py > ingest_run.txt 2>&1`

### Full paste of ingest_run.txt

```
No files in historical_archives/, nothing to ingest.
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0 (per terminal). |
| (b) Output contains "No files in historical_archives/" or similar — graceful empty exit | **PASS** | Exact message present. |
| (c) No traceback | **PASS** | No traceback in output. |

**TEST 2:** PASS (all checks)

---

## TEST 3 — check_data_integrity.py (global tickers appear)

**Command run:** `python scripts/check_data_integrity.py > integrity_run2.txt 2>&1`

**Evidence:** `scripts/check_data_integrity.py` reads `config/universe.yaml` (pillars) for the table, not `data_config.yaml` watchlist. The run produced a table with pillars compute, energy, infra, adoption only; no "global" pillar rows.

### Global pillar rows from integrity table + summary line

**Global pillar rows:** None. The integrity table in integrity_run2.txt contains no row with `Pillar="global"`. The table lists 40 tickers under compute, energy, infra, adoption.

**Summary line from integrity_run2.txt:**  
`Data ready: 39/40 tickers have price data, 5/40 have news.`

*(Full table in integrity_run2.txt: 44 lines; no 9988.HK, 0700.HK, 1810.HK, SAP.DE, ORSTED.CO, 6861.T, 6758.T rows.)*

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) 7 global tickers in table with Pillar="global" (9988.HK, 0700.HK, 1810.HK, SAP.DE, ORSTED.CO, 6861.T, 6758.T) | **FAIL** | No "global" pillar in script output; table built from `config/universe.yaml` pillars (compute, energy, infra, adoption). |
| (c) All 7 show Price_Start_Date="MISSING" | N/A | No global rows. |
| (d) Summary line shows 47 total tickers | **FAIL** | Summary: "39/40 tickers" (40 total). |

**TEST 3:** FAIL (checks b, d)

### Paste: full integrity_run2.txt summary and any global rows

Summary line only (no global rows present):

```
Data ready: 39/40 tickers have price data, 5/40 have news.
```

---

## Summary

| Test | Result | Failing checks |
|------|--------|----------------|
| TEST 1 — sync_universe (47 + global_equities) | PASS | — |
| TEST 2 — ingest_historical_news (graceful empty) | PASS | — |
| TEST 3 — check_data_integrity (global tickers) | FAIL | (b) no global pillar rows, (d) summary 40 not 47 |

---

## Overall verdict

**Failures:** TEST 3(b) and TEST 3(d). Sync and data_config show 47 tickers and 7 global tickers; `check_data_integrity.py` output is built from `config/universe.yaml` (pillars) and did not include a "global" pillar or 47-ticker summary. So: **sync_universe and data_config (47 + global_equities) confirmed; ingest_historical_news graceful empty exit confirmed; check_data_integrity does not yet show global pillar or 47-ticker summary.**

**Verdict:** **Not fully confirmed** — list remaining failures: TEST 3(b) — 7 global tickers with Pillar="global" not present in integrity table; TEST 3(d) — summary shows 40 tickers, not 47.

---

## Global Universe Final Validation

**Context:** check_data_integrity.py fixed in commit 13532f4 to iterate pillars dynamically. Re-run of TEST 3 only (Tests 1 and 2 already confirmed).

**Command run:** `python scripts/check_data_integrity.py > integrity_run3.txt 2>&1`

### Global pillar rows from the table

```
| 9988.HK   | global   | MISSING          | 0                  | N/A           |
| 0700.HK   | global   | MISSING          | 0                  | N/A           |
| 1810.HK   | global   | MISSING          | 0                  | N/A           |
| SAP.DE    | global   | MISSING          | 0                  | N/A           |
| ORSTED.CO | global   | MISSING          | 0                  | N/A           |
| 6861.T    | global   | MISSING          | 0                  | N/A           |
| 6758.T    | global   | MISSING          | 0                  | N/A           |
```

### Summary line

```
Data ready: 39/47 tickers have price data, 5/47 have news.
```

### Full output (54 lines, under 60)

```
                                 Data Integrity                                 
+------------------------------------------------------------------------------+
| Ticker    | Pillar   | Price_Start_Date | News_Article_Count | Gaps_Detected |
|-----------+----------+------------------+--------------------+---------------|
| NVDA      | compute  | 1999-01-22       | 514                | 1             |
...
| ORCL      | adoption | 2015-01-02       | 0                  | 0             |
| 9988.HK   | global   | MISSING          | 0                  | N/A           |
| 0700.HK   | global   | MISSING          | 0                  | N/A           |
| 1810.HK   | global   | MISSING          | 0                  | N/A           |
| SAP.DE    | global   | MISSING          | 0                  | N/A           |
| ORSTED.CO | global   | MISSING          | 0                  | N/A           |
| 6861.T    | global   | MISSING          | 0                  | N/A           |
| 6758.T    | global   | MISSING          | 0                  | N/A           |
+------------------------------------------------------------------------------+
Data ready: 39/47 tickers have price data, 5/47 have news.
```

*(Full 54-line output in integrity_run3.txt.)*

### TEST 3 per-check results

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) 7 global tickers with Pillar="global": 9988.HK, 0700.HK, 1810.HK, SAP.DE, ORSTED.CO, 6861.T, 6758.T | **PASS** | All seven appear in table (lines 45–51 of integrity_run3.txt). |
| (c) All 7 show Price_Start_Date="MISSING" | **PASS** | Each global row has Price_Start_Date="MISSING", Gaps_Detected="N/A". |
| (d) Summary line shows 47 total tickers | **PASS** | Summary: "39/47 tickers have price data, 5/47 have news." |

### Overall verdict

**GLOBAL UNIVERSE CONFIRMED**
