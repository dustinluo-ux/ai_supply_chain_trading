# Loose Ends Checklist

Run by the `integrator` agent after every build cycle.
Source of truth: `~/.claude/rules/loose-end-detection.md` (full operational protocol).

---

## Pre-Build

- [ ] Contract exists for this module (`docs/contracts/<module>.md`)
- [ ] Contract has no `{PLACEHOLDER}` fields
- [ ] All dependency contracts are `approved` or `implemented`
- [ ] No critical open risks in `ACTIVE_RISK_REGISTER.md` for this module
- [ ] `CONTRACT_INDEX.md` updated to include this module

## Post-Build: Code Quality

- [ ] No `float(` in monetary code paths
- [ ] No hardcoded secrets (password, api_key, token literals)
- [ ] No `print()` in `src/` — uses `logging`
- [ ] No `eval()` / `exec()` on user-controlled input
- [ ] No `../` path traversal from user input
- [ ] All file writes use atomic pattern (`.tmp` → `os.replace()`)

## Post-Build: Tests

- [ ] Coverage report generated
- [ ] Line coverage ≥ 80%
- [ ] Each external API/DB boundary has at least one integration test
- [ ] No monetary assertion uses `float` — all use `Decimal`

## Post-Build: File Hygiene

- [ ] No orphaned files (unreferenced, not in `docs/ARCHITECTURE.md`)
- [ ] No `*.tmp` files remaining
- [ ] No `TODO` / `FIXME` / `HACK` in `src/` unless tracked in risk register

## Post-Build: Cross-Module

- [ ] All contract outputs consumed or documented as terminal
- [ ] All contract inputs have confirmed upstream providers
- [ ] `CONTRACT_INDEX.md` reflects current implementation status
- [ ] No stale imports referencing deleted or renamed modules

## Post-Build: Documentation

- [ ] `STORY.md` updated (one line per milestone)
- [ ] `ACTIVE_RISK_REGISTER.md` updated if any risk changed
- [ ] `STATE_HANDOFF.md` updated with next step
- [ ] `README.md` exists — updated if architecture changed

## Completion Gate

Work is complete only when all boxes above are checked and the integrator returns PASS.
