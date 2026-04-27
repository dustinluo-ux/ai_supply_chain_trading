# RUN

Canonical interpreter:

```text
C:\Users\dusro\anaconda3\envs\wealth\python.exe
```

Core commands:

```text
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\run_e2e_pipeline.py --skip-data --dry-run
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\run_optimizer.py --n-trials 2 --skip-data
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\daily_workflow.py
```

Paper execution requires explicit intent:

```text
C:\Users\dusro\anaconda3\envs\wealth\python.exe scripts\run_execution.py --mode paper --confirm-paper --check-fills
```

Expected gates:

- `run_e2e_pipeline.py` returns nonzero if execution fails.
- `run_optimizer.py` returns nonzero if promotion or scheduler registration fails.
- `daily_workflow.py` writes `outputs/daily_workflow_status.json` and returns nonzero on critical step failure.
- `scripts\test_fill_reconciliation.py` should print `PASS: all 6 checks passed`.

Known Windows constraint:

- Broad pytest may fail if `%TEMP%\pytest-of-dusro` is inaccessible. Targeted tests in this repo should use repo-local temporary output paths.
