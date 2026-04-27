"""
Quarterly retrain pipeline:
1) Force retrain via run_factory
2) Prior-year OOS backtest with no LLM
3) Promotion gate vs baseline
4) Self-schedule next run via Windows Task Scheduler
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

FACTORY_WINNER_PATH = ROOT / "models" / "factory_winner.json"
FACTORY_WINNER_BAK_PATH = ROOT / "models" / "factory_winner.json.bak"
RETRAIN_OOS_PATH = ROOT / "outputs" / "retrain_oos_latest.json"
RETRAIN_BASELINE_PATH = ROOT / "outputs" / "retrain_baseline.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def _read_strategy_backtest_params() -> tuple[int, float]:
    import yaml

    p = ROOT / "config" / "strategy_params.yaml"
    if not p.exists():
        return (5, 0.0)
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    promo = cfg.get("optimizer_promotion") or {}
    top_n = int(promo.get("top_n", 5))
    score_floor = float(promo.get("score_floor", 0.0))
    return (top_n, score_floor)


def _run_factory_force_retrain() -> int:
    import run_factory

    if FACTORY_WINNER_PATH.exists():
        FACTORY_WINNER_BAK_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FACTORY_WINNER_PATH, FACTORY_WINNER_BAK_PATH)
        FACTORY_WINNER_PATH.unlink()
        print(f"[STEP 1] Backed up winner to {FACTORY_WINNER_BAK_PATH}", flush=True)

    saved_argv = sys.argv
    try:
        sys.argv = ["run_factory.py", "--force-retrain"]
        try:
            return int(run_factory.main())
        except SystemExit as exc:
            # run_factory.main currently parses only --no-news and --train-years.
            print(
                f"[STEP 1][WARN] run_factory --force-retrain unsupported ({exc}); retrying without flag.",
                flush=True,
            )
            sys.argv = ["run_factory.py"]
            return int(run_factory.main())
    finally:
        sys.argv = saved_argv


def _run_prior_year_oos_backtest() -> dict:
    import pandas as pd
    from src.data.csv_provider import load_data_config, load_prices
    from src.utils.config_manager import get_config
    import backtest_technical_library as btl

    today = date.today()
    prior_year = today.year - 1
    start = f"{prior_year}-01-01"
    end = f"{prior_year}-12-31"
    top_n, score_floor = _read_strategy_backtest_params()

    cfg = get_config()
    tickers = cfg.get_watchlist()
    data_dir = Path(load_data_config()["data_dir"])
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        raise RuntimeError("No prices loaded for retrain OOS backtest.")

    result = btl.run_backtest_master_score(
        prices_dict=prices_dict,
        data_dir=data_dir,
        news_dir=None,
        top_n=top_n,
        score_floor=score_floor,
        start_date=start,
        end_date=end,
        llm_enabled=False,
        verbose=False,
    )

    sharpe = float(result.get("sharpe", 0.0))
    total_return = float(result.get("total_return", 0.0))
    d0 = pd.to_datetime(start)
    d1 = pd.to_datetime(end)
    years = max((d1 - d0).days / 365.25, 1e-6)
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0
    max_dd = float(result.get("max_drawdown", 0.0))

    payload = {
        "period_start": start,
        "period_end": end,
        "top_n": top_n,
        "score_floor": score_floor,
        "llm_enabled": False,
        "sharpe": sharpe,
        "cagr": cagr,
        "total_return": total_return,
        "max_drawdown": max_dd,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(RETRAIN_OOS_PATH, payload)
    print(
        f"[STEP 2] OOS complete: Sharpe={sharpe:.4f} CAGR={cagr:.2%} window={start}..{end}",
        flush=True,
    )
    return payload


def _promotion_gate(new_metrics: dict) -> int:
    new_sharpe = float(new_metrics.get("sharpe", 0.0))
    new_cagr = float(new_metrics.get("cagr", 0.0))

    baseline = None
    if RETRAIN_BASELINE_PATH.exists():
        try:
            with open(RETRAIN_BASELINE_PATH, encoding="utf-8") as f:
                baseline = json.load(f)
        except Exception as exc:
            print(f"[STEP 3][WARN] Could not read baseline: {exc}", flush=True)

    promote = False
    if not baseline:
        promote = True
        print("[STEP 3] No baseline found; promoting current model.", flush=True)
    else:
        base_sharpe = float(baseline.get("sharpe", 0.0))
        base_cagr = float(baseline.get("cagr", 0.0))
        sharpe_ok = new_sharpe >= 0.9 * base_sharpe
        cagr_ok = new_cagr >= 0.9 * base_cagr
        promote = bool(sharpe_ok and cagr_ok)
        print(
            "[STEP 3] Gate compare: "
            f"new_sharpe={new_sharpe:.4f} vs base={base_sharpe:.4f}, "
            f"new_cagr={new_cagr:.2%} vs base={base_cagr:.2%}, "
            f"promote={promote}",
            flush=True,
        )

    if promote:
        baseline_payload = {
            "sharpe": new_sharpe,
            "cagr": new_cagr,
            "period_start": str(new_metrics.get("period_start", "")),
            "period_end": str(new_metrics.get("period_end", "")),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write_json(RETRAIN_BASELINE_PATH, baseline_payload)
        print("[STEP 3] Promotion accepted; baseline updated.", flush=True)
        return 0

    if FACTORY_WINNER_BAK_PATH.exists():
        FACTORY_WINNER_BAK_PATH.replace(FACTORY_WINNER_PATH)
        print(
            "[STEP 3] Promotion rejected; restored previous factory_winner.json.",
            flush=True,
        )
    else:
        print(
            "[STEP 3][WARN] Promotion rejected, but no backup exists to restore.",
            flush=True,
        )
    return 2


def _schedule_next_run() -> None:
    next_date = date.today() + timedelta(days=91)
    next_date_str = next_date.strftime("%m/%d/%Y")
    py = sys.executable
    script = str(ROOT / "scripts" / "run_quarterly_retrain.py")
    tr = f'cmd /c cd /d "{ROOT}" && "{py}" "{script}"'
    cmd = [
        "schtasks",
        "/Create",
        "/F",
        "/TN",
        "AITrading_QuarterlyRetrain",
        "/TR",
        tr,
        "/SC",
        "ONCE",
        "/ST",
        "06:00",
        "/SD",
        next_date_str,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        msg = (res.stderr or res.stdout or "").strip()
        print(f"[STEP 4][WARN] schtasks exit {res.returncode}: {msg}", flush=True)
    else:
        print(
            f"[STEP 4] Scheduled AITrading_QuarterlyRetrain on {next_date_str} at 06:00.",
            flush=True,
        )


def main() -> int:
    print("[RETRAIN] Quarterly retrain start.", flush=True)

    step1 = _run_factory_force_retrain()
    if step1 != 0:
        print(
            f"[RETRAIN][ERROR] Step 1 failed with exit {step1}. Aborting.", flush=True
        )
        return 1
    print("[STEP 1] Factory retrain completed.", flush=True)

    try:
        latest = _run_prior_year_oos_backtest()
    except Exception as exc:
        print(f"[RETRAIN][ERROR] Step 2 failed: {exc}", flush=True)
        return 1

    gate_code = _promotion_gate(latest)
    if gate_code == 2:
        return 2

    _schedule_next_run()
    print("[RETRAIN] Quarterly retrain complete.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
