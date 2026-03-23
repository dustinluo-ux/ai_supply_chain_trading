from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.execution.risk_manager import RiskOverlay

ROOT = Path(__file__).resolve().parent.parent.parent


class RegimeController:
    def __init__(self, prices_dict: dict[str, pd.DataFrame], as_of: Any | None = None) -> None:
        self._prices_dict = prices_dict or {}
        self._as_of = as_of
        self._risk_overlay = RiskOverlay(prices_dict=self._prices_dict)

    def compute(self, as_of_date: Any) -> dict[str, Any]:
        risk = self._risk_overlay.evaluate(as_of_date if as_of_date is not None else self._as_of)
        tier1 = str(risk.get("tier1_trend", "BULL"))
        regime_state = "Contraction" if tier1 == "BEAR" else "Expansion"

        if regime_state == "Contraction":
            return {
                "regime_state": "Contraction",
                "multiplier": 0.6,
                "score_floor": 0.65,
                "max_longs": 3,
                "n_shorts": 3,
                "meta_weights": {"core": 0.35, "extension": 0.05, "ballast": 0.60},
                "tier1_trend": risk.get("tier1_trend", "BEAR"),
                "tier2_vix": risk.get("tier2_vix", "NORMAL"),
                "tier3_corr": float(risk.get("tier3_corr", 0.0) or 0.0),
            }

        return {
            "regime_state": "Expansion",
            "multiplier": 1.0,
            "score_floor": 0.50,
            "max_longs": 5,
            "n_shorts": 0,
            "meta_weights": {"core": 0.50, "extension": 0.30, "ballast": 0.20},
            "tier1_trend": risk.get("tier1_trend", "BULL"),
            "tier2_vix": risk.get("tier2_vix", "NORMAL"),
            "tier3_corr": float(risk.get("tier3_corr", 0.0) or 0.0),
        }

    def write_regime_status(self, regime_state_dict: dict[str, Any], path: Path) -> None:
        payload = dict(regime_state_dict)
        is_contraction = str(payload.get("regime_state", "")) == "Contraction"
        payload["spy_below_sma200"] = bool(is_contraction)
        payload["score_floor"] = float(payload.get("score_floor", 0.65 if is_contraction else 0.50))
        payload["allocation_multiplier"] = float(payload.get("multiplier", 0.6 if is_contraction else 1.0))
        payload["meta_weights_override"] = payload.get("meta_weights", {})
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
