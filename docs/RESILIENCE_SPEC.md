# Institutional Resilience Specification

**Purpose:** Data criticality, explicit error handling in data loaders, IBKR connection state machine, broker-native server-side stops, file list, config, and integration. No code—markdown specification only.

**Evidence discipline:** Design decisions that reference existing code cite `filename:line_number`.

**Relationship to RISK_MANAGEMENT_SPEC.md:** The Global Stop-Loss (Section 2 of RISK_MANAGEMENT_SPEC.md) remains unchanged. Broker-native server-side stops (Section 4 below) **extend** it: the local engine stop-loss stays; IBKR bracket/STP orders add a per-position stop at the broker.

---

## Section 1 — Data Criticality Classification

| Source | Criticality | Rationale |
|--------|-------------|-----------|
| Price CSVs | CRITICAL | Cannot size positions without prices (`scripts/run_execution.py:58` load_prices; delta trades and share counts depend on prices). |
| EODHD news parquet | DEGRADED | News features default to 0.5 neutral; strategy continues (`src/data/eodhd_news_loader.py:69–72` currently returns `{}` on error; pipeline uses neutral defaults). |
| Tiingo parquets | DEGRADED | Live news optional; Marketaux is fallback. |
| Marketaux JSON | DEGRADED | Dual news source; EODHD covers gaps. |
| SMH benchmark | CRITICAL | Required for regime detection and beta calculation (`scripts/run_execution.py:491–494` hedge logic; regime_monitor and beta use SMH). |
| regime_status.json | CRITICAL | Required by all pods (`scripts/run_execution.py:211–216`; THREE_POD_ARCHITECTURE). |
| meta_weights.json | DEGRADED | Falls back to prior weights (`scripts/run_execution.py:266–278` default_meta when file missing). |

### IncompleteDataError and DataQualityReport

**File:** `src/data/data_quality.py` (new).

- **IncompleteDataError:** Exception class. Attributes: `missing_sources: list[str]`, `criticality: str` (e.g. `"CRITICAL"` or `"DEGRADED"`). Raised when a CRITICAL source is missing or fails and the caller is configured to raise.
- **DataQualityReport:** Dataclass. Fields:
  - `critical_missing: list[str]` — source names that are CRITICAL and missing/failed.
  - `degraded_missing: list[str]` — source names that are DEGRADED and missing/failed.
  - `warnings: list[str]` — human-readable warning messages (e.g. from module-level _load_warnings).
  - `can_rebalance: bool` — `True` if and only if `len(critical_missing) == 0`.

---

## Section 2 — Explicit Error Handling in Data Loaders

### Identified silent or broad exception handling

**src/data/eodhd_news_loader.py**

- **Lines 69–72:** `except Exception as e: print(...); return {}`. Swallows any exception (missing file, parquet read error, column missing, etc.) and returns empty dict with no logging to Python logging, no quality report.

**src/data/news_fetcher_factory.py**

- **Lines 65–66:** `except Exception as e: logger.error(...); raise`. Does **not** silently return; it re-raises. No change to return type. If `create_from_config` is used and the config file is missing or invalid, the exception propagates; callers that catch and proceed without news should produce a DataQualityReport (degraded_missing).

### Replacement behaviour (for loaders that currently return {} on exception)

For each **silent** `except Exception: return {}` (or equivalent) in the data load path:

1. **Log** the exception type and message at **ERROR** level using Python `logging` (not only `print`).
2. **Append** the source name (e.g. `"eodhd_news"`) to a module-level `_load_warnings` list (or equivalent shared list used to populate `DataQualityReport.warnings`).
3. **Return** either:
   - A tuple `(result, DataQualityReport)` with `result` the loaded data (or empty dict/list if failure) and the report with `degraded_missing` or `critical_missing` and `warnings` populated; or
   - **Raise** `IncompleteDataError(missing_sources=[source_name], criticality="CRITICAL")` if the source is classified as CRITICAL and the implementation chooses to raise instead of return partial result.
