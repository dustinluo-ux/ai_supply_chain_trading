"""
Position Manager - Reads current positions from IB and calculates delta trades.

Ported from wealth_signal_mvp_v1. Works with:
- IBDataProvider (get_account_info() -> {margin_info, positions})
- Or an executor with get_positions() + get_account_value() (adapted to account_info)
"""
import pandas as pd
from typing import Optional, Union

from src.utils.logger import setup_logger

logger = setup_logger()


def _account_info_from_executor(executor) -> dict:
    """Build account_info dict from executor.get_positions() and get_account_value()."""
    positions_df = executor.get_positions()
    nav = float(executor.get_account_value())
    pos_list = []
    if not positions_df.empty and "symbol" in positions_df.columns:
        for _, row in positions_df.iterrows():
            sym = row.get("symbol", "")
            qty = float(row.get("quantity", 0))
            avg = float(row.get("avg_cost", 0))
            pos_list.append({"symbol": sym, "position": qty, "avgCost": avg})
    return {"margin_info": {"NetLiquidation": nav, "TotalCashValue": nav}, "positions": pos_list}


class PositionManager:
    """Manages current positions and calculates portfolio delta trades."""

    def __init__(self, account_provider: Union[object, "BaseExecutor"]):
        """
        Args:
            account_provider: Either (1) object with get_account_info() -> {margin_info, positions},
                              e.g. IBDataProvider; or (2) executor with get_positions() + get_account_value().
        """
        self.provider = account_provider

    def get_account_info(self) -> dict:
        if hasattr(self.provider, "get_account_info") and callable(self.provider.get_account_info):
            return self.provider.get_account_info()
        return _account_info_from_executor(self.provider)

    def get_current_positions(self) -> pd.DataFrame:
        """
        Get current positions from provider (e.g. IB TWS).

        Returns:
            DataFrame with columns: symbol, quantity, avg_cost, market_value, weight
        """
        account_info = self.get_account_info()
        positions = account_info.get("positions", account_info.get("pos_list", []))
        margin_info = account_info.get("margin_info", {})

        nav = float(margin_info.get("NetLiquidation", 0))
        if nav == 0:
            nav = float(margin_info.get("TotalCashValue", 0))

        if not positions:
            return pd.DataFrame(columns=["symbol", "quantity", "avg_cost", "market_value", "weight"])

        pos_data = []
        for pos in positions:
            symbol = pos.get("symbol", "")
            qty = float(pos.get("position", 0))
            avg_cost = float(pos.get("avgCost", 0))
            current_price = avg_cost
            market_value = qty * current_price if qty != 0 else 0
            weight = market_value / nav if nav > 0 else 0
            pos_data.append({
                "symbol": symbol,
                "quantity": qty,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "market_value": market_value,
                "weight": weight,
            })
        return pd.DataFrame(pos_data)

    def get_account_value(self) -> float:
        """Total account value (NAV)."""
        margin_info = self.get_account_info().get("margin_info", {})
        nav = float(margin_info.get("NetLiquidation", 0))
        if nav == 0:
            nav = float(margin_info.get("TotalCashValue", 0))
        return nav

    def positions_to_weights(self, positions_df: pd.DataFrame) -> pd.Series:
        if positions_df.empty:
            return pd.Series(dtype=float)
        return positions_df.set_index("symbol")["weight"]

    def calculate_delta_trades(
        self,
        current_weights: pd.Series,
        optimal_weights: pd.Series,
        account_value: float,
        prices: Optional[pd.Series] = None,
        min_trade_size: float = 0.01,
        significance_threshold: float = 0.02,
    ) -> pd.DataFrame:
        """
        Delta trades to rebalance from current_weights to optimal_weights.

        Returns:
            DataFrame with columns: symbol, current_weight, optimal_weight, delta_weight,
            delta_dollars, quantity, side (BUY/SELL/HOLD), should_trade
        """
        all_symbols = set(current_weights.index) | set(optimal_weights.index)
        current_aligned = current_weights.reindex(all_symbols, fill_value=0.0)
        optimal_aligned = optimal_weights.reindex(all_symbols, fill_value=0.0)
        delta_weights = optimal_aligned - current_aligned
        delta_dollars = delta_weights * account_value

        trades = []
        for symbol in all_symbols:
            delta_w = delta_weights[symbol]
            delta_d = delta_dollars[symbol]
            if abs(delta_w) < min_trade_size:
                should_trade = False
            elif abs(delta_w) < significance_threshold:
                should_trade = False
            else:
                should_trade = True

            current_price = 0.0
            if prices is not None and symbol in prices.index:
                current_price = float(prices[symbol])
            elif current_aligned[symbol] != 0:
                pos_df = self.get_current_positions()
                if not pos_df.empty and symbol in pos_df["symbol"].values:
                    row = pos_df[pos_df["symbol"] == symbol].iloc[0]
                    current_price = row.get("current_price", 0) or row.get("avg_cost", 0)

            qty = int(round(abs(delta_d) / current_price)) if current_price > 0 else 0
            side = "BUY" if delta_w > 0 else "SELL" if delta_w < 0 else "HOLD"
            trades.append({
                "symbol": symbol,
                "current_weight": current_aligned[symbol],
                "optimal_weight": optimal_aligned[symbol],
                "delta_weight": delta_w,
                "delta_dollars": delta_d,
                "current_price": current_price,
                "quantity": qty if should_trade else 0,
                "side": side,
                "should_trade": should_trade,
            })
        return pd.DataFrame(trades)
