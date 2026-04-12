# Scripts Directory

## Canonical Entry Points

### Full autonomous run (production)

```bash
python scripts/run_optimizer.py
```

Random-searches `config/optimizer_config.yaml` search space over 30 trials. After completion:
- Writes `outputs/optimizer_results.json` (atomic)
- Promotes winner → `config/strategy_params.yaml` (atomic, `.bak` preserved)
- Registers `AITrading_WeeklyOptimizer` task in Windows Task Scheduler (next Mon 06:00)

### Single E2E pipeline run

```bash
python scripts/run_e2e_pipeline.py [--skip-data] [--skip-model] [--top-n N] [--score-floor F] [--track A|D] [--no-hedge] [--no-llm]
```

Five stages:
1. Price + news data refresh (`--skip-data` to bypass)
2. ML factory with rolling 4yr training window (`--skip-model` uses cached winner)
3. OOS backtest → `outputs/e2e_oos_backtest.json`
4. Mock execution → `outputs/last_valid_weights.json`
5. ASCII summary + STATUS: PASS/WARN/FAIL

### Smoke test

```bash
python scripts/run_optimizer.py --n-trials 2 --skip-data
```

### Standalone backtest

```bash
python scripts/backtest_technical_library.py \
    --tickers NVDA,AMD,TSM,ASML,AMAT \
    --top-n 5 \
    --start 2019-01-01 \
    --end 2024-12-31 \
    --no-llm
```

### Weekly rebalance (standalone)

```bash
python scripts/run_weekly_rebalance.py --dry-run
```

### Config promotion (standalone)

```bash
python scripts/run_promoter.py
```

Reads `outputs/optimizer_results.json`, writes winner params to `config/strategy_params.yaml`.

---

## Data Refresh

```bash
python scripts/update_price_data.py   # refresh price CSVs
python scripts/update_news_data.py    # refresh Marketaux news JSON
```

---

## Determinism Gate

```bash
python scripts/verify_determinism.py --start 2022-01-01 --end 2022-12-31
```

Exit 0 = PASS. Runs canonical backtest twice, compares SHA256 of result files.

---

## Legacy / Research

| Script | Purpose |
|--------|---------|
| `research_grid_search.py` | Parameter sweep (replaced by run_optimizer.py for production) |
| `download_fnspid.py` | One-time FNSPID dataset download |
| `process_fnspid.py` | Convert FNSPID CSV → per-ticker JSON |
| `test_gemini.py` | Verify Gemini API connection |

---

See `docs/INDEX.md` for the full documentation index.
