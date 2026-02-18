# Regression snapshot test for target_weight_pipeline.
# First run: creates contracts/target_weight_snapshot_<date>.json.
# Later runs: assert computed weights match snapshot within 1e-12.
# Locks the spine; no new logic; reuses backtest/execution loaders and config.
#
# Run from project root: python scripts/test_target_weight_regression.py
# Requires: data_config.yaml data_dir with CSV price data; same deps as parity (e.g. pandas_ta).
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# Fixed historical date for snapshot (deterministic)
SNAPSHOT_DATE = "2024-01-08"
# CSV subdirs aligned with backtest_technical_library / run_execution find_csv_path
CSV_SUBDIRS = ["nasdaq/csv", "sp500/csv", "nyse/csv", "forbes2000/csv"]
TOLERANCE_RTOL = 1e-12
TOLERANCE_ATOL = 1e-12


def _discover_tickers(data_dir: Path, max_tickers: int = 20) -> list[str]:
    tickers = []
    for sub in CSV_SUBDIRS:
        d = data_dir / sub
        if not d.exists():
            continue
        for f in d.glob("*.csv"):
            tickers.append(f.stem)
    return sorted(set(tickers))[:max_tickers]


def _backtest_config() -> dict:
    path = ROOT / "config" / "config.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_prices_and_context():
    """Reuse existing loaders from backtest module."""
    from backtest_technical_library import load_config, load_prices

    config = load_config()
    data_dir = config["data_dir"]
    tickers = _discover_tickers(data_dir)
    if not tickers:
        raise FileNotFoundError("No CSV tickers found under data_dir; check data_config.yaml and CSV subdirs.")
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        raise ValueError("load_prices returned empty; check data_dir and tickers.")
    # Use actual loaded universe (prices_dict keys) for pipeline
    return data_dir, list(prices_dict.keys()), prices_dict


def _snapshot_path() -> Path:
    return ROOT / "contracts" / f"target_weight_snapshot_{SNAPSHOT_DATE}.json"


def _weights_to_snapshot(weights: pd.Series) -> dict:
    """Deterministic JSON-serializable snapshot: date + sorted ticker -> weight."""
    sorted_weights = weights.sort_index()
    return {
        "date": SNAPSHOT_DATE,
        "weights": {str(k): float(v) for k, v in sorted_weights.items()},
    }


def _snapshot_to_series(snapshot: dict) -> pd.Series:
    return pd.Series(snapshot["weights"])


def run_regression() -> int:
    from src.core import compute_target_weights

    as_of = pd.to_datetime(SNAPSHOT_DATE).normalize()
    data_dir, tickers, prices_dict = _load_prices_and_context()
    backtest_cfg = _backtest_config()
    top_n = backtest_cfg.get("backtest", {}).get("portfolio_size", 3)

    weights = compute_target_weights(
        as_of,
        tickers,
        prices_dict,
        data_dir,
        top_n=top_n,
        sideways_risk_scale=0.5,
        weight_mode="fixed",
        path=None,
    )

    snapshot_path = _snapshot_path()
    if not snapshot_path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _weights_to_snapshot(weights)
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        print(f"Snapshot created: {snapshot_path}", flush=True)
        return 0

    with open(snapshot_path, "r", encoding="utf-8") as f:
        stored = json.load(f)
    stored_series = _snapshot_to_series(stored)
    all_idx = weights.index.union(stored_series.index).unique().sort_values()
    current = weights.reindex(all_idx, fill_value=0.0).sort_index()
    expected = stored_series.reindex(all_idx, fill_value=0.0).sort_index()
    np.testing.assert_allclose(
        current.values,
        expected.values,
        rtol=TOLERANCE_RTOL,
        atol=TOLERANCE_ATOL,
        err_msg=f"Target weights diverged from snapshot {snapshot_path}",
    )
    print(f"Regression OK: weights match snapshot {snapshot_path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_regression())
    except Exception as e:
        print(f"Error: {e}", flush=True)
        sys.exit(1)
