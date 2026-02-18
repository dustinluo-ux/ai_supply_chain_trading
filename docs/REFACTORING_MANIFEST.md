# Refactoring Manifest — Un-Ghost Legacy Supply Chain & Centralize Config

**Date:** 2026-02-16  
**Goal:** Transition from backtest-only to live-ready spine; centralize constants; no code deleted without evidence.

**Constraints:** Evidence discipline; backtest compatibility; modular file-by-file changes.  
**Reference:** INDEX.md, AI_RULES.md, local `data/` context.

---

## 1. Semantic Search & Recovery (The Graveyard)

### 1.1 Legacy / Commented Code: Google Generative AI & Gemini

| Location | What Exists | Evidence |
|----------|-------------|----------|
| `graveyard/src/signals/gemini_analyzer.py` | **GeminiAnalyzer**: `google.generativeai` (genai), proxy bypass, supply chain extraction prompt (supplier, customer_type, product, ai_related, sentiment, relevance_score). Uses `GEMINI_API_KEY` or `GOOGLE_API_KEY` from env. | L17–22, L30–62, L68–115, L119–195 |
| `graveyard/src/signals/gemini_news_analyzer.py` | **GeminiNewsAnalyzer**: Wraps Gemini for news scoring; JSON cache; `google.generativeai` import and GenerationConfig. | L15–16, L406, L425 |
| `graveyard/src/signals/llm_analyzer.py` | **LLMAnalyzer**: Dual provider (FinBERT + Gemini); supply chain extraction; raises if `google-generativeai` missing. | L55 |
| `graveyard/scripts/test_llm_supply_chain_knowledge.py` | Test script: `genai.configure(api_key=os.getenv('GEMINI_API_KEY'))`, Gemini 2.5 Flash Lite. | L8, L55–60 |
| `graveyard/scripts/test_gemini_connection.py` | Connection test: `os.getenv('GEMINI_API_KEY')`, proxy pop/restore, Gemini 2.0 Flash. | L45–58, L96–97 |
| `graveyard/scripts/test_gemini.py` | dotenv load; `os.getenv('GEMINI_API_KEY')`. | L34–38 |

**Summary:** No `vertexai` references. All Gemini usage is `google.generativeai` in graveyard. **No active `src/` code imports Gemini**; live path uses FinBERT + `SentimentPropagator` only.

### 1.2 Upstream / Downstream Entity Extraction

| Location | Logic | Evidence |
|----------|--------|----------|
| `graveyard/src/signals/gemini_analyzer.py` | **LLM extraction** (no Spacy): Prompt asks for `supplier`, `customer_type`, `product` from article text. Not “upstream/downstream” by name; semantically supplier = upstream, customer = downstream. | L68–115 `_create_prompt`, L119+ `analyze_article` |
| `graveyard/src/signals/llm_analyzer.py` | Same: supply chain extraction via Gemini; `_default_extraction()` with supplier/customer/product. | L114–120, L195–241 |
| `graveyard/src/signals/supply_chain_scanner.py` | Batch processing: `process_article()` → LLM extraction → `supplier`, `customer`; writes `*_extractions.json` and `supply_chain_mentions.csv`. | L52–71, L79–108, L246–269 |
| `src/signals/news_engine.py` | **Spacy** used only for **EventDetector** (Earnings, M&A, Lawsuit, FDA, CEO), not for supply chain entity extraction. | L4, L110–162, L419+ `strategy_event_priority` |

**Summary:** “Upstream/downstream” extraction lives in **graveyard** (Gemini prompts: supplier/customer/product). Active pipeline uses **supply_chain_relationships.json** (SEC/Apple list) and **SentimentPropagator**; no LLM extraction in `src/` for live path.

### 1.3 SentimentPropagator ↔ supply_chain_relationships.json

| Component | Link | Evidence |
|-----------|------|----------|
| **SentimentPropagator** | `SupplyChainManager(db_path)` default `db_path='data/supply_chain_relationships.json'`. | `src/signals/sentiment_propagator.py` L64, L78 |
| **SupplyChainManager** | Loads JSON from `db_path`; `relationships` key = ticker → suppliers/customers/competitors. | `src/data/supply_chain_manager.py` L34–50 |
| **SignalEngine** | Lazy-inits `SentimentPropagator()` with no args → uses default db path. | `src/signals/signal_engine.py` L52–54 |
| **Config** | `strategy_params.propagation` has `tier_1_weight`, `tier_2_weight`, `blend_factor`, `enabled`. **Only `blend_factor`** is read in signal_engine; **tier weights are not** passed to SentimentPropagator (it uses constructor defaults 0.5 / 0.2). | `config/strategy_params.yaml` L4–9; `signal_engine.py` L437 |

