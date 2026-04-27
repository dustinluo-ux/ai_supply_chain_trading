"""
E2E fill reconciliation test: fill ledger read + fill-miss detection + send_alert("fill_miss") no-op.
Runs without TWS. Exit 0 if all checks PASS, 1 if any FAIL.
"""

from __future__ import annotations

import sys
import tempfile
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# Check 1 & 2: Write temp fills.jsonl with 2 records; read via read_fill_ledger; assert both records with correct fields
def _check_1_and_2() -> tuple[bool, str]:
    import json

    rec_a = {
        "run_id": "test_run",
        "timestamp": "2025-01-01T12:00:00Z",
        "ticker": "AAPL",
        "side": "BUY",
        "qty_requested": 100,
        "qty_filled": 100,
        "status": "full",
        "fill_check_passed": True,
        "fill_check_reason": "full fill",
    }
    rec_b = {
        "run_id": "test_run",
        "timestamp": "2025-01-01T12:01:00Z",
        "ticker": "MSFT",
        "side": "SELL",
        "qty_requested": 50,
        "qty_filled": 30,
        "status": "partial",
        "fill_check_passed": False,
        "fill_check_reason": "partial: expected 50, got 30",
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        f.write(json.dumps(rec_a) + "\n")
        f.write(json.dumps(rec_b) + "\n")
        temp_path = f.name
    try:
        from src.execution.fill_ledger import read_fill_ledger

        records = read_fill_ledger(path=temp_path)
        if len(records) != 2:
            return False, f"expected 2 records, got {len(records)}"
        r0, r1 = records[0], records[1]
        if (
            r0.get("qty_requested") != 100
            or r0.get("qty_filled") != 100
            or r0.get("status") != "full"
        ):
            return False, f"Record A fields wrong: {r0}"
        if (
            r1.get("qty_requested") != 50
            or r1.get("qty_filled") != 30
            or r1.get("status") != "partial"
        ):
            return False, f"Record B fields wrong: {r1}"
        return True, "2 records with correct fields"
    finally:
        Path(temp_path).unlink(missing_ok=True)


# Check 3: From ledger records, filter qty_filled < qty_requested; assert exactly 1 miss (Record B)
def _check_3() -> tuple[bool, str]:
    import json

    rec_a = {"qty_requested": 100, "qty_filled": 100, "ticker": "AAPL"}
    rec_b = {"qty_requested": 50, "qty_filled": 30, "ticker": "MSFT"}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        f.write(json.dumps(rec_a) + "\n")
        f.write(json.dumps(rec_b) + "\n")
        temp_path = f.name
    try:
        from src.execution.fill_ledger import read_fill_ledger

        records = read_fill_ledger(path=temp_path)
        misses = [
            r for r in records if r.get("qty_filled", 0) < r.get("qty_requested", 0)
        ]
        if len(misses) != 1:
            return False, f"expected 1 miss, got {len(misses)}"
        if misses[0].get("qty_requested") != 50 or misses[0].get("qty_filled") != 30:
            return False, f"miss record wrong: {misses[0]}"
        return True, "exactly 1 fill miss (Record B)"
    finally:
        Path(temp_path).unlink(missing_ok=True)


# Check 4: send_alert("fill_miss", Record B data) does not raise (no-op if no token)
def _check_4() -> tuple[bool, str]:
    try:
        from src.monitoring.telegram_alerts import send_alert

        send_alert(
            "fill_miss",
            {
                "ticker": "MSFT",
                "side": "SELL",
                "qty_requested": 50,
                "qty_filled": 30,
                "fill_check_reason": "partial: expected 50, got 30",
            },
        )
        return True, "send_alert('fill_miss', ...) did not raise"
    except Exception as e:
        return False, f"send_alert raised: {e}"


# Check 5: read_fill_ledger(non-existent path) returns []
def _check_5() -> tuple[bool, str]:
    from src.execution.fill_ledger import read_fill_ledger

    nonexistent = ROOT / "outputs" / "fills" / "_nonexistent_ledger_12345.jsonl"
    if nonexistent.exists():
        nonexistent = ROOT / "_nonexistent_fill_test_98765.jsonl"
    records = read_fill_ledger(path=nonexistent)
    if records != []:
        return False, f"expected [], got {records}"
    return True, "read_fill_ledger(non-existent) returns []"


def _check_6() -> tuple[bool, str]:
    from src.execution.fill_ledger import read_fill_ledger, write_fill_ledger_atomic

    records = [
        {
            "run_id": "atomic_test",
            "ticker": "AAPL",
            "side": "BUY",
            "qty_requested": 1,
            "qty_filled": 1,
            "status": "full",
        },
        {
            "run_id": "atomic_test",
            "ticker": "MSFT",
            "side": "SELL",
            "qty_requested": 2,
            "qty_filled": 0,
            "status": "unknown",
        },
    ]
    temp_dir_path = ROOT / "outputs" / f"_fill_ledger_test_{os.getpid()}"
    temp_dir_path.mkdir(parents=True, exist_ok=True)
    try:
        ledger_path = temp_dir_path / "fills.jsonl"
        write_fill_ledger_atomic(records, ledger_path)
        reread = read_fill_ledger(ledger_path)
        tmp_files = list(temp_dir_path.glob("*.tmp"))
    finally:
        for path in temp_dir_path.glob("*"):
            path.unlink(missing_ok=True)
        temp_dir_path.rmdir()
    if reread != records:
        return False, f"atomic rewrite changed records: {reread}"
    if tmp_files:
        return False, f"atomic rewrite left temp files: {tmp_files}"
    return True, "write_fill_ledger_atomic round-trips records"


def main() -> int:
    all_ok = True
    result_1_and_2 = _check_1_and_2()
    if not result_1_and_2[0]:
        print(f"FAIL 1: {result_1_and_2[1]}", flush=True)
        print(f"FAIL 2: {result_1_and_2[1]}", flush=True)
        all_ok = False
    else:
        print(
            "PASS 1: temp fills.jsonl written with 2 records (A full, B partial)",
            flush=True,
        )
        print(
            "PASS 2: read_fill_ledger returned both records with correct fields",
            flush=True,
        )
    ok3, msg3 = _check_3()
    print(f"PASS 3: {msg3}" if ok3 else f"FAIL 3: {msg3}", flush=True)
    if not ok3:
        all_ok = False
    ok4, msg4 = _check_4()
    print(f"PASS 4: {msg4}" if ok4 else f"FAIL 4: {msg4}", flush=True)
    if not ok4:
        all_ok = False
    ok5, msg5 = _check_5()
    print(f"PASS 5: {msg5}" if ok5 else f"FAIL 5: {msg5}", flush=True)
    if not ok5:
        all_ok = False
    ok6, msg6 = _check_6()
    print(f"PASS 6: {msg6}" if ok6 else f"FAIL 6: {msg6}", flush=True)
    if not ok6:
        all_ok = False
    if all_ok:
        print("PASS: all 6 checks passed", flush=True)
        return 0
    print("FAIL: one or more checks failed", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