4. For **DEGRADED** sources: return the partial result (e.g. `{}`) with `DataQualityReport.degraded_missing` containing that source and `warnings` containing the message; `can_rebalance` remains `True` unless a CRITICAL source is also missing.

**eodhd_news_loader.py** is DEGRADED: replace the single `except Exception` block so that it logs at ERROR, appends to `_load_warnings`, and returns `(out, DataQualityReport(degraded_missing=["eodhd_news"], ...))` on failure, or `(out, DataQualityReport())` on success. Callers must accept the new return shape (tuple) or a wrapper that unpacks it.

**news_fetcher_factory.py** does not have a silent `return {}`; `create_source` raises. Where the execution or pipeline calls `create_from_config` or a fetcher and catches exceptions to proceed without news, that caller must build a `DataQualityReport` with `degraded_missing` (e.g. `["marketaux"]` or `["tiingo"]`) and pass it along so that `execution_status.json` can reflect degraded data.

### run_execution.py integration

- **scripts/run_execution.py** must obtain a **DataQualityReport** from the data-load step (whether from a new helper that aggregates loader results or from the first loader that returns a report). Before any weight generation (pods or `compute_target_weights`):
  - If **`report.can_rebalance` is False**: log the missing critical sources (e.g. at ERROR), write **outputs/execution_status.json** with `can_rebalance: false`, `critical_missing` populated, and `manual_intervention_required` true if critical data is missing; then **return (1, [])** without attempting weight generation or order submission.
  - If `can_rebalance` is True, proceed as today; optionally still write `execution_status.json` with `can_rebalance: true` and any `degraded_missing` / `warnings` for visibility.

### outputs/execution_status.json schema

```json
{
  "as_of": "<ISO timestamp>",
  "can_rebalance": false,
  "critical_missing": ["regime_status", "prices"],
  "degraded_missing": ["eodhd_news"],
  "warnings": ["EODHD parquet not found"],
  "ibkr_state": "CONNECTED",
  "manual_intervention_required": true
}
```

- **as_of:** ISO timestamp of the last check.
- **can_rebalance:** bool — false if any CRITICAL source is missing.
- **critical_missing:** list of source names (from the table in Section 1).
- **degraded_missing:** list of source names that are DEGRADED and missing/failed.
- **warnings:** list of strings from _load_warnings or equivalent.
- **ibkr_state:** `"CONNECTED"` | `"FROZEN"` | `"DISCONNECTED"` | `"UNKNOWN"` (and optionally `"DEGRADED"`); from IBKRStateMachine (Section 3).
- **manual_intervention_required:** bool — true if `can_rebalance` is false or `ibkr_state` is FROZEN/DISCONNECTED (or as defined by policy).

---

## Section 3 — IBKR Connection State Machine

### New class: IBKRStateMachine

**File:** `src/execution/ibkr_state_machine.py`.

**States:** `UNKNOWN` → `CONNECTING` → `CONNECTED` → `DEGRADED` → `FROZEN` → `DISCONNECTED`

**Transitions and triggers:**

| From | To | Trigger |
|------|-----|--------|
| UNKNOWN | CONNECTING | First connection attempt. |
| CONNECTING | CONNECTED | Successful heartbeat response within 500 ms. |
| CONNECTED | DEGRADED | Any API call latency &gt; 500 ms OR heartbeat misses one cycle. |
| CONNECTED | FROZEN | Heartbeat fails twice consecutively OR latency &gt; 2000 ms. |
| DEGRADED | CONNECTED | Successful heartbeat within 500 ms. |
| DEGRADED | FROZEN | Second consecutive degraded heartbeat. |
| FROZEN | DISCONNECTED | No recovery within 60 seconds. |
| ANY | DISCONNECTED | Explicit disconnect or unhandled socket error. |
| DISCONNECTED | CONNECTING | Reconnect attempt. |

**Heartbeat mechanism:** A lightweight `ping()` method that measures round-trip time (ms) for a benign API call (e.g. IB API `reqCurrentTime`). Latency is measured in milliseconds. Thresholds: 500 ms = latency threshold for CONNECTED→DEGRADED; 2000 ms = freeze latency; 60 s = freeze timeout before FROZEN→DISCONNECTED.

