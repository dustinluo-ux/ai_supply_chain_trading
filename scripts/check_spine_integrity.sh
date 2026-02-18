#!/usr/bin/env bash
# P0 Spine integrity guardrail: run determinism gate and exit on FAIL.
# Usage: from repo root, ./scripts/check_spine_integrity.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

python scripts/verify_determinism.py --start 2022-01-01 --end 2022-12-31
code=$?
if [ "$code" -eq 0 ]; then
    echo "Spine integrity PASS"
    exit 0
else
    echo "Spine integrity FAIL – do not merge"
    exit 1
fi
