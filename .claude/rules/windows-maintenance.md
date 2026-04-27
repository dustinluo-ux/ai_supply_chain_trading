# Windows Maintenance Rules

## Shell Compatibility

- Always use Unix-style paths in Claude tool calls (forward slashes, `/c/Users/...`).
- When generating shell scripts for the user to run on Windows, provide PowerShell equivalents.
- Never assume `bash` is available system-wide; the Claude Code shell is bash via Git for Windows.
- Repo automation and validation commands should prefer the wealth interpreter:
  `C:\Users\dusro\anaconda3\envs\wealth\python.exe`.

## Temp File Hygiene

Claude Code's native Windows binary leaks `.node` temp files into `%TEMP%` (~7 MB/session).
Unchecked, this reaches 20 GB/week on active machines.

No temp-file cleanup hook is enabled by default. If `.node` temp files become a problem, use an explicit maintenance script instead of a broad SessionEnd deletion hook.

## Permission Posture

Keep day-to-day Claude Code usage low-prompt for normal repo work, but do not restore broad project-local command allowlists. Global permissions may allow common read/edit/test commands; project-local config should only add narrow repo-specific exceptions.

Hard boundaries:

- Do not auto-allow recursive deletion, drive-level cleanup, `git reset --hard`, or credential writes.
- Do not auto-allow live IBKR order submission. Paper order submission still requires explicit command intent such as `--confirm-paper`.
- Do not use fail-open hooks as safety controls. If a hook can fail open, treat it as telemetry only.
- Do not let MCP tools read `.env` unless the specific MCP server needs exactly one named key and documents that access.

## Atomic Write Pattern (Windows)

Windows locks open file handles. Always:

1. Write to `<target>.tmp`
2. Validate file is non-empty (`os.path.getsize > 0`)
3. Use `os.replace()` (atomic on NTFS), not `shutil.move()`

```python
import os
tmp = f"{target}.tmp"
with open(tmp, "w") as f:
    f.write(content)
assert os.path.getsize(tmp) > 0, "Atomic write guard: empty file"
os.replace(tmp, target)
```

## Path Handling

Use `pathlib.Path` everywhere. Never string-concatenate paths. Never hardcode drive letters.

```python
from pathlib import Path
base = Path.home() / "OneDrive" / "Programming" / "ai_supply_chain_trading"
```

## Environment Variables

Read `TEMP` via `os.environ.get("TEMP", "/tmp")` — never hardcode `C:\Users\...`.