**Public interface:**

- **current_state:** str
- **latency_ms:** float | None (last measured RTT).
- **last_heartbeat:** datetime | None
- **can_submit_orders:** bool — True **only** when `current_state == "CONNECTED"`.
- **transition(event: str) → None** — drive state by events (e.g. `"heartbeat_ok"`, `"heartbeat_slow"`, `"heartbeat_fail"`, `"disconnect"`, `"connect_attempt"`).

**When state enters FROZEN:**

1. Write **`manual_intervention_required: true`** to **outputs/execution_status.json** (merge with existing keys; update `ibkr_state` to `"FROZEN"`).
2. Send a new Telegram alert type **connection_freeze** with payload `{state, latency_ms, reason}`.
3. All order submission paths in **ib_executor.py** must check **state_machine.can_submit_orders** before calling the broker. If **False**: log (e.g. WARNING) and skip submission without raising (return a result dict indicating skipped).

**Dashboard:** **scripts/dashboard.py** reads **outputs/execution_status.json** and displays a **banner**:

- **Amber** when `ibkr_state == "DEGRADED"`.
- **Red** when `ibkr_state` in `("FROZEN", "DISCONNECTED")` with text **"Manual Intervention Required"** (and use `manual_intervention_required` when true).
- Banner placement: near the top of the page (e.g. after sidebar, before Probabilistic Regime panel).

---

## Section 4 — Broker-Native Server-Side Stops

**Extension to existing Global Stop-Loss** (docs/RISK_MANAGEMENT_SPEC.md Section 2). The local engine stop-loss (drawdown_tracker, flatten all) remains as-is.

When the **IBKR paper or live** executor submits positions via **ib_executor.py**, it must attach a **bracket order** with a **server-side stop**:

- **Stop price:** `entry_price × (1 − stop_loss_per_position)`. `stop_loss_per_position` is configurable in **config/model_config.yaml** under **risk_management** (default **0.08** = 8% per position).
- **Stop type:** IBKR native **STP** (Stop) order, not a trailing stop.
- The stop order must be submitted as a **child** of the parent fill order (e.g. OCA group or bracket so the stop is linked to the position).
- If the broker **rejects** the stop attachment (e.g. bracket not supported for the contract), **log a WARNING** and **do not abort** the parent order; the parent fill still goes through.
- **Mock mode:** Skip stop attachment silently (no IBKR connection in mock; `ib_executor` is not used for real orders in mock).

**Config:** Add under **risk_management** in model_config.yaml: **stop_loss_per_position: 0.08**.

---

## Section 5 — File List & Integration Sequence

### New files

| File | Purpose |
|------|---------|
| src/data/data_quality.py | Defines **IncompleteDataError** and **DataQualityReport**; used by loaders and run_execution. |
| src/execution/ibkr_state_machine.py | **IBKRStateMachine** with states, heartbeat, latency, `can_submit_orders`, and FROZEN handling (execution_status.json + connection_freeze alert). |

### Modified files and integration order

1. **src/data/eodhd_news_loader.py** — Replace the single silent `except Exception` with ERROR logging, append to _load_warnings, return `(result, DataQualityReport)` (or raise IncompleteDataError for CRITICAL; EODHD is DEGRADED so return partial + report).
2. **src/data/news_fetcher_factory.py** — Where used in a pipeline that aggregates data quality, ensure callers can build DataQualityReport on failure (e.g. catch from create_from_config and add to degraded_missing). No change to create_source signature unless a unified loader API is introduced.
3. **src/monitoring/telegram_alerts.py** — Add alert type **connection_freeze**; payload `{state, latency_ms, reason}`; message format e.g. “Connection freeze: state={state}, latency_ms={latency_ms}, reason={reason}. Manual intervention may be required.”
4. **src/execution/ib_executor.py** — (a) Before any order submission, check **state_machine.can_submit_orders** (state machine must be injectable or accessible); if False, log and return without calling IB. (b) When submitting orders in paper/live mode, attach server-side STP stop per Section 4; on broker rejection of stop, log WARNING and do not abort parent.
5. **scripts/run_execution.py** — After data loading, obtain DataQualityReport; if not `can_rebalance`, write execution_status.json, return (1, []). Write execution_status.json on each run with as_of, can_rebalance, critical_missing, degraded_missing, warnings, ibkr_state (from state machine when available), manual_intervention_required.
6. **scripts/dashboard.py** — Read **outputs/execution_status.json**; display connection banner (amber for DEGRADED, red for FROZEN/DISCONNECTED with “Manual Intervention Required” when applicable).

