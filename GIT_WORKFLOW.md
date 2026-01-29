# Git Workflow (Guardrails for this Repo)

## Principles
- Git tracks **code/config/docs only**.
- Data, outputs, logs, caches, models, and downloaded artifacts are **never committed**.
- Use terminal for Git operations (commit/push). Cursor is for coding, not repo-wide Git automation.

## What is allowed in Git
- `src/`, `scripts/`, `config/`, `docs/`
- Root entrypoints `*.py`
- `README.md`, `requirements.txt`, `*.md`
- `.gitignore`

## What must never be committed
- `.env*` (local secrets)
- `data/`, `outputs/`, `backtests/`, `runs/`, `artifacts/`, `reports/`, `cache/`, `logs/`, `models/`
- Large/binary files: `*.csv`, `*.parquet`, `*.pkl`, `*.npy`, `*.joblib`, `*.zip`, `*.h5`, `*.pt`, `*.pth`, `*.whl`
- Virtualenvs: `.venv/`, `venv/`
- IDE state: `.cursor/`, `.vscode/`, `.idea/`

## Standard commit flow (safe)
1) Check status:
   - `git status`
2) Stage explicitly (never `git add .`):
   - `git add .gitignore README.md requirements.txt *.md`
   - `git add src/ scripts/ config/ docs/`
   - `git add *.py`
3) Verify staged list:
   - `git diff --cached --name-only`
   - Confirm NO data/output/log/binaries are staged
4) Commit + push:
   - `git commit -m "<message>"`
   - `git push`

## If Git gets slow / Cursor gets stuck
- Suspect large tracked files or accidental staging.
- Check what’s tracked:
  - `git ls-files`
- Remove generated dirs from index (does not delete local files):
  - `git rm -r --cached -- data outputs backtests logs runs artifacts reports cache models`
  - `git commit -m "chore: untrack generated artifacts"`
  - `git push`

## OneDrive note (Windows)
- This repo may live under OneDrive. Avoid committing large churn files, as sync + diff can become slow.
- Keep generated outputs outside the repo or in ignored folders.