**Conclusion:** Propagator is correctly linked to `supply_chain_relationships.json`. Tier weights in YAML are **not** yet wired into SentimentPropagator (refactor opportunity).

---

## 2. Configuration Centralization (YAML Consolidation)

### 2.1 Constants to Move from `src/signals/news_engine.py`

| Constant | Current Value | Proposed YAML Key |
|----------|----------------|-------------------|
| `DEDUP_SIMILARITY_THRESHOLD` | 0.85 | `strategy_params.deduplication.similarity_threshold` |
| `SENTIMENT_BASELINE_DAYS` | 30 | `strategy_params.sentiment.baseline_days` |
| `EVENT_PRIORITY_HOURS` | 48 | `strategy_params.sentiment.event_priority_hours` |
| Strategy B “cold start” min obs (currently 1) | 1 | `strategy_params.sentiment.min_baseline_obs` (optional) |
| Strategy C `top_pct` (0.10) | 0.10 | `strategy_params.sentiment.sector_top_pct` (optional) |

**File to modify:** `src/signals/news_engine.py` — replace module-level constants with `get_config().get_param("strategy_params....", default)` (or inject config). Keep defaults in code for backward compatibility if key missing.

### 2.2 Constants to Move from `src/signals/signal_engine.py`

| Constant | Current Usage | Proposed YAML Key |
|----------|----------------|-------------------|
| Neutral default 0.5 | Multiple fallbacks | Leave as literal (semantic “neutral”); no move. |
| (None) | — | **Wire** `strategy_params.propagation.tier_1_weight` and `tier_2_weight` into `SentimentPropagator` construction in signal_engine. |

**File to modify:** `src/signals/signal_engine.py` — when creating `SentimentPropagator()`, pass `tier1_weight` and `tier2_weight` from `get_config().get_param("strategy_params.propagation.tier_1_weight", 0.5)` (and tier_2_weight 0.2). Optional: pass `db_path` from config.

### 2.3 Constants in `src/signals/sentiment_propagator.py`

| Constant | Current | Proposed |
|----------|---------|----------|
| `db_path` | `'data/supply_chain_relationships.json'` | Keep default; allow override from config (e.g. `strategy_params.propagation.db_path`) when provided by caller. |
| `tier1_weight` | 0.5 | Set by **caller** (signal_engine) from `strategy_params.propagation.tier_1_weight`. |
| `tier2_weight` | 0.2 | Set by **caller** from `strategy_params.propagation.tier_2_weight`. |

**File to modify:** `src/signals/sentiment_propagator.py` — accept optional `tier1_weight`/`tier2_weight` (and optionally `db_path`) so signal_engine can pass config values. No hardcoded keys inside propagator if we pass in.

### 2.4 New Sections in `config/strategy_params.yaml`

Add (or extend) under `strategy_params`:

```yaml
# strategy_params.yaml (add)

sentiment:
  baseline_days: 30
  event_priority_hours: 48
  min_baseline_obs: 1
  sector_top_pct: 0.10

deduplication:
  similarity_threshold: 0.85
```

`propagation` already has `tier_1_weight`, `tier_2_weight`, `blend_factor`, `enabled`. Optionally add `db_path: "data/supply_chain_relationships.json"`.

---

## 3. Supply Chain “Live” Preparation

### 3.1 NewsEngine and “Supply Chain Switch”

- **Current:** `src/signals/news_engine.py` has **no** “Supply Chain Switch” or partner-ticker logic. It computes FinBERT sentiment, buzz, surprise, sector-relative, event priority; **SentimentPropagator** runs in **signal_engine** after news composite, using **relationship map** (supply_chain_relationships.json) and **sentiment_current** per ticker. Propagation is “from ticker with news → related tickers” by graph, not “if headline mentions partner then propagate.”
- **Gap:** To support “if headline mentions a partner ticker from the relationship map, propagate sentiment by strategy_params weights,” one would either: (a) add optional LLM/entity step (e.g. restore Gemini path or use Spacy NER + ticker match) to detect mentioned entities and map to relationship map, or (b) keep current design (propagate by graph from each ticker with news). The manifest does **not** implement (a); it only ensures **config weights** (tier_1, tier_2, blend) are used so that when propagation runs, it uses YAML.

### 3.2 extractions.json in data/

