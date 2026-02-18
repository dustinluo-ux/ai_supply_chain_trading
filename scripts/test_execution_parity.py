# P1 Parity Harness: compare backtest entry vs execution entry target weights.
# Two independent pathways (backtest_technical_library, run_execution), same canonical
# engines (SignalEngine -> PolicyEngine -> PortfolioEngine). No duplicated scoring/regime/sizing.
#
# Backtest path: scripts/backtest_technical_library.compute_target_weights (single-date spine).
# Execution path: scripts/run_execution.compute_target_weights (spine before delta).
#
# Requirements: data_config.yaml data_dir with CSV price data. Run from project root:
#   python scripts/test_execution_parity.py --date YYYY-MM-DD
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# CSV subdirs aligned with backtest_technical_library.find_csv_path / run_execution.find_csv_path
CSV_SUBDIRS = ["nasdaq/csv", "sp500/csv", "nyse/csv", "forbes2000/csv"]


def _backtest_config():
    path = ROOT / "config" / "config.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _discover_tickers(data_dir: Path, max_tickers: int = 20) -> list[str]:
    tickers = []
    for sub in CSV_SUBDIRS:
        d = data_dir / sub
        if not d.exists():
            continue
        for f in d.glob("*.csv"):
            tickers.append(f.stem)
    return sorted(set(tickers))[:max_tickers]


def get_backtest_weights(date: str | pd.Timestamp) -> pd.Series:
    """
    Call backtest entry: compute_target_weights from scripts/backtest_technical_library.
    Returns final target weights (intent.weights) for that date from the backtest path.
    """
    from backtest_technical_library import load_config, load_prices, compute_target_weights

    config = load_config()
    data_dir = config["data_dir"]
    tickers = _discover_tickers(data_dir)
    if not tickers:
        raise FileNotFoundError("No CSV tickers found under data_dir; check data_config.yaml and CSV subdirs.")
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        raise ValueError("Backtest load_prices returned empty; check data_dir and tickers.")
    as_of = pd.to_datetime(date).normalize()
    backtest_cfg = _backtest_config()
    top_n = backtest_cfg.get("backtest", {}).get("portfolio_size", 3)
    return compute_target_weights(
        as_of,
        prices_dict,
        data_dir=data_dir,
        top_n=top_n,
        sideways_risk_scale=0.5,
        weight_mode="fixed",
    )


def get_execution_weights(date: str | pd.Timestamp) -> pd.Series:
    """
    Call execution entry: compute_target_weights from scripts/run_execution.
    Returns optimal target weights (intent.weights) before delta computation.
    """
    from run_execution import load_config, load_prices, compute_target_weights

    config = load_config()
    data_dir = config["data_dir"]
    tickers = _discover_tickers(data_dir)
    if not tickers:
        raise FileNotFoundError("No CSV tickers found under data_dir; check data_config.yaml and CSV subdirs.")
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        raise ValueError("Execution load_prices returned empty; check data_dir and tickers.")
    as_of = pd.to_datetime(date).normalize()
    backtest_cfg = _backtest_config()
    top_n = backtest_cfg.get("backtest", {}).get("portfolio_size", 3)
    return compute_target_weights(
        as_of,
        tickers,
        prices_dict,
        data_dir,
        top_n=top_n,
        sideways_risk_scale=0.5,
    )


def assert_parity(date: str | pd.Timestamp) -> None:
    """
    Compare backtest target weights vs execution optimal weights for the given rebalance date.
    Raises AssertionError on mismatch (no soft warnings).
    """
    backtest_weights = get_backtest_weights(date)
    execution_weights = get_execution_weights(date)

    all_idx = backtest_weights.index.union(execution_weights.index).unique().sort_values()
    bt = backtest_weights.reindex(all_idx, fill_value=0.0).sort_index()
    ex = execution_weights.reindex(all_idx, fill_value=0.0).sort_index()

    np.testing.assert_allclose(
        bt.values,
        ex.values,
        rtol=1e-12,
        atol=1e-12,
        err_msg=f"Backtest vs execution weight mismatch on {date}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="P1 parity harness: assert backtest and execution target weights match for a rebalance date.",
    )
    parser.add_argument("--date", type=str, required=True, help="Rebalance date YYYY-MM-DD")
    args = parser.parse_args()

    try:
        assert_parity(args.date)
        print(f"Parity OK for {args.date}", flush=True)
        return 0
    except AssertionError as e:
        print(f"Parity FAILED: {e}", flush=True)
        return 1
    except Exception as e:
        print(f"Error: {e}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
