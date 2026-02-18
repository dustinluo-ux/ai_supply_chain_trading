# GeminiIntelligenceBridge — Design for Review

**Status:** Proposed (awaiting approval before implementation)  
**Canonical refs:** INDEX.md, AI_RULES.md, TECHNICAL_SPEC.md, STRATEGY_LOGIC.md  
**Legacy source (read-only):** `legacy/graveyard/src/signals/gemini_news_analyzer.py`, `legacy/graveyard/src/signals/gemini_analyzer.py`

---

## 1. Evidence Summary

| Claim | Evidence |
|-------|----------|
| Current NewsEngine flow | `src/signals/news_engine.py` L330–387: `compute_news_composite()` → `load_ticker_news()` → per-article FinBERT (`sentiment_finbert()` L86–108) → EventDetector → strategies A–D → composite. No LLM call. |
| Legacy supply-chain prompt | `legacy/graveyard/src/signals/gemini_news_analyzer.py` L266–324 `_create_supply_chain_prompt()`: asks for relationship (Supplier/Buyer/Neutral), supply_chain_health_score (-1..1), sentiment_score (-1..1), reasoning. Does **not** extract upstream/downstream entity names. |
| Legacy Gemini API usage | `legacy/graveyard/src/signals/gemini_analyzer.py` L51–54: `api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')`; L62–64: `genai.configure(api_key=...)`, `genai.GenerativeModel(model_name)`. |
| SentimentPropagator data source | `src/signals/sentiment_propagator.py` L62–79: uses `SupplyChainManager(db_path)`; relationships come only from `data/supply_chain_relationships.json`. No API today for session-scoped “discovered” links. |
| SupplyChainManager relationships | `src/data/supply_chain_manager.py` L346 `get_suppliers()`, L358 `get_customers()`, L379 `get_related_companies()` — all read from loaded JSON; no `add_discovered_link` or equivalent. |

---

## 2. Proposed Class Structure

### 2.1 New Module: `src/signals/llm_bridge.py`

**Purpose:** Single bridge to Google Gemini for “gated” deep analysis. No import from graveyard; logic recovered and adapted per AI_RULES §3 (Reuse-First: copy minimal logic into `src/`, adapt to canonical interfaces).

**Pydantic output schema (canonical contract):**

```python
# src/signals/llm_bridge.py

from pydantic import BaseModel
from typing import Literal

class DeepAnalysisOutput(BaseModel):
    sentiment: float                    # -1.0 to 1.0
    category: Literal[
        "SUPPLY_CHAIN_DISRUPTION",
        "DEMAND_SHOCK",
        "M&A",
        "MACRO"
    ]
    relationships: dict[str, list[str]]  # "upstream": ["Entity A", "Entity B"], "downstream": ["Entity C"]
    reasoning: str
```

**Class: `GeminiAnalyzer` (name chosen to match user request; lives in `llm_bridge.py` to avoid confusion with graveyard `gemini_analyzer.py`):**

| Member | Type | Description |
|--------|------|-------------|
| `__init__(self, api_key: str \| None = None, model: str \| None = None)` | — | `api_key` from arg or `GOOGLE_API_KEY` / `GEMINI_API_KEY` from env. `model` from arg or `config/strategy_params.yaml` → `llm_analysis.model`. |
| `deep_analyze(self, headline: str, text: str) -> DeepAnalysisOutput \| None` | method | Calls Gemini with structured prompt; returns Pydantic-validated object or `None` on failure/empty. |
| `_build_prompt(self, headline: str, text: str) -> str` | private | Builds prompt that asks for: sentiment (-1..1), category (enum), **upstream** (list of entity names), **downstream** (list of entity names), reasoning. “Upstream” = suppliers / inputs; “Downstream” = customers / outputs. |
| `_call_gemini(self, prompt: str) -> str` | private | Proxy bypass (legacy L22–27 in gemini_analyzer), `genai.configure` + `model.generate_content` with `response_mime_type="application/json"`; returns raw JSON string. |

**Recovery notes from legacy:**

- **Upstream/Downstream wording:** Legacy `_create_supply_chain_prompt` (L301–322) asks for “Relationship: Supplier/Buyer/Neutral” and scores. We extend to: “List **upstream** entities (suppliers, input providers) and **downstream** entities (customers, output recipients) mentioned in the article; use company or product names.”
- **Structured JSON:** Legacy uses free-form JSON; we enforce Pydantic so `relationships` always has keys `"upstream"` and `"downstream"` (lists of strings).

**Dependencies:** `google-generativeai`, `pydantic`. API key from env (no hardcoding); config from `get_config().get_param("strategy_params.llm_analysis.*")`.

