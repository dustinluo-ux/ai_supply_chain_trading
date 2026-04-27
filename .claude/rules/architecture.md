# Architecture Rules

## Path Confirmation Rule

Before scaffolding any new structure: confirm the target directory explicitly. Never default to assumed locations. Ask once if not stated.

## ADR Convention

Architectural decisions live in `docs/adr/NNNN-title.md` (MADR format). Required fields: Status, Context, Decision, Consequences.

## Single Point of Failure Rule

Before any plan is approved, name exactly one SPOF per milestone. If multiple SPOFs exist, decompose into sub-milestones until each has exactly one.

## API Design

- REST: plural nouns, versioned (`/v1/`), no verbs in paths.
- All responses: `{ data, meta, errors }` envelope.
- Auth: Bearer JWT only. No API keys in query strings.

## Dependency Policy

- Prefer stdlib over third-party for < 50 LOC tasks.
- Every new dependency requires a one-line justification comment in `environment.yml` or `pyproject.toml`.
- No dependency with < 1000 GitHub stars unless explicitly approved.

## Agent Naming

Default agents live globally in `~/.claude/agents/`. Use project-local agents only for repo-specific overrides.

All agents use descriptive names:
- `planner` — architectural planner, produces PLAN.md
- `risk-checker` — validates risk register before implementation
- `builder` — implements milestones from PLAN.md
- `reviewer` — anti-hallucination audit
- `compressor` — context compaction with state preservation
