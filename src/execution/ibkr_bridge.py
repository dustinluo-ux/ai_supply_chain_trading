"""
Live Execution Bridge for IBKR: account monitoring, risk (Smart Stop), order dispatch, circuit breaker.

Uses src.data.ib_provider.IBDataProvider and src.execution.ib_executor.IBExecutor.
Design: docs/LIVE_EXECUTION_BRIDGE_DESIGN.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Order comment for audit: propagated/supply-chain signals must be tagged
PROHIBITED_LLM_DISCOVERY_LINK = "PROHIBITED_LLM_DISCOVERY_LINK"
LIVE_SPINE_TAG = "LIVE_SPINE"


# ---------------------------------------------------------------------------
# LiveSignal
# ---------------------------------------------------------------------------
@dataclass
class LiveSignal:
    """One signal to dispatch; is_propagated True → order comment PROHIBITED_LLM_DISCOVERY_LINK."""
    ticker: str
    weight: float  # target weight 0..1
    direction: str  # "BUY" | "SELL"
    is_propagated: bool  # True if from SentimentPropagator (source_type == "propagated")
    atr_per_share: float
    entry_price: float
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# AccountMonitor
# ---------------------------------------------------------------------------
class AccountMonitor:
    """Fetches and caches AvailableFunds, NetLiquidation, positions from IB via ib_provider."""

    def __init__(self, ib_provider: Any) -> None:
        """ib_provider: object with get_account_info() -> {margin_info, positions}."""
        self._provider = ib_provider
        self._snapshot: Dict[str, Any] = {"margin_info": {}, "positions": []}

    def refresh(self) -> None:
        """Refresh cache from ib_provider.get_account_info()."""
        try:
            self._snapshot = self._provider.get_account_info()
        except Exception as e:
            logger.warning("AccountMonitor refresh failed: %s", e)
            self._snapshot = {"margin_info": {}, "positions": []}

    def log_nav_snapshot(self, label: str, nav: float) -> None:
        """Log NAV for rebalance audit (e.g. 'Pre-Rebalance NAV', 'Post-Rebalance NAV')."""
        logger.info("%s: %.2f", label, nav)

    def get_available_funds(self) -> float:
        """AvailableFunds or FullAvailableFunds; 0 if disconnected."""
        mi = self._snapshot.get("margin_info") or {}
        v = mi.get("AvailableFunds") or mi.get("FullAvailableFunds")
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def get_net_liquidation(self) -> float:
        """NetLiquidation or TotalCashValue fallback."""
        mi = self._snapshot.get("margin_info") or {}
        v = mi.get("NetLiquidation") or mi.get("TotalCashValue")
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def get_existing_positions(self) -> List[Dict[str, Any]]:
        """List of {symbol, position, avgCost, market_value?} from cached positions."""
        pos_list = self._snapshot.get("positions") or []
        out = []
        for p in pos_list:
            rec = {
                "symbol": p.get("symbol", ""),
                "position": p.get("position", 0),
                "avgCost": p.get("avgCost", 0.0),
            }
            if "market_value" in p:
                rec["market_value"] = p["market_value"]
            else:
                rec["market_value"] = rec["position"] * rec["avgCost"]
            out.append(rec)
        return out

    def get_margin_utilization(self) -> Optional[float]:
        """MaintMarginReq / NetLiquidation (0–1+); None if missing."""
        mi = self._snapshot.get("margin_info") or {}
        maint = mi.get("MaintMarginReq")
        nav = mi.get("NetLiquidation")
        try:
            if maint is not None and nav is not None and float(nav) > 0:
                return float(maint) / float(nav)
        except (TypeError, ValueError):
            pass
        return None

    def get_account_snapshot(self) -> Dict[str, Any]:
        """Full cached {margin_info, positions} for PositionSizer/RiskManager."""
        return dict(self._snapshot)


# ---------------------------------------------------------------------------
# RiskManager (Smart Stop)
# ---------------------------------------------------------------------------
class RiskManager:
    """Smart Stop: entry ± atr_multiplier * ATR. Default atr_multiplier from config or 2.0."""

    def __init__(self, atr_multiplier: Optional[float] = None) -> None:
        if atr_multiplier is not None:
            self._atr_mult = float(atr_multiplier)
        else:
            try:
                from src.utils.config_manager import get_config
                self._atr_mult = float(
                    get_config().get_param("trading_config.position_sizing.atr_multiplier", 2.0)
                )
            except Exception:
                self._atr_mult = 2.0

    def compute_smart_stop(
        self,
        side: str,
        entry_price: float,
        atr_per_share: float,
    ) -> float:
        """
        Long: stop = entry - atr_mult * atr_per_share (floor 0.01).
        Short: stop = entry + atr_mult * atr_per_share.
        """
        delta = self._atr_mult * max(0.0, float(atr_per_share))
        if (side or "").upper() == "SELL":
            return float(entry_price) + delta
        stop = float(entry_price) - delta
        return max(0.01, stop)

    def get_stop_pct(
        self,
        side: str,
        entry_price: float,
        atr_per_share: float,
    ) -> float:
        """(entry - stop) / entry for long; (stop - entry) / entry for short; for logging."""
        stop = self.compute_smart_stop(side, entry_price, atr_per_share)
        ep = max(1e-8, float(entry_price))
        if (side or "").upper() == "SELL":
            return (stop - ep) / ep
        return (ep - stop) / ep


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------
class CircuitBreaker:
    """1-day drawdown kill switch: pause trading if NAV drop >= max_1d_drawdown_pct."""

    def __init__(self, config: Any = None) -> None:
        self._config = config
        self._enabled = True
        self._max_1d_pct = 0.05
        self._paused = False
        self._nav_history: List[tuple[float, float]] = []  # (timestamp_epoch, nav)
        self._load_config()

    def _load_config(self) -> None:
        if self._config is None:
            try:
                from src.utils.config_manager import get_config
                self._config = get_config()
            except Exception:
                pass
        if self._config is not None:
            try:
                self._enabled = bool(
                    self._config.get_param("strategy_params.circuit_breaker.enabled", True)
                )
                self._max_1d_pct = float(
                    self._config.get_param("strategy_params.circuit_breaker.max_1d_drawdown_pct", 0.05)
                )
            except Exception:
                pass

    def record_nav(self, timestamp: float, nav: float) -> None:
        """Store (timestamp, nav). Keep ~2 calendar days for 1d lookback."""
        self._nav_history.append((float(timestamp), float(nav)))
        # Keep last 500 points (enough for 2 days at 1/min)
        if len(self._nav_history) > 500:
            self._nav_history = self._nav_history[-500:]

    def check_1d_drawdown(self, current_nav: float) -> Optional[float]:
        """Return (current_nav - nav_1d_ago) / nav_1d_ago if we have history; else None."""
        if len(self._nav_history) < 2:
            return None
        # Simple: use oldest as proxy for "1d ago" or find closest to now - 1d
        import time
        now = time.time()
        one_day_sec = 86400.0
        target = now - one_day_sec
        best_ts, best_nav = self._nav_history[0]
        for ts, nav in self._nav_history:
            if abs(ts - target) < abs(best_ts - target):
                best_ts, best_nav = ts, nav
        if best_nav <= 0:
            return None
        return (current_nav - best_nav) / best_nav

    def is_trading_paused(self) -> bool:
        """True if enabled and (manually paused or 1d drawdown <= -max_1d_drawdown_pct)."""
        if not self._enabled:
            return False
        if self._paused:
            return True
        return False

    def pause(self) -> None:
        """Force pause (e.g. after breach)."""
        self._paused = True
        logger.warning("CircuitBreaker: trading PAUSED")

    def reset(self) -> None:
        """Clear pause (manual or after cooldown)."""
        self._paused = False
        logger.info("CircuitBreaker: trading reset (unpaused)")

    def check_and_pause_if_breach(self, current_nav: float) -> bool:
        """If 1d drawdown <= -max_1d_drawdown_pct, call pause() and return True."""
        dd = self.check_1d_drawdown(current_nav)
        if dd is not None and dd <= -self._max_1d_pct:
            logger.warning("CircuitBreaker: 1d drawdown %.2f%% >= max %.2f%% → pausing", dd * 100, self._max_1d_pct * 100)
            self.pause()
            return True
        return False


# ---------------------------------------------------------------------------
# RebalanceLogic (portfolio-level drift thresholds)
# ---------------------------------------------------------------------------
@dataclass
class RebalanceOrder:
    """One rebalance order: only generated if |drift| > threshold and |delta_dollars| > min_trade."""
    ticker: str
    side: str  # "BUY" | "SELL"
    quantity: int
    delta_dollars: float
    drift: float  # (current/target - 1) when target > 0
    target_weight: float
    current_weight: float
    target_dollars: float
    current_dollars: float


class RebalanceLogic:
    """
    Portfolio-level rebalancing: only generate orders when drift and min trade size are exceeded.
    Config: strategy_params.rebalancing.drift_threshold_pct, min_trade_dollar_value.
    """

    def __init__(
        self,
        drift_threshold_pct: Optional[float] = None,
        min_trade_dollar_value: Optional[float] = None,
    ) -> None:
        if drift_threshold_pct is not None:
            self._drift_threshold = float(drift_threshold_pct)
        else:
            try:
                from src.utils.config_manager import get_config
                self._drift_threshold = float(
                    get_config().get_param("strategy_params.rebalancing.drift_threshold_pct", 0.05)
                )
            except Exception:
                self._drift_threshold = 0.05
        if min_trade_dollar_value is not None:
            self._min_trade_dollar = float(min_trade_dollar_value)
        else:
            try:
                from src.utils.config_manager import get_config
                self._min_trade_dollar = float(
                    get_config().get_param("strategy_params.rebalancing.min_trade_dollar_value", 500.0)
                )
            except Exception:
                self._min_trade_dollar = 500.0

    def calculate_rebalance_orders(
        self,
        target_weights: Dict[str, float],
        current_positions: List[Dict[str, Any]],
        nav: float,
        prices: Dict[str, float],
    ) -> List[RebalanceOrder]:
        """
        Target Dollar = NAV * target_weight; Current Dollar from positions (market_value or position*price).
        Drift = (Current / Target) - 1 when Target > 0.
        Only include order if |drift| > drift_threshold_pct and |delta_dollars| > min_trade_dollar_value.
        """
        if nav <= 0:
            return []
        # Build current_dollars per symbol (use market_value if present, else position * prices[sym] or avgCost)
        current_dollars: Dict[str, float] = {}
        for p in current_positions:
            sym = (p.get("symbol") or "").strip().upper()
            if not sym:
                continue
            pos = float(p.get("position", 0))
            mv = p.get("market_value")
            if mv is not None:
                current_dollars[sym] = float(mv)
            else:
                price = prices.get(sym) or p.get("avgCost") or 0.0
                current_dollars[sym] = pos * float(price)
        # All tickers: union of target and current
        all_tickers = set(target_weights.keys()) | set(current_dollars.keys())
        orders: List[RebalanceOrder] = []
        for ticker in all_tickers:
            target_w = float(target_weights.get(ticker, 0.0))
            target_dollars = nav * target_w
            current_d = current_dollars.get(ticker, 0.0)
            current_w = (current_d / nav) if nav > 0 else 0.0
            # Drift: (current / target) - 1 when target > 0; else treat as "full rebalance" if current > 0
            if target_dollars > 0:
                drift = (current_d / target_dollars) - 1.0
            else:
                drift = 1.0 if current_d > 0 else 0.0
            delta_dollars = target_dollars - current_d
            # Filters
            if abs(drift) <= self._drift_threshold:
                continue
            if abs(delta_dollars) < self._min_trade_dollar:
                continue
            price = prices.get(ticker) or 0.0
            if price <= 0:
                continue
            quantity = int(round(abs(delta_dollars) / price))
            if quantity <= 0:
                continue
            side = "BUY" if delta_dollars > 0 else "SELL"
            orders.append(RebalanceOrder(
                ticker=ticker,
                side=side,
                quantity=quantity,
                delta_dollars=delta_dollars,
                drift=drift,
                target_weight=target_w,
                current_weight=current_w,
                target_dollars=target_dollars,
                current_dollars=current_d,
            ))
        return orders


# ---------------------------------------------------------------------------
# OrderDispatcher
# ---------------------------------------------------------------------------
class OrderDispatcher:
    """Converts LiveSignal to IB order with Smart Stop and order comment (PROHIBITED_LLM_DISCOVERY_LINK if propagated)."""

    def __init__(
        self,
        ib_executor: Any,
        risk_manager: RiskManager,
        account_monitor: AccountMonitor,
        trading_cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._executor = ib_executor
        self._risk = risk_manager
        self._account = account_monitor
        self._trading_cfg = trading_cfg or {}

    def _quantity_from_weight(
        self,
        weight: float,
        nav: float,
        price: float,
        min_order_size: int = 1,
        max_position_size: int = 10000,
    ) -> int:
        """Round to shares; cap by liquidity and max position size."""
        if price <= 0 or nav <= 0 or weight <= 0:
            return 0
        dollar = nav * weight
        shares = int(round(dollar / price))
        available = self._account.get_available_funds()
        if available > 0:
            max_by_liquidity = int(available / price)
            shares = min(shares, max_by_liquidity)
        shares = max(0, min(shares, max_position_size))
        if shares < min_order_size:
            return 0
        return shares

    def _place_order_with_stop(
        self,
        ticker: str,
        quantity: int,
        side: str,
        order_type: str,
        limit_price: Optional[float],
        stop_price: Optional[float],
        order_comment: Optional[str],
    ) -> Dict[str, Any]:
        """Call ib_executor.submit_order with comment and stop_price in kwargs."""
        kwargs: Dict[str, Any] = {}
        if order_comment is not None:
            kwargs["order_comment"] = order_comment
        if stop_price is not None:
            kwargs["stop_price"] = stop_price
        return self._executor.submit_order(
            ticker=ticker,
            quantity=quantity,
            side=side,
            order_type=order_type,
            limit_price=limit_price,
            **kwargs,
        )

    def dispatch(
        self,
        signal: LiveSignal,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        min_order_size: int = 1,
        max_position_size: int = 10000,
    ) -> Dict[str, Any]:
        """
        Convert LiveSignal to order: compute quantity, Smart Stop, set comment to
        PROHIBITED_LLM_DISCOVERY_LINK if signal.is_propagated else LIVE_SPINE_TAG.
        """
        nav = self._account.get_net_liquidation()
        if nav <= 0:
            nav = 1.0  # fallback to avoid zero
        quantity = self._quantity_from_weight(
            signal.weight,
            nav,
            signal.entry_price,
            min_order_size=min_order_size,
            max_position_size=max_position_size,
        )
        if quantity <= 0:
            return {
                "order_id": None,
                "ticker": signal.ticker,
                "quantity": 0,
                "side": signal.direction,
                "stop_price": None,
                "comment": None,
                "status": "skipped",
                "reason": "quantity 0 (below min or no size)",
            }
        stop_price = self._risk.compute_smart_stop(
            signal.direction,
            signal.entry_price,
            signal.atr_per_share,
        )
        comment = PROHIBITED_LLM_DISCOVERY_LINK if signal.is_propagated else LIVE_SPINE_TAG
        try:
            result = self._place_order_with_stop(
                ticker=signal.ticker,
                quantity=quantity,
                side=signal.direction,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                order_comment=comment,
            )
            result["stop_price"] = stop_price
            result["comment"] = comment
            return result
        except Exception as e:
            logger.exception("OrderDispatcher dispatch failed for %s: %s", signal.ticker, e)
            return {
                "order_id": None,
                "ticker": signal.ticker,
                "quantity": quantity,
                "side": signal.direction,
                "stop_price": stop_price,
                "comment": comment,
                "status": "error",
                "error": str(e),
            }

    def dispatch_from_delta(
        self,
        ticker: str,
        quantity: int,
        side: str,
        entry_price: float,
        atr_per_share: float,
        is_propagated: bool,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch using explicit quantity (e.g. from delta_trades). Still applies Smart Stop
        and order comment PROHIBITED_LLM_DISCOVERY_LINK when is_propagated is True.
        """
        if quantity <= 0:
            return {
                "order_id": None,
                "ticker": ticker,
                "quantity": 0,
                "side": side,
                "stop_price": None,
                "comment": None,
                "status": "skipped",
                "reason": "quantity <= 0",
            }

        # Load execution limits
        try:
            _exec_cfg = self._trading_cfg.get("execution", {})
        except AttributeError:
            _exec_cfg = {}
        _min_order_size = int(_exec_cfg.get("min_order_size", 1))
        _max_position_size = int(_exec_cfg.get("max_position_size", 10000))

        # Derive current position for ticker
        _current_pos = 0
        try:
            _positions = self._account.get_existing_positions()
            for _rec in (_positions or []):
                if str(_rec.get("symbol", "")).upper() == ticker.upper():
                    _current_pos = int(_rec.get("position", 0))
                    break
        except Exception:
            _current_pos = 0

        # Enforce min_order_size
        if quantity < _min_order_size:
            return {
                "order_id": None,
                "ticker": ticker,
                "quantity": 0,
                "side": side,
                "stop_price": None,
                "comment": None,
                "status": "skipped",
                "reason": f"quantity {quantity} below min_order_size {_min_order_size}",
            }

        # Enforce max_position_size (BUY only)
        if side.upper() == "BUY":
            quantity = min(quantity, max(0, _max_position_size - _current_pos))
            if quantity <= 0:
                return {
                    "order_id": None,
                    "ticker": ticker,
                    "quantity": 0,
                    "side": side,
                    "stop_price": None,
                    "comment": None,
                    "status": "skipped",
                    "reason": f"would exceed max_position_size {_max_position_size}",
                }

        stop_price = self._risk.compute_smart_stop(side, entry_price, atr_per_share)
        comment = PROHIBITED_LLM_DISCOVERY_LINK if is_propagated else LIVE_SPINE_TAG
        try:
            result = self._place_order_with_stop(
                ticker=ticker,
                quantity=quantity,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                order_comment=comment,
            )
            result["stop_price"] = stop_price
            result["comment"] = comment
            return result
        except Exception as e:
            logger.exception("OrderDispatcher dispatch_from_delta failed for %s: %s", ticker, e)
            return {
                "order_id": None,
                "ticker": ticker,
                "quantity": quantity,
                "side": side,
                "stop_price": stop_price,
                "comment": comment,
                "status": "error",
                "error": str(e),
            }


def check_fill(
    ticker: str,
    side: str,
    quantity_submitted: int,
    position_before: int,
    position_after: int,
) -> dict:
    """Compare expected vs actual position delta for one submitted order.

    Returns a dict with keys:
      ticker, side, quantity_expected, delta_actual, passed (bool), reason (str)
    """
    expected_delta = quantity_submitted if side.upper() == "BUY" else -quantity_submitted
    actual_delta = position_after - position_before

    if expected_delta > 0 and actual_delta <= 0:
        passed = False
        reason = f"BUY expected delta +{expected_delta}, got {actual_delta} (wrong direction)"
    elif expected_delta < 0 and actual_delta >= 0:
        passed = False
        reason = f"SELL expected delta {expected_delta}, got {actual_delta} (wrong direction)"
    elif actual_delta == expected_delta:
        passed = True
        reason = "full fill confirmed"
    else:
        passed = True  # right direction, partial fill
        reason = f"partial fill: expected {expected_delta}, got {actual_delta}"

    return {
        "ticker": ticker,
        "side": side,
        "quantity_expected": quantity_submitted,
        "delta_actual": actual_delta,
        "passed": passed,
        "reason": reason,
    }
