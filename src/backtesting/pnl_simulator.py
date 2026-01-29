"""
PnL Simulator - Flexible PnL simulation for trades and positions
Ported from wealth_signal_mvp_v1/core/simulation/pnl_simulator.py
"""
import pandas as pd


def simulate_pnl_from_trades(
    trade_series: pd.Series,
    price_series: pd.Series,
    horizon: int = 21
) -> pd.DataFrame:
    """
    Simulates PnL by matching trade actions with actual forward returns (impulse style).

    Args:
        trade_series: Series of trade signals (+1, 0, -1) with datetime index.
        price_series: Series of prices (e.g., close prices) with same datetime index.
        horizon: Number of days to look forward for return realization.

    Returns:
        DataFrame: Table with action, actual return, PnL, and cumulative PnL per trade date.
    """
    results = []

    for date, action in trade_series.items():
        try:
            entry_price = price_series.loc[date]

            # Get the exit price `horizon` steps forward
            future_idx = price_series.index.get_loc(date) + horizon
            if future_idx >= len(price_series):
                continue  # Not enough future data

            exit_price = price_series.iloc[future_idx]
            actual_return = (exit_price - entry_price) / entry_price
            pnl = action * actual_return

            results.append({
                "date": date,
                "action": action,
                "actual_return": actual_return,
                "pnl": pnl
            })

        except (KeyError, IndexError):
            continue

    df = pd.DataFrame(results).set_index("date")
    if not df.empty:
        df["cum_pnl"] = df["pnl"].cumsum()
    return df


def simulate_pnl_position_mode(
    positions: pd.Series,
    price_series: pd.Series
) -> pd.DataFrame:
    """
    Simulates PnL from a position series (stateful holding), mark-to-market daily.

    Args:
        positions: Series of positions (+1 long, 0 flat, -1 short), indexed by date.
        price_series: Price series with same index.

    Returns:
        DataFrame: Daily PnL and cumulative PnL.
    """
    price_series = price_series.reindex(positions.index).ffill()
    daily_returns = price_series.pct_change().fillna(0.0)

    # Yesterday's position applied to today's return
    pnl = positions.shift(1).fillna(0) * daily_returns

    df = pnl.to_frame("pnl")
    df["cum_pnl"] = df["pnl"].cumsum()
    return df
