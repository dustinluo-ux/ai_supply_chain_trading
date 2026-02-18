# AI_RULES — Development Guardrails

**Last Updated:** 2026-02-14  
**Status:** Enforced guardrails for AI-assisted development  
**Scope:** Applies to all AI agent usage on this repository  
**Enforcement Level:** Mandatory

---

## 0. Purpose

This file exists to prevent:
- **Architectural drift** — unauthorized structural changes
- **Hallucination** — inventing non-existent behavior
- **Silent interface mutation** — breaking contracts without notice
- **Legacy resurrection** — wholesale revival of archived code
- **Spine fragmentation** — diverging from single canonical structure

**These rules are binding.**  
If a task cannot be completed under these rules, it must stop and ask.

---

## 1. Canonical Documentation (Order of Authority)

AI must treat the following as authoritative, in this order:

1. **ARCHITECTURE.md** — System design, data flow, module organization, key paths
2. **WORKFLOW.md** — Execution stages (what happens, in order)
3. **SYSTEM_MAP.md** — Code mapping (workflow → modules, canonical entry points)
4. **STRATEGY_LOGIC.md** — Capital decision spine (how decisions are made)
5. **DECISIONS.md** — Architectural decision records (why choices were made)
6. **TECHNICAL_SPEC.md** — Indicator math, Master Score, News Alpha strategies
7. **BACKTEST_JOURNAL.md** — Execution assumptions, safety audits, results
8. **PROJECT_STATUS.md** — Current state, readiness assessment, action items

**Location:** All canonical docs in **project root** (consolidated 2026-02-14).

**No other document defines truth** unless explicitly referenced by the canon.

### Read-Only Evidence Sources

**Never revive logic from:**
- `graveyard/` — Archived legacy code
- `wealth_signal_mvp_v1/` — Read-only reference implementation

**Purpose:** Source material for code reuse only (see Section 3).

---

## 2. AI Agent Safety Preamble (MANDATORY)

**Paste this block at the start of all AI agent sessions:**

```
CANONICAL DOCUMENTATION (load first):
All docs in project root (consolidated 2026-02-14):
- ARCHITECTURE.md — system design, data flow, module organization
- WORKFLOW.md — execution stages (what happens, in order)
- SYSTEM_MAP.md — code mapping (workflow → modules)
- STRATEGY_LOGIC.md — capital decision spine
- DECISIONS.md — architectural decisions (why)
- TECHNICAL_SPEC.md — indicator math, Master Score
- BACKTEST_JOURNAL.md — execution details, results
- PROJECT_STATUS.md — current state, readiness

READ-ONLY SOURCE FOLDERS (never import at runtime):
- graveyard/
- wealth_signal_mvp_v1/

CURRENT OPERATING MODE:
- P0 Fix Mode (LOCKED) — see DECISIONS.md
- Only fix documented but broken features
- No new features or interface changes without approval

YOU MUST (before coding):
1. Identify which module in SYSTEM_MAP.md this change belongs to
2. Search BOTH read-only folders for reuse candidates
3. Report file paths + what is reusable
4. Produce a plan:
   - Files to touch
   - Interface impact: NONE or PROPOSED
   - Validation steps
   - Documentation updates

IF interface impact = PROPOSED → STOP and wait for approval.

EVIDENCE RULE:
- Any claim about current behavior must cite: file path + symbol name
- If unclear → say UNKNOWN
- If not found → say NOT FOUND and stop
- Do not guess, invent, or assume

DO NOT:
- Invent behavior not in canonical docs
- Refactor unless explicitly requested
- Modify or import from read-only folders
- Change public interfaces silently
- Skip the plan-first sequence
```

---

## 3. Reuse-First Rule (Graveyard + wealth_signal_mvp_v1)

These folders contain **read-only source material** for code reuse.

**Never:**
- Edit, move, rename, or delete anything inside them
- Add runtime imports from them
- Resurrect full legacy modules wholesale

**Before implementing ANY new feature or module:**

1. **Search both folders** for reusable logic
2. **Report candidates:** file path + description
3. **If reuse is justified:**
   - Copy minimal required logic into `src/`
   - Adapt to canonical interfaces
   - Do NOT preserve legacy interfaces if conflicting
   - Attribute origin in commit message or header comment
4. **If full resurrection seems required:**
   - Write justification in DECISIONS.md
   - Wait for approval
   - Then proceed with adaptation

---

## 4. Plan-First Rule (Anti-Hallucination)

AI must **never** jump directly into multi-file or architectural coding.