---

### 2.2 NewsEngine Changes (Gated Logic)

**File:** `src/signals/news_engine.py`

**Current flow (unchanged until gate):**

1. `load_ticker_news(news_dir, ticker)`  
2. For each article: `sentiment_finbert(text)` → `articles_with_sentiment`  
3. EventDetector → `articles_with_events`  
4. Strategies A–D (buzz, surprise, sector, event)  
5. `sentiment_current`, `sentiment_baseline`, composite  

**Proposed addition: “The Gatekeeper” (after step 2, before or alongside Strategy B):**

- **FinBERT First:** Already true — every article is scored by local FinBERT (`sentiment_finbert()` L86–108).
- **Gate condition:** For the **ticker-week** (or per-article, see below), call Gemini **only if**:
  - **Option A (per article):** For any article, EventDetector or keyword heuristic labels it as “Supply Chain” **or** the absolute sentiment surprise for that article (vs baseline) exceeds a threshold.
  - **Option B (per ticker-week):** After computing `sentiment_current` and `sentiment_baseline`, compute surprise = current - baseline; if `abs(surprise) > threshold` **or** a simple “supply chain” keyword check on aggregated text, trigger Gemini on the **top 1–2 articles** (e.g. most recent or highest FinBERT variance).

**Recommended:** Option B (ticker-week gate) to limit API calls. Threshold from config: `llm_analysis.trigger_threshold` (e.g. 2.0). Interpret as **Z-score of surprise** if we have a rolling std of surprise; otherwise interpret as **absolute delta** in [0,1] space (e.g. threshold 0.2 → trigger if |current - baseline| > 0.2). Design choice: document “trigger_threshold: 2.0” as Z-score and compute Z using rolling mean/std of past surprises; if insufficient history, use absolute delta with a default cap.

**Modified `compute_news_composite` flow (high level):**

```
1. Load articles, dedupe.
2. FinBERT + EventDetector per article → articles_with_sentiment, articles_with_events.
3. Compute baseline/recent sentiment (current logic).
4. [NEW] Gate:
   - category_supply_chain = any article has supply-chain keyword or event hint (e.g. "supply chain", "supplier", "shortage", or EventDetector extended).
   - surprise = sentiment_current - sentiment_baseline; surprise_z = surprise / (rolling_std + 1e-6) if we have history else 0.
   - trigger_llm = llm_analysis.enabled and (category_supply_chain or abs(surprise) > trigger_threshold or abs(surprise_z) > 2.0).
5. If trigger_llm:
   - Select 1–2 articles (e.g. most recent, or max |sentiment - baseline|).
   - For each selected article: headline = title, text = description/content; call GeminiAnalyzer.deep_analyze(headline, text).
   - Merge result: e.g. use Gemini sentiment as override or blend with FinBERT; attach category and relationships.
   - [NEW_NETWORK_LINK] For each (upstream/downstream) entity in relationships not already in SupplyChainManager for this ticker, log or register as NEW_NETWORK_LINK (see §2.3).
6. Else: no Gemini call; use only FinBERT + strategies A–D.
7. Strategies A–D and composite as today; optionally blend Gemini sentiment when present.
```

**Return shape of `compute_news_composite`:** Extend the returned dict with optional keys when Gemini was used, e.g. `llm_category`, `llm_relationships`, `llm_reasoning`, `new_network_links` (list of {source_ticker, target_entity, direction: "upstream"|"downstream"}) so callers or SentimentPropagator can consume them.

---

### 2.3 Supply Chain Integration (NEW_NETWORK_LINK)

**Requirement:** If Gemini identifies a relationship **not** in `supply_chain_relationships.json`, log it for SentimentPropagator to use dynamically.

**Options:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Log only | Log structured NEW_NETWORK_LINK (ticker, entity name, direction) to logger and/or append to `compute_news_composite` return value. | No change to SupplyChainManager; no persistence. | SentimentPropagator cannot use it unless we pass through data_context. |
| B. Session-scoped in-memory store | Add `SupplyChainManager.add_discovered_link(ticker, target_entity, direction, source="gemini")` that stores in an in-memory dict for the run; `get_suppliers`/`get_customers` merge static JSON + discovered. | Propagator can use new links in same run without schema change. | Manager stateful; need one manager per run or clear after run. |
| C. Return in composite; propagator accepts optional “extra_links” | `compute_news_composite` returns `new_network_links: list[dict]`. SignalEngine passes these into SentimentPropagator (e.g. `propagator.propagate(news_item, discovered_links=...)`). Propagator uses discovered_links for this ticker when building graph. | No change to SupplyChainManager; explicit data flow. | Propagator interface gains an optional argument. |

