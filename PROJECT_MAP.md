# PROJECT_MAP

Primary execution spine:

```text
scripts/run_e2e_pipeline.py
  -> scripts/run_factory.py
  -> scripts/backtest_technical_library.py
  -> scripts/run_execution.py
  -> outputs/last_valid_weights.json
```

Production operation:

```text
scripts/daily_workflow.py
  -> update_price_data.py
  -> update_news_data.py
  -> generate_daily_weights.py
  -> regime_monitor.py
  -> portfolio_optimizer.py
  -> optional run_execution.py --mode paper --confirm-paper
  -> optional sync_fills_from_ibkr.py
  -> update_signal_db.py
  -> reconcile_fills.py
  -> risk_report.py
```

Important directories:

- `src/core/` — signal-to-portfolio spine and state objects.
- `src/execution/` — IBKR execution, order guardrails, fill ledger.
- `src/signals/` — technical, layered, news, and LLM-adjacent signal code.
- `src/data/` — CSV, IBKR live, FMP, EDGAR, and news providers.
- `scripts/` — operator entry points.
- `config/` — YAML configuration; some files are machine-written.
- `outputs/` — runtime state and reports.

Critical shared utilities:

- `src/utils/atomic_io.py` — validated atomic text/JSON/YAML writes.
- `src/execution/ib_executor.py` — common IBKR order preflight and submission path.
- `src/execution/fill_ledger.py` — durable JSONL fill ledger.
