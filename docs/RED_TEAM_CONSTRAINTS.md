# Red Team Constraints — Safety Rails

**Authority:** `AI_RULES.md` (highest precedence). These constraints are not configurable at runtime. Any code change that weakens them requires an explicit update to `AI_RULES.md` with a documented justification.

**Enforcement:** `tdo_validator.py` + `auditor/tdo_gate.py`. Both must pass independently.

---

## Constraint Index

| # | Name | Location | Blocks |
|---|------|----------|--------|
| 1 | Circuit Breaker | `tdo_bridge.py` + `tdo_validator.py` | Scout output |
| 2 | Audit Hash Gate | `tdo_gate.py` Check 2 | Execution |
| 3 | 50B-Cap Rule | `tdo_gate.py` Check 3-4 + `orchestrator.py` | Execution |
| 4 | Pure-Play Filter | `tes_scorer.py` (TES formula) | Audit scoring |
| 5 | 10-K Decay (90-day expiry) | `tdo_gate.py` Check 6 | Execution |
| 6 | 24h Contamination Gate | `tdo_gate.py` Check 5 | Execution |
| 7 | Bear-Regime Halt | `regime_watcher.py` + `run_weekly_rebalance.py` | Execution |
| 8 | Tier-3 Visibility Limit | `supply_chain_scraper.py` (SEC depth) | Audit scope |
| 9 | Liquidity Rule | `tdo_gate.py` Check 7 | Execution (live) |
| 10 | Kill Switch | `tdo_gate.py` Check 6 | All execution |

---

## 1. Circuit Breaker
**What it does:** Prevents low-confidence or under-researched theses from entering the pipeline.

**Rule:**
- `supporting_findings` must contain ≥ 3 items
- Every finding must have `composite_score ≥ 0.30`
- Thesis `confidence` must be ≥ 0.30

**Enforcement:** `tdo_bridge.promote_to_tdo()` raises `MappingError` before the TDO is even created. `tdo_validator.py` re-checks on every phase read.

**Rationale:** A thesis with fewer than 3 independent corroborating sources, or low composite evidence, represents speculation rather than structured discovery. The circuit breaker is the first and cheapest filter in the pipeline.

---

## 2. Audit Hash Gate
**What it does:** Prevents execution of any TDO whose audit data has been tampered with after sealing.

**Rule:** `tdo["auditor"]["audit_hash"]` must match `SHA-256(canonical_audit_payload)` exactly.

**Enforcement:** `tdo_gate.py` Check 2. `verify_audit_hash(tdo["auditor"])` re-derives the hash from `tes_score`, `tes_components`, `market_cap_usd`, `cap_rule_passed`, `supply_chain`, `bom_components`. Timestamps are intentionally excluded from the hash to allow re-verification at any future point.

**Rationale:** Any modification to audit fields after sealing — including manual edits to the JSON — invalidates the hash and halts execution. This prevents "audit laundering."

---

## 3. 50B-Cap Rule
**What it does:** Restricts the pipeline to investable mid/small-cap supply chain plays. Mega-cap stocks are excluded because their supply chain leverage is diffuse and their prices are efficiently discovered.

**Rule:** `auditor.market_cap_usd` must be `< 50,000,000,000` (USD 50 billion).

**Enforcement:** `auditor/orchestrator.py` sets `cap_rule_passed = False` during audit. `tdo_gate.py` Checks 3-4 verify `cap_rule_passed == True` and independently re-check the raw market cap.

**Edge case:** If `market_cap_usd` is unresolvable (company name cannot be mapped to a ticker), `cap_rule_passed` is set to `True` with a WARNING audit failure. This prevents sector-level theses from being permanently blocked on a lookup failure, but requires manual verification before live execution.

---

## 4. Pure-Play Filter (TES Score)
**What it does:** Filters out conglomerate companies whose revenue is too diversified to provide concentrated supply chain exposure.

**Rule (TES formula):**
```
TES = (niche_revenue / total_revenue) × (1 + CAGR) × patent_density
```

The `niche_revenue / total_revenue` ratio is the pure-play filter. A company deriving only 5% of revenue from the bottleneck segment scores near zero on TES regardless of its growth rate.

**Enforcement:** `auditor/tes_scorer.py`. Low TES does not hard-block execution (it is a scoring signal), but it reduces the TDO's effective conviction weight in downstream portfolio construction.

**Rationale:** Supply chain scarcity alpha is concentrated in companies whose entire business is that one constraint. Diversified exposure dilutes the signal.

