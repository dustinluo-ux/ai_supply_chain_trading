import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.core.portfolio_engine import hrp_alpha_tilt


def _mock_prices(tickers, n=120):
    """Synthetic prices: random walk, n days."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    return {
        t: pd.DataFrame(
            {
                "close": 100 * np.cumprod(1 + rng.normal(0, 0.01, n)),
                "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
            },
            index=dates,
        )
        for t in tickers
    }


def test_cap_enforced():
    """Single dominant ticker must not exceed 0.40 after clamp."""
    tickers = ["A", "B", "C", "D", "E"]
    prices = _mock_prices(tickers)
    # Give A a huge score to force concentration
    scores = {"A": 100.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": 1.0}
    as_of = pd.Timestamp("2022-06-01")
    w = hrp_alpha_tilt(scores, prices, as_of, top_n=5, max_single_weight=0.40)
    assert w.get("A", 0.0) <= 0.40 + 1e-9, f"A weight {w['A']:.4f} > 0.40"


def test_weights_sum_to_one():
    """After clamp, active weights must still sum to 1.0."""
    tickers = ["A", "B", "C"]
    prices = _mock_prices(tickers)
    scores = {"A": 50.0, "B": 1.0, "C": 1.0}
    as_of = pd.Timestamp("2022-06-01")
    w = hrp_alpha_tilt(scores, prices, as_of, top_n=3, max_single_weight=0.40)
    active = {t: v for t, v in w.items() if v > 0}
    assert abs(sum(active.values()) - 1.0) < 1e-9, f"Weights sum to {sum(active.values()):.6f}"


def test_no_op_when_within_cap():
    """If no ticker exceeds 0.40, clamp must not alter weights."""
    tickers = ["A", "B", "C", "D"]
    prices = _mock_prices(tickers)
    scores = {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0}
    as_of = pd.Timestamp("2022-06-01")
    w_capped = hrp_alpha_tilt(scores, prices, as_of, top_n=4, max_single_weight=0.40)
    w_uncapped = hrp_alpha_tilt(scores, prices, as_of, top_n=4, max_single_weight=1.0)
    for t in w_capped:
        assert abs(w_capped[t] - w_uncapped[t]) < 1e-9, (
            f"{t}: capped={w_capped[t]:.6f} uncapped={w_uncapped[t]:.6f}"
        )


if __name__ == "__main__":
    test_cap_enforced()
    test_weights_sum_to_one()
    test_no_op_when_within_cap()
    print("ALL PASS")
