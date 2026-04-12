# TDO Data Contract — THESIS_SCHEMA v1.0.0

**Source file:** `shared_schemas/THESIS_SCHEMA.json`
**Schema ID:** `https://alpha-scout-pipeline/thesis-data-object/v1`
**Purpose:** Immutable, deterministic handoff format between Scout → Auditor → Pulse. No capital deployment is permitted without a TDO that has traversed all three phases.

---

## TDO Lifecycle

```
SCOUTED → AUDIT_PENDING → AUDITED → PULSE_ELIGIBLE → EXECUTED
                       ↘ AUDIT_FAILED     ↘ PULSE_BLOCKED
```

| Phase | Set By | Meaning |
|-------|--------|---------|
| `SCOUTED` | alpha_scout/main.py | Scout has emitted a validated thesis |
| `AUDIT_PENDING` | auto_audit_watcher.py | Auditor has claimed the TDO |
| `AUDITED` | auditor/orchestrator.py | Physical verification complete, hash sealed |
| `AUDIT_FAILED` | auditor/orchestrator.py | ≥4 core audit stages failed |
| `PULSE_ELIGIBLE` | tdo_gate.py | Passed all 7 execution checks |
| `EXECUTED` | run_weekly_rebalance.py | Orders submitted |
| `PULSE_BLOCKED` | tdo_gate.py | Gate failed (cap rule, age, hash, etc.) |
| `EXPIRED` | tdo_validator.py | > 90 days old |

---

## Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `thesis_id` | string | Yes | `tdo_{uuid5}` — deterministic from `thesis_claim` text. Immutable. |
| `schema_version` | string | Yes | `"1.0.0"` — const |
| `phase` | enum | Yes | Current lifecycle state (see above) |
| `created_at` | datetime | Yes | UTC timestamp of Scout emission. Immutable. |
| `last_updated_at` | datetime | No | UTC timestamp of last phase transition |
| `scout` | object | Yes | Module 1 output. Immutable after SCOUTED. |
| `auditor` | object\|null | No | Module 2 output. Null until AUDIT_PENDING. |
| `pulse` | object\|null | No | Module 3 output. Null until AUDITED. |
| `red_team_constraints` | object | No | Hard-coded safety constants (schema-level) |
| `provenance` | object | No | Git SHAs, version, pipeline run ID |

---

## `scout` Section (Module 1 Output)

| Field | Type | Required | Constraint |
|-------|------|----------|-----------|
| `title` | string | Yes | max 120 chars |
| `thesis_claim` | string | Yes | 50–1000 chars. The canonical falsifiable claim. |
| `summary` | string | Yes | max 2000 chars |
| `confidence` | number | Yes | [0.0, 1.0]. Below 0.30 → blocked. |
| `horizon` | enum | Yes | `H1_TACTICAL` \| `H2_STRUCTURAL` \| `H3_DISCOVERY` |
| `supporting_findings` | array | Yes | Min 3 items. Each must have `composite_score ≥ 0.30`. |
| `bottleneck_description` | string\|null | No | Free-text supply chain constraint. Feeds BOM Decomposer. |
| `critical_disagreement` | string\|null | No | Counter-narrative from Gemini synthesis. |
| `research_risks` | array[string] | No | Risk factors identified during synthesis. |
| `query_origin` | string | No | Original search query. |
| `trigger_source` | enum | No | `MANUAL_QUERY` \| `SENTINEL_ACCELERATION` \| `SEED_PAPER` \| `CRON_SCHEDULED` |

### `supporting_findings` item fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string (uri) | Yes | Source URL |
| `title` | string | Yes | Article/paper title |
| `source_domain` | string | Yes | e.g. `"arxiv.org"` |
| `composite_score` | number | Yes | `0.40×relevance + 0.35×novelty + 0.25×evidence`. Must be ≥ 0.30. |
| `snippet` | string | No | Text excerpt |
| `published_date` | date\|null | No | `YYYY-MM-DD` |
| `relevance_score` | number | No | [0.0, 1.0] |
| `novelty_score` | number | No | [0.0, 1.0] |
| `evidence_quality` | number | No | [0.0, 1.0] |

---

