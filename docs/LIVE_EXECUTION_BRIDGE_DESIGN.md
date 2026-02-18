# LiveExecutionBridge for IBKR — Design for Review

**Status:** Proposed (awaiting approval before implementation)  
**Canonical refs:** INDEX.md, AI_RULES.md, SYSTEM_MAP.md, WORKFLOW.md  
**Config refs:** `config/trading_config.yaml`, `config/strategy_params.yaml`, `config/config.yaml`

---

## 1. Evidence Summary

| Claim | Evidence |
|-------|----------|
| IB connection and account data | `src/data/ib_provider.py` L229–264 `get_account_info()`: returns `margin_info` (NetLiquidation, TotalCashValue, EquityWithLoanValue, InitMarginReq, MaintMarginReq, **BuyingPower**, **AvailableFunds**, ExcessLiquidity, FullInitMarginReq, FullMaintMarginReq, FullAvailableFunds, FullExcessLiquidity) and `positions`. |
| IB executor and order API | `src/execution/ib_executor.py` L30–90 `submit_order(ticker, quantity, side, order_type, limit_price, **kwargs)`; uses `ib_insync` MarketOrder/LimitOrder; no order comment or attached stop today. L118–146 `get_positions()`, L148–164 `get_account_value()` (via `ib_provider.get_account_info()`). |
| Trading config | `config/trading_config.yaml`: `trading.ib` (host, port, client_id), `trading.execution` (paper_account, live_account, min_order_size, max_position_size), `position_sizing` (risk_pct, atr_multiplier). |
| Drawdown kill switch (existing) | `config/config.yaml` L74: `backtest.max_drawdown_pct: -0.15` (backtest context). User requirement: circuit breaker for **live** in `strategy_params.yaml`. |
| Position sizing / ATR stop distance | `src/portfolio/position_sizer.py` L36–87 `compute_weights()`: uses `atr_multiplier` as “stop distance in ATRs”; config `trading_config.position_sizing`. No standalone RiskManager or Smart Stop in `src/`. |
| Propagated vs direct signal | `src/signals/sentiment_propagator.py` L21–34 `PropagatedSignal`: `source_type: str` — `'direct'` or `'propagated'`. L208–218: propagated signals set `source_type='propagated'`. |
| PositionManager account adapter | `src/portfolio/position_manager.py` L36–44: accepts provider with `get_account_info()` or executor with `get_positions()` + `get_account_value()`; L53–57, L84–87 use `margin_info.NetLiquidation`, `TotalCashValue`. |

---

## 2. Proposed Class Structure

### 2.1 New Module: `src/execution/ibkr_bridge.py`

**Purpose:** Live spine for IBKR: account monitoring, liquidity-aware sizing input, order dispatch with safety (Smart Stop), supply-chain order tagging, and circuit breaker. Uses existing `ib_insync` and `IBDataProvider`; no new connection stack.

---

#### 2.1.1 AccountMonitor

| Member | Type | Description |
|--------|------|-------------|
| `__init__(self, ib_provider: IBDataProvider)` | — | Holds reference to connected `IBDataProvider` (from `src.data.ib_provider`). |
| `refresh(self) -> None` | method | Calls `ib_provider.get_account_info()`; caches result for current snapshot. |
| `get_available_funds(self) -> float` | method | Returns `margin_info.get("AvailableFunds", 0)` or `FullAvailableFunds`; 0 if disconnected. |
| `get_net_liquidation(self) -> float` | method | Returns `margin_info.get("NetLiquidation", 0)` or `TotalCashValue` fallback. |
| `get_existing_positions(self) -> list[dict]` | method | Returns list of `{symbol, position, avgCost, market_value?}` from cached positions. |
| `get_margin_utilization(self) -> float \| None` | method | If `MaintMarginReq` and `NetLiquidation` present, return `MaintMarginReq / NetLiquidation` (0–1+); else `None`. |
| `get_account_snapshot(self) -> dict` | method | Returns full cached `{margin_info, positions}` for PositionSizer and RiskManager. |