**Recommendation:** **C** for minimal surface and clear data flow. NEW_NETWORK_LINK is “entities mentioned by Gemini not in DB”; we pass them as `discovered_links` into the propagation step so the same run can propagate along both static and discovered edges. Logging (Option A) in addition for audit.

**Entity name → ticker:** Gemini returns entity **names** (e.g. “Taiwan Semiconductor”). We need to map to tickers (e.g. TSM) for propagation. Options: (1) simple name→ticker map in config or code for known names; (2) leave as names and let propagator match by name in DB; (3) log as name only for this design and add ticker resolution in a follow-up. For the design, **output and pass through “entity names”**; ticker resolution can be a later enhancement.

---

## 3. YAML Configuration

**File:** `config/strategy_params.yaml`

**Add block:**

```yaml
llm_analysis:
  enabled: true
  provider: "google"
  model: "gemini-2.0-flash"   # Low latency, high reasoning
  trigger_threshold: 2.0      # Z-score surprise threshold (or absolute delta; see §2.2)
```

**Loading:** `src/signals/news_engine.py` and `src/signals/llm_bridge.py` use `get_config().get_param("strategy_params.llm_analysis.enabled")`, etc. No new config file; AI_RULES §10: strategy params live in `strategy_params.yaml`.

---

## 4. Interface Impact

| Item | Impact |
|------|--------|
| `compute_news_composite()` return dict | **PROPOSED:** Add optional keys: `llm_category`, `llm_relationships`, `llm_reasoning`, `new_network_links`. Existing keys unchanged. |
| `SentimentPropagator.propagate()` | **PROPOSED:** Optional `discovered_links: list[dict] | None = None` (each dict: e.g. `{"direction": "upstream"|"downstream", "entity": str}`). Backward compatible. |
| New module `src/signals/llm_bridge.py` | New; no existing callers. |
| `config/strategy_params.yaml` | Add `llm_analysis` block. |

**Per AI_RULES §5:** Interface impact is PROPOSED; approval required before implementation.

---

## 5. Files to Touch (Implementation Phase)

| File | Action |
|------|--------|
| `src/signals/llm_bridge.py` | **Create:** GeminiAnalyzer, DeepAnalysisOutput, prompt + Gemini call, Pydantic validation. |
| `src/signals/news_engine.py` | **Modify:** Gate logic; optional call to GeminiAnalyzer; merge result; NEW_NETWORK_LINK collection; extend return dict. |
| `src/signals/sentiment_propagator.py` | **Modify:** Optional `discovered_links` in `propagate()`; use discovered links when building graph for this run. |
| `config/strategy_params.yaml` | **Modify:** Add `llm_analysis` section. |
| `docs/SYSTEM_MAP.md` | **Update:** Register `llm_bridge.py` under Stage 2 (Signals). |
| `docs/TECHNICAL_SPEC.md` or `docs/STRATEGY_LOGIC.md` | **Update:** Short subsection on Gated LLM (FinBERT first, gate, NEW_NETWORK_LINK). |

---

## 6. Validation (After Implementation)

- Unit test: `GeminiAnalyzer.deep_analyze(headline, text)` with a mock or fixture returns `DeepAnalysisOutput` with valid category and relationships.
- Unit test: Gate: with `enabled=true` and high surprise, `compute_news_composite` returns `llm_category` / `llm_relationships` when Gemini is called; with `enabled=false` or low surprise, no Gemini call and no new keys (or keys absent).
- Integration: Run backtest with `llm_analysis.enabled: false` → no behavior change. With `enabled: true` and a ticker that has supply-chain news, confirm one Gemini call when threshold exceeded and log NEW_NETWORK_LINK when entity not in DB.
- No import from `graveyard/` or `legacy/`.

---

## 7. Summary

- **GeminiAnalyzer** in `src/signals/llm_bridge.py`: `deep_analyze(headline, text)` → Pydantic `DeepAnalysisOutput` (sentiment, category, relationships {upstream, downstream}, reasoning). API key from env; model/trigger from `strategy_params.yaml`.
- **NewsEngine:** FinBERT first; gate on supply-chain category or sentiment surprise (configurable); on trigger, call Gemini on 1–2 articles; merge result; collect NEW_NETWORK_LINK for entities not in DB; extend return dict.
- **SentimentPropagator:** Optional `discovered_links` in `propagate()` so propagation can use Gemini-discovered upstream/downstream in the same run.
- **Config:** `strategy_params.yaml` gains `llm_analysis.enabled`, `provider`, `model`, `trigger_threshold`.

If this design is approved, next step is implementation per §5 and validation per §6.
