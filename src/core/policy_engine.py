"""
PolicyEngine: apply(as_of_date, scores, aux, context) -> (gated_scores, flags).
P0: Single canonical regime policy for backtest and execution (identical risk behavior).
All paths use _apply_backtest(): CASH_OUT, SIDEWAYS scaling, kill-switch.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.core.types import Context


class PolicyEngine:
    """
    Applies regime/policy gates to scores.
    Returns (gated_scores: dict[str, float], flags: dict e.g. cash_out, action, sideways_scale_applied).
    """

    def apply(
        self,
        as_of_date: pd.Timestamp,
        scores: dict[str, float],
        aux: dict[str, Any],
        context: Context,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """
        Returns (gated_scores, flags).
        gated_scores: ticker -> score after CASH_OUT / sideways scaling.
        flags: e.g. cash_out: bool, action: str, sideways_scale_applied: float.
        P0: Always uses _apply_backtest() for canonical regime gating.
        """
        return self._apply_backtest(scores, context)

    def _apply_backtest(
        self,
        scores: dict[str, float],
        context: Context,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Same logic as backtest lines 379–398: CASH_OUT (zero) and SIDEWAYS scaling."""
        regime_state = context.get("regime_state")
        spy_below_sma200 = context.get("spy_below_sma200", False)
        sideways_risk_scale = context.get("sideways_risk_scale", 0.5)
        kill_switch_mode = context.get("kill_switch_mode", "cash")

        gated = dict(scores)
        action = "Trade"

        if regime_state == "BEAR" and spy_below_sma200:
            # Fractional exposure: BEAR -> 0.5 (reduce whiplash; backtest Stage 4 scales weights to sum 0.5)
            gated = {t: s * 0.5 for t, s in scores.items()}
            action = "Trade"
        elif regime_state == "SIDEWAYS":
            gated = {t: w * sideways_risk_scale for t, w in gated.items()}
            action = "Trade"
        elif regime_state is not None and context.get("kill_switch_active") and spy_below_sma200 and regime_state != "BULL":
            if kill_switch_mode == "cash":
                gated = {t: 0.0 for t in gated}
                action = "Cash"
            else:
                gated = {t: w * 0.5 for t, w in gated.items()}
                action = "Trade"

        flags = {
            "policy_mode": "full",
            "regime": regime_state,
            "cash_out": action == "Cash",
            "action": action,
            "sideways_scale_applied": sideways_risk_scale if regime_state == "SIDEWAYS" else None,
        }
        return gated, flags

    def _apply_weekly(
        self,
        scores: dict[str, float],
        context: Context,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Deprecated: P0 enforces canonical regime gating via _apply_backtest(). Not used for gating."""
        flags = {
            "policy_mode": "passthrough",
            "regime": None,
            "cash_out": None,
            "action": "Trade",
            "sideways_scale_applied": None,
        }
        return dict(scores), flags
