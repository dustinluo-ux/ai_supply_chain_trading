"""
Autonomous optimizer: random search over portfolio params -> composite scoring -> results file.
Promoter (config promotion) and scheduler (schtasks) handled by Engineer E.

Usage:
    python scripts/run_optimizer.py                      # 30 trials (config default)
    python scripts/run_optimizer.py --n-trials 2        # smoke test
    python scripts/run_optimizer.py --skip-data         # skip price/news refresh per trial
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_optimizer_config() -> dict:
    import yaml
    p = ROOT / "config" / "optimizer_config.yaml"
    if not p.exists():
        raise FileNotFoundError(f"optimizer_config.yaml not found: {p}")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _sample_trial(search_space: dict, rng: random.Random) -> dict:
    return {k: rng.choice(v) for k, v in search_space.items()}


def _run_trial(trial_params: dict, skip_data: bool, n_trial: int, n_total: int) -> dict:
    argv = [
        sys.executable,
        str(ROOT / "scripts" / "run_e2e_pipeline.py"),
        "--skip-model",         # optimizer varies portfolio params, not the model per trial
        "--top-n", str(trial_params.get("top_n", 5)),
        "--score-floor", str(trial_params.get("score_floor", 0.0)),
        "--track", str(trial_params.get("track", "A")),
    ]
    if skip_data or n_trial > 1:
        argv.append("--skip-data")   # only refresh data on first trial
    if trial_params.get("no_llm", True):
        argv.append("--no-llm")
    if trial_params.get("no_hedge", False):
        argv.append("--no-hedge")

    print(f"[OPTIMIZER] Trial {n_trial}/{n_total}: {trial_params}", flush=True)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(ROOT),
        )
        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        print(f"  [WARN] Trial {n_trial} timed out (600s)", flush=True)
        return {"params": trial_params, "oos_sharpe": None, "oos_cagr": None,
                "oos_maxdd": None, "status": "TIMEOUT", "exit_code": -1, "stdout": ""}

    result = _parse_summary(stdout)
    result["params"] = trial_params
    result["exit_code"] = exit_code
    result["stdout"] = stdout[-2000:]
    if stderr:
        result["stderr"] = stderr[-500:]
    return result


def _parse_summary(stdout: str) -> dict:
    def _extract(pattern: str, text: str, cast):
        m = re.search(pattern, text)
        if not m:
            return None
        try:
            return cast(m.group(1).strip().rstrip("%"))
        except Exception:
            return None

    oos_sharpe = _extract(r"OOS Sharpe:\s*([\-\d\.]+|N/A)", stdout,
                          lambda x: None if x == "N/A" else float(x))
    oos_cagr   = _extract(r"OOS CAGR:\s*([\-\d\.]+|N/A)%?", stdout,
                          lambda x: None if x == "N/A" else float(x) / 100.0)
    oos_maxdd  = _extract(r"Max Drawdown:\s*([\-\d\.]+|N/A)%?", stdout,
                          lambda x: None if x == "N/A" else float(x) / 100.0)

    status = "UNKNOWN"
    if "STATUS: PASS" in stdout:
        status = "PASS"
    elif "STATUS: WARN" in stdout:
        status = "WARN"
    elif "STATUS: FAIL" in stdout:
        status = "FAIL"

    return {"oos_sharpe": oos_sharpe, "oos_cagr": oos_cagr,
            "oos_maxdd": oos_maxdd, "status": status}


def _composite_score(result: dict, min_sharpe: float, weights: dict) -> float:
    sharpe = result.get("oos_sharpe")
    cagr   = result.get("oos_cagr")
    maxdd  = result.get("oos_maxdd")
    if sharpe is None:
        return -999.0
    if sharpe < min_sharpe:
        return -999.0
    w_sharpe = float(weights.get("sharpe", 0.5))
    w_cagr   = float(weights.get("cagr",   0.3))
    w_maxdd  = float(weights.get("maxdd",  0.2))
    cagr_v  = float(cagr)  if cagr  is not None else 0.0
    maxdd_v = float(maxdd) if maxdd is not None else 0.0
    return w_sharpe * sharpe + w_cagr * cagr_v + w_maxdd * (1.0 - abs(maxdd_v))


def main() -> int:
    cfg = _load_optimizer_config()
    opt = cfg.get("optimizer", {})
    search_space = cfg.get("search_space", {})

    parser = argparse.ArgumentParser(description="Autonomous random-search optimizer.")
    parser.add_argument("--n-trials", type=int, default=int(opt.get("n_trials", 30)))
    parser.add_argument("--skip-data", action="store_true", default=False,
                        help="Skip price/news refresh (pass --skip-data on every trial).")
    parser.add_argument("--results-path", type=str, default=str(opt.get("results_path",
                        "outputs/optimizer_results.json")))
    args = parser.parse_args()

    min_sharpe        = float(opt.get("min_sharpe", 0.0))
    composite_weights = opt.get("composite_weights", {"sharpe": 0.5, "cagr": 0.3, "maxdd": 0.2})
    results_path      = ROOT / args.results_path

    rng = random.Random(int(time.time()))
    trials: list[dict] = []

    for i in range(1, args.n_trials + 1):
        params  = _sample_trial(search_space, rng)
        result  = _run_trial(params, skip_data=args.skip_data, n_trial=i, n_total=args.n_trials)
        result["composite"] = _composite_score(result, min_sharpe, composite_weights)
        trials.append(result)
        print(f"  Sharpe={result['oos_sharpe']}  composite={result['composite']:.4f}", flush=True)

    ranked = sorted(trials, key=lambda x: x["composite"], reverse=True)
    best   = ranked[0]

    print("\n[OPTIMIZER] === TOP 5 RESULTS ===", flush=True)
    for r in ranked[:5]:
        print(f"  composite={r['composite']:.4f}  sharpe={r['oos_sharpe']}  "
              f"params={r['params']}", flush=True)
    print(f"\n[OPTIMIZER] WINNER: {best['params']}", flush=True)
    print(f"  Sharpe={best['oos_sharpe']}  CAGR={best['oos_cagr']}  "
          f"MaxDD={best['oos_maxdd']}", flush=True)

    # Atomic write
    results_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = results_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({
            "run_at": datetime.now(timezone.utc).isoformat(),
            "n_trials": args.n_trials,
            "winner": best,
            "ranked": ranked,
            "trials": trials,
        }, f, indent=2)
    tmp.replace(results_path)

    print(f"\n[OPTIMIZER] Results written to {results_path}", flush=True)

    try:
        from run_promoter import main as promoter_main

        _saved_argv = sys.argv
        try:
            sys.argv = ["run_promoter.py"]
            _pc = promoter_main()
        finally:
            sys.argv = _saved_argv
        if _pc != 0:
            print(
                f"[OPTIMIZER][WARN] run_promoter.main() exit {_pc}; continuing.",
                file=sys.stderr,
                flush=True,
            )
    except Exception as _pe:
        print(f"[OPTIMIZER][WARN] Promotion failed: {_pe}", file=sys.stderr, flush=True)

    try:
        _opt = cfg.get("optimizer", {})
        _interval = int(_opt.get("run_interval_days", 30))
        _sd = date.today() + timedelta(days=_interval)
        _sd_str = _sd.strftime("%m/%d/%Y")
        _py = sys.executable
        _script = str(ROOT / "scripts" / "run_optimizer.py")
        _tr = f'cmd /c cd /d "{ROOT}" && "{_py}" "{_script}" --skip-data'
        _sch = [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            "AITrading_WeeklyOptimizer",
            "/TR",
            _tr,
            "/SC",
            "WEEKLY",
            "/D",
            "MON",
            "/ST",
            "06:00",
            "/SD",
            _sd_str,
        ]
        _sr = subprocess.run(_sch, capture_output=True, text=True)
        if _sr.returncode != 0:
            print(
                f"[OPTIMIZER][WARN] schtasks exit {_sr.returncode}: "
                f"{(_sr.stderr or _sr.stdout or '').strip()}",
                file=sys.stderr,
                flush=True,
            )
    except Exception as _se:
        print(f"[OPTIMIZER][WARN] Scheduler registration failed: {_se}", file=sys.stderr, flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
