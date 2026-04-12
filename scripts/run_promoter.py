"""
Promote optimizer winner params into config/strategy_params.yaml.

Reads outputs/optimizer_results.json (from run_optimizer.py). Atomic YAML write (.tmp + rename).
Standalone: python scripts/run_promoter.py
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS = ROOT / "outputs" / "optimizer_results.json"
STRATEGY_PARAMS = ROOT / "config" / "strategy_params.yaml"
STRATEGY_BAK = ROOT / "config" / "strategy_params.yaml.bak"


def main() -> int:
    import yaml

    parser = argparse.ArgumentParser(description="Promote optimizer winner into strategy_params.yaml.")
    parser.add_argument(
        "--results-path",
        type=str,
        default=str(DEFAULT_RESULTS),
        help="Path to optimizer_results.json",
    )
    args = parser.parse_args()
    results_path = Path(args.results_path)
    if not results_path.is_absolute():
        results_path = ROOT / results_path

    if not results_path.exists():
        print(f"[PROMOTER] ERROR: results not found: {results_path}", flush=True)
        return 1

    with open(results_path, encoding="utf-8") as f:
        data = json.load(f)
    winner = data.get("winner") or {}
    params = winner.get("params")
    if not isinstance(params, dict) or not params:
        print("[PROMOTER] ERROR: winner.params missing or empty in results file.", flush=True)
        return 1

    if not STRATEGY_PARAMS.exists():
        print(f"[PROMOTER] ERROR: {STRATEGY_PARAMS} not found.", flush=True)
        return 1

    with open(STRATEGY_PARAMS, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    cfg["optimizer_promotion"] = {
        **params,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "source_results": str(results_path.as_posix()),
    }

    tmp = STRATEGY_PARAMS.with_name(STRATEGY_PARAMS.name + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    shutil.copy2(STRATEGY_PARAMS, STRATEGY_BAK)
    tmp.replace(STRATEGY_PARAMS)

    print(f"[PROMOTER] Promoted: {params} -> config/strategy_params.yaml", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
