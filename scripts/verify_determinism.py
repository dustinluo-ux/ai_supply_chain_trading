"""
P0 Determinism Gate: run canonical backtest twice with identical config/inputs
and verify outputs match (SHA256 for files; regime ledger row comparison).
Exit 0 = PASS, 1 = FAIL.
Requires --start and --end (YYYY-MM-DD).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# Project root (script lives in scripts/)
ROOT = Path(__file__).resolve().parent.parent

# Canonical P0 backtest runner (docs/SYSTEM_MAP.md, CONTRACT.md)
CANONICAL_RUNNER = ROOT / "scripts" / "backtest_technical_library.py"
DEFAULT_LEDGER = ROOT / "data" / "logs" / "regime_ledger.csv"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_manifest_for_hash(manifest: dict) -> bytes:
    """Strip timestamps so two runs produce same hash."""
    m = dict(manifest)
    if "timestamps" in m:
        m["timestamps"] = {"start": "", "end": ""}
    return json.dumps(m, sort_keys=True, indent=2).encode("utf-8")


def _last_ledger_row_data(path: Path) -> str | None:
    """Last data row of regime ledger (Regime, Strategy_ID, Return, Max_Drawdown) for comparison."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return None
    if len(lines) < 2:
        return None
    # Header: Timestamp, Regime, Strategy_ID, Return, Max_Drawdown
    header = lines[0].split(",")
    last = lines[-1].split(",")
    if len(header) != len(last):
        return None
    # Build row key excluding Timestamp (index 0)
    parts = []
    for i, h in enumerate(header):
        if h.strip().lower() == "timestamp":
            continue
        parts.append(f"{h.strip()}={last[i].strip()}")
    return ",".join(parts)


def run_backtest(out_dir: Path, start: str, end: str, regime_ledger_path: Path | None = None) -> int:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    cmd = [
        sys.executable,
        str(CANONICAL_RUNNER),
        "--out-dir", str(out_dir),
        "--start", start,
        "--end", end,
    ]
    if regime_ledger_path is not None:
        cmd.extend(["--regime-ledger", str(regime_ledger_path)])
    result = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=300)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="P0 Determinism Gate: run backtest twice and verify identical outputs.")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD (required)")
    parser.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD (required)")
    args = parser.parse_args()
    start = (args.start or "").strip()
    end = (args.end or "").strip()
    if not start or not end:
        print("ERROR: Both --start and --end are required (YYYY-MM-DD).", file=sys.stderr, flush=True)
        return 1

    if not CANONICAL_RUNNER.exists():
        print("FAIL: Canonical runner not found:", CANONICAL_RUNNER, flush=True)
        return 1

    import shutil
    import tempfile
    with tempfile.TemporaryDirectory(prefix="verify_det_") as tmpdir:
        out_dir = Path(tmpdir)
        temp_ledger = out_dir / "regime_ledger.csv"
        if DEFAULT_LEDGER.exists():
            shutil.copy2(DEFAULT_LEDGER, temp_ledger)

        # Run 1
        ret1 = run_backtest(out_dir, start, end, regime_ledger_path=temp_ledger)
        if ret1 != 0:
            print("FAIL: First backtest run exited with code", ret1, flush=True)
            return 1

        log_path = out_dir / "backtest_master_score.txt"
        manifest_path = out_dir / "run_manifest.json"

        if not log_path.exists():
            print("FAIL: Backtest log not produced:", log_path, flush=True)
            return 1

        log1 = log_path.read_bytes()
        manifest1_raw = manifest_path.read_bytes() if manifest_path.exists() else b"{}"
        try:
            manifest1 = json.loads(manifest1_raw)
        except json.JSONDecodeError:
            manifest1 = {}
        ledger_row1 = _last_ledger_row_data(temp_ledger)

        # Run 2
        ret2 = run_backtest(out_dir, start, end, regime_ledger_path=temp_ledger)
        if ret2 != 0:
            print("FAIL: Second backtest run exited with code", ret2, flush=True)
            return 1

        log2 = log_path.read_bytes()
        manifest2_raw = manifest_path.read_bytes() if manifest_path.exists() else b"{}"
        try:
            manifest2 = json.loads(manifest2_raw)
        except json.JSONDecodeError:
            manifest2 = {}
        ledger_row2 = _last_ledger_row_data(temp_ledger)

        # Compare
        failures = []

        h1 = _sha256(log1)
        h2 = _sha256(log2)
        if h1 != h2:
            failures.append((str(log_path), h1, h2))

        norm1 = _sha256(_normalize_manifest_for_hash(manifest1))
        norm2 = _sha256(_normalize_manifest_for_hash(manifest2))
        if norm1 != norm2:
            failures.append((str(manifest_path), norm1, norm2))

        if ledger_row1 is not None and ledger_row2 is not None:
            if ledger_row1 != ledger_row2:
                failures.append((str(temp_ledger) + " (last row data)", _sha256(ledger_row1.encode()), _sha256(ledger_row2.encode())))
        elif ledger_row1 != ledger_row2:
            failures.append((str(temp_ledger), "missing or unreadable after run1/run2", ""))

        if failures:
            print("FAIL", flush=True)
            for path, a, b in failures:
                print(f"  {path}: hash1={a} hash2={b}", flush=True)
            return 1

    print("PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
