# ACTIVE_RISK_REGISTER

## Critical

None.

## High

1. Full pytest remains blocked by Windows temp permission issues.
   Impact: targeted tests pass, but full-suite confidence is incomplete.
   Mitigation: fix `%TEMP%\pytest-of-dusro` permissions or run pytest with repo-local temp base.

## Medium

1. Older scripts (non-production path) still have direct non-atomic writes and broad `except Exception` patterns.
   Impact: lower-priority workflows can hide failures or leave partial state.
   Mitigation: migrate as needed when touching those scripts. Tracked in `deferred_cleanup.md`.

## Closed (2026-04-27)

1. ~~Dirty worktree~~ — Committed clean in `82f2402`.
2. ~~Brave MCP reads `.env`~~ — Acceptable. Only reads `BRAVE_API_KEY`, not full file. Consolidated to global per policy.
3. ~~Repo-local hooks deleted while global hooks remain~~ — Intentional. Consolidated to global per `windows-maintenance.md`.
