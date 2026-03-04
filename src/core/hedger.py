"""
Hedger: apply SMH hedge to portfolio returns with borrow cost.

Implements hedge math and metrics per docs/FINAL_TRUTH_SYSTEM_SPEC.md §1.
Sharpe, total_return, max_drawdown per docs/STRATEGY_MATH.md lines 186–209,
using periods_per_year (e.g. 52) for annualization.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Union

import numpy as np


@dataclass
class HedgeResult:
    """Result of applying hedge to portfolio returns. All fields required."""

    hedged_returns: List[float]
    sharpe: float
    total_return: float
    max_drawdown: float
    n_periods: int
    portfolio_beta_used: float  # scalar or mean of per-period betas


class Hedger:
    """
    Apply a linear hedge (e.g. SMH) to portfolio returns with per-period borrow cost.

    NaN in inputs: NaN values in portfolio_returns or smh_returns produce NaN in
    the corresponding hedged_returns entry; metrics (sharpe, total_return, max_drawdown)
    are computed on the series and may be NaN if any NaN remains. Caller may drop
    NaN periods before calling apply_hedge to avoid this.
    """

    def __init__(
        self,
        hedge_ratio: float = 1.0,
        annual_borrow_rate: float = 0.05,
        periods_per_year: int = 52,
    ) -> None:
        self.hedge_ratio = hedge_ratio
        self.annual_borrow_rate = annual_borrow_rate
        self.periods_per_year = periods_per_year

    @staticmethod
    def rolling_ols_beta(
        portfolio_returns: Union[List[float], np.ndarray],
        smh_returns: Union[List[float], np.ndarray],
        window: int = 60,
        min_periods: int = 10,
        default_beta: float = 1.0,
    ) -> List[float]:
        """
        Compute per-period rolling OLS beta of portfolio vs SMH.

        For each period t, regresses portfolio_returns[max(0, t-window):t]
        against smh_returns[max(0, t-window):t]. If fewer than min_periods
        of history are available, returns default_beta for that period.

        beta_t = cov(portfolio[t-w:t], smh[t-w:t]) / var(smh[t-w:t])

        Returns a list of length len(portfolio_returns).
        """
        pr = np.asarray(portfolio_returns, dtype=float)
        sr = np.asarray(smh_returns, dtype=float)
        n = len(pr)
        betas: List[float] = []
        for t in range(n):
            start = max(0, t - window)
            p_win = pr[start:t]
            s_win = sr[start:t]
            if len(p_win) < min_periods:
                betas.append(default_beta)
                continue
            s_var = float(np.var(s_win, ddof=1))
            if s_var <= 0:
                betas.append(default_beta)
                continue
            s_cov = float(np.cov(p_win, s_win, ddof=1)[0, 1])
            betas.append(s_cov / s_var)
        return betas

    def apply_hedge(
        self,
        portfolio_returns: Union[List[float], np.ndarray],
        smh_returns: Union[List[float], np.ndarray],
        portfolio_beta: Union[float, List[float], np.ndarray, None] = None,
    ) -> HedgeResult:
        """
        Compute hedged returns and metrics.

        portfolio_beta: scalar applied uniformly, or per-period array of length
        equal to portfolio_returns. None defaults to 1.0 (scalar).

        weekly_borrow_cost = (annual_borrow_rate * hedge_ratio) / periods_per_year
        hedge_offset_t = hedge_ratio * beta_t * smh_return_t
        hedged_r_t = portfolio_r_t - hedge_offset_t - weekly_borrow_cost
        """
        if not (0.0 <= self.hedge_ratio <= 1.0):
            raise ValueError(
                f"hedge_ratio must be in [0.0, 1.0], got {self.hedge_ratio}"
            )

        pr = np.asarray(portfolio_returns, dtype=float)
        sr = np.asarray(smh_returns, dtype=float)
        if len(pr) != len(sr):
            raise ValueError(
                f"portfolio_returns and smh_returns must have same length; "
                f"got {len(pr)} and {len(sr)}."
            )

        # Resolve beta: scalar or per-period array
        if portfolio_beta is None:
            beta_arr = np.ones(len(pr), dtype=float)
        elif np.isscalar(portfolio_beta):
            beta_arr = np.full(len(pr), float(portfolio_beta), dtype=float)
        else:
            beta_arr = np.asarray(portfolio_beta, dtype=float)
            if len(beta_arr) != len(pr):
                raise ValueError(
                    f"portfolio_beta array length {len(beta_arr)} != "
                    f"portfolio_returns length {len(pr)}"
                )
        mean_beta = float(np.mean(beta_arr))

        if self.hedge_ratio == 0.0:
            weekly_borrow_cost = 0.0
            hedge_offset = np.zeros(len(pr), dtype=float)
        else:
            weekly_borrow_cost = (
                self.annual_borrow_rate * self.hedge_ratio
            ) / self.periods_per_year
            hedge_offset = self.hedge_ratio * beta_arr * sr

        hedged = pr - hedge_offset - weekly_borrow_cost
        hedged_list: List[float] = hedged.tolist()

        arr = np.asarray(hedged_list, dtype=float)
        n_periods = len(arr)
        if n_periods == 0:
            return HedgeResult(
                hedged_returns=hedged_list,
                sharpe=0.0,
                total_return=0.0,
                max_drawdown=0.0,
                n_periods=0,
                portfolio_beta_used=mean_beta,
            )

        cumulative = np.cumprod(1.0 + arr)
        total_return = float(cumulative[-1] - 1.0)

        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / np.where(
            running_max != 0, running_max, np.nan
        )
        max_drawdown = float(np.nanmin(drawdown))

        mean_r = float(np.mean(arr))
        std_r = float(np.std(arr))
        if std_r <= 0:
            sharpe = 0.0
        else:
            sharpe = (mean_r * self.periods_per_year) / (
                std_r * math.sqrt(self.periods_per_year)
            )

        return HedgeResult(
            hedged_returns=hedged_list,
            sharpe=float(sharpe),
            total_return=total_return,
            max_drawdown=float(max_drawdown),
            n_periods=n_periods,
            portfolio_beta_used=mean_beta,
        )
