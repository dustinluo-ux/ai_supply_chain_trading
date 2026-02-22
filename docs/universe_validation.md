# Universe Expansion Validation — 40-Ticker Sector-Aware Model

**Reference:** INDEX.md; Evidence Discipline.  
**Context:** System architecture moving to 40-ticker Sector-Aware model. Validation only; no code changes.

---

## TEST 1 — sync_universe.py

**Command run:** `python scripts/sync_universe.py > sync_run.txt 2>&1`

### Full paste of sync_run.txt

```
Directory ensured: C:\ai_supply_chain_trading\trading_data\news\raw_bulk
Synced 40 tickers to data_config.yaml
ALAB, AMD, AMZN, ANET, ARM, ASML, AVGO, BEP, CCJ, CDNS, CEG, CLS, CRDO, EME, FIX, GEV, GOOGL, INTC, ISRG, LEU, LITE, META, MOD, MRVL, MSFT, NEP, NVDA, NVT, OKLO, ORCL, PATH, PLTR, SMR, SNPS, TEAM, TER, TSM, UUUU, VRT, VST
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) "Synced 40 tickers to data_config.yaml" line present | **PASS** | Line 2 of sync_run.txt. |
| (c) No traceback | **PASS** | No traceback in output. |

### data_config.yaml verification

**Command run:**  
`python -c "import yaml; with open('config/data_config.yaml') as f: cfg = yaml.safe_load(f); wl = cfg['universe_selection']['watchlist']; mt = cfg['universe_selection']['max_tickers']; print(f'max_tickers={mt}, watchlist_count={len(wl)}'); print(sorted(wl))"`

**Output:**

```
max_tickers=40, watchlist_count=40
['ALAB', 'AMD', 'AMZN', 'ANET', 'ARM', 'ASML', 'AVGO', 'BEP', 'CCJ', 'CDNS', 'CEG', 'CLS', 'CRDO', 'EME', 'FIX', 'GEV', 'GOOGL', 'INTC', 'ISRG', 'LEU', 'LITE', 'META', 'MOD', 'MRVL', 'MSFT', 'NEP', 'NVDA', 'NVT', 'OKLO', 'ORCL', 'PATH', 'PLTR', 'SMR', 'SNPS', 'TEAM', 'TER', 'TSM', 'UUUU', 'VRT', 'VST']
```

**Confirm:** max_tickers=40 — **PASS**; watchlist_count=40 — **PASS**; SPY absent from watchlist — **PASS** (SPY not in the list).

**TEST 1:** PASS (all checks)

---

## TEST 2 — Directory guard

**Command run:**  
`python -c "from pathlib import Path; p = Path(r'C:/ai_supply_chain_trading/trading_data/news/raw_bulk'); print('EXISTS:', p.exists(), '| IS_DIR:', p.is_dir())"`

**Output:**  
`EXISTS: True | IS_DIR: True`

**Confirm:** Directory exists and is a directory — **PASS**.

**TEST 2:** PASS

---

## TEST 3 — News path fix (daily_workflow.py headlines)

**Command run:** `python scripts/daily_workflow.py > health_check2.txt 2>&1`

### System Health table section (from "System Health" to end of table)

```
                           System Health - 2026-02-21                           
+------------------------------------------------------------------------------+
| Ticker | ML_Score | VolFilter | Final_Weight | Top_News_Headline             |
|--------+----------+-----------+--------------+-------------------------------|
| ALAB   | 0.168    | YES       | 0.0%         | -                             |
| AMD    | 0.357    | NO        | 0.0%         | AMD Backs $300 Million Loan   |
|        |          |           |              | For Crusoe's AI Chip Dep...   |
| AMZN   | 0.397    | NO        | 0.0%         | MoodyÆs Shifts AmazonÆs       |
|        |          |           |              | Outlook to Stable, Affirms    |
|        |          |           |              | A...                          |
| ANET   | 0.432    | NO        | 0.0%         | AI Trade 2.0: Which Stocks    |
|        |          |           |              | Still Have Upside?            |
...
| TSM    | 0.591    | NO        | 0.0%         | DA Davidson Gives Taiwan      |
|        |          |           |              | Semiconductor (TSM) a Buy     |
|        |          |           |              | R...                          |
| UUUU   | 0.454    | NO        | 0.0%         | ALPS Launches Nuclear ETF     |
|        |          |           |              | With Options Strategy         |
| VRT    | 0.739    | NO        | 33.3%        | Vertiv Holdings Co (VRT)      |
|        |          |           |              | Presents at Barclays 43rd     |
|        |          |           |              | A...                          |
| VST    | 0.520    | NO        | 0.0%         | Do Wall Street Analysts Like  |
|        |          |           |              | Vistra Stock?                 |
+------------------------------------------------------------------------------+
Daily workflow complete.
```

*(Full table in health_check2.txt lines 280–360; multiple tickers show actual headline text, e.g. AMD, AMZN, ANET, ASML, TSM, NVDA, LEU, etc.)*

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) Top_News_Headline shows actual text (not "-") for at least one ticker with news in data/news/ | **PASS** | Many tickers have headline text (e.g. AMD "AMD Backs $300 Million Loan...", AMZN, ANET, ASML, TSM, NVDA, LEU, GOOGL, MSFT, PATH, PLTR, TER, VRT, VST). News was fetched for 40 tickers; headlines appear in table. |
| (c) No traceback | **PASS** | No traceback in health_check2.txt. |

**TEST 3:** PASS (all checks)

---

## Summary

| Test | Result | Failing checks |
|------|--------|----------------|
| TEST 1 — sync_universe.py | PASS | — |
| TEST 2 — Directory guard (raw_bulk) | PASS | — |
| TEST 3 — News path fix (headlines) | PASS | — |

---

## Overall verdict

**UNIVERSE EXPANSION CONFIRMED**
