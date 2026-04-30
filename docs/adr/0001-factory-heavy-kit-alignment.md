---
status: accepted
date: 2026-04-30
---

# 0001 — Adopt HEAVY Kit for Factory Alignment

## Context

The `ai_supply_chain_trading` repository is an autonomous quantitative trading pipeline with external API dependencies (IBKR, Marketaux, Tiingo, FMP, EDGAR), persistent file-based state, and irreversible operations (live order submission to a brokerage). It was built before the factory kit system existed and was retroactively aligned to STANDARD kit in April 2026.

The HEAVY kit adds: risk-checker validation gate, Managed Agents API cloud builder (sandboxed per-module builds), ADR gate (blocks `git commit` until decisions are recorded), and the full audit scaffold (checklists, escalation protocol).

HEAVY-relevant signals present in this repo:
- External APIs with auth tokens and SLAs (IBKR, Tiingo, FMP, Marketaux, EDGAR)
- Irreversible operations (live paper/live order submission via IBKR)
- >3 modules with chained I/O (signal_engine → policy_engine → portfolio_engine → execution)
- File-based persistent state (model weights, portfolio weights, backtest results)

## Decision

Adopt HEAVY kit. Install all HEAVY components additive-only (no existing file overwritten):
- `scripts/check_adr.py` — ADR gate hook
- `scripts/managed_builder.py` — per-module cloud builder (Managed Agents API)
- `scripts/auto_watcher.py` — optional contract watcher helper
- `docs/checklists/` — 5 audit checklists (COMPLETION_GATE, INTEGRATION_CHECKLIST, KIT_SELECTOR, LOOSE_ENDS_CHECKLIST, QUESTION_CLASSIFIER)
- `docs/escalation_protocol.md` — non-retryable FAIL template
- PreToolUse hook in `.claude/settings.json` wired to `check_adr.py`

Historical architectural decisions remain in `docs/DECISIONS.md` (55+ entries). ADRs in `docs/adr/` cover forward-looking decisions from 2026-04-30 onward.

## Consequences

- `git commit` is blocked until at least one real ADR exists in `docs/adr/`. This ADR (0001) unblocks the gate from day 1.
- `managed_builder.py` requires one-time setup: `conda run -n wealth python scripts/managed_builder.py --setup` to provision a Managed Agent + environment via the Anthropic API. The printed IDs must be added to `.env` as `MANAGED_BUILDER_ENVIRONMENT_ID`, `MANAGED_BUILDER_AGENT_ID`, `MANAGED_BUILDER_AGENT_VERSION`.
- `DECISIONS.md` is the historical record; `docs/adr/` is the forward-looking record. Both are maintained in parallel.
- `auto_watcher.py` is optional — requires `watchdog` package (`pip install watchdog`). Not required for normal operation.