**Integration with PositionSizer:** PositionSizer (or the live execution path) receives `get_account_snapshot()` or at least `get_available_funds()` and `get_net_liquidation()` so that signal conviction is adjusted by actual liquidity (e.g. cap target dollar exposure by AvailableFunds, or scale weights by NetLiquidation).

**Evidence:** `src/data/ib_provider.py` L240–246 already exposes `AvailableFunds`, `BuyingPower`, `MaintMarginReq`, `NetLiquidation` in `margin_info`.

---

#### 2.1.2 RiskManager (Smart Stop)

| Member | Type | Description |
|--------|------|-------------|
| `__init__(self, atr_multiplier: float \| None = None)` | — | `atr_multiplier` from config (`trading_config.position_sizing.atr_multiplier`) or default 2.0. |
| `compute_smart_stop(self, side: str, entry_price: float, atr_per_share: float) -> float` | method | **Long:** `stop_price = entry_price - atr_multiplier * atr_per_share`. **Short:** `stop_price = entry_price + atr_multiplier * atr_per_share`. Floor at 0.01 for long, no cap for short. Returns stop price (not percent). |
| `get_stop_pct(self, side: str, entry_price: float, atr_per_share: float) -> float` | method | Optional: returns (entry - stop) / entry for long, for logging or bracket order percent. |

**Safety rule:** Every live order must include a Smart Stop. Implementation can attach it as (1) a separate STP LMT or MOC parent/child, or (2) a trailing stop order, or (3) at minimum store stop_price in order metadata and submit a follow-up stop order after fill — design leaves execution detail to implementation; contract is “OrderDispatcher always calls RiskManager.compute_smart_stop() and associates the result with the order”.

---

#### 2.1.3 OrderDispatcher

| Member | Type | Description |
|--------|------|-------------|
| `__init__(self, ib_executor: IBExecutor, risk_manager: RiskManager, account_monitor: AccountMonitor)` | — | Depends on existing `IBExecutor` (from `src.execution.ib_executor`), RiskManager, AccountMonitor. |
| `dispatch(self, signal: LiveSignal) -> dict` | method | Converts one signal to an IBKR order (Market or Limit), attaches Smart Stop, sets order comment per §2.1.4. Returns order result dict (order_id, ticker, quantity, side, stop_price, comment, etc.). |
| `_quantity_from_weight(self, weight: float, nav: float, price: float) -> int` | private | Rounds to shares; respects `trading_config.execution.min_order_size` and `max_position_size`. Uses `account_monitor.get_available_funds()` or `nav` to cap by liquidity. |
| `_place_order_with_stop(self, ticker, quantity, side, order_type, limit_price, stop_price, comment) -> dict` | private | Calls `ib_executor.submit_order(..., **kwargs)`; passes `comment` via IB order tag if API supports it; places or schedules stop order per implementation. |

**LiveSignal (proposed dataclass):**

```python
@dataclass
class LiveSignal:
    ticker: str
    weight: float          # target weight 0..1
    direction: str        # "BUY" | "SELL"
    is_propagated: bool   # True if signal came from SentimentPropagator (source_type == "propagated")
    atr_per_share: float  # for Smart Stop
    entry_price: float    # current/mid for sizing and stop
    metadata: dict | None # optional: source_ticker, regime, etc.
```

**Evidence:** `IBExecutor.submit_order` L30–90 accepts `**kwargs`; IB `Order` objects typically support a reference or tag field that can carry the comment (exact field name in ib_insync to be used in implementation).

---

#### 2.1.4 Supply Chain Execution Logic (Order Comment)

**Rule:** If a signal is **propagated** (e.g. news for NVDA creates a buy signal for TSM), the order comment must reflect: **`PROHIBITED_LLM_DISCOVERY_LINK`**.

**Rationale:** Audit trail so that orders stemming from LLM-discovered or propagated links are identifiable and can be prohibited or reviewed in compliance.

**Implementation:** When building the order in `OrderDispatcher.dispatch()`:

