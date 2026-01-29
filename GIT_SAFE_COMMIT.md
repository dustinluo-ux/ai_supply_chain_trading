# Safe Git Commit / Push Guide (Quant Research Repo)

**Do NOT run Git inside Cursor.** Run these commands in your own terminal.

---

## 1. What SHOULD be tracked

| Category | Paths |
|----------|--------|
| **Source** | `src/` (all `.py`, `__init__.py`) |
| **Scripts** | `scripts/` (all `.py`, `scripts/README.md`) |
| **Config** | `config/` (all `.yaml`: `config.yaml`, `data_config.yaml`, `model_config.yaml`, `signal_weights.yaml`, `trading_config.yaml`) |
| **Docs** | `docs/` (all `.md`, `RESEARCH_QUEUE.txt`) |
| **Root** | `README.md`, `requirements.txt`, `.gitignore` |
| **Root .py** | `run_phase1_test.py`, `run_phase2_pipeline.py`, `run_phase3_backtest.py`, `run_strategy.py`, `run_technical_backtest.py`, `download_*.py`, `process_polygon_news.py`, `check_csv_format.py`, `test_*.py`, `simple_backtest_v2.py`, `setup_env.py`, `download_simple.py`, `download_from_list.py`, `download_full_dataset.py`, `download_more_tickers.py`, `download_news_marketaux.py` |
| **Root .md** | `ALIGNMENT_FIX.md`, `BEST_COVERAGE_APPROACH.md` |

**Small sample data (optional):**  
If you want a tiny ticker list in repo (e.g. `data/russell2000_tickers.csv` or `data/sample_tickers.csv`), add an exception in `.gitignore` **after** the `data/` line, e.g.:

```gitignore
data/
!data/sample/
# or: !data/russell2000_tickers.csv
```

Otherwise treat all of `data/` as generated and untracked.

---

## 2. Files to UNTRACK (generated / outputs) — use `git rm --cached`

If any of these are **currently tracked**, untrack them (files stay on disk; only Git stops tracking):

- Anything under **`data/`** (prices, news, raw, cache, signals, historical, `*_extractions.json`, `supply_chain_relationships.json`, `stock_market_data/`)
- Anything under **`outputs/`** (logs, `*.json` test outputs)
- Anything under **`backtests/`** (results, plots, reports)
- **`logs/`**
- **`*.csv`**, **`*.parquet`**, **`*.pkl`**, **`*.npy`**, **`*.joblib`**, **`*.zip`** at repo root or in script dirs

**Check what is tracked** (see Step 3b) and run `git rm --cached` only for paths that appear in that list and match the patterns above.

---

## 3. Exact command sequence (run in terminal)

### a) Verify current status

```powershell
cd c:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading
git status
```

**Expected:** You see branch name, and either "nothing to commit, working tree clean" or lists of modified/untracked files. No Git operations run yet.

---

### b) See what is currently tracked (before changing .gitignore)

```powershell
git ls-files
```

**Check:** Look for any of: `data/`, `outputs/`, `backtests/`, `logs/`, `*.csv`, `*.parquet`, `*.pkl`, `*.json` under `data/` or `outputs/`.  
If present, you will untrack them in step (c).

---

### c) Add/update .gitignore (already done in repo)

`.gitignore` has been updated. If you edited it elsewhere, ensure it includes:  
`data/`, `outputs/`, `backtests/`, `artifacts/`, `runs/`, `reports/`, `cache/`, `__pycache__/`, `*.csv`, `*.parquet`, `*.pkl`, `*.npy`, `*.joblib`, `*.zip`, `logs/`, `.env*`, `venv/`, `.ipynb_checkpoints/`.

---

### d) Untrack accidentally tracked generated files (no local delete)

Run **only** for paths that appeared in `git ls-files` and are generated. Examples (adjust to what you actually see):

