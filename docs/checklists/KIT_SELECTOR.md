# Kit Selector — Reference for Stage 0.5

Factory always proposes **STANDARD**. This file defines what signals to surface and how to run the selection conversation.

---

## HEAVY-Relevant Signals

Surface these when detected — they are information, not a decision tree. The user decides.

| Signal | Example |
|--------|---------|
| Money transmission or billing | Stripe, invoicing, payouts, subscription tiers |
| Production deployment | Cloud (AWS/GCP/Azure), VPS, serverless, Docker prod |
| Persistent database or shared state | Postgres, SQLite, Redis, any file-based state shared across users |
| External API with reliability/secrets implications | Third-party APIs with rate limits, auth tokens, or SLAs |
| Auth / security boundaries | Login, JWT, OAuth, role-based access, session management |
| >3 modules with chained I/O | Complex pipelines where one module's output feeds the next |
| Irreversible technical choices at project level | Schema design, serialization format, async I/O model |

---

## What Each Kit Gives

**STANDARD** — contracts + builder + reviewer + integrator; user makes the architectural calls
- No risk-checker blocking step
- No managed builder (cloud API)
- No ADR gate
- No CI workflow
- Lighter scaffold: faster to start, easier to inspect

**HEAVY** — full pipeline kit; agents drive, user approves milestones
- risk-checker validates before any build
- managed_builder.py (Managed Agents API) for sandboxed cloud builds
- ADR gate (check_adr.py hook) on git commit
- CI workflow template
- Full audit trail: risk register, SPOF per milestone, escalation protocol

---

## Stage 0.5 Script

```
Factory: Here's what I understand about <idea>:
         - <bullet 1>
         - <bullet 2>
         - <bullet 3>

         Signals detected: <list any HEAVY signals, or "none">
         Proposed kit: STANDARD (you stay involved in architectural calls)

         What each kit gives:
           STANDARD — contracts + builder + reviewer + integrator; you make the calls
           HEAVY    — full pipeline kit, risk-checker, managed builder, ADR gate

         Does this match your intent? Any corrections or questions?

[user may discuss, correct the summary, ask questions — loop until they confirm]

User: <confirms STANDARD or upgrades to HEAVY>

Factory: <kit> confirmed. Scaffolding now.
```

**Rules:**
- Never auto-select HEAVY regardless of signals.
- Never proceed to scaffold before explicit user confirmation.
- If the user asks "what's the difference?" — explain, don't decide for them.
- If the user says "you decide" — still propose STANDARD and explain why.

---

## Example Exchanges

### Low-complexity, no signals → STANDARD (quick confirm)

```
/manufacture "CLI tool to rename files by date"

Factory: Here's what I understand:
         - Single-purpose CLI utility
         - Reads file metadata, renames by date pattern
         - Local use only

         Signals detected: none
         Proposed kit: STANDARD

         What each kit gives:
           STANDARD — contracts + builder + reviewer + integrator; you make the calls
           HEAVY    — full pipeline kit, risk-checker, managed builder, ADR gate

         Does this match your intent?

User: yes, STANDARD

Factory: STANDARD confirmed. Scaffolding now.
```

### External API dependency → surface signal, user keeps STANDARD

```
/manufacture "profit margin reporter pulling from exchange rate API"

Factory: Here's what I understand:
         - Multi-module calculation pipeline
         - Pulls from an external exchange rate API
         - Internal reporting tool

         Signal flagged: external API dependency → may suggest HEAVY
         Proposed kit: STANDARD

         What each kit gives:
           STANDARD — contracts + builder + reviewer + integrator; you make the calls
           HEAVY    — full pipeline kit, risk-checker, managed builder, ADR gate

         Does this match your intent? Any corrections?

User: let's keep STANDARD, the API is read-only and low-risk

Factory: STANDARD confirmed. Scaffolding now.
```

### Multiple signals → user upgrades to HEAVY

```
/manufacture "billing portal with Stripe + Postgres"

Factory: Here's what I understand:
         - Billing portal with subscription management
         - Stripe integration for payments
         - Postgres for persistent user + subscription data

         Signals flagged:
           - Money transmission (Stripe)
           - Persistent database (Postgres)
           - External API with secrets (Stripe API key)
         Proposed kit: STANDARD (you can still upgrade)

         What each kit gives:
           STANDARD — contracts + builder + reviewer + integrator; you make the calls
           HEAVY    — full pipeline kit, risk-checker, managed builder, ADR gate

         Given the payment + DB signals, HEAVY would add risk-checker validation
         and managed builder sandbox. Your call.

User: let's go HEAVY

Factory: HEAVY confirmed. Scaffolding now.
```
