#!/usr/bin/env python3
"""
Pre-tool-use hook: BUDGET_USD kill switch + CLAUDE_MAX_TURNS guard.

Template — copy to: <project>/.claude/hooks/pre-tool-use.py
(Or run: python3 ~/.claude/scripts/scaffold_project.py)

Two independent kill-switch gates. Either triggers a block.

Gate 1 — BUDGET_USD + .cost_accumulator:
  Blocks when accumulated cost >= BUDGET_USD.
  Requires PostToolUse hook (post-tool-use.py) to be registered AND Claude Code
  to expose cost in PostToolUse context. Currently Claude Code does NOT expose
  cost in hook stdin, so this gate only activates if that changes in future.
  Register post-tool-use.py in settings.local.json to complete the circuit.

Gate 2 — CLAUDE_MAX_TURNS + .turn_counter (works now):
  Set CLAUDE_MAX_TURNS=N to block after N completed tool invocations.
  .turn_counter is incremented by post-tool-use.py after each tool call.
  Use as a hard ceiling for headless runs while Gate 1 is unavailable.

SPOF: must not crash. Any exception path → exit 0 (fail open, not closed).
"""

import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

BUDGET_ENV = "BUDGET_USD"
MAX_TURNS_ENV = "CLAUDE_MAX_TURNS"
COST_LOG = Path(".claude/hooks/.cost_accumulator")
TURN_LOG = Path(".claude/hooks/.turn_counter")


def _read_decimal(path: Path) -> Decimal:
    try:
        return Decimal(path.read_text().strip())
    except (FileNotFoundError, InvalidOperation, OSError):
        return Decimal("0")


def get_budget() -> Decimal | None:
    raw = os.environ.get(BUDGET_ENV)
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def get_max_turns() -> int | None:
    raw = os.environ.get(MAX_TURNS_ENV)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # fail open

    tool_name = hook_input.get("tool_name", "unknown")

    # ── Gate 1: BUDGET_USD + cost accumulator ─────────────────────────────────
    budget = get_budget()
    if budget is not None:
        accumulated = _read_decimal(COST_LOG)
        if accumulated >= budget:
            msg = (
                f"KILL SWITCH (budget): BUDGET_USD=${budget} exceeded "
                f"(accumulated=${accumulated:.4f}). "
                f"Blocking: {tool_name}. "
                f"Unset {BUDGET_ENV} or increase budget to continue."
            )
            print(json.dumps({"decision": "block", "reason": msg}))
            sys.exit(2)

    # ── Gate 2: CLAUDE_MAX_TURNS + turn counter ────────────────────────────────
    max_turns = get_max_turns()
    if max_turns is not None:
        try:
            turns = int(_read_decimal(TURN_LOG))
        except Exception:
            turns = 0  # fail open — unknown count, allow
        if turns >= max_turns:
            msg = (
                f"KILL SWITCH (turns): CLAUDE_MAX_TURNS={max_turns} reached "
                f"(completed turns={turns}). "
                f"Blocking: {tool_name}. "
                f"Unset {MAX_TURNS_ENV} or increase limit to continue."
            )
            print(json.dumps({"decision": "block", "reason": msg}))
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
