from __future__ import annotations

import pandas as pd

from src.hedging.black_scholes_engine import estimate_smh_put_cost


class TailHedge:
    def __init__(
        self,
        smh_prices: pd.Series,
        vix_prices: pd.Series,
        portfolio_usd: float = 740_000,
        roll_weeks: int = 4,
        expiry_days: int = 45,
        target_delta: float = 0.20,
    ) -> None:
        self.smh_prices = smh_prices.sort_index()
        self.vix_prices = vix_prices.sort_index()
        self.portfolio_usd = float(portfolio_usd)
        self.roll_weeks = int(roll_weeks)
        self.expiry_days = int(expiry_days)
        self.target_delta = float(target_delta)
        self.smh_50sma = self.smh_prices.rolling(50).mean()

        self._strike: float | None = None
        self._expiry_date: pd.Timestamp | None = None
        self._contracts: int | None = None
        self._weeks_since_roll: int = 0

    def n_contracts(self, as_of_date) -> int:
        as_of = pd.Timestamp(as_of_date)
        smh = self.smh_prices.asof(as_of)
        sma = self.smh_50sma.asof(as_of)
        if pd.isna(smh) or pd.isna(sma):
            return 1
        return 1 if float(smh) >= float(sma) else 2

    def step(self, monday_date, smh_close: float, vix_close: float) -> dict:
        monday = pd.Timestamp(monday_date)
        smh_close = float(smh_close)
        vix_close = float(vix_close) if vix_close is not None else float("nan")

        hedge_cost_usd = 0.0
        hedge_payoff_usd = 0.0
        roll_happened = (self._contracts is None) or (
            self._weeks_since_roll >= self.roll_weeks
        )

        if roll_happened:
            if self._strike is not None and self._contracts is not None:
                hedge_payoff_usd = (
                    max(float(self._strike) - smh_close, 0.0)
                    * 100.0
                    * int(self._contracts)
                )

            n = int(self.n_contracts(monday))
            price_per_share, strike_k, _sigma = estimate_smh_put_cost(
                smh_close,
                vix_close,
                T=self.expiry_days / 365.0,
                target_delta=self.target_delta,
            )
            hedge_cost_usd = float(price_per_share) * 100.0 * n

            self._strike = float(strike_k)
            self._contracts = n
            self._expiry_date = monday + pd.Timedelta(days=7 * self.roll_weeks)
            self._weeks_since_roll = 0
        else:
            self._weeks_since_roll += 1

        return {
            "hedge_cost_pct": float(hedge_cost_usd / self.portfolio_usd),
            "hedge_payoff_pct": float(hedge_payoff_usd / self.portfolio_usd),
            "contracts": int(self._contracts) if self._contracts is not None else 0,
            "strike": float(self._strike) if self._strike is not None else 0.0,
            "roll_occurred": bool(roll_happened),
        }
