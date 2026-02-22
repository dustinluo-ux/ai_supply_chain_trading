# Ecosystem Validation — Live Volatility & Historical Backfill Prep

**Reference:** INDEX.md; Evidence Discipline.  
**Context:** System detecting live volatility triggers; preparing for deep historical backfill. Validation only; no code changes.

---

## TEST 1 — sync_universe.py creates historical_archives

**Command run:** `python scripts/sync_universe.py > sync_run2.txt 2>&1`

### Full paste of sync_run2.txt

```
Directory ensured: C:\ai_supply_chain_trading\trading_data\news\raw_bulk
Directory ensured: C:\ai_supply_chain_trading\trading_data\news\historical_archives
Synced 40 tickers to data_config.yaml
ALAB, AMD, AMZN, ANET, ARM, ASML, AVGO, BEP, CCJ, CDNS, CEG, CLS, CRDO, EME, FIX, GEV, GOOGL, INTC, ISRG, LEU, LITE, META, MOD, MRVL, MSFT, NEP, NVDA, NVT, OKLO, ORCL, PATH, PLTR, SMR, SNPS, TEAM, TER, TSM, UUUU, VRT, VST
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) Both directory lines present | **PASS** | Line 1: `Directory ensured: ...news\raw_bulk`; Line 2: `Directory ensured: ...news\historical_archives`. |
| (c) "Synced 40 tickers" line present | **PASS** | Line 3: `Synced 40 tickers to data_config.yaml`. |

**TEST 1:** PASS (all checks)

---

## TEST 2 — check_data_integrity.py

**Command run:** `python scripts/check_data_integrity.py > integrity_run.txt 2>&1`

### Full paste of integrity_run.txt (key diagnostic — complete)

```
                               Data Integrity                                
+---------------------------------------------------------------------------+
| Ticker | Pillar   | Price_Start_Date | News_Article_Count | Gaps_Detected |
|--------+----------+------------------+--------------------+---------------|
| NVDA   | compute  | 1999-01-22       | 514                | 1             |
| AMD    | compute  | 1980-03-17       | 367                | 1             |
| AVGO   | compute  | 2009-08-06       | 0                  | 0             |
| TSM    | compute  | 1997-10-09       | 306                | 1             |
| ASML   | compute  | 1995-03-15       | 660                | 1             |
| ARM    | compute  | 2023-09-14       | 0                  | 0             |
| MRVL   | compute  | 2000-06-30       | 0                  | 1             |
| INTC   | compute  | 1980-03-17       | 1376               | 1             |
| SNPS   | compute  | 1992-02-26       | 0                  | 1             |
| CDNS   | compute  | 1987-06-10       | 0                  | 1             |
| CEG    | energy   | 2022-01-19       | 0                  | 0             |
| VST    | energy   | 2016-10-05       | 0                  | 0             |
| GEV    | energy   | 2024-03-27       | 0                  | 0             |
| CCJ    | energy   | 2015-01-02       | 0                  | 0             |
| OKLO   | energy   | 2021-07-08       | 0                  | 0             |
| UUUU   | energy   | 2015-01-02       | 0                  | 0             |
| LEU    | energy   | 1998-07-23       | 0                  | 1             |
| BEP    | energy   | 2005-11-15       | 0                  | 0             |
| SMR    | energy   | 2022-03-01       | 0                  | 0             |
| NEP    | energy   | MISSING          | 0                  | N/A           |
| VRT    | infra    | 2018-08-02       | 0                  | 0             |
| MOD    | infra    | 1982-09-20       | 0                  | 1             |
| ANET   | infra    | 2014-06-06       | 0                  | 0             |
| ALAB   | infra    | 2024-03-20       | 0                  | 0             |
| CRDO   | infra    | 2022-01-27       | 0                  | 0             |
| CLS    | infra    | 2015-01-02       | 0                  | 0             |
| LITE   | infra    | 2015-07-23       | 0                  | 0             |
| NVT    | infra    | 2018-04-24       | 0                  | 0             |
| FIX    | infra    | 1997-06-27       | 0                  | 1             |
| EME    | infra    | 1995-01-10       | 0                  | 1             |
| PLTR   | adoption | 2020-09-30       | 0                  | 0             |
| PATH   | adoption | 2021-04-21       | 0                  | 0             |
| MSFT   | adoption | 1986-03-13       | 0                  | 1             |
| GOOGL  | adoption | 2015-01-02       | 0                  | 0             |
| META   | adoption | 2015-01-02       | 0                  | 0             |
| AMZN   | adoption | 1997-05-15       | 0                  | 1             |
| ISRG   | adoption | 2000-06-16       | 0                  | 1             |
| TER    | adoption | 2015-01-02       | 0                  | 0             |
| TEAM   | adoption | 2015-12-09       | 0                  | 0             |
| ORCL   | adoption | 2015-01-02       | 0                  | 0             |
+---------------------------------------------------------------------------+
Data ready: 39/40 tickers have price data, 5/40 have news.
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) Table with all 5 columns (Ticker, Pillar, Price_Start_Date, News_Article_Count, Gaps_Detected) | **PASS** | Header and rows show all five columns. |
| (c) Summary line present | **PASS** | Last line: `Data ready: 39/40 tickers have price data, 5/40 have news.` |
| (d) No traceback | **PASS** | No traceback in output. |