---

## 5. 10-K Decay (90-Day Expiry)
**What it does:** Forces re-audit of any TDO older than 90 days. SEC 10-K and 10-Q filings are the evidence base for the audit. Supply chain conditions can change materially within a fiscal quarter.

**Rule:** `created_at + 90 days` must not have passed at execution time.

**Enforcement:** `tdo_gate.py` Check 6. Computed against `tdo["created_at"]` (immutable from Scout emission).

**Rationale:** Named "10-K decay" because the audit evidence (SEC filings) has a natural quarterly refresh cycle. An audit performed against last quarter's 10-K is stale once a new filing is published. The 90-day window enforces re-validation on a similar cadence.

---

## 6. 24-Hour Contamination Gate
**What it does:** Prevents the Pulse module from executing on a thesis the same day Scout emitted it. This eliminates the risk of market-moving Scout activity (Exa searches, LLM synthesis calls) contaminating the same-day trading signal.

**Rule:** `execution_time - tdo["created_at"] ≥ 24 hours`.

**Enforcement:** `tdo_gate.py` Check 5.

**Rationale:** If Scout searches for "HBM4 bottleneck" at 09:00 and Pulse trades AMAT at 09:05, the search activity itself could constitute a signal loop. The 24h gate creates a clean separation between discovery and execution.

---

## 7. Bear-Regime Halt
**What it does:** Halts all Pulse execution when macro conditions indicate elevated systemic risk.

**Rule:** If `RegimeWatcher` returns `regime = BEAR` (VIX > ceiling AND SPY below 200-day SMA), `run_weekly_rebalance.py` exits before reaching the TDO gate.

**Enforcement:** `src/monitoring/regime_watcher.py` → `run_weekly_rebalance.py` regime check block.

**Rationale:** Supply chain bottleneck theses are long-vol, long-growth plays. In a BEAR regime, the correlation between supply chain scarcity and stock price breaks down — the market sells everything regardless of fundamental scarcity. Preserving capital takes precedence.

---

## 8. Tier-3 Visibility Limit
**What it does:** Caps the depth of supply chain graph traversal to prevent audit scope explosion and ensures SEC-verifiable sourcing.

**Rule:** The supply chain scraper only traverses relationships that are disclosed in SEC filings (10-K, 10-Q "risk factors" and "customers/suppliers" sections). Tier-1 = direct suppliers/customers. Tier-2 = their disclosed suppliers. Tier-3 = limit.

**Enforcement:** `auditor/supply_chain_scraper.py`. The scraper uses `sec_edgar_user_agent` and resolves CIK → filings → disclosed relationships. It does not attempt to reconstruct undisclosed Tier-4+ relationships.

**Rationale:** Undisclosed supply chain relationships are speculative. SEC-disclosed relationships carry legal accountability. Limiting to Tier-3 keeps the audit evidence base legally defensible and computationally tractable.

---

## 9. Liquidity Rule
**What it does:** Prevents execution when IBKR account margin is insufficient to fund the intended portfolio.

**Rule:** `available_funds` must be `> 0` and `≥ USD 1,000`.

**Enforcement:** `tdo_gate.py` Check 7. Only fires when `available_funds` is provided (non-`None`). In dry-run mode, `available_funds = None` → check skipped. In `--live` mode, `AccountMonitor.get_available_funds()` is called and passed to the gate.

**Rationale:** Executing a rebalance with insufficient margin risks forced liquidation by the broker. The $1,000 floor is a minimum position size floor, not a portfolio floor — it prevents fragment trades.

---

## 10. Kill Switch
**What it does:** Allows an operator to halt all Pulse execution immediately without modifying code.

**Rule:** `tdo_gate.py` checks `tdo.get("kill_switch_active", False)`. If `True`, execution is blocked.

**Enforcement:** `tdo_gate.py` Check 6. Can be set on any TDO JSON file manually.

**Rationale:** Emergency override for unexpected market events, regulatory notices, or audit discrepancies that require human review before execution resumes.

---

## Constraint Hierarchy
```
AI_RULES.md (highest authority — cannot be overridden programmatically)
  └── tdo_validator.py (schema + Red Team — runs at every phase read/write)
        └── tdo_gate.py (execution gate — runs immediately before order submission)
              └── regime_watcher.py (macro gate — runs before TDO gate)
```

Any constraint failure at any level halts the pipeline with `exit(1)` and logs a structured error.
