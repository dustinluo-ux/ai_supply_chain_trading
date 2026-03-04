"""
Generate Final Truth table and report from 6 FINAL_*.json backtest outputs.

Reads FINAL_BASELINE_ABS_2022/2023/2024 and FINAL_RESIDUAL_ALPHA_2022/2023/2024,
applies Hedger to residual track for hedged_residual metrics, writes
outputs/FINAL_TRUTH_TABLE.json and outputs/FINAL_TRUTH_REPORT.md.

Per docs/FINAL_TRUTH_SYSTEM_SPEC.md §2.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Explicit filenames per spec (no glob)
FINAL_ABS_FILES = [
    "FINAL_BASELINE_ABS_2022.json",
    "FINAL_BASELINE_ABS_2023.json",
    "FINAL_BASELINE_ABS_2024.json",
]
FINAL_RESIDUAL_FILES = [
    "FINAL_RESIDUAL_ALPHA_2022.json",
    "FINAL_RESIDUAL_ALPHA_2023.json",
    "FINAL_RESIDUAL_ALPHA_2024.json",
]
OUTPUTS_DIR = ROOT / "outputs"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_data_dir() -> Path:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    data_dir_str = os.getenv("DATA_DIR")
    if data_dir_str:
        return Path(data_dir_str) / "stock_market_data"
    from src.data.csv_provider import load_data_config
    config = load_data_config()
    return Path(config["data_dir"])


def _smh_path(model_config: dict) -> Path:
    raw = model_config.get("training", {}).get("smh_benchmark_path", "")
    if not raw:
        raise KeyError("config/model_config.yaml training.smh_benchmark_path required")
    p = Path(raw)
    if p.is_absolute():
        return p
    return ROOT / raw


def _weekly_returns_from_csv(csv_path: str | Path) -> tuple[list[float], list[str]]:
    """Load CSV (Close), resample to week-ending Friday, pct_change. Returns (returns_list, week_end_dates)."""
    import pandas as pd
    df = pd.read_csv(csv_path, index_col=0, parse_dates=False)
    df.index = pd.to_datetime(df.index, format="mixed", dayfirst=True)
    df.columns = [c.lower() for c in df.columns]
    if "close" not in df.columns:
        raise ValueError(f"CSV must have 'close' column: {csv_path}")
    close = df["close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    weekly = close.resample("W-FRI").last()
    ret = weekly.pct_change().dropna()
    return ret.tolist(), [str(d.date()) for d in ret.index]


def _align_smh_returns(
    smh_returns: list[float],
    smh_dates: list[str],
    period_start: str,
    period_end: str,
    n_periods: int,
) -> list[float]:
    """Return first n_periods SMH returns that fall within [period_start, period_end]. Same length as portfolio weekly_returns."""
    import pandas as pd
    if len(smh_returns) < n_periods or len(smh_dates) != len(smh_returns):
        if len(smh_returns) < n_periods:
            raise ValueError(
                f"SMH has {len(smh_returns)} weekly returns but need {n_periods} for period {period_start} to {period_end}"
            )
        return smh_returns[:n_periods]
    start_ts = pd.Timestamp(period_start)
    end_ts = pd.Timestamp(period_end)
    aligned = []
    for i, d in enumerate(smh_dates):
        if len(aligned) >= n_periods:
            break
        dt = pd.Timestamp(d)
        if start_ts <= dt <= end_ts:
            aligned.append(smh_returns[i])
    if len(aligned) < n_periods:
        return smh_returns[:n_periods]
    return aligned[:n_periods]


def main() -> int:
    import yaml
    from src.data.csv_provider import find_csv_path
    from src.core.hedger import Hedger

    outputs = Path(OUTPUTS_DIR)
    outputs.mkdir(parents=True, exist_ok=True)

    # Load model config for SMH path
    model_config_path = ROOT / "config" / "model_config.yaml"
    with open(model_config_path, "r", encoding="utf-8") as f:
        model_config = yaml.safe_load(f)
    smh_csv_path = _smh_path(model_config)
    if not smh_csv_path.exists():
        print(f"ERROR: SMH benchmark not found at {smh_csv_path}", file=sys.stderr)
        return 1

    data_dir = _resolve_data_dir()
    data_dir_str = str(data_dir)

    # Load all 6 JSON files by explicit path
    abs_by_year: dict[str, dict] = {}
    for name in FINAL_ABS_FILES:
        year = name.replace("FINAL_BASELINE_ABS_", "").replace(".json", "")
        path = outputs / name
        if not path.exists():
            print(f"ERROR: Missing {path}", file=sys.stderr)
            return 1
        abs_by_year[year] = _load_json(path)

    res_by_year: dict[str, dict] = {}
    for name in FINAL_RESIDUAL_FILES:
        year = name.replace("FINAL_RESIDUAL_ALPHA_", "").replace(".json", "")
        path = outputs / name
        if not path.exists():
            print(f"ERROR: Missing {path}", file=sys.stderr)
            return 1
        res_by_year[year] = _load_json(path)

    # SMH weekly returns (full series)
    smh_returns_list, smh_dates_list = _weekly_returns_from_csv(smh_csv_path)

    # Hedger
    hedger = Hedger(hedge_ratio=1.0, annual_borrow_rate=0.05, periods_per_year=52)

    by_year: dict[str, dict] = {}
    for year in ("2022", "2023", "2024"):
        abs_data = abs_by_year[year]
        res_data = res_by_year[year]
        period_start = abs_data["period_start"]
        period_end = abs_data["period_end"]
        res_weekly = res_data["weekly_returns"]
        n_periods = len(res_weekly)
        smh_aligned = _align_smh_returns(
            smh_returns_list, smh_dates_list, period_start, period_end, n_periods
        )
        if len(smh_aligned) != n_periods:
            smh_aligned = smh_returns_list[:n_periods]
        # Rolling OLS beta: for each week, regress prior 60 weeks of portfolio
        # returns vs SMH returns. Falls back to 1.0 for first 10 periods.
        per_period_betas = Hedger.rolling_ols_beta(
            res_weekly, smh_aligned, window=60, min_periods=10, default_beta=1.0
        )
        hedge_result = hedger.apply_hedge(res_weekly, smh_aligned, portfolio_beta=per_period_betas)
        mean_beta = hedge_result.portfolio_beta_used

        sample_type = "out_of_sample" if year == "2024" else "in_sample"
        by_year[year] = {
            "sample_type": sample_type,
            "absolute": {
                "sharpe": abs_data["sharpe"],
                "total_return": abs_data["total_return"],
                "max_drawdown": abs_data["max_drawdown"],
            },
            "residual": {
                "sharpe": res_data["sharpe"],
                "total_return": res_data["total_return"],
                "max_drawdown": res_data["max_drawdown"],
            },
            "hedged_residual": {
                "sharpe": hedge_result.sharpe,
                "total_return": hedge_result.total_return,
                "max_drawdown": hedge_result.max_drawdown,
                "mean_beta": round(mean_beta, 4),
            },
        }

    universe_size = len(abs_by_year["2022"].get("tickers", []))
    truth_table = {
        "generated": datetime.now().isoformat(),
        "universe_size": universe_size,
        "hedge_params": {"hedge_ratio": 1.0, "annual_borrow_rate": 0.05, "beta_method": "rolling_ols_60w"},
        "tracks": ["absolute", "residual", "hedged_residual"],
        "by_year": by_year,
    }

    table_path = outputs / "FINAL_TRUTH_TABLE.json"
    with open(table_path, "w", encoding="utf-8") as f:
        json.dump(truth_table, f, indent=2)

    # SPY for report context (optional)
    spy_path = find_csv_path(data_dir_str, "SPY") if data_dir else None
    spy_row = ""
    if spy_path and Path(spy_path).exists():
        spy_ret, _ = _weekly_returns_from_csv(spy_path)
        # Could compute SPY sharpe/total_return/max_dd for same periods; keep report simple
        spy_row = "\n| SPY (benchmark) | — | — | — |\n"

    # Markdown report
    report_lines = [
        "# Final Truth Table — Absolute vs Residual vs Hedged",
        "",
        f"**Generated:** {truth_table['generated']}",
        "",
        "| Year | Track A Absolute | Track B Residual | Track C Hedged (HR=1.0, OLS beta) |",
        "|------|------------------|-------------------|-----------------------------------|",
    ]
    for year in ("2022", "2023", "2024"):
        row = by_year[year]
        sample = row["sample_type"]
        a = row["absolute"]
        r = row["residual"]
        h = row["hedged_residual"]
        mean_beta = h.get("mean_beta", 1.0)
        report_lines.append(
            f"| **{year}** ({sample}) | | | mean β={mean_beta:.2f} |"
        )
        report_lines.append(
            f"| Sharpe | {a['sharpe']:.4f} | {r['sharpe']:.4f} | {h['sharpe']:.4f} |"
        )
        report_lines.append(
            f"| Total Return | {a['total_return']:.2%} | {r['total_return']:.2%} | {h['total_return']:.2%} |"
        )
        report_lines.append(
            f"| Max DD | {a['max_drawdown']:.2%} | {r['max_drawdown']:.2%} | {h['max_drawdown']:.2%} |"
        )
    if spy_row:
        report_lines.append(spy_row)
    report_lines.extend([
        "",
        "> ⚠ LOOK-AHEAD BIAS NOTICE",
        "> The Ridge model was trained on 2022–2023 data (train_start/train_end in",
        "> config/model_config.yaml). Results for 2022 and 2023 are IN-SAMPLE and",
        "> carry look-ahead bias in the model parameters. Only 2024 results are",
        "> OUT-OF-SAMPLE and statistically valid for performance evaluation.",
        "",
    ])

    report_path = outputs / "FINAL_TRUTH_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # Final config check
    training = model_config.get("training", {})
    residual_ok = training.get("residual_target") is True
    model_path = training.get("model_path") or ""
    path_ok = "ridge_optimized_20260227_230227.pkl" in str(model_path)
    if not residual_ok or not path_ok:
        print(
            "WARNING: config/model_config.yaml should have residual_target: true and "
            "model_path ending with ridge_optimized_20260227_230227.pkl for production.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