**TEST 2:** PASS (all checks)

---

## TEST 3 — daily_workflow.py news path (trading_data/news/)

**Command run:** `python scripts/daily_workflow.py > health_check3.txt 2>&1`

### System Health table section (from "System Health" to end of table)

```
                           System Health - 2026-02-21                           
+------------------------------------------------------------------------------+
| Ticker | ML_Score | VolFilter | Final_Weight | Top_News_Headline             |
|--------+----------+-----------+--------------+-------------------------------|
| ALAB   | 0.168    | YES       | 0.0%         | -                             |
| AMD    | 0.357    | NO        | 0.0%         | Biden team weighs fully       |
|        |          |           |              | cutting off Huawei from US    |
|        |          |           |              | s...                          |
| AMZN   | 0.397    | NO        | 0.0%         | -                             |
| ANET   | 0.432    | NO        | 0.0%         | -                             |
| ARM    | 0.545    | NO        | 0.0%         | -                             |
| ASML   | 0.595    | NO        | 0.0%         | ASML (ASML) Outpaces Stock    |
|        |          |           |              | Market Gains: What You Sh...  |
| AVGO   | 0.429    | NO        | 0.0%         | -                             |
| BEP    | 0.684    | NO        | 0.0%         | -                             |
| CCJ    | 0.488    | NO        | 0.0%         | -                             |
| CDNS   | 0.423    | NO        | 0.0%         | -                             |
| CEG    | 0.488    | NO        | 0.0%         | -                             |
| CLS    | 0.362    | NO        | 0.0%         | -                             |
| CRDO   | 0.393    | NO        | 0.0%         | -                             |
| EME    | 0.676    | NO        | 0.0%         | -                             |
| FIX    | 0.721    | NO        | 0.0%         | -                             |
| GEV    | 0.668    | NO        | 0.0%         | -                             |
| GOOGL  | 0.409    | NO        | 0.0%         | -                             |
| INTC   | 0.397    | NO        | 0.0%         | Be Greedy When Experts Are    |
|        |          |           |              | Fearful of AMD Stock          |
| ISRG   | 0.459    | NO        | 0.0%         | -                             |
| LEU    | 0.171    | YES       | 0.0%         | -                             |
| LITE   | 0.731    | NO        | 0.0%         | -                             |
| META   | 0.438    | NO        | 0.0%         | -                             |
| MOD    | 0.791    | NO        | 33.3%        | -                             |
| MRVL   | 0.453    | NO        | 0.0%         | -                             |
| MSFT   | 0.362    | NO        | 0.0%         | -                             |
| NEP    | 0.500    | NO        | 0.0%         | -                             |
| NVDA   | 0.448    | NO        | 0.0%         | Tesla, Nvidia Lead Today's    |
|        |          |           |              | Biggest S&P 500 Stock Mar...  |
| NVT    | 0.519    | NO        | 0.0%         | -                             |
| OKLO   | 0.338    | NO        | 0.0%         | -                             |
| ORCL   | 0.374    | NO        | 0.0%         | -                             |
| PATH   | 0.352    | NO        | 0.0%         | -                             |
| PLTR   | 0.396    | NO        | 0.0%         | -                             |
| SMR    | 0.374    | NO        | 0.0%         | -                             |
| SNPS   | 0.446    | NO        | 0.0%         | -                             |
| TEAM   | 0.358    | NO        | 0.0%         | -                             |
| TER    | 0.739    | NO        | 33.3%        | -                             |
| TSM    | 0.591    | NO        | 0.0%         | Better Semiconductor Stock:   |
|        |          |           |              | TSMC vs. ASML                 |
| UUUU   | 0.454    | NO        | 0.0%         | -                             |
| VRT    | 0.739    | NO        | 33.3%        | -                             |
| VST    | 0.520    | NO        | 0.0%         | -                             |
+------------------------------------------------------------------------------+
Daily workflow complete.
```

### Result per check

| Check | Result | Evidence |
|-------|--------|----------|
| (a) Exit code 0 | **PASS** | Script exited 0. |
| (b) Top_News_Headline shows actual text for tickers with news in trading_data/news/ (not "-" for all) | **PASS** | AMD, ASML, INTC, NVDA, TSM show headline text; integrity report shows 5/40 have news (NVDA, AMD, TSM, ASML, INTC have News_Article_Count > 0); headlines present for those. |
| (c) No traceback | **PASS** | No traceback in health_check3.txt. |

**TEST 3:** PASS (all checks)

---

## Summary

| Test | Result | Failing checks |
|------|--------|----------------|
| TEST 1 — sync_universe.py (historical_archives) | PASS | — |
| TEST 2 — check_data_integrity.py | PASS | — |
| TEST 3 — daily_workflow news path | PASS | — |

---

## Overall verdict

**ECOSYSTEM PREP CONFIRMED**
