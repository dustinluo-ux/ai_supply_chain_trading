# Architectural Blueprint: Dynamic Universe Expansion

**Source of truth:** INDEX.md, Verified Requirement Table (Signal Engine L160–L310, Propagator L253–L327)  
**Doctrine:** Evidence Discipline. Every action preceded by non-destructive investigation. No fire-and-forget logic; verification explicit.  
**Status:** Blueprint for approval — no file modifications until approved.

---

## 1. Research: Current Handling

### 1.1 Signal Engine — `src/signals/signal_engine.py`

**`_generate_backtest` flow (L84–321):**

| Section | Lines | Evidence |
|--------|--------|----------|
| Entry / locals | 96–118 | `prices_dict`, `news_dir`, `enable_propagation`, etc. from `data_context`. |
| Regime resolution | 119–155 | Optional; does not touch `enriched_composites`. |
| **Initialization block** | **157–164** | `week_scores`, `atr_norms`, `buzz_by_ticker`, **`enriched_composites: dict[str, float] = {}`**, then `cached`. |
| Phase 1 | 166–234 | Loop over `universe`; populate `cached[t]` with `row`, `news_composite`, `sentiment_current`, `new_network_links`. No assignment to `enriched_composites`. |
| Phase 2 | 245–293 | **Conditional:** `if enable_propagation and news_dir is not None` → call `_propagate_sentiments(...)` → **assign** `enriched_composites, propagated_targets = ...`. Then extend universe and optionally load new tickers into `cached`. |
| Phase 3 | 295–321 | Loop `for t in extended_universe`; **read** `enriched_composites.get(t, entry.get("news_composite"))` at L310. |

**Branches that affect `enriched_composites`:**
- **Propagation off or no news_dir:** Phase 2 block is skipped. `enriched_composites` is never reassigned; it remains the empty dict from L160. Phase 3 still runs and uses `enriched_composites.get(t, ...)`, which is safe.
- **Propagation on:** Phase 2 assigns `enriched_composites` from `_propagate_sentiments`. Phase 3 uses that dict (and falls back to `entry.get("news_composite")` when key missing).

**Conclusion:** With the current L160 initialization, there is no NameError: `enriched_composites` is always bound at method entry and is either `{}` or the return value from `_propagate_sentiments`. The verified requirement (init at L160) is already satisfied.

---

### 1.2 Sentiment Propagator — `src/signals/sentiment_propagator.py`

**Relevant symbols:**

| Symbol | Lines | Role |
|--------|--------|------|
| `propagate(news_item, discovered_links, valid_tickers)` | 126–171 | Entry for propagation; passes `valid_tickers` into `_get_relationships`. |
| `_get_relationships(ticker, discovered_links, valid_tickers)` | 288–339 | Merges static DB relationships with `discovered_links`; for each link calls `_resolve_entity_to_ticker(entity, valid_tickers)` and logs mapping. |
| `_normalize_entity_name(entity)` | 253–260 | Static. Strips suffixes (INC, CORP, CO, LLC, etc.) and trailing punctuation; returns uppercase. |
| `_resolve_entity_to_ticker(entity, valid_tickers)` | 262–286 | Static. Reads `strategy_params.llm_analysis.entity_ticker_map`; then checks normalized name in `valid_tickers`; returns uppercase ticker or normalized string. |

**Data flow:** LLM → `new_network_links` (in `cached`) → `discovered_links` in `propagate()` → `_get_relationships(..., discovered_links, valid_tickers)` → per link: `entity` → `_normalize_entity_name` → `_resolve_entity_to_ticker` → `resolved_ticker` → `PropagatedSignal(ticker=resolved_ticker)` → consumed by Signal Engine as `propagated_targets`.

---

## 2. Plan: Fail-Safe Initialization for `enriched_composites`

**Requirement:** Prevent NameErrors in multi-branch logic regardless of propagation or exception paths.

**Current state (evidence):** At L160 in `_generate_backtest` the code already has:

```text
enriched_composites: dict[str, float] = {}
```

