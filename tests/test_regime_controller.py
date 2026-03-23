from __future__ import annotations

import pandas as pd

from src.execution.regime_controller import RegimeController
from src.execution.risk_manager import RiskOverlay


def _synthetic_spy_series(kind: str) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=260, freq="B")
    if kind == "above":
        vals = [100.0 + i * 0.5 for i in range(len(idx))]
    else:
        vals = [220.0 - i * 0.5 for i in range(len(idx))]
    return pd.Series(vals, index=idx)


def test_regime_controller_expansion_above_200sma() -> None:
    spy = _synthetic_spy_series("above")
    vix = pd.Series(18.0, index=spy.index)
    rc = RegimeController(prices_dict={}, as_of=spy.index[-1])
    rc._risk_overlay = RiskOverlay(spy_series=spy, vix_series=vix, prices_dict={})
    out = rc.compute(spy.index[-1])

    assert out["regime_state"] == "Expansion"
    assert out["score_floor"] == 0.50
    assert out["n_shorts"] == 0


def test_regime_controller_contraction_below_200sma() -> None:
    spy = _synthetic_spy_series("below")
    vix = pd.Series(18.0, index=spy.index)
    rc = RegimeController(prices_dict={}, as_of=spy.index[-1])
    rc._risk_overlay = RiskOverlay(spy_series=spy, vix_series=vix, prices_dict={})
    out = rc.compute(spy.index[-1])

    assert out["regime_state"] == "Contraction"
    assert out["score_floor"] == 0.65
    assert out["n_shorts"] == 3
