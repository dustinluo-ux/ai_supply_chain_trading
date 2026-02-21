"""
Task 7: Performance tracker — compute portfolio and SPY metrics from daily signals CSV.

Reads outputs/daily_signals.csv (date, ticker, target_weight, latest_close, notional_units),
loads prices via csv_provider for next-day close lookup, builds equity curves,
returns total_return, spy_return, alpha_vs_spy, max_drawdown, sharpe_ratio, n_days.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path


def _next_trading_close(close_series: pd.Series, as_of: pd.Timestamp, max_days: int = 10):
    """First close strictly after as_of within as_of+max_days. Returns None if not found."""
    mask = (close_series.index > as_of) & (close_series.index <= as_of + pd.Timedelta(days=max_days))
    future = close_series.index[mask]
    if len(future) == 0:
        return None
    return close_series.loc[future[0]]


class PerformanceTracker:
    """Compute portfolio and benchmark metrics from a daily signals CSV."""

    def run(self, signals_csv: str, data_dir: str) -> dict:
        """
        Read signals CSV, compute daily returns (weighted) and SPY buy-and-hold,
        build equity curves, return metrics dict and print summary.
        Uses load_prices() from csv_provider for next-day close lookup.
        """
        from src.data.csv_provider import load_prices

        path = Path(signals_csv)
        if not path.exists():
            return {
                "total_return": 0.0,
                "spy_return": 0.0,
                "alpha_vs_spy": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "n_days": 0,
            }
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date", ascending=True)
        dates = df["date"].unique().tolist()
        if not dates:
            return {
                "total_return": 0.0,
                "spy_return": 0.0,
                "alpha_vs_spy": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "n_days": 0,
            }
        tickers = df["ticker"].unique().tolist()
        if "SPY" not in tickers:
            tickers.append("SPY")
        prices_dict = load_prices(Path(data_dir), tickers)
        if not prices_dict:
            return {
                "total_return": 0.0,
                "spy_return": 0.0,
                "alpha_vs_spy": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "n_days": 0,
            }

        daily_returns = []
        spy_returns = []
        for d in dates:
            row_date = pd.Timestamp(d)
            sub = df[df["date"] == d]
            ret = 0.0
            for _, r in sub.iterrows():
                t = r["ticker"]
                w = float(r["target_weight"])
                close_i = float(r["latest_close"])
                if pd.isna(close_i) or close_i <= 0 or t not in prices_dict:
                    continue
                next_c = _next_trading_close(prices_dict[t]["close"], row_date)
                if next_c is None or pd.isna(next_c):
                    continue
                ret += w * (float(next_c) / close_i - 1.0)
            daily_returns.append(ret)
            # SPY buy-and-hold
            if "SPY" in prices_dict:
                close_spy = prices_dict["SPY"]["close"].asof(row_date)
                next_spy = _next_trading_close(prices_dict["SPY"]["close"], row_date)
                if close_spy is not None and next_spy is not None and close_spy > 0:
                    spy_returns.append(float(next_spy) / float(close_spy) - 1.0)
                else:
                    spy_returns.append(0.0)
            else:
                spy_returns.append(0.0)

        daily_returns = np.array(daily_returns)
        spy_returns = np.array(spy_returns)
        equity = np.ones(len(daily_returns) + 1)
        for i in range(len(daily_returns)):
            equity[i + 1] = equity[i] * (1 + daily_returns[i])
        spy_equity = np.ones(len(spy_returns) + 1)
        for i in range(len(spy_returns)):
            spy_equity[i + 1] = spy_equity[i] * (1 + spy_returns[i])

        total_return = float(equity[-1] - 1.0)
        spy_return = float(spy_equity[-1] - 1.0)
        alpha_vs_spy = total_return - spy_return
        running_max = np.maximum.accumulate(equity)
        dd = (running_max - equity) / np.where(running_max > 0, running_max, 1.0)
        max_drawdown = float(np.max(dd))
        std_ret = np.std(daily_returns)
        sharpe_ratio = float(np.mean(daily_returns) / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
        n_days = len(dates)

        first_date = dates[0]
        last_date = dates[-1]
        if hasattr(first_date, "strftime"):
            first_str = first_date.strftime("%Y-%m-%d")
            last_str = last_date.strftime("%Y-%m-%d")
        else:
            first_str = str(first_date)[:10]
            last_str = str(last_date)[:10]

        result = {
            "total_return": total_return,
            "spy_return": spy_return,
            "alpha_vs_spy": alpha_vs_spy,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "n_days": n_days,
        }
        print("=== Performance Summary ===")
        print(f"Period:        {first_str} -> {last_str}  ({n_days} trading days)")
        print(f"Total Return:  {total_return:.2%}")
        print(f"SPY Return:    {spy_return:.2%}")
        print(f"Alpha vs SPY:  {alpha_vs_spy:+.2%}")
        print(f"Max Drawdown:  {max_drawdown:.2%}")
        print(f"Sharpe Ratio:  {sharpe_ratio:.2f}")
        return result
