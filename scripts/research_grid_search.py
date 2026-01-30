"""
Grid Search Orchestrator: systematic backtest over Technical vs News weights, signal horizon, and SIDEWAYS risk scale.
Runs scripts/backtest_technical_library.py in parallel for 2022 (or --start/--end), aggregates results,
and writes docs/REGIME_MATRIX.md with best combo per regime.
Uses SPY.csv for consistent regime detection; errors logged to grid_search_errors.log.
"""
from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import subprocess
import sys
from pathlib import Path
from typing import Any

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "outputs" / "grid_search"
ERROR_LOG = OUT_DIR / "grid_search_errors.log"
REGIME_MATRIX_PATH = ROOT / "docs" / "REGIME_MATRIX.md"

# Grid dimensions
NEWS_WEIGHTS = [0.0, 0.1, 0.2, 0.3]
SIGNAL_HORIZONS = [1, 5]
SIDEWAYS_RISK_SCALES = [0.5, 1.0]


def _ensure_spy(data_dir: Path) -> bool:
    """Check that SPY.csv exists for consistent regime detection."""
    for sub in ["nasdaq/csv", "sp500/csv", "nyse/csv", "forbes2000/csv"]:
        if (data_dir / sub / "SPY.csv").exists():
            return True
    return False


def _run_one(
    combo: dict[str, Any],
    script_path: Path,
    data_dir: Path,
    news_dir: Path | None,
    start: str,
    end: str,
    tickers: str,
    top_n: int,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """
    Run one backtest combination via subprocess. Returns (key, result_dict, error).
    """
    nw = combo["news_weight"]
    horiz = combo["signal_horizon_days"]
    risk = combo["sideways_risk_scale"]
    key = f"nw{nw}_horiz{horiz}_risk{risk}"
    out_json = OUT_DIR / f"results_{key}.json"
    cmd = [
        sys.executable,
        str(script_path),
        "--start", start,
        "--end", end,
        "--tickers", tickers,
        "--top-n", str(top_n),
        "--weight-mode", "regime",
        "--news-weight", str(nw),
        "--signal-horizon-days", str(horiz),
        "--sideways-risk-scale", str(risk),
        "--out-json", str(out_json),
        "--no-safety-report",
    ]
    if news_dir is not None and nw > 0:
        cmd.extend(["--news-dir", str(news_dir)])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            return key, None, f"exit {proc.returncode}: {proc.stderr[:500] if proc.stderr else proc.stdout[:500]}"
        if not out_json.exists():
            return key, None, "out-json file not created"
        with open(out_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["params"] = combo
        return key, data, None
    except subprocess.TimeoutExpired:
        return key, None, "timeout (600s)"
    except Exception as e:
        return key, None, str(e)


def _worker(args: tuple) -> tuple[str, dict[str, Any] | None, str | None]:
    """Thunk for multiprocessing: unpack and call _run_one."""
    return _run_one(*args)


def _build_grid() -> list[dict[str, Any]]:
    return [
        {"news_weight": nw, "signal_horizon_days": h, "sideways_risk_scale": r}
        for nw in NEWS_WEIGHTS
        for h in SIGNAL_HORIZONS
        for r in SIDEWAYS_RISK_SCALES
    ]


def _aggregate_and_write_matrix(results: dict[str, dict[str, Any]]) -> None:
    """
    For each regime (BULL, BEAR, SIDEWAYS), find the combo with best Sharpe in regime_stats.
    Write docs/REGIME_MATRIX.md.
    """
    regimes = ["BULL", "BEAR", "SIDEWAYS"]
    rows = []
    for reg in regimes:
        best_key = None
        best_sharpe = float("-inf")
        best_dd: float | str = "?"
        best_nw = best_horiz = best_risk = "?"
        for key, data in results.items():
            if not data or "regime_stats" not in data:
                continue
            rs = data["regime_stats"]
            if reg not in rs or rs[reg].get("n_weeks", 0) == 0:
                continue
            sharpe = rs[reg].get("sharpe", float("-inf"))
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_dd = rs[reg].get("max_drawdown", 0.0)
                best_key = key
                p = data.get("params", {})
                best_nw = str(p.get("news_weight", "?"))
                best_horiz = str(p.get("signal_horizon_days", "?"))
                best_risk = str(p.get("sideways_risk_scale", "?"))
        dd_str = f"{best_dd:.2%}" if best_key is not None and isinstance(best_dd, (int, float)) else "?"
        rows.append({
            "regime": reg,
            "best_news_weight": best_nw,
            "best_horizon": best_horiz,
            "best_risk_scale": best_risk,
            "sharpe": best_sharpe if best_key is not None else "?",
            "max_dd": dd_str,
        })
    REGIME_MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGIME_MATRIX_PATH, "w", encoding="utf-8") as f:
        f.write("# Regime–Performance Matrix (Grid Search)\n\n")
        f.write("Best Technical vs News configuration per market regime from grid search backtest.\n\n")
        f.write("| Regime | Best News Weight | Best Horizon | Best Risk Scale | Sharpe | Max DD |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for r in rows:
            sharpe_str = f"{r['sharpe']:.4f}" if isinstance(r["sharpe"], (int, float)) else r["sharpe"]
            f.write(f"| {r['regime']} | {r['best_news_weight']} | {r['best_horizon']} | {r['best_risk_scale']} | {sharpe_str} | {r['max_dd']} |\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Grid search: optimal Technical vs News weights per regime")
    parser.add_argument("--start", type=str, default="2022-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default="2022-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--news-dir", type=str, default=None, help="Path to news JSON dir (required for nw > 0)")
    parser.add_argument("--tickers", type=str, default="NVDA,AMD,TSM,AAPL,MSFT", help="Comma-separated tickers")
    parser.add_argument("--top-n", type=int, default=3, help="Number of stocks to hold")
    parser.add_argument("--workers", type=int, default=None, help="Parallel workers (default: CPU count - 1)")
    parser.add_argument("--no-parallel", action="store_true", help="Run combinations sequentially (no multiprocessing)")
    args = parser.parse_args()

    # Config: data_dir for SPY and backtest
    try:
        import yaml
        cfg_path = ROOT / "config" / "data_config.yaml"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            data_dir = Path(data.get("data_sources", {}).get("data_dir", str(ROOT / "data" / "stock_market_data")))
        else:
            data_dir = ROOT / "data" / "stock_market_data"
    except Exception:
        data_dir = ROOT / "data" / "stock_market_data"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger(__name__)

    if not _ensure_spy(data_dir):
        log.warning("SPY.csv not found under %s; regime detection may fall back to binary. Create SPY data for consistent regimes.", data_dir)

    script_path = ROOT / "scripts" / "backtest_technical_library.py"
    if not script_path.exists():
        log.error("Backtest script not found: %s", script_path)
        return 1
    news_dir = Path(args.news_dir) if args.news_dir else None
    if news_dir and not news_dir.exists():
        log.warning("News dir does not exist: %s; runs with nw>0 may fail.", news_dir)

    grid = _build_grid()
    log.info("Grid size: %d combinations (news_weight=%s, horizon=%s, risk_scale=%s)", len(grid), NEWS_WEIGHTS, SIGNAL_HORIZONS, SIDEWAYS_RISK_SCALES)

    task_args = [
        (combo, script_path, data_dir, news_dir, args.start, args.end, args.tickers, args.top_n)
        for combo in grid
    ]
    results: dict[str, dict[str, Any] | None] = {}
    error_log_path = OUT_DIR / "grid_search_errors.log"
    error_lines: list[str] = []

    if args.no_parallel or len(grid) == 1:
        for t in task_args:
            key, data, err = _run_one(*t)
            results[key] = data
            if err:
                error_lines.append(f"{key}: {err}")
                log.warning("%s failed: %s", key, err)
    else:
        workers = args.workers or max(1, multiprocessing.cpu_count() - 1)
        with multiprocessing.Pool(workers) as pool:
            for key, data, err in pool.starmap(_run_one, task_args):
                results[key] = data
                if err:
                    error_lines.append(f"{key}: {err}")
                    log.warning("%s failed: %s", key, err)

    if error_lines:
        with open(error_log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(error_lines))
        log.info("Errors logged to %s", error_log_path)

    successful = {k: v for k, v in results.items() if v is not None}
    if not successful:
        log.error("No combinations succeeded; cannot build REGIME_MATRIX.")
        return 1
    _aggregate_and_write_matrix(successful)
    log.info("Regime matrix written to %s", REGIME_MATRIX_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