- If `signal.is_propagated is True` → set order comment (or IB tag/ref) to `"PROHIBITED_LLM_DISCOVERY_LINK"`.
- Otherwise → comment can be empty or a generic tag (e.g. `"LIVE_SPINE"`).

**Evidence:** `PropagatedSignal.source_type` in `src/signals/sentiment_propagator.py` L32 is `'direct'` or `'propagated'`. The live spine must receive a flag per ticker/signal indicating whether that signal came from propagation; that flag is `is_propagated` on `LiveSignal`.

---

#### 2.1.5 Circuit Breaker (Global Kill Switch)

**Rule:** If the **1-day portfolio drawdown** exceeds X% (from config), pause all trading (no new orders until reset or manual override).

**Config (proposed addition to `config/strategy_params.yaml`):**

```yaml
circuit_breaker:
  enabled: true
  max_1d_drawdown_pct: 0.05   # 5%: pause if 1-day NAV drop >= 5%
  # Optional: cooldown_minutes: 60  # require manual reset or wait before re-enable
```

**Class: CircuitBreaker**

| Member | Type | Description |
|--------|------|-------------|
| `__init__(self, config)` | — | Reads `strategy_params.circuit_breaker.enabled`, `max_1d_drawdown_pct` via ConfigManager. |
| `record_nav(self, timestamp, nav: float) -> None` | method | Store (timestamp, nav) for 1-day lookback (e.g. rolling 2 calendar days). |
| `check_1d_drawdown(self, current_nav: float) -> float \| None` | method | Compute 1-day ago NAV from stored series; return (current_nav - nav_1d_ago) / nav_1d_ago if available, else None. |
| `is_trading_paused(self) -> bool` | method | Returns True if `enabled` and 1-day drawdown <= -max_1d_drawdown_pct (e.g. -5% → pause). Once paused, remains True until reset (manual or cooldown). |
| `pause(self) -> None` | method | Force pause (e.g. after breach). |
| `reset(self) -> None` | method | Clear pause (manual or after cooldown). |

**Integration:** Before any order is sent, the Live Spine (or OrderDispatcher) calls `circuit_breaker.is_trading_paused()`. If True, do not call `dispatch()`; log and optionally notify. `record_nav()` is called after each account refresh (e.g. from AccountMonitor) so 1-day drawdown is always current.

**Evidence:** `config/config.yaml` L74 defines `backtest.max_drawdown_pct: -0.15` for backtest; live circuit breaker is separate and in `strategy_params.yaml` per user request.

---

## 3. Signal-to-Trade Sequence Diagram

```mermaid
sequenceDiagram
    participant Spine as Live Spine (run_execution / target_weight_pipeline)
    participant SE as SignalEngine
    participant PE as PolicyEngine
    participant PoE as PortfolioEngine
    participant CB as CircuitBreaker
    participant AM as AccountMonitor
    participant PS as PositionSizer / RiskManager
    participant OD as OrderDispatcher
    participant IB as IBExecutor / IBKR

    Spine->>AM: refresh()
    AM->>IB: get_account_info()
    IB-->>AM: margin_info, positions
    AM-->>Spine: snapshot (AvailableFunds, NAV, positions)

    Spine->>SE: generate(as_of, universe, data_context)
    SE-->>Spine: scores, aux (atr_norms, regime, buzz, etc.)

    Spine->>PE: apply(scores, aux, context)
    PE-->>Spine: gated_scores

    Spine->>CB: check_1d_drawdown(current_nav)
    CB-->>Spine: is_paused?
    alt is_trading_paused
        Spine-->>Spine: Log "Circuit breaker active"; skip orders; exit
    end

    Spine->>PoE: build(as_of, gated_scores, context)
    PoE-->>Spine: Intent (tickers, weights)

    Spine->>AM: get_available_funds() / get_net_liquidation()
    AM-->>Spine: liquidity
    Spine->>PS: compute_weights / adjust by liquidity (optional)
    PS-->>Spine: final weights

    loop For each (ticker, weight) in Intent
        Spine->>Spine: Build LiveSignal (ticker, weight, direction, is_propagated, atr, price)
        Spine->>OD: dispatch(LiveSignal)
        OD->>PS: compute_smart_stop(side, entry_price, atr)
        PS-->>OD: stop_price
        OD->>OD: Set comment = PROHIBITED_LLM_DISCOVERY_LINK if is_propagated
        OD->>IB: submit_order(ticker, quantity, side, order_type, limit_price?, comment, stop_price)
        IB->>IBKR: placeOrder(contract, order) [+ attach stop]
        IBKR-->>IB: trade ack
        IB-->>OD: order result
        OD-->>Spine: order result
    end

    Spine->>AM: record_nav(now, nav)  [for next 1d drawdown]
    Spine->>CB: record_nav(now, nav)
```