**Note:** Telegram alerts live in **src/monitoring/telegram_alerts.py** (not src/execution). The connection_freeze alert is added there.

---

## Section 6 — Config Additions

Add to **config/model_config.yaml** under existing **risk_management:** (see `config/model_config.yaml:76–83`):

```yaml
risk_management:
  # ... existing keys (ic_baseline, stop_loss_threshold, etc.) ...
  stop_loss_per_position: 0.08
  ibkr_latency_threshold_ms: 500
  ibkr_freeze_latency_ms: 2000
  ibkr_freeze_timeout_seconds: 60
  critical_data_sources:
    - prices
    - smh_benchmark
    - regime_status
```

- **stop_loss_per_position:** Fraction of entry price for server-side stop (default 8%).
- **ibkr_latency_threshold_ms:** Above this, CONNECTED→DEGRADED (500 ms).
- **ibkr_freeze_latency_ms:** Above this, CONNECTED→FROZEN (2000 ms).
- **ibkr_freeze_timeout_seconds:** Time in FROZEN without recovery before FROZEN→DISCONNECTED (60 s).
- **critical_data_sources:** List of source names that must be present for rebalance (align with Section 1 table).

---

## Reconciliation

- **Circuit breaker vs state machine:** **src/execution/ibkr_bridge.py** defines **CircuitBreaker** (lines 163–237): 1-day drawdown kill switch (`record_nav`, `check_1d_drawdown`, `is_trading_paused`, `check_and_pause_if_breach`). It is **NAV-based** and does not model connection state or latency. The new **IBKRStateMachine** is **connection/latency-based**. They are **complementary**: CircuitBreaker can still pause trading on 1d drawdown; the state machine gates order submission on connection health. When both are used: order submission should respect **both** (e.g. `can_submit_orders` and not `is_trading_paused()`). No removal of CircuitBreaker; state machine is additive.
- **ib_executor.py order guards:** **src/execution/ib_executor.py** has **no** current check of a “can submit” or connection state before `placeOrder` (lines 93–94, 109). It does catch exceptions and re-raises (133–135). So the spec **adds** the `can_submit_orders` check; no existing guard conflicts.
- **can_submit_orders vs bypass:** If any code path is designed to “bypass” checks (e.g. admin override), the spec does not define one; the Engineer may add an override (e.g. env or config) that allows submission when state is FROZEN for emergency flatten. By default, `can_submit_orders` is the gate; no conflict with existing bypass logic because none exists today.
- **Telegram alerts path:** Section 5 lists “src/execution/telegram_alerts.py”; the actual module is **src/monitoring/telegram_alerts.py**. Add **connection_freeze** there.
- **IB provider location:** The task referenced **src/execution/ib_provider.py**; the codebase has **src/data/ib_provider.py** (IBDataProvider, `get_account_info`, `is_available`). The state machine may use the same IB connection (e.g. via `reqCurrentTime` or equivalent) for heartbeat; it can be wired to the executor’s `ib_provider` or the IB instance in `ib_executor`.
- **eodhd_news_loader return type:** Current callers (e.g. retrain_model, backtest) may expect a single return value (dict). Changing to `(result, DataQualityReport)` requires call sites to unpack or use a compatibility wrapper that returns only the dict and optionally fills a global/module report for aggregation.

---

**End of specification.**