```powershell
# If data/ is tracked (whole dir or files under it):
git rm -r --cached data/ 2>$null; if ($LASTEXITCODE -ne 0) { git ls-files data/ | ForEach-Object { git rm --cached $_ } }

# If outputs/ is tracked:
git rm -r --cached outputs/ 2>$null; if ($LASTEXITCODE -ne 0) { git ls-files outputs/ | ForEach-Object { git rm --cached $_ } }

# If backtests/ is tracked:
git rm -r --cached backtests/ 2>$null; if ($LASTEXITCODE -ne 0) { git ls-files backtests/ | ForEach-Object { git rm --cached $_ } }

# If logs/ is tracked:
git rm -r --cached logs/ 2>$null; if ($LASTEXITCODE -ne 0) { git ls-files logs/ | ForEach-Object { git rm --cached $_ } }
```

**Or** untrack specific files (safer if you prefer one-by-one):

```powershell
git ls-files "data/" "outputs/" "backtests/" "logs/"
# Then for each path listed (or for a folder):
git rm --cached -- <path>
# e.g. git rm -r --cached -- data/
```

**Expected:** `git status` shows these as "deleted" (from index only). Files remain on disk.

---

### e) Stage only the right files (no `git add .`)

**Option A — Explicit paths (safest):**

```powershell
git add .gitignore
git add README.md requirements.txt
git add ALIGNMENT_FIX.md BEST_COVERAGE_APPROACH.md
git add config/
git add docs/
git add src/
git add scripts/
git add run_phase1_test.py run_phase2_pipeline.py run_phase3_backtest.py run_strategy.py run_technical_backtest.py
git add process_polygon_news.py check_csv_format.py setup_env.py simple_backtest_v2.py
git add download_5_tickers_csv.py download_simple.py download_from_list.py download_full_dataset.py download_more_tickers.py download_news_marketaux.py
git add test_data_compatibility.py test_marketaux.py test_signal_combination.py test_signals.py test_weights_direct.py
```

**Option B — Review then add:**

```powershell
git status
# Inspect "Untracked files" and "Changes not staged". Then add only desired paths, e.g.:
git add .gitignore README.md requirements.txt config/ docs/ src/ scripts/
git add run_*.py process_polygon_news.py check_csv_format.py setup_env.py simple_backtest_v2.py
git add download_*.py test_*.py ALIGNMENT_FIX.md BEST_COVERAGE_APPROACH.md
```

**Before staging more:** List what will be committed:

```powershell
git diff --cached --name-only
# or
git status
```

**Expected:** Only source, config, docs, scripts, root entrypoints, README, requirements, .gitignore. No `data/`, `outputs/`, `backtests/`, logs, or large binaries.

---

### f) Commit with a sensible message

```powershell
git commit -m "chore: tighten .gitignore and track only source/config/docs; untrack data/outputs/backtests"
```

**Expected:** "X files changed, Y insertions(+), Z deletions(-)". No errors.

---

### g) Push to origin

```powershell
git push origin
# or, if your branch is not set upstream:
git push -u origin <branch-name>
```

**Expected:** Push completes to `origin/<branch-name>`. Resolve any "rejected" or "non-fast-forward" per your workflow (pull/rebase then push).

---

## 4. Safety checklist

- [ ] Did **not** use `git add .` without first reviewing `git status` / `git diff --cached --name-only`.
- [ ] Staged only: `src/`, `scripts/`, `config/`, `docs/`, root `.py`/`.md`, `README.md`, `requirements.txt`, `.gitignore`.
- [ ] Untracked generated dirs: `data/`, `outputs/`, `backtests/`, `logs/` (via `git rm --cached`).
- [ ] No large or generated files in `git ls-files` after staging (re-run `git ls-files` after add if unsure).

---

## 5. Optional: verify after commit

```powershell
git ls-files
```

Confirm no paths under `data/`, `outputs/`, `backtests/`, or large `*.csv`/`*.parquet`/`*.pkl`/`*.npy`/`*.zip` are listed.