---

## 4. Data Flow Summary

1. **AccountMonitor** refreshes from IB → provides Available Funds, NAV, positions, margin utilization.
2. **PositionSizer** (and optionally a liquidity cap step) uses account snapshot so conviction is adjusted by actual liquidity.
3. **CircuitBreaker** uses 1-day NAV history; if drawdown exceeds X%, `is_trading_paused()` is True and no orders are dispatched.
4. **OrderDispatcher** converts each Intent item to a **LiveSignal**, then to an IB order with **Smart Stop** from **RiskManager** and order comment **PROHIBITED_LLM_DISCOVERY_LINK** when the signal is propagated.
5. **Propagated** flag must be set by the spine from signal metadata (e.g. from SentimentPropagator’s output or from aux that marks which scores came from propagation).

---

## 5. Files to Touch (Implementation Phase)

| File | Action |
|------|--------|
| `src/execution/ibkr_bridge.py` | **Create:** AccountMonitor, RiskManager, OrderDispatcher, CircuitBreaker, LiveSignal. |
| `src/execution/ib_executor.py` | **Modify:** Extend `submit_order()` to accept optional `order_comment` and `stop_price` (or equivalent) and attach stop order / tag per IB API. |
| `config/strategy_params.yaml` | **Modify:** Add `circuit_breaker` section. |
| `docs/SYSTEM_MAP.md` | **Update:** Stage 6 — add `ibkr_bridge.py` (AccountMonitor, OrderDispatcher, CircuitBreaker); document Live Spine flow. |
| `docs/WORKFLOW.md` or execution doc | **Update:** Add Live Execution paragraph and reference this design. |

---

## 6. Interface Impact

| Item | Impact |
|------|--------|
| `IBExecutor.submit_order()` | **PROPOSED:** Optional kwargs `order_comment: str \| None`, `stop_price: float \| None`; behavior: set order ref/tag and place or link stop order. |
| New public types | **PROPOSED:** `LiveSignal` dataclass; return shape of `OrderDispatcher.dispatch()`. |
| `config/strategy_params.yaml` | **PROPOSED:** New `circuit_breaker` block. |
| PositionSizer / PortfolioEngine | **NONE** for basic flow; optional later: pass `account_snapshot` into sizing so weights respect AvailableFunds. |

Per AI_RULES §5, interface impact is PROPOSED; approval required before implementation.

---

## 7. Validation (After Implementation)

- Unit: AccountMonitor returns numeric AvailableFunds and NetLiquidation when given a mock provider with fixed `get_account_info()`.
- Unit: RiskManager.compute_smart_stop(long, 100, 2) with atr_multiplier=2 → stop_price = 96.
- Unit: CircuitBreaker with recorded NAV 100 → 94 → is_trading_paused True when max_1d_drawdown_pct = 0.05.
- Integration: LiveSignal with is_propagated=True → order comment contains PROHIBITED_LLM_DISCOVERY_LINK.
- Integration: When circuit breaker paused, dispatch() is never called (or returns immediately without placing order).

---

This design is the proposed LiveExecutionBridge for IBKR. If approved, next step is implementation per §5 and validation per §7.
