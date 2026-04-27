# TOOL_INDEX

Python:

```text
C:\Users\dusro\anaconda3\envs\wealth\python.exe
```

Validation:

```text
C:\Users\dusro\anaconda3\envs\wealth\python.exe -m py_compile <files>
C:\Users\dusro\anaconda3\envs\wealth\python.exe -m pytest tests\test_atomic_io.py tests\test_ib_executor_preflight.py tests\test_ibkr_live_provider.py -q
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\test_fill_reconciliation.py
```

Operations:

```text
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\daily_workflow.py
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\run_optimizer.py --n-trials 2 --skip-data
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\run_e2e_pipeline.py --skip-data --dry-run
```

IBKR:

```text
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\run_execution.py --mode paper --confirm-paper --check-fills
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\sync_fills_from_ibkr.py --date YYYY-MM-DD
```

Safety notes:

- Do not use live IBKR accounts unless `ALLOW_LIVE_IBKR=1` is intentionally set.
- Do not use recursive delete or reset commands as default cleanup.
- Use `rg` for repo search.
