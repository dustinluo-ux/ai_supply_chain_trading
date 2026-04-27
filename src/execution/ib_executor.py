"""
IB Executor - Interactive Brokers order execution
"""

import os
import pandas as pd
from pathlib import Path
from typing import Any, Dict, Optional
from ib_insync import MarketOrder, LimitOrder, Order
from src.execution.base_executor import BaseExecutor
from src.data.ib_provider import IBDataProvider
from src.utils.logger import setup_logger

logger = setup_logger()
ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_ib_contract(ticker: str) -> tuple[str, str, str]:
    """Return (symbol, exchange, currency) for IB Stock contract from canonical ticker."""
    t = (ticker or "").strip()
    if t.endswith(".T"):
        return t[:-2], "TSE", "JPY"
    if t.endswith(".HK"):
        return t[:-3], "SEHK", "HKD"
    if t.endswith(".DE"):
        return t[:-3], "IBIS", "EUR"
    if t.endswith(".CO"):
        return t[:-3], "SFB", "DKK"
    return t, "SMART", "USD"


class IBExecutor(BaseExecutor):
    """Interactive Brokers executor for live/paper trading."""

    def __init__(self, ib_provider: IBDataProvider, account: str):
        """
        Initialize IB executor.

        Args:
            ib_provider: IBDataProvider instance (must be connected)
            account: Account number (paper or live)
        """
        self.ib_provider = ib_provider
        self.ib = ib_provider.ib
        self.account = account
        logger.info(f"IBExecutor initialized for account: {account}")

    def _load_risk_config(self) -> Dict:
        """Read risk_management from config/model_config.yaml."""
        path = ROOT / "config" / "model_config.yaml"
        if not path.exists():
            return {}
        try:
            import yaml

            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("risk_management", {}) or {}
        except Exception:
            return {}

    def _load_execution_config(self) -> Dict:
        """Read execution guardrails from config/trading_config.yaml."""
        path = ROOT / "config" / "trading_config.yaml"
        if not path.exists():
            return {}
        try:
            import yaml

            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return (cfg.get("trading", {}) or {}).get("execution", {}) or {}
        except Exception:
            return {}

    def validate_order_request(
        self,
        ticker: str,
        quantity: int,
        side: str,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
    ) -> None:
        """Fail before any broker call if an order request is structurally unsafe."""
        if not getattr(self.ib, "isConnected", lambda: False)():
            raise RuntimeError("IBKR preflight failed: broker is not connected")

        symbol = (ticker or "").strip().upper()
        if not symbol:
            raise ValueError("IBKR preflight failed: ticker is required")
        if not all(ch.isalnum() or ch in "._-" for ch in symbol):
            raise ValueError(f"IBKR preflight failed: invalid ticker {ticker!r}")

        try:
            qty = int(quantity)
        except (TypeError, ValueError):
            raise ValueError(f"IBKR preflight failed: invalid quantity {quantity!r}")
        if qty <= 0:
            raise ValueError("IBKR preflight failed: quantity must be positive")

        side_u = (side or "").strip().upper()
        if side_u not in {"BUY", "SELL"}:
            raise ValueError(f"IBKR preflight failed: unsupported side {side!r}")

        order_type_u = (order_type or "").strip().upper()
        if order_type_u not in {"MARKET", "LIMIT"}:
            raise ValueError(
                f"IBKR preflight failed: unsupported order type {order_type!r}"
            )
        if order_type_u == "LIMIT":
            if limit_price is None or float(limit_price) <= 0:
                raise ValueError("IBKR preflight failed: LIMIT order needs price > 0")

        account = (self.account or "").strip()
        if not account or account == "U123456":
            raise RuntimeError("IBKR preflight failed: real account id is not set")
        if account.upper().startswith("U") and os.environ.get("ALLOW_LIVE_IBKR") != "1":
            raise RuntimeError(
                "IBKR preflight failed: live account blocked unless ALLOW_LIVE_IBKR=1"
            )

        exec_cfg = self._load_execution_config()
        max_qty = int(exec_cfg.get("max_order_quantity", 0) or 0)
        max_position_size = int(exec_cfg.get("max_position_size", 0) or 0)
        if max_qty <= 0:
            max_qty = max_position_size
        if max_qty > 0 and qty > max_qty:
            raise RuntimeError(
                f"IBKR preflight failed: quantity {qty} exceeds max {max_qty}"
            )

    def submit_contract_order(
        self,
        contract: Any,
        ticker: str,
        quantity: int,
        side: str,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        order_comment: Optional[str] = None,
    ) -> Dict:
        """Submit an already-resolved IB contract after common preflight checks."""
        self.validate_order_request(ticker, quantity, side, order_type, limit_price)

        if order_type.upper() == "MARKET":
            order = MarketOrder(side.upper(), int(quantity))
        elif order_type.upper() == "LIMIT":
            if limit_price is None:
                raise ValueError("limit_price required for LIMIT orders")
            order = LimitOrder(side.upper(), int(quantity), float(limit_price))
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

        order.account = self.account
        if order_comment is not None and isinstance(order_comment, str):
            order.orderRef = order_comment[:128]

        trade = self.ib.placeOrder(contract, order)
        logger.info(
            "Contract order submitted: %s %s %s (%s) ref=%r",
            side.upper(),
            quantity,
            ticker,
            order_type,
            order_comment,
        )
        return {
            "order_id": str(trade.order.orderId),
            "ticker": ticker,
            "quantity": int(quantity),
            "side": side.upper(),
            "order_type": order_type,
            "status": trade.orderStatus.status,
            "filled_quantity": trade.orderStatus.filled,
            "filled_price": (
                trade.orderStatus.avgFillPrice
                if trade.orderStatus.avgFillPrice > 0
                else None
            ),
            "order_comment": order_comment,
        }

    def submit_order(
        self,
        ticker: str,
        quantity: int,
        side: str,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        order_comment: Optional[str] = None,
        stop_price: Optional[float] = None,
        state_machine: Any = None,
        attach_server_stops: bool = True,
        **kwargs,
    ) -> Dict:
        """
        Submit order to IB.

        Args:
            ticker: Stock ticker
            quantity: Number of shares
            side: 'BUY' or 'SELL'
            order_type: 'MARKET' or 'LIMIT'
            limit_price: Required for LIMIT orders
            order_comment: Optional ref/tag (e.g. PROHIBITED_LLM_DISCOVERY_LINK, LIVE_SPINE); set on order.orderRef
            stop_price: Optional; stored in return for bracket/stop; caller may place stop separately
            state_machine: Optional IBKRStateMachine; if provided and can_submit_orders is False, no order is submitted.
            attach_server_stops: If False (e.g. mock mode), server-side STP is not attached; default True.
            **kwargs: Additional parameters

        Returns:
            Dict with order information (includes stop_price, order_comment when provided), or False if guarded by state_machine.
        """
        from ib_insync import Stock

        if state_machine is not None and not getattr(
            state_machine, "can_submit_orders", True
        ):
            state = getattr(state_machine, "current_state", "?")
            logger.error(
                "[IBExecutor] Order guard: can_submit_orders is False (state=%s); skipping order ticker=%s side=%s quantity=%s",
                state,
                ticker,
                side,
                quantity,
            )
            return False

        self.validate_order_request(ticker, quantity, side, order_type, limit_price)

        try:
            # Create contract
            symbol, exchange, currency = _resolve_ib_contract(ticker)
            contract = Stock(symbol, exchange, currency)
            self.ib.qualifyContracts(contract)

            # Create order
            if order_type.upper() == "MARKET":
                order = MarketOrder(side.upper(), quantity)
            elif order_type.upper() == "LIMIT":
                if limit_price is None:
                    raise ValueError("limit_price required for LIMIT orders")
                order = LimitOrder(side.upper(), quantity, limit_price)
            else:
                raise ValueError(f"Unsupported order type: {order_type}")

            order.account = self.account
            if order_comment is not None and isinstance(order_comment, str):
                order.orderRef = order_comment[
                    :128
                ]  # IB typically allows limited ref length

            # Submit order
            trade = self.ib.placeOrder(contract, order)

            # Optional: place stop order if stop_price provided, or server-side STP from config (paper/live only)
            stop_order_id = None
            effective_stop_price: Optional[float] = stop_price
            if stop_price is not None and quantity != 0:
                try:
                    stop_side = "SELL" if side.upper() == "BUY" else "BUY"
                    stop_order = Order()
                    stop_order.orderType = "STP"
                    stop_order.auxPrice = float(stop_price)
                    stop_order.action = stop_side
                    stop_order.totalQuantity = abs(quantity)
                    stop_order.account = self.account
                    if order_comment:
                        stop_order.orderRef = order_comment[:128]
                    stop_trade = self.ib.placeOrder(contract, stop_order)
                    stop_order_id = str(stop_trade.order.orderId)
                except Exception as se:
                    logger.warning(
                        "Stop order placement failed (main order still placed) ticker=%s: %s",
                        ticker,
                        se,
                    )
            elif attach_server_stops and quantity != 0:
                # Server-side STP from risk_management.stop_loss_per_position (after fill)
                try:
                    _risk_cfg = self._load_risk_config()
                    stop_loss_frac = float(
                        _risk_cfg.get("stop_loss_per_position", 0.08)
                    )
                    fill_ok = False
                    entry = 0.0
                    try:
                        if hasattr(trade, "fillEvent") and trade.fillEvent:
                            trade.fillEvent.wait(timeout=5)
                        if (
                            trade.orderStatus.avgFillPrice
                            and trade.orderStatus.avgFillPrice > 0
                        ):
                            entry = float(trade.orderStatus.avgFillPrice)
                            fill_ok = True
                    except Exception:
                        pass
                    if fill_ok:
                        is_long = quantity > 0
                        if is_long:
                            effective_stop_price = entry * (1.0 - stop_loss_frac)
                        else:
                            effective_stop_price = entry * (1.0 + stop_loss_frac)
                        stop_side = "SELL" if is_long else "BUY"
                        stop_order = Order()
                        stop_order.orderType = "STP"
                        stop_order.auxPrice = effective_stop_price
                        stop_order.action = stop_side
                        stop_order.totalQuantity = abs(quantity)
                        stop_order.account = self.account
                        if order_comment:
                            stop_order.orderRef = order_comment[:128]
                        stop_trade = self.ib.placeOrder(contract, stop_order)
                        stop_order_id = str(stop_trade.order.orderId)
                    else:
                        logger.warning(
                            "Could not get fill price for server-side stop ticker=%s; skip STP",
                            ticker,
                        )
                except Exception as se:
                    logger.warning(
                        "Server-side STP attachment failed (main order still placed) ticker=%s: %s",
                        ticker,
                        se,
                    )
            elif not attach_server_stops and quantity != 0:
                logger.debug("Server-side stops are not attached in mock mode.")

            logger.info(
                f"Order submitted: {side} {quantity} {ticker} ({order_type}) ref={order_comment!r} stop={effective_stop_price}"
            )

            out = {
                "order_id": str(trade.order.orderId),
                "ticker": ticker,
                "quantity": quantity,
                "side": side.upper(),
                "order_type": order_type,
                "status": trade.orderStatus.status,
                "filled_quantity": trade.orderStatus.filled,
                "filled_price": (
                    trade.orderStatus.avgFillPrice
                    if trade.orderStatus.avgFillPrice
                    else 0.0
                ),
            }
            if order_comment is not None:
                out["order_comment"] = order_comment
            if effective_stop_price is not None:
                out["stop_price"] = effective_stop_price
            if stop_order_id is not None:
                out["stop_order_id"] = stop_order_id
            return out

        except Exception as e:
            logger.error(f"Error submitting order for {ticker}: {e}")
            raise

    def cancel_all_orders(self, timeout_seconds: int = 30) -> list:
        """Cancel all open orders; poll until drain or timeout. Returns list of cancelled order IDs. Never raises."""
        is_connected = getattr(self.ib, "isConnected", lambda: False)()
        if not is_connected:
            logger.warning("[IBExecutor] cancel_all_orders: not connected — skipping")
            return []
        try:
            self.ib.reqAllOpenOrders()
            open_orders = getattr(self.ib, "openOrders", lambda: [])()
            if not open_orders and hasattr(self.ib, "openTrades"):
                open_orders = [getattr(t, "order", t) for t in self.ib.openTrades()]
            cancelled_ids = []
            for order in open_orders:
                oid = getattr(order, "orderId", None)
                if oid is not None:
                    cancelled_ids.append(oid)
                self.ib.cancelOrder(order)
            initial_count = len(cancelled_ids)
            for _ in range(timeout_seconds):
                sleep_fn = getattr(self.ib, "sleep", None)
                if sleep_fn is not None and callable(sleep_fn):
                    sleep_fn(1)
                else:
                    import time

                    time.sleep(1)
                remaining = getattr(self.ib, "openOrders", lambda: [])()
                if not remaining and hasattr(self.ib, "openTrades"):
                    remaining = self.ib.openTrades()
                remaining = len(remaining) if isinstance(remaining, list) else 0
                if remaining == 0:
                    break
            remaining_final = getattr(self.ib, "openOrders", lambda: [])()
            if not remaining_final and hasattr(self.ib, "openTrades"):
                remaining_final = self.ib.openTrades()
            remaining_final = (
                len(remaining_final) if isinstance(remaining_final, list) else 0
            )
            logger.info(
                "[IBExecutor] cancel_all_orders: cancelled %d orders, remaining=%d",
                initial_count,
                remaining_final,
            )
            return cancelled_ids
        except Exception as e:
            logger.error("[IBExecutor] cancel_all_orders failed: %s", e)
            return []

    def verify_safe_state(self, timeout_seconds: int = 10) -> dict:
        """Check that no open orders remain after reqAllOpenOrders. Returns dict with safe_state, open_orders_remaining. Never raises."""
        is_connected = getattr(self.ib, "isConnected", lambda: False)()
        if not is_connected:
            return {
                "safe_state": False,
                "open_orders_remaining": -1,
                "note": "not connected",
            }
        try:
            self.ib.reqAllOpenOrders()
            for _ in range(timeout_seconds):
                sleep_fn = getattr(self.ib, "sleep", None)
                if sleep_fn is not None and callable(sleep_fn):
                    sleep_fn(1)
                else:
                    import time

                    time.sleep(1)
            remaining_list = getattr(self.ib, "openOrders", lambda: [])()
            if not remaining_list and hasattr(self.ib, "openTrades"):
                remaining_list = self.ib.openTrades()
            remaining = len(remaining_list) if isinstance(remaining_list, list) else 0
            return {"safe_state": remaining == 0, "open_orders_remaining": remaining}
        except Exception as e:
            return {"safe_state": False, "open_orders_remaining": -1, "error": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successful
        """
        try:
            # Find order
            trades = self.ib.openTrades()
            for trade in trades:
                if str(trade.order.orderId) == order_id:
                    self.ib.cancelOrder(trade.order)
                    logger.info(f"Order cancelled: {order_id}")
                    return True

            logger.warning(f"Order not found: {order_id}")
            return False

        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    def get_positions(self) -> pd.DataFrame:
        """
        Get current positions from IB.

        Returns:
            DataFrame with positions
        """
        try:
            positions = self.ib.positions()

            if not positions:
                return pd.DataFrame(
                    columns=["symbol", "quantity", "avg_cost", "market_value"]
                )

            data = []
            for pos in positions:
                if pos.position != 0:
                    data.append(
                        {
                            "symbol": pos.contract.symbol,
                            "quantity": pos.position,
                            "avg_cost": pos.avgCost,
                            "market_value": pos.position * pos.avgCost,  # Simplified
                        }
                    )

            return pd.DataFrame(data)

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return pd.DataFrame(
                columns=["symbol", "quantity", "avg_cost", "market_value"]
            )

    def get_account_value(self) -> float:
        """
        Get account value from IB.

        Returns:
            Account value (NAV)
        """
        try:
            account_info = self.ib_provider.get_account_info()
            margin_info = account_info.get("margin_info", {})
            nav = float(margin_info.get("NetLiquidation", 0))
            if nav == 0:
                nav = float(margin_info.get("TotalCashValue", 0))
            return nav
        except Exception as e:
            logger.error(f"Error getting account value: {e}")
            return 0.0

    def get_name(self) -> str:
        """Return executor name."""
        return "IB"
