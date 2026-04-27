# Handoff Directory

File-based message bus between Claude Code (planner) and Cursor (executor).

## Lifecycle

```
TASK_NNN.md   → written by Claude Code, read by Cursor
RESULT_NNN.md → written by Cursor, read by Claude Code
```

Cursor writes RESULT_NNN.md and leaves TASK_NNN.md in place.
Claude Code reads RESULT_NNN.md, then archives both files to `handoffs/archive/`.

## Task ID

NNN = zero-padded 3-digit integer. Scan directory for highest existing ID, increment by 1.

## Business-Decision Flag

If Cursor encounters a decision it cannot make autonomously (API choice, data scope, cost trade-off),
it writes RESULT_NNN.md with `status: NEEDS_HUMAN` and a `question:` field. Claude Code surfaces
this to the user before continuing.