**Blueprint rule (no change if already present):**
- **Placement:** In the same initialization block as `week_scores`, `atr_norms`, `buzz_by_ticker` (i.e. at method entry, before Phase 1).
- **Invariant:** Before Phase 3 runs, `enriched_composites` must always be a dict (possibly empty). Phase 3 must never assume it was assigned only inside the `if enable_propagation and news_dir` block.
- **Verification:** Grep for all references to `enriched_composites` in `_generate_backtest`; confirm the only assignments are (1) the initial `= {}` and (2) the unpack from `_propagate_sentiments` inside the conditional. All reads (e.g. `.get(t, ...)`) are then safe.

**Action:** Confirm L160 contains the above line. No further code change required for this item if confirmed.

---

## 3. Bridge Logic: Dynamic Expansion Protocol (Phase 2)

**Objective:** Any ticker discovered by the LLM (via propagation) that is not in the initial `universe` may be promoted into the scoring universe **only** after verification that a price CSV exists for that ticker. Verification is the single gate for inclusion.

**Source of verification:** `src/data/csv_provider.py` — `find_csv_path(data_dir: Path, ticker: str) -> Path | None`. Searches subdirs `nasdaq/csv`, `sp500/csv`, `nyse/csv`, `forbes2000/csv` for `{ticker}.csv`; returns first match or `None`.

**Protocol (step-by-step):**

1. **Inputs**
   - `universe`: initial ticker list (e.g. from `--tickers` or config).
   - `enriched_composites`, `propagated_targets` = `_propagate_sentiments(universe, cached, valid_tickers=set(prices_dict.keys()))`.
   - `data_dir`: from `load_data_config().get("data_dir")` (or fallback), type `Path`.

2. **Extended universe**
   - Start: `extended_universe = list(universe)`.
   - For each `target` in `propagated_targets`:
     - If `target` is already in `universe`, skip (no expansion).
     - Normalize: `ticker_upper = target.upper()`.
     - **Verification gate:** Call `find_csv_path(data_dir, ticker_upper)`.
     - If result is `None`, do **not** add to `extended_universe` or `cached`; skip.
     - If result is a `Path`, then:
       - Add `ticker_upper` to `extended_universe` (with deduplication, e.g. an `added_new` set).
       - If `ticker_upper not in cached`, load price data (e.g. `load_prices(data_dir, [ticker_upper])`), compute indicators, and insert into `cached` and `prices_dict` so Phase 3 can score this ticker.

3. **Invariants**
   - No ticker is appended to `extended_universe` unless `find_csv_path(data_dir, ticker_upper)` has returned a path.
   - No ticker is added to `cached` for scoring unless it has passed the same CSV check and load/indicator steps succeeded.

4. **Current implementation (evidence):** L255–268 use `find_csv_path(data_dir, ticker_upper)`; the `continue` when it is `None` (L266) enforces the gate. L268–293 add to `extended_universe` and then to `cached` only after the gate. Blueprint is aligned with current behavior; any future change must preserve the “verify CSV before inclusion” rule.

---

## 4. Normalization: "NVIDIA Corp" → "NVDA" via `entity_ticker_map`

**Goal:** Map LLM-reported entity names (e.g. "NVIDIA Corp") to exchange ticker symbols (e.g. "NVDA") so that propagation and CSV verification use the same symbol.

**Config source:** `config/strategy_params.yaml` — under `llm_analysis`:

```yaml
entity_ticker_map: {}   # e.g. { "NVIDIA": "NVDA", "Taiwan Semiconductor": "TSM" }
```

**Flow (evidence: Propagator L253–L327):**

1. **LLM output**  
   Discovered link contains e.g. `target_entity: "NVIDIA Corp"` (or `entity`).  
   Source: NewsEngine → `compute_news_composite` → `new_network_links` → `cached[t]["new_network_links"]`.

