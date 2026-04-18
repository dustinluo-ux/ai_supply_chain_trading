"""
ExecutionPlanner: reconcile Alpha Lane TargetPortfolio with Risk Lane constraints.
"""
from __future__ import annotations

from decimal import Decimal

from src.risk.types import FinalExecutionPlan, OverlayOrder, RiskConstraints, TargetPortfolio


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

        gap = Decimal("1.0") - constraints.beta_cap
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
