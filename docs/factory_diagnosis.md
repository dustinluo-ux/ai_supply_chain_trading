# Factory & Train Pipeline Bug Diagnosis

**Reference:** INDEX.md, Evidence Discipline.  
**Scope:** `src/models/factory.py`, `src/models/train_pipeline.py`. No code modified.

---

## Pre-check: numpy.NaN patch

- **File:** `src/signals/technical_library.py`
- **Line 19:** `_np.NaN = _np.nan  # numpy 2.x removed NaN; patch for pandas_ta compatibility`
- **Verdict:** Patch present and unchanged.

---

## Bug 1 — Model type not propagating

### Where the factory sets the active model type

- **File:** `src/models/factory.py`
- **Lines 166–171:**
  - `pipeline = ModelTrainingPipeline(str(config_path))` (166)
  - `pipeline.config["training"]["residual_target"] = True` (167)
  - `pipeline.config["training"]["save_models"] = False` (168)
  - **`pipeline.active_model_type = model_type`** (169)
  - **`pipeline.model_config = pipeline.config.get("models", {}).get(model_type) or {}`** (170–171)

So the factory sets both `active_model_type` and `model_config` on the pipeline instance **after** construction.

### Where the pipeline sets and reads `active_model_type`

- **File:** `src/models/train_pipeline.py`
- **Init (first write from config):**
  - **Line 42:** `self.active_model_type = self.config['active_model']`
  - **Line 43:** `self.model_config = self.config['models'][self.active_model_type]`
- **Read during `train()`:**
  - **Lines 360–363:** `create_model({**{'type': self.active_model_type}, **self.model_config}, self.feature_names)` — uses instance `active_model_type` and `model_config`.
- **Read during `evaluate_ic()`:**
  - **Lines 422–425:** `create_model({**{'type': self.active_model_type}, **self.model_config}, self.feature_names)` — same for per-fold model creation.
- **Other reads:** Line 378 uses `self.active_model_type` for save path when `save_models` is True.

The pipeline **never** re-reads `config['active_model']` after `__init__`. All training and IC evaluation use the instance attributes `self.active_model_type` and `self.model_config`, which the factory overwrites before each `train()` / `evaluate_ic()` call.

### Override behavior

- **Override:** The factory sets `pipeline.active_model_type` and `pipeline.model_config` at factory.py:169–171 **before** calling `pipeline.train()` (174) and `pipeline.evaluate_ic()` (183). So for each candidate (`ridge`, `xgboost`, `catboost`), the pipeline uses the overridden type and config.
- **Conclusion:** The post-construction override **is** sufficient; the pipeline does **not** ignore it. If “model type not propagating” is observed, the cause is not the override itself. Possible other causes: `config["models"]` missing a key for that model type (so `model_config` is `{}` and only default hyperparams are used), or Bug 2 causing that model to be skipped so only one type appears in results.

### One-line diagnosis (Bug 1)

**The factory sets `active_model_type` and `model_config` at factory.py:169–171; the pipeline reads them only from instance attributes at train_pipeline.py:360–363 and 422–425. The override works; observed non-propagation is likely from empty `model_config` for that type or from Bug 2 (silent skip).**

---

## Bug 2 — XGBoost/CatBoost silent failure

### Where the factory calls `evaluate_ic()` and catches exceptions

- **File:** `src/models/factory.py`
- **First try/except (train):**
  - **Lines 173–181:**
    ```python
    try:
        model = pipeline.train(
            prices_dict,
            technical_signals=None,
            news_signals=news_signals,
        )
    except Exception:
        continue
    ```
  - On **any** `Exception` from `pipeline.train()`, the block catches and **continues** to the next `model_type`. No result is appended; no error is logged or re-raised.
- **Second try/except (evaluate_ic):**
  - **Lines 182–192:**
    ```python
    try:
        mean_ic, _ = pipeline.evaluate_ic(
            model,
            prices_dict,
            test_start=test_start,
            test_end=test_end,
            news_signals=news_signals,
        )
    except Exception:
        continue
    results.append((model, model_type, float(mean_ic)))
    ```
  - On **any** `Exception` from `pipeline.evaluate_ic()`, the block catches and **continues**. Again no result is appended and no error is reported.

### Fallback IC value on failure

- There is **no** fallback IC value returned for a failed model type. On `train()` or `evaluate_ic()` exception, that model type is **skipped**: no tuple is appended to `results`, so it never enters the “passed” list or winner logic. The failure is **silent** (no log, no re-raise).
- So the effective “IC on failure” is: **no result for that model** (not a numeric fallback like 0.0).

### One-line diagnosis (Bug 2)

**Exceptions from `train()` and `evaluate_ic()` are caught with `except Exception: continue` at factory.py:173–181 and 182–192; failed model types produce no result and no error output, so XGBoost/CatBoost failures appear as silent skips and only Ridge (or whichever runs without raising) shows in results.**

---

## Summary

| Bug | Relevant locations | Conclusion |
|-----|--------------------|------------|
| **1** | Set: factory.py:169–171. Read: train_pipeline.py:42–43 (init), 360–363 (train), 422–425 (evaluate_ic). | Override is effective; propagation failure likely due to empty `model_config` or Bug 2. |
| **2** | factory.py:173–181 (train), 182–192 (evaluate_ic). | Exceptions are swallowed; no result and no fallback IC; failed candidates are silently skipped. |

No code changes were made; this document is diagnosis only.
