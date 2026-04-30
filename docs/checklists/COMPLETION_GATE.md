# Completion Gate

A task or session is **not complete** unless every item below is satisfied.
The system must not use the words "complete," "done," or "all fixes applied" unless this gate has been run and returned PASS.

---

## Gate Checklist

### Contract
- [ ] Contract exists at `docs/contracts/<module>.md`
- [ ] Contract has no `{PLACEHOLDER}` fields
- [ ] Contract `Status: implemented`
- [ ] All inputs and outputs fully specified (no `TBD` without justification)

### Implementation
- [ ] Implementation files exist at paths named in the contract
- [ ] Signatures match contract inputs/outputs exactly
- [ ] No extra scope beyond what the contract specifies

### Tests
- [ ] Test file exists — OR — exemption explicitly logged in contract with justification
- [ ] Coverage ≥ 80% for the module
- [ ] No monetary assertion uses `float` — all use `Decimal`

### Review
- [ ] spec-reviewer: PASS (contract compliance)
- [ ] code-reviewer: PASS (code quality)

### Integration
- [ ] integrator: PASS (end-to-end sweep)
- [ ] No orphaned files (unreferenced, not in `docs/ARCHITECTURE.md`)
- [ ] No dangling TODO/FIXME in `src/` unless tracked in risk register
- [ ] No stale imports or missing upstream providers
- [ ] No hardcoded secrets (password, api_key, token literals)

### Questions
- [ ] No unresolved class-A or class-B questions (see QUESTION_CLASSIFIER.md)
- [ ] All class-B decisions researched, resolved, and logged as `[DECIDED]`
- [ ] Only class-C or class-D questions may remain — only if awaiting user input

### State
- [ ] `STATE_HANDOFF.md` updated — Status: COMPLETE or exact next step stated
- [ ] `ACTIVE_RISK_REGISTER.md` updated if any risk changed
- [ ] `STORY.md` updated (one line per milestone)
- [ ] `CONTRACT_INDEX.md` updated to `implemented`

---

## Required Output Block

Every completion report must include:

```
Completion Gate: PASS | FAIL
Reviewer:        PASS | FAIL
Integrator:      PASS | FAIL
Unresolved technical questions: N  (must be 0 for PASS)
User decisions required: <list or "none">
```

---

## Enforcement

Enforced by agent instruction. The integrator is the last mandatory gate and must confirm PASS before emitting any completion signal. See QUESTION_CLASSIFIER.md for question routing rules.
