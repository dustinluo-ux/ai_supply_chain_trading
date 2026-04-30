# Question Classifier

Classify every question before deciding whether to ask the user.
Only class C and D may be escalated. Classes A and B must be resolved internally.

---

## Classes

### A — Technical / Reversible
Decision is derivable from code, docs, web research, or established convention. Can be changed cheaply later.

**Action:** Resolve internally. No log required.

**Examples:** Library selection for < 50 LOC task, naming conventions, log level, test fixture structure, helper function design.

---

### B — Technical / Irreversible
Technical decision that is hard or costly to change after implementation begins.

**Action:** Use `researcher` agent first. Choose a reasonable default. Log as `[DECIDED: reason]` in STORY.md. Ask user only if no reasonable default exists AND impact is high.

**Examples:** Database schema, API response envelope format, serialization format (JSON vs MessagePack), async vs sync I/O model.

---

### C — Business / Product / Valuation
Requires business intent, pricing knowledge, market context, or regulatory information that an agent cannot derive.

**Action:** Ask user. Batch all class-C questions in a single message with 2–4 options and a recommendation.

**Examples:** Pricing model, target market segment, approved data sources, budget ceiling, what is explicitly out of scope.

---

### D — Security / Credential / Destructive
Involves credentials, secrets, external accounts, production data, or irreversible operations.

**Action:** Ask user unconditionally. No exceptions.

**Examples:** Writing to `.env`, force-pushing to main, dropping database tables, changing auth model, adopting paid external services.

---

## Quick Reference

| Class | Type | Action |
|-------|------|--------|
| A | Technical / reversible | Resolve internally |
| B | Technical / irreversible | Research → decide → log `[DECIDED]`; ask only if no default + high impact |
| C | Business / product | Ask user, batch with options and recommendation |
| D | Security / destructive | Ask user, no exceptions |

---

## Logging Rule

Class-B decisions resolved internally:
- STORY.md: `[DECIDED: <reason>] <decision>`
- Output: prefix with `[DECIDED: reason]` so the user can identify autonomous choices

Class-C / D awaiting user input:
- Add to `STATE_HANDOFF.md` under **Open Questions** with `class: C` or `class: D`