- **Search:** `data/**/extractions*.json` → **0 files** in `data/`.
- **Graveyard:** `graveyard/scripts/check_supply_chain_ranking.py` and `supply_chain_scanner.py` expect `*_extractions.json` in a data dir (e.g. `data_dir.glob("*_extractions.json")`), produced by **SupplyChainScanner** (graveyard) when running LLM extraction. Current project does **not** run that pipeline; hence no extractions.json in `data/`.
- **Format (from graveyard):** Each extraction has `supplier`, `customer`, `product`, `ai_related`, `sentiment`, `relevance_score`, `article_url`, `article_date`, `ticker`, etc. For “live” supply chain switch using extractions, one would need to (1) run an extraction step (e.g. restore/adapt Gemini or use precomputed extractions) and (2) feed that into propagation or into news_engine. **Out of scope for this manifest** except to note: no extractions exist yet; format is documented in graveyard.

---

## 4. Environment & Security Sweep

### 4.1 Hardcoded API Keys / Sensitive Strings

| Scope | Result |
|-------|--------|
| **Active `src/`** | No hardcoded API keys or long secrets found. `src/signals/metrics.py` hit on “risk-free” (false positive). |
| **Graveyard** | Gemini/Google: `api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')`. Marketaux: `os.getenv("MARKETAUX_API_KEY")`. Hugging Face: `os.getenv('HF_TOKEN')` / `HUGGINGFACE_HUB_TOKEN`. All use env, not literals. |
| **Scripts (active)** | `scripts/verify_determinism.py` uses `os.environ.copy()`. `src/utils/client_id_rotation.py` uses `os.environ.get("IBKR_CLIENT_ID_START", ...)`. `src/utils/yfinance_cache_init.py` uses `os.environ.get("YFINANCE_CACHE_DIR")`. No keys in repo. |

### 4.2 .env Consolidation

| File | Purpose |
|------|---------|
| `.env` | Present (root); not read by most of `src/` (no dotenv in signal_engine/news_engine). |
| `.env.example` | Present. |
| `.env.template` | Present (graveyard references); `graveyard/setup_env.py` creates .env from template. |

**Recommendation:** Document in one place (e.g. README or docs) that all runtime keys must live in `.env` and be read via `os.getenv()` or a small loader. ConfigManager does **not** load .env; if any active code needs API keys, use `os.getenv("KEY")` and document the key name in `.env.example`. No hardcoded keys to remove in active code.

---

## 5. Files to Modify (Summary)

| # | File | Change |
|---|------|--------|
| 1 | `config/strategy_params.yaml` | Add `sentiment` (baseline_days, event_priority_hours, min_baseline_obs, sector_top_pct) and `deduplication` (similarity_threshold). Optionally add `propagation.db_path`. |
| 2 | `src/signals/news_engine.py` | Replace `DEDUP_SIMILARITY_THRESHOLD`, `SENTIMENT_BASELINE_DAYS`, `EVENT_PRIORITY_HOURS` with ConfigManager lookups (with same defaults). |
| 3 | `src/signals/signal_engine.py` | In `_get_propagator()`, read `strategy_params.propagation.tier_1_weight` and `tier_2_weight` (and optionally `db_path`); pass into `SentimentPropagator(...)`. |
| 4 | `src/signals/sentiment_propagator.py` | Constructor: accept optional `tier1_weight`, `tier2_weight`, `db_path` (defaults 0.5, 0.2, current path) so signal_engine can inject config. |

**Not modified in this refactor:**  
- Graveyard (no un-ghosting of Gemini into `src/` in this pass).  
- Backtest script (no change except possibly env if we add dotenv for keys later).  
- New NewsEngine “headline mentions partner” logic (deferred).

---

## 6. Legacy Code Recovered (No Delete Without Summary)

- **gemini_analyzer.py** (graveyard): Full Gemini 2.5 Flash Lite integration; supply chain extraction prompt (supplier, customer_type, product, ai_related, sentiment, relevance_score); JSON validation; proxy bypass.  
- **gemini_news_analyzer.py** (graveyard): News scoring + caching; uses Gemini.  
- **llm_analyzer.py** (graveyard): FinBERT + Gemini dual path; supply chain extraction.  
- **supply_chain_scanner.py** (graveyard): Batch LLM extraction → `*_extractions.json` and `supply_chain_mentions.csv`.  
- **news_analyzer.py** (graveyard): Wrapper: GeminiNewsAnalyzer + SentimentPropagator with configurable tier weights.

To “un-ghost” for a live LLM path later: restore or adapt one of the graveyard analyzers behind a feature flag and feed its output into propagation or news composite; keep FinBERT as default.

---

## 7. Next Step

**Before applying changes:** This manifest is the agreed plan.  
**After approval:** Apply changes file-by-file (strategy_params.yaml → news_engine → sentiment_propagator → signal_engine), then run existing backtest to ensure compatibility.