## `auditor` Section (Module 2 Output)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audit_hash` | string | Yes | `audit_{sha256hex}` — SHA-256 of canonical audit payload. Must be verified by Pulse. |
| `tes_score` | number | Yes | Technology Exposure Score ≥ 0.0 |
| `tes_components` | object | Yes | Disaggregated TES inputs (see below) |
| `market_cap_usd` | number\|null | Yes | Market cap in USD. Null if unresolvable. |
| `cap_rule_passed` | boolean | Yes | **RED TEAM**: `True` only if `market_cap_usd < 50,000,000,000`. |
| `audited_at` | datetime | No | UTC timestamp when hash was sealed |
| `bom_components` | array[string] | No | Bill of materials from Gemini BOM decomposition |
| `supply_chain` | object | No | SEC-scraped suppliers, customers, competitors |
| `audit_failures` | array | No | Non-fatal warnings (WARNING or ERROR severity) |

### TES Formula
```
TES = (niche_revenue / total_revenue) × (1 + CAGR) × patent_density
```

### `tes_components` fields

| Field | Description |
|-------|-------------|
| `primary_ticker` | CIK-resolved ticker symbol |
| `niche_revenue_usd` | Divisional revenue in the bottleneck segment |
| `total_revenue_usd` | Total company revenue |
| `niche_revenue_ratio` | `niche / total` — the pure-play filter [0.0, 1.0] |
| `divisional_cagr` | e.g. `0.25` = 25% CAGR |
| `patent_density` | Patent count per $1B revenue, or normalized [0.0, 1.0] |
| `data_vintage` | Date of most recent SEC filing used |
| `data_confidence` | `HIGH` \| `MEDIUM` \| `LOW` \| `ESTIMATED` |

### `audit_hash` Computation
SHA-256 is computed over a canonical JSON payload of: `tes_score`, `tes_components`, `market_cap_usd`, `cap_rule_passed`, `supply_chain`, `bom_components`. Timestamps are **excluded** to allow re-verification at any future time.

---

## `pulse` Section (Module 3 Output)

| Field | Type | Description |
|-------|------|-------------|
| `execution_permitted` | boolean | **RED TEAM**: Must be `True` AND `audit_hash` must verify before any order |
| `execution_blocked_reason` | string\|null | Human-readable block reason |
| `macro_gate` | object | Regime state at evaluation time (`BULL`/`SIDEWAYS`/`BEAR`) |
| `target_tickers` | array[string] | Tickers resolved from supply chain mapping |
| `suggested_position_bias` | enum | `OVERWEIGHT`/`NEUTRAL`/`UNDERWEIGHT`/`NO_POSITION` |
| `thesis_expiry_date` | date\|null | 90 days from `audited_at`. Re-audit required after this date. |
| `execution_log` | array | Immutable append-only log of all execution events |

---

## `red_team_constraints` Section (Hard-Coded Constants)

| Constraint | Value | Rule |
|------------|-------|------|
| `market_cap_ceiling_usd` | `50,000,000,000` | Pulse MUST NOT execute if market cap ≥ $50B |
| `min_supporting_findings` | `3` | Scout must supply ≥3 findings above threshold |
| `min_composite_score` | `0.30` | Minimum per-finding composite score |
| `audit_hash_required_for_execution` | `true` | No execution without a verified SHA-256 seal |
| `max_thesis_age_days` | `90` | Re-audit required after 90 days |
| `same_day_execution_gate_hours` | `24` | Pulse cannot execute within 24h of Scout emission |

---

## Full Example TDO (Condensed)

```
thesis_id:     tdo_7f3a9b12-4e1c-4d2f-a83b-9c0e1f2d3a4b
phase:         AUDITED
created_at:    2026-03-10T09:00:00Z

scout:
  title:       "GaN Power Semiconductor Supply Constraint"
  confidence:  0.74
  horizon:     H3_DISCOVERY
  findings:    3 items, composite_scores: [0.85, 0.79, 0.81]

auditor:
  tes_score:         0.68
  market_cap_usd:    4,200,000,000  (< $50B → cap_rule_passed: true)
  cap_rule_passed:   true
  audit_hash:        audit_a3f9c1d2...
  primary_ticker:    WOLFSPEED
  niche_rev_ratio:   0.873  (87.3% revenue from GaN — pure-play confirmed)
  divisional_cagr:   0.31   (31% growth)

pulse:
  execution_permitted:  true
  regime:               BULL
  target_tickers:       [WOLF, ON, AIXA.DE]
  position_bias:        OVERWEIGHT
  thesis_expiry:        2026-06-08
```

---

## Validation

All TDOs are validated by `tdo_validator.validate_tdo_or_raise()` at every phase transition.
Boolean convenience: `tdo_validator.validate_schema(tdo)` → `True`/`False`.
