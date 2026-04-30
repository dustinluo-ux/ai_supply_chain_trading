# Integration Checklist

Run by the `integrator` agent as the final gate across all modules in a build cycle.

---

## Module Completeness

For each module in `CONTRACT_INDEX.md`:
- [ ] Contract status is `implemented`
- [ ] Implementation file(s) exist in `src/`
- [ ] Function/class signatures match contract inputs and outputs exactly
- [ ] Test file exists for this module
- [ ] Reviewer returned PASS for this module

## End-to-End Wiring

- [ ] Every module output is consumed by a downstream consumer OR documented as a terminal output
- [ ] Every module input has a confirmed upstream provider (no dangling inputs)
- [ ] Execution graph in `docs/ARCHITECTURE.md` matches actual import/dependency structure
- [ ] No circular dependencies

## Stale Reference Sweep

- [ ] No imports pointing to files that no longer exist
- [ ] No references to removed functions or classes
- [ ] No stale env var names in code vs. `.env.example`
- [ ] No references to old module names after any rename

## Documentation Integrity

- [ ] `README.md` exists and describes what was actually built (not the plan)
- [ ] `README.md` intro is readable without technical background
- [ ] All env vars in `.env.example` match what the code reads from `os.environ`
- [ ] `docs/adr/` has an entry for any architecture decision made during this build
- [ ] `STORY.md` has one line per milestone, in order

## State Files

- [ ] `STATE_HANDOFF.md` updated — Status: COMPLETE or next step clearly stated
- [ ] `ACTIVE_RISK_REGISTER.md` — no risk left at `open` severity `high` without mitigation
- [ ] `CONTRACT_INDEX.md` — all entries are `implemented` or `deprecated`

## Git

- [ ] All changes committed (no uncommitted src/ or tests/ changes)
- [ ] Commit messages follow conventional commits format
- [ ] No `.env` in staging area

## Final Gate

Integrator signs off → work is complete. No further approval needed unless a business decision arises.
