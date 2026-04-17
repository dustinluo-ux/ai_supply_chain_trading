#!/usr/bin/env python3
"""
Post-tool-use hook: cost accumulator + turn counter.

Template — copy to: <project>/.claude/hooks/post-tool-use.py
(Or run: python3 ~/.claude/scripts/scaffold_project.py)

Register in settings.local.json to activate:
  "hooks": {
    "PostToolUse": [{
      "matcher": ".*",
      "hooks": [{"type": "command", "command": "python3 .claude/hooks/post-tool-use.py"}]
    }]
  }

LIMITATION: Claude Code does not currently expose per-tool cost in the
PostToolUse hook context. stdin JSON contains tool_name, tool_input, and
tool_response — but no cost or token fields. The cost_usd branch below is
future-proof scaffolding; update the field name if Claude Code adds it.

Because cost is unavailable, the working kill-switch proxy is the turn counter:
  - post-tool-use.py increments .turn_counter after each tool call
  - pre-tool-use.py reads .turn_counter and blocks when CLAUDE_MAX_TURNS is reached

SPOF: this hook must not crash. Every exception path exits 0 (fail open).
"""

import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

COST_LOG = Path(".claude/hooks/.cost_accumulator")
TURN_LOG = Path(".claude/hooks/.turn_counter")


def _read_decimal(path: Path) -> Decimal:
    try:
        return Decimal(path.read_text().strip())
    except (FileNotFoundError, InvalidOperation, OSError):
        return Decimal("0")


def _write_decimal(path: Path, value: Decimal) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(value))
    except OSError:
        pass  # fail open


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # fail open — can't parse, allow

    # ── Cost accumulation (future-proof) ──────────────────────────────────────
    # Claude Code does not currently expose cost here. If it ever does, the
    # field name will likely be "cost_usd" or "cost". Update as needed.
    cost_raw = hook_input.get("cost_usd") or hook_input.get("cost")
    if cost_raw is not None:
        try:
            delta = Decimal(str(cost_raw))
            _write_decimal(COST_LOG, _read_decimal(COST_LOG) + delta)
        except Exception:
            pass  # fail open

    # ── Turn counter (proxy kill switch — works now) ───────────────────────────
    try:
        _write_decimal(TURN_LOG, _read_decimal(TURN_LOG) + Decimal("1"))
    except Exception:
        pass  # fail open


if __name__ == "__main__":
    main()
