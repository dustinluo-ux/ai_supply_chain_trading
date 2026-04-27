"""
Monthly BAU orchestrator:
1) quarterly fundamentals refresh
2) optimizer run (--skip-data)
3) conditional ML retrain when promoted params are newer than retrain baseline
4) e2e dry-run validation
5) weekly rebalance dry-run

Fail-fast on any step failure (non-zero return or subprocess exception).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import atomic_write_json

OUTPUTS_DIR = ROOT / "outputs"
STATUS_PATH = OUTPUTS_DIR / "maintenance_status.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _should_retrain() -> bool:
    """
    Retrain only when strategy_params.yaml is newer than outputs/retrain_baseline.json.
    Missing baseline => retrain.
    """
    params = ROOT / "config" / "strategy_params.yaml"
    baseline = ROOT / "outputs" / "retrain_baseline.json"
    if not params.exists():
        return False
    if not baseline.exists():
        return True
    return params.stat().st_mtime > baseline.stat().st_mtime


def _write_status(payload: dict) -> None:
    atomic_write_json(STATUS_PATH, payload)


def _run_subprocess(
    step_num: int, step_name: str, cmd: list[str], dry_run: bool
) -> int:
    print(f"[STEP {step_num}] {step_name}", flush=True)
    print("  CMD: " + " ".join(cmd), flush=True)
    if dry_run:
        return 0
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT))
        return int(proc.returncode)
    except Exception as exc:
        print(f"[ERROR] Step {step_num} raised exception: {exc}", flush=True)
        return -1


def _register_next_run() -> tuple[int, str]:
    py = sys.executable
    script = str(ROOT / "scripts" / "run_monthly_maintenance.py")
    run_date = (datetime.now() + timedelta(days=30)).strftime("%m/%d/%Y")
    run_time = "06:00"
    tr = f'cmd /c cd /d "{ROOT}" && "{py}" "{script}"'
    sch = [
        "schtasks",
        "/Create",
        "/F",
        "/TN",
        "AITrading_MonthlyMaintenance",
        "/TR",
        tr,
        "/SC",
        "ONCE",
        "/SD",
        run_date,
        "/ST",
        run_time,
    ]
    try:
        res = subprocess.run(sch, capture_output=True, text=True, cwd=str(ROOT))
        out = (res.stderr or res.stdout or "").strip()
        return int(res.returncode), out
    except Exception as exc:
        return -1, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run monthly maintenance steps sequentially."
    )
    parser.add_argument(
        "--step", type=int, default=1, help="Start from step N (1-5) for recovery."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print steps only; do not execute."
    )
    args = parser.parse_args()

    if args.step < 1 or args.step > 5:
        print("ERROR: --step must be between 1 and 5.", flush=True)
        return 1

    should_retrain = _should_retrain()
    steps: list[tuple[int, str, list[str], bool]] = [
        (
            1,
            "Quarterly fundamentals refresh",
            [
                sys.executable,
                str(ROOT / "scripts" / "fetch_quarterly_fundamentals.py"),
                "--mode",
                "quarterly",
            ],
            True,
        ),
        (
            2,
            "Optimizer run (uses optimizer_config n_trials)",
            [sys.executable, str(ROOT / "scripts" / "run_optimizer.py"), "--skip-data"],
            True,
        ),
        (
            3,
            "Conditional ML retrain (--skip-tournament)",
            [
                sys.executable,
                str(ROOT / "scripts" / "train_ml_model.py"),
                "--skip-tournament",
            ],
            should_retrain,
        ),
        (
            4,
            "E2E validation dry-run",
            [
                sys.executable,
                str(ROOT / "scripts" / "run_e2e_pipeline.py"),
                "--skip-data",
                "--dry-run",
            ],
            True,
        ),
        (
            5,
            "Weekly rebalance dry-run final check",
            [
                sys.executable,
                str(ROOT / "scripts" / "run_weekly_rebalance.py"),
                "--dry-run",
            ],
            True,
        ),
    ]

    for step_num, step_name, cmd, enabled in steps:
        if step_num < args.step:
            continue
        if step_num == 3 and not enabled:
            print(
                f"[STEP 3] {step_name}\n  SKIP: strategy_params.yaml not newer than outputs/retrain_baseline.json",
                flush=True,
            )
            continue

        rc = _run_subprocess(step_num, step_name, cmd, args.dry_run)
        if rc != 0:
            print(f"[FAIL] Step {step_num} '{step_name}' exit={rc}", flush=True)
            if not args.dry_run:
                _write_status(
                    {
                        "status": "FAILED",
                        "step": step_num,
                        "step_name": step_name,
                        "exit_code": rc,
                        "failed_at": _iso_now(),
                    }
                )
            return 1

    if args.dry_run:
        print(
            "[DRY-RUN] Planned 5-step monthly maintenance flow; no commands executed.",
            flush=True,
        )
        return 0

    sched_rc, sched_msg = _register_next_run()
    if sched_rc != 0:
        print(f"[FAIL] Scheduler registration failed: {sched_msg}", flush=True)
        _write_status(
            {
                "status": "FAILED",
                "step": "scheduler",
                "task_name": "AITrading_MonthlyMaintenance",
                "exit_code": sched_rc,
                "error": sched_msg,
                "failed_at": _iso_now(),
            }
        )
        return 1

    _write_status(
        {
            "status": "PASS",
            "completed_at": _iso_now(),
            "task_name": "AITrading_MonthlyMaintenance",
        }
    )
    print("[PASS] Monthly maintenance complete. READY FOR PAPER", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
