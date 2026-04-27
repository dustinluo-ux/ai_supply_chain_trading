# ACTIVE_RISK_REGISTER

## Critical

None currently marked as unfixed in the touched execution path.

## High

1. Dirty worktree mixes code changes, generated `catboost_info/*`, config churn, and deleted `.claude` files.
   Impact: hard to review or commit safely.
   Mitigation: stage code/doc changes separately from generated/config changes.

2. Global `~/.claude/mcp.json` Brave MCP reads `.env` from the current project at startup.
   Impact: any repo-local `.env` parse bug or prompt/tool misuse can expose more secret context than intended.
   Mitigation: prefer named environment variables over MCP startup reads from `.env`.

3. Full pytest remains blocked by Windows temp permission issues.
   Impact: targeted tests pass, but full-suite confidence is incomplete.
   Mitigation: fix `%TEMP%\pytest-of-dusro` permissions or run pytest with repo-local temp base.

4. Some older scripts still contain direct non-atomic writes and broad `except Exception` patterns.
   Impact: lower-priority workflows can still hide failures or leave partial state.
   Mitigation: continue migrating only production-reachable scripts to `src/utils/atomic_io.py`.

## Medium

1. `STATE_HANDOFF.md` content in `handoffs/` is stale and internally contradictory.
   Impact: future agents may trust incorrect test and file-state claims.
   Mitigation: treat this root risk register and current git status as newer than that handoff.

2. Claude project hooks are deleted while global hooks remain configured.
   Impact: hook behavior depends on global machine state, not repo state.
   Mitigation: keep hooks telemetry-only or document exact project-local hook policy before restoring.
