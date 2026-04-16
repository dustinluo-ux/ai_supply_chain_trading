"""
Alpha Calibration -- 3-Way Ablation Study.

Runs three backtest configurations over the same period and watchlist,
then aggregates results into docs/research/CALIBRATION_REPORT.md.

Runs:
  1. BASELINE   -- Pure technicals (no --news-dir, propagation inert)
  2. FULL_ALPHA -- Technicals + News + Supply-Chain Propagation (YAML defaults)
  3. CAPPED     -- News at 50% weight, propagation tier_1 capped at 0.25

Propagation control:
  - BASELINE: No --news-dir flag -> news_dir is None -> SignalEngine skips
    both news overlay and propagation (L235: enable_propagation AND news_dir).
  - FULL_ALPHA: --news-dir data/news -> news + propagation from YAML defaults.
  - CAPPED: --news-dir data/news --news-weight 0.10 + temporary YAML swap
    setting propagation.tier_1_weight to 0.25 (restored after run).

Usage:
    python scripts/run_calibration.py
    python scripts/run_calibration.py --start 2023-01-01 --end 2024-12-31
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BACKTEST_SCRIPT = ROOT / "scripts" / "backtest_technical_library.py"
OUTPUT_DIR = ROOT / "outputs" / "calibration"
REPORT_PATH = ROOT / "docs" / "research" / "CALIBRATION_REPORT.md"
STRATEGY_PARAMS_PATH = ROOT / "config" / "strategy_params.yaml"

# ---- Run definitions --------------------------------------------------------
RUNS: list[dict] = [
    {
        "label": "BASELINE",
        "description": "Pure technicals (no news, no propagation)",
        "extra_args": [],
        "yaml_overrides": None,
    },
    {
        "label": "FULL_ALPHA",
        "description": (
            "Technicals + News (weight=0.20) + Supply-Chain Propagation "
            "(tier_1=0.50, blend=0.30)"
        ),
        "extra_args": ["--news-dir", "data/news"],
        "yaml_overrides": None,
    },
    {
        "label": "CAPPED",
        "description": (
            "Technicals + News (weight=0.10, 50% of default) + "
            "Propagation capped (tier_1=0.25)"
        ),
        "extra_args": ["--news-dir", "data/news", "--news-weight", "0.10"],
        "yaml_overrides": {
            "propagation": {
                "tier_1_weight": 0.25,
            },
        },
    },
]


def _apply_yaml_overrides(
    yaml_path: Path, overrides: dict,
) -> Path:
    """Apply nested overrides to a YAML file. Returns backup path for restore."""
    backup_path = yaml_path.with_suffix(".yaml.bak")
    shutil.copy2(yaml_path, backup_path)

    with open(yaml_path, "r", encoding="utf-8") as f:
        original = yaml.safe_load(f)
    modified = copy.deepcopy(original)

    for section_key, section_overrides in overrides.items():
        if section_key not in modified:
            modified[section_key] = {}
        for k, v in section_overrides.items():
            modified[section_key][k] = v

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(modified, f, default_flow_style=False, sort_keys=False)

    print(f"    [YAML] Overwrote {yaml_path.name}: {overrides}", flush=True)
    return backup_path


def _restore_yaml(yaml_path: Path, backup_path: Path) -> None:
    """Restore YAML file from backup (preserves comments and formatting)."""
    shutil.copy2(backup_path, yaml_path)
    backup_path.unlink(missing_ok=True)
    print(f"    [YAML] Restored {yaml_path.name} from backup", flush=True)


def run_backtest(
    label: str,
    extra_args: list[str],
    start: str,
    end: str,
    out_json: Path,
    yaml_overrides: dict | None = None,
) -> dict | None:
    """Execute a single backtest run and return parsed JSON results."""
    backup_path = None
    try:
        if yaml_overrides is not None:
            backup_path = _apply_yaml_overrides(
                STRATEGY_PARAMS_PATH, yaml_overrides,
            )

        cmd = [
            sys.executable,
            str(BACKTEST_SCRIPT),
            "--start", start,
            "--end", end,
            "--no-safety-report",
            "--out-json", str(out_json),
            *extra_args,
        ]
        print(f"\n{'=' * 60}", flush=True)
        print(f"  RUN: {label}", flush=True)
        print(f"  CMD: {' '.join(cmd)}", flush=True)
        print(f"{'=' * 60}", flush=True)

        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=False)
        if result.returncode != 0:
            print(f"  [ERROR] {label} exited with code {result.returncode}", flush=True)
            return None

        if not out_json.exists():
            print(f"  [ERROR] {label} did not produce {out_json}", flush=True)
            return None

        with open(out_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(
            f"  [OK] {label} -> Sharpe={data['sharpe']:.4f}, "
            f"Return={data['total_return']:.2%}, "
            f"MaxDD={data['max_drawdown']:.2%}",
            flush=True,
        )
        return data
    finally:
        if backup_path is not None:
            _restore_yaml(STRATEGY_PARAMS_PATH, backup_path)


def generate_report(results: dict[str, dict], start: str, end: str) -> None:
    """Write the CALIBRATION_REPORT.md markdown file."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Alpha Calibration -- 3-Way Ablation Study (2023-2024)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Period:** {start} to {end}")
    lines.append("")

    first = next(iter(results.values()), {})
    tickers = first.get("tickers", [])
    lines.append(f"**Watchlist:** {', '.join(tickers) if tickers else 'default'}")
    lines.append(f"**Top-N:** 5")
    lines.append(f"**Rebalance:** Weekly (Monday)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Results table
    lines.append("## Results")
    lines.append("")
    lines.append("| Metric | BASELINE | FULL_ALPHA | CAPPED |")
    lines.append("|--------|----------|------------|--------|")

    def _val(label: str, key: str, fmt: str) -> str:
        r = results.get(label)
        if r is None:
            return "FAILED"
        v = r.get(key)
        if v is None:
            return "N/A"
        return fmt.format(v)

    lines.append(
        f"| Total Return | {_val('BASELINE', 'total_return', '{:.2%}')} "
        f"| {_val('FULL_ALPHA', 'total_return', '{:.2%}')} "
        f"| {_val('CAPPED', 'total_return', '{:.2%}')} |"
    )
    lines.append(
        f"| Sharpe Ratio | {_val('BASELINE', 'sharpe', '{:.4f}')} "
        f"| {_val('FULL_ALPHA', 'sharpe', '{:.4f}')} "
        f"| {_val('CAPPED', 'sharpe', '{:.4f}')} |"
    )
    lines.append(
        f"| Max Drawdown | {_val('BASELINE', 'max_drawdown', '{:.2%}')} "
        f"| {_val('FULL_ALPHA', 'max_drawdown', '{:.2%}')} "
        f"| {_val('CAPPED', 'max_drawdown', '{:.2%}')} |"
    )
    lines.append(
        f"| Rebalances   | {_val('BASELINE', 'n_rebalances', '{}')} "
        f"| {_val('FULL_ALPHA', 'n_rebalances', '{}')} "
        f"| {_val('CAPPED', 'n_rebalances', '{}')} |"
    )
    lines.append("")

    # Run descriptions
    lines.append("## Run Configuration")
    lines.append("")
    lines.append("| Run | news_weight | propagation | tier_1_weight | blend_factor |")
    lines.append("|-----|-------------|-------------|---------------|--------------|")
    lines.append("| BASELINE | OFF (no --news-dir) | OFF | -- | -- |")
    lines.append("| FULL_ALPHA | 0.20 (YAML) | ON | 0.50 (YAML) | 0.30 (YAML) |")
    lines.append("| CAPPED | 0.10 (CLI) | ON | 0.25 (swapped) | 0.30 (YAML) |")
    lines.append("")
    for run_def in RUNS:
        label = run_def["label"]
        desc = run_def["description"]
        lines.append(f"- **{label}:** {desc}")
    lines.append("")

    # Interpretation
    lines.append("## Interpretation")
    lines.append("")

    baseline = results.get("BASELINE")
    full = results.get("FULL_ALPHA")
    capped = results.get("CAPPED")

    if baseline and full and capped:
        b_sharpe = baseline["sharpe"]
        f_sharpe = full["sharpe"]
        c_sharpe = capped["sharpe"]

        if f_sharpe > b_sharpe:
            lines.append(
                f"- Full Alpha (News + Supply Chain) **improved** Sharpe by "
                f"{f_sharpe - b_sharpe:+.4f} vs baseline."
            )
        elif f_sharpe < b_sharpe:
            lines.append(
                f"- Full Alpha (News + Supply Chain) **reduced** Sharpe by "
                f"{f_sharpe - b_sharpe:+.4f} vs baseline."
            )
        else:
            lines.append(
                "- Full Alpha had **no effect** on Sharpe vs baseline."
            )

        if c_sharpe > b_sharpe:
            lines.append(
                f"- Capped overlay **improved** Sharpe by "
                f"{c_sharpe - b_sharpe:+.4f} vs baseline."
            )
        elif c_sharpe < b_sharpe:
            lines.append(
                f"- Capped overlay **reduced** Sharpe by "
                f"{c_sharpe - b_sharpe:+.4f} vs baseline."
            )
        else:
            lines.append(
                "- Capped overlay had **no effect** on Sharpe vs baseline."
            )

        b_dd = abs(baseline["max_drawdown"])
        f_dd = abs(full["max_drawdown"])
        c_dd = abs(capped["max_drawdown"])
        best_dd_label = "BASELINE"
        best_dd = b_dd
        if f_dd < best_dd:
            best_dd_label = "FULL_ALPHA"
            best_dd = f_dd
        if c_dd < best_dd:
            best_dd_label = "CAPPED"
        lines.append(f"- Best drawdown protection: **{best_dd_label}**.")

        b_ret = baseline["total_return"]
        f_ret = full["total_return"]
        c_ret = capped["total_return"]
        best_ret_label = max(
            [("BASELINE", b_ret), ("FULL_ALPHA", f_ret), ("CAPPED", c_ret)],
            key=lambda x: x[1],
        )[0]
        lines.append(f"- Highest return: **{best_ret_label}**.")
    elif not any([baseline, full, capped]):
        lines.append(
            "- **All runs failed.** Likely cause: price CSVs do not cover "
            "the requested date range. Check `data/stock_market_data/` CSV "
            "end dates. Current CSVs end at 2022-12-12."
        )
    else:
        lines.append("- Incomplete results -- some runs failed.")

    lines.append("")
    lines.append("## Data Notes")
    lines.append("")
    lines.append(
        "- Supply-chain propagation is **now wired** into the backtest "
        "pipeline (`enable_propagation` read from "
        "`strategy_params.propagation.enabled` via ConfigManager)."
    )
    lines.append(
        "- News data JSON files cover 2023-01-01 to 2024-12-31 "
        "(source: FNSPID per `data_config.yaml`)."
    )
    lines.append(
        "- Price CSV coverage: verify that CSVs extend into the test period. "
        "If CSVs end at 2022-12-12, runs targeting 2023+ will produce "
        "0 rebalances."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*This file is a temporary research note (non-canonical). "
        "See `docs/INDEX.md` -- Adding New Documentation.*"
    )
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Report written: {REPORT_PATH}", flush=True)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="3-Way Alpha Calibration")
    parser.add_argument("--start", type=str, default="2023-01-01")
    parser.add_argument("--end", type=str, default="2024-12-31")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    for run_def in RUNS:
        label = run_def["label"]
        out_json = OUTPUT_DIR / f"{label.lower()}.json"
        data = run_backtest(
            label=label,
            extra_args=run_def["extra_args"],
            start=args.start,
            end=args.end,
            out_json=out_json,
            yaml_overrides=run_def.get("yaml_overrides"),
        )
        if data is not None:
            results[label] = data

    print(f"\n{'=' * 60}", flush=True)
    print(f"  COMPLETED: {len(results)}/{len(RUNS)} runs successful", flush=True)
    print(f"{'=' * 60}", flush=True)

    generate_report(results, args.start, args.end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
