# Windows Maintenance Rules

## Shell Compatibility

- Always use Unix-style paths in Claude tool calls (forward slashes, `/c/Users/...`).
- When generating shell scripts for the user to run on Windows, provide PowerShell equivalents.
- Never assume `bash` is available system-wide; the Claude Code shell is bash via Git for Windows.

## Temp File Hygiene

Claude Code's native Windows binary leaks `.node` temp files into `%TEMP%` (~7 MB/session).
Unchecked, this reaches 20 GB/week on active machines.

No temp-file cleanup hook is enabled by default. If `.node` temp files become a problem, use an explicit maintenance script instead of a broad SessionEnd deletion hook.

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