2. **Propagator**  
   In `_get_relationships(..., discovered_links, valid_tickers)`:
   - For each link, read `entity = link.get("entity") or link.get("target_entity") or ""`.
   - **Normalize:** `_normalize_entity_name(entity)` (L253–260):
     - Strip, uppercase.
     - Remove trailing suffixes: ` INC.`, ` INC`, ` CORP.`, ` CORP`, ` CO.`, ` CO`, `, LLC`, ` LLC`, `.`, and trailing `,.\-`.
     - Example: `"NVIDIA Corp"` → `"NVIDIA"`.
   - **Resolve:** `_resolve_entity_to_ticker(entity, valid_tickers)` (L262–286):
     - Load `entity_map = get_config().get_param("strategy_params.llm_analysis.entity_ticker_map", None) or {}`.
     - `normalized = _normalize_entity_name(entity)` (e.g. `"NVIDIA"`).
     - Lookup order: `entity_map.get(normalized)`, then `entity_map.get(normalized.title())`, then `entity_map.get(entity.strip())`.
     - If a string value is found (e.g. `"NVDA"`), return `resolved.strip().upper()`.
     - Else if `valid_tickers` and `normalized.upper()` in `valid_tickers`, return `normalized.upper()`.
     - Else return `normalized.upper()` (caller may later filter by CSV).
   - **Log:** `logger.debug("Mapped '%s' to '%s'", entity.strip(), resolved_ticker)` (L327).
   - Use `resolved_ticker` in relationship records (suppliers/customers); propagation then produces `PropagatedSignal(ticker=resolved_ticker)`.

3. **Example for "NVIDIA Corp" → "NVDA"**
   - Config: `entity_ticker_map: { "NVIDIA": "NVDA" }`.
   - `_normalize_entity_name("NVIDIA Corp")` → `"NVIDIA"`.
   - `_resolve_entity_to_ticker("NVIDIA Corp", valid_tickers)` → `entity_map.get("NVIDIA")` → `"NVDA"` → return `"NVDA"`.
   - Log: `Mapped 'NVIDIA Corp' to 'NVDA'`.
   - Downstream: Signal Engine receives `propagated_targets` containing `"NVDA"`; Phase 2 then verifies `find_csv_path(data_dir, "NVDA")` and, if present, adds to `extended_universe` and `cached`.

**Blueprint rule:** To support "NVIDIA Corp" → "NVDA", the project must set in `config/strategy_params.yaml` under `llm_analysis` at least:

```yaml
entity_ticker_map:
  "NVIDIA": "NVDA"
  # "Taiwan Semiconductor": "TSM"  # optional
```

No code change is required for this mapping; only config population. The Propagator already uses `entity_ticker_map` and logs all mappings at DEBUG.

---

## 5. Verified Requirement Table (Reference)

| Component | Location | Requirement |
|-----------|----------|-------------|
| Signal Engine | L160 | `enriched_composites: dict[str, float] = {}` at method entry. |
| Signal Engine | L249–293 | Phase 2: `extended_universe`; promote only after `find_csv_path(data_dir, ticker_upper)` succeeds. |
| Signal Engine | L300–310 | Phase 3: iterate `for t in extended_universe`; use `enriched_composites.get(t, entry.get("news_composite"))`. |
| Propagator | L253–260 | `_normalize_entity_name`: strip corporate suffixes and punctuation. |
| Propagator | L262–286 | `_resolve_entity_to_ticker`: config `entity_ticker_map` then `valid_tickers`. |
| Propagator | L311–327 | `_get_relationships`: for each discovered link, resolve entity → ticker; log `Mapped 'entity' to 'ticker'`. |
| Config | strategy_params.yaml | `llm_analysis.entity_ticker_map` (optional dict). |
| CSV verification | csv_provider | `find_csv_path(data_dir, ticker)` — single source of truth for “CSV exists”. |

---

## 6. Summary

- **Research:** `enriched_composites` is initialized at L160 and is either left as `{}` or set by `_propagate_sentiments`; Phase 3 reads it safely. Propagator normalizes and resolves entity names and logs mappings.
- **Plan:** Keep fail-safe init at L160; no change needed if already present.
- **Bridge:** Dynamic expansion in Phase 2 must use `find_csv_path` as the only gate for adding a discovered ticker to `extended_universe` and `cached`; current code already does this.
- **Normalization:** "NVIDIA Corp" → "NVDA" is achieved by setting `entity_ticker_map: { "NVIDIA": "NVDA" }` in `config/strategy_params.yaml`; resolution and debug logging are already implemented in the Propagator.

**No file modifications are proposed in this blueprint.** Implementation is already aligned with the above. Pending your approval, the only optional step is to add example entries to `entity_ticker_map` in config if you want those mappings active.
