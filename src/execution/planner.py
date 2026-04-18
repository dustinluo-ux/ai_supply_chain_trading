"""
ExecutionPlanner: reconcile Alpha Lane TargetPortfolio with Risk Lane constraints.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from src.risk.types import FinalExecutionPlan, OverlayOrder, RiskConstraints, TargetPortfolio


def _compute_portfolio_beta(
    weights: dict[str, Decimal],
    prices_dict: dict[str, Any],
    spy_series: pd.Series,
    lookback_days: int = 60,
) -> Decimal:
    """
    Dollar-style weights (sum ~ 1): portfolio beta = sum_i w_i * beta_i vs SPY.
    Per-ticker beta from last ``lookback_days`` aligned daily returns (min 20 obs);
    insufficient data -> beta_i = 1.0. Result clamped to [0, 3].
    """
    try:
        if spy_series is None or getattr(spy_series, "empty", True):
            return Decimal("1.0")
        spy = spy_series.sort_index().copy()
        spy.index = pd.to_datetime(spy.index).normalize()
        spy_ret = spy.pct_change().dropna()
        if spy_ret.empty:
            return Decimal("1.0")

        pb = 0.0
        for ticker, w_dec in weights.items():
            wt = float(w_dec)
            if wt <= 0:
                continue
            key_u = str(ticker).strip().upper()
            df = prices_dict.get(ticker) if prices_dict else None
            if df is None and prices_dict:
                df = prices_dict.get(key_u)
            if df is None or getattr(df, "empty", True):
                continue
            dfc = df.copy()
            dfc.columns = [str(c).lower() for c in dfc.columns]
            if "close" not in dfc.columns:
                continue
            px = pd.to_numeric(dfc["close"], errors="coerce").dropna()
            px.index = pd.to_datetime(px.index).normalize()
            px = px.sort_index().astype(float)
            r_t = px.pct_change().dropna()
            combined = pd.concat([r_t.rename("t"), spy_ret.rename("s")], axis=1, join="inner").dropna()
            if len(combined) < lookback_days:
                window = combined
            else:
                window = combined.iloc[-lookback_days:]
            n = len(window)
            if n < 20:
                beta_i = 1.0
            else:
                rt = window["t"].to_numpy(dtype=float)
                rs = window["s"].to_numpy(dtype=float)
                var_s = float((rs - rs.mean()).dot(rs - rs.mean()))
                if var_s <= 1e-12:
                    beta_i = 1.0
                else:
                    cov_ts = float((rt - rt.mean()).dot(rs - rs.mean()))
                    beta_i = cov_ts / var_s
            pb += wt * float(beta_i)

        pb = max(0.0, min(3.0, pb))
        return Decimal(str(pb))
    except Exception:
        return Decimal("1.0")


class ExecutionPlanner:
    BETA_GAP_THRESHOLD = Decimal("0.05")  # only add overlay if gap > 5%
    MNQ_MULTIPLIER = Decimal("2")  # MNQ = $2 per point
    MES_MULTIPLIER = Decimal("5")  # MES = $5 per point

    def reconcile(
        self,
        target: TargetPortfolio,
        constraints: RiskConstraints,
        nav: Decimal,
        nq_price: Decimal | None = None,
        prices_dict: dict[str, Any] | None = None,
        spy_series: pd.Series | None = None,
    ) -> FinalExecutionPlan:
        audit_log: list[str] = list(constraints.audit_log)

        if constraints.stop_loss_active:
            long_orders = {t: Decimal("0") for t in target.weights}
            audit_log.append("stop_loss_active: all weights zeroed")
            return FinalExecutionPlan(
                as_of=target.as_of,
                long_orders=long_orders,
                overlay_orders=[],
                audit_log=audit_log,
            )

        ps = constraints.position_scale
        scaled: dict[str, Decimal] = {t: (w * ps) for t, w in target.weights.items()}

        if prices_dict is not None and spy_series is not None:
            portfolio_beta = _compute_portfolio_beta(target.weights, prices_dict, spy_series)
            gap = max(Decimal("0"), portfolio_beta - constraints.beta_cap)
        else:
            gap = max(Decimal("0"), Decimal("1") - constraints.beta_cap)
            audit_log.append("portfolio_beta: prices unavailable, using 1.0 proxy")
        overlay_orders: list[OverlayOrder] = []
        if gap > self.BETA_GAP_THRESHOLD and nq_price is not None and nq_price > 0:
            notional_short = nav * gap
            denom = nq_price * self.MNQ_MULTIPLIER
            contracts_dec = notional_short // denom
            contracts = int(contracts_dec)
            if contracts >= 1:
                notional_short_neg = -notional_short
                gap_s = format(gap, ".2f")
                nav_s = format(nav, ".0f")
                nq_s = format(nq_price, "f")
                overlay_orders.append(
                    OverlayOrder(
                        symbol="MNQ",
                        contracts=-contracts,
                        notional_usd=notional_short_neg,
                        reason=f"beta_gap={gap_s} × nav={nav_s}",
                    )
                )
                audit_log.append(f"beta_gap={gap_s}: shorting {contracts}× MNQ @ {nq_s}")

        return FinalExecutionPlan(
            as_of=target.as_of,
            long_orders=scaled,
            overlay_orders=overlay_orders,
            audit_log=audit_log,
        )