**Required Sequence:**
```
1. PLAN
   ↓
2. APPROVAL (if interfaces change)
   ↓
3. CODE
   ↓
4. VALIDATE
   ↓
5. DOCUMENT (only if behavior/structure changed)
```

**Skipping any step = violation.**

**Plan Contents:**

1. **Canonical location** (which module/stage/decision)
2. **Reuse search results** (graveyard + wealth_signal_mvp_v1)
3. **Implementation scope** (files, functions, tests)
4. **Interface impact** (NONE or PROPOSED)
5. **Validation steps** (unit/integration/determinism tests)
6. **Documentation updates** (which canonical docs affected)

---

## 5. Public Interface Freeze (CRITICAL)

**Public interfaces are contracts:**
- Engine method signatures (`SignalEngine`, `PolicyEngine`, `PortfolioEngine`)
- Intent/data models (`PortfolioIntent`, `RegimeState`, `SignalResult`)
- Config schemas (all YAML files in `config/`)

**Rules:**
- No silent interface changes
- Any interface change requires:
  1. Explicit proposal in plan
  2. Documentation update in canonical docs
  3. Migration note (if breaking change)
  4. Approval before implementation

**Execution parity:** Backtest and execution paths must call identical scoring/regime/sizing logic.

### 5.2 The Scavenge Protocol

Before coding any new utility, data helper, or signal module, AI **must** search `graveyard/ARCHIVE_MAP.md` for reusable logic.

**Required steps:**
1. Search `ARCHIVE_MAP.md` for keywords matching the needed functionality
2. If a candidate exists, read the archived file and evaluate reuse potential
3. If reuse is justified, follow the Reuse-First Rule (Section 3)
4. If no candidate exists, proceed with new implementation

**Rationale:** The graveyard contains proven logic (API integrations, math formulas, data format converters) that should not be reinvented.

### 5.3 Immutability: ARCHITECTURE.md and STRATEGY_MATH.md

**From now on, do not modify the following documents without asking the user for a "Proposal Review" first:**

- **docs/ARCHITECTURE.md** — System design, data flow, module organization
- **docs/STRATEGY_MATH.md** — Signal formulas, combination, portfolio math

**Required steps before any edit:**
1. Propose the change (scope, rationale, exact sections affected)
2. Request: "Proposal Review: [brief description]"
3. Proceed only after explicit user approval

**Rationale:** These docs are structural and mathematical truth; changes have broad impact and must be reviewed.

---

## 6. Canonical Entry Points Only

**Canonical (production-ready):**
- `scripts/backtest_technical_library.py`
- `scripts/research_grid_search.py`
- `scripts/run_execution.py`
- `scripts/run_weekly_rebalance.py` (Automated Rebalancing; delegates to run_execution)

**Non-canonical (experimental/legacy):**
- `run_phase1_test.py`, `run_phase2_pipeline.py`, `run_phase3_backtest.py`
- `run_strategy.py`, `run_technical_backtest.py`, `test_signals.py`

**Rule:** AI must not fix, extend, or refactor non-canonical scripts unless explicitly requested.

---

## 7. Documentation Discipline

**Update docs when:**
- Behavior changed
- Structure changed
- New decision made
- Interface modified

**Do NOT update docs when:**
- Implementation details unchanged
- Refactoring without functional impact
- Bug fixes that restore documented behavior

**Rule:** Docs updated **before or alongside** code, never after. No doc churn.

---

## 8. Failure Mode (Hard Stop Protocol)

**If any rule is violated:**

1. Stop immediately
2. State which rule is violated
3. Explain why progress is blocked
4. Ask for clarification or override

**Proceeding silently = failure.**

---

## 9. Enforcement Hierarchy

**If conflict exists between:**

1. This file (AI_RULES.md) — **highest authority**
2. .cursorrules
3. Cursor agent instruction
4. Ad hoc user prompt

**This file wins** unless user provides explicit override.

**Overrides must be:** Explicit, narrow in scope, documented.

## 10.  **RULE: CONFIGURATION DISCIPLINE (ZERO HARDCODING)**
1. **No Magic Numbers:** Never hardcode weights (0.2, 0.4), lookback periods (60, 200), or fixed ratios in `.py` files.
2. **Canonical Config Mapping:**
   - **Data Ingestion:** Use `config/data_config.yaml`
   - **Signal Weights:** Use `config/technical_master_score.yaml`
   - **Supply Chain/Sentiment:** Use `config/strategy_params.yaml`
3. **Dynamic Loading:** If a parameter is needed, the code MUST use `load_data_config()` or a YAML parser. 
4. **Validation:** If a required config key is missing, the code should raise a clear `KeyError` explaining which YAML file needs updating.

