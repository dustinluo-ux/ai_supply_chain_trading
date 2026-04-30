#!/usr/bin/env python3
"""
ADR checker utility for optional Claude Code PreToolUse wiring.
Reads tool call JSON from stdin. Blocks `git commit` when src/ has Python
files but docs/adr/ contains only the template (no real decisions recorded).

Exit codes:
  0 — proceed
  2 — block (Claude Code interprets exit 2 as a hook block)
"""
import sys
import json
from pathlib import Path


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0

    if data.get("tool_name") != "Bash":
        return 0

    command = data.get("tool_input", {}).get("command", "")
    if "git commit" not in command:
        return 0

    root = Path.cwd()
    adr_dir = root / "docs" / "adr"

    if not adr_dir.exists():
        return 0

    real_adrs = [f for f in adr_dir.glob("*.md") if f.name != "0000-template.md"]
    if real_adrs:
        return 0

    src_dir = root / "src"
    if src_dir.exists() and any(src_dir.rglob("*.py")):
        print("ADR GATE: src/ has implementation but docs/adr/ has no recorded decisions.")
        print("Create docs/adr/0001-<title>.md using the template before committing.")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
