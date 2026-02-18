# Gemini Bridge Activation Plan — Phase 2 Intelligence Expansion

**Last Updated:** 2026-02-15  
**References:** INDEX.md, GEMINI_BRIDGE_DESIGN.md, PROJECT_STATUS.md  
**Evidence rule:** All claims cite file path and symbol or doc.

This plan enables **Intelligence-Driven** rebalancing by activating the GeminiBridge per GEMINI_BRIDGE_DESIGN.md. Goal: step-by-step implementation so the next weekly rebalance can use Gemini-driven analysis with safe fallback.

---

## 1. Configuration Audit

**File:** `config/strategy_params.yaml`

**Current state (evidence):**
- `config/strategy_params.yaml` L13–18: block `llm_analysis` exists with `enabled: false`, `provider: "google"`, `model: "gemini-2.0-flash"`, `trigger_threshold: 0.2`.
- Design doc (GEMINI_BRIDGE_DESIGN.md §3) proposes `enabled: true` and `trigger_threshold: 2.0` (Z-score); code interprets threshold as **absolute sentiment delta** in [0,1] (news_engine.py L522–523, L529).

**Proposed changes:**

| Change | Value | Rationale |
|--------|--------|-----------|
| `llm_analysis.enabled` | `true` | Turn on gated Gemini path for rebalance. |
| `llm_analysis.trigger_threshold` | Keep `0.2` or set `0.15`–`0.25` | Code uses **absolute delta**: trigger when \|sentiment_current − sentiment_baseline\| > threshold (news_engine.py L523, L529). Design’s “2.0” is Z-score; current implementation uses delta. 0.2 = trigger on 20% sentiment move vs baseline; lower = more triggers (more API calls). |

**Optional (no code change):**
- Add a short comment in `strategy_params.yaml`: `# absolute delta in [0,1]; trigger when |current - baseline| > this (see GEMINI_BRIDGE_DESIGN.md §2.2)`.

**Pre-flight:**
- Ensure `GOOGLE_API_KEY` or `GEMINI_API_KEY` is set in `.env` (llm_bridge.py L76; design §2.1).
- Ensure `google-genai` and `pydantic` are in `requirements.txt` (llm_bridge.py L71–74, L76–79).

---

## 2. Logic Flow Verification

**Path:** NewsEngine → gate → GeminiAnalyzer → return dict → SignalEngine → SentimentPropagator → PortfolioEngine.

### 2.1 NewsEngine gate and Gemini call

| Step | Location | Evidence |
|------|----------|----------|
| 1 | Load articles, FinBERT, baseline/current | `src/signals/news_engine.py` `compute_news_composite()` L451–513 (load_ticker_news, sentiment_finbert, strategies, sentiment_baseline/sentiment_current). |
| 2 | Gate condition | L521–529: `llm_enabled = cfg.get_param("strategy_params.llm_analysis.enabled", False)`; `trigger_threshold = cfg.get_param("strategy_params.llm_analysis.trigger_threshold", 0.2)`; `surprise_abs = abs(sentiment_current - sentiment_baseline)`; `supply_chain_keyword` = any of "supply chain", "supplier", "shortage", "supply disruption" in aggregated text; `trigger_llm = llm_enabled and (supply_chain_keyword or surprise_abs > trigger_threshold)`. |
| 3 | On trigger: select articles, call Gemini | L529–555: select up to 2 articles by priority `_article_priority` (max \|sentiment − baseline\|); `from src.signals.llm_bridge import GeminiAnalyzer`; `analyzer = GeminiAnalyzer()`; for each selected article `analyzer.deep_analyze(headline, text)`; on non-None result set `llm_category`, `llm_sentiment`, `llm_relationships`, `llm_reasoning`, append to `new_network_links` (upstream/downstream). |
| 4 | Return shape | L561–575: dict includes `llm_category`, `llm_sentiment`, `llm_relationships`, `llm_reasoning`, `new_network_links` (and existing keys news_composite, sentiment_current, etc.). |

So when a **sentiment anomaly** is detected (supply-chain keyword **or** \|current − baseline\| > trigger_threshold), the NewsEngine triggers Gemini on 1–2 articles and attaches LLM outputs and new_network_links to the composite result.

### 2.2 SignalEngine → Propagator

| Step | Location | Evidence |
|------|----------|----------|
| 1 | Cache news result per ticker | `src/signals/signal_engine.py` L211–231: `r = compute_news_composite(...)`; `cached[t]["new_network_links"] = r.get("new_network_links", []) or []`. |
| 2 | Propagation phase | L248–252: `enriched_composites = self._propagate_sentiments(universe, cached)` when `enable_propagation` and `news_dir` are set. |
| 3 | Pass discovered_links into propagator | L432–433: `discovered_links = entry.get("new_network_links") or None`; `signals = propagator.propagate(news_item, discovered_links=discovered_links)`. |

So **intelligence signals** (Gemini’s new_network_links) are passed into SentimentPropagator as `discovered_links` for the primary ticker.

### 2.3 SentimentPropagator → enriched composites

| Step | Location | Evidence |
|------|----------|----------|
| 1 | propagate() accepts discovered_links | `src/signals/sentiment_propagator.py` L125–128, L135: `propagate(news_item, discovered_links=...)`; used only for primary ticker. |
| 2 | Merge with static DB | L160–162: `use_discovered = links_for_primary if (current_ticker == primary_ticker) else None`; `relationships = self._get_relationships(current_ticker, discovered_links=use_discovered)`. |
| 3 | _get_relationships merges links | L264–278: for each `discovered_links` item, `direction` → suppliers (upstream) or customers (downstream); `entity` or `target_entity` used as ticker/name (matches news_engine’s `target_entity`). |
| 4 | Propagated signals → enriched composite | signal_engine.py L448–461: for each target ticker, average propagated sentiment, blend with base: `enriched_val = (1.0 - blend_factor) * base + blend_factor * prop_unipolar`. |

So Propagator receives **intelligence** via `discovered_links` (new_network_links from Gemini), merges them with static supply chain DB in `_get_relationships`, and produces propagated signals that SignalEngine blends into **enriched_composites**.

### 2.4 Enriched composites → target weights

| Step | Location | Evidence |
|------|----------|----------|
| 1 | Use enriched composite in final score | `src/signals/signal_engine.py` L268–269: `news_composite_val = enriched_composites.get(t, entry.get("news_composite"))`. |
| 2 | Final score → gated_scores | L271–278: `compute_signal_strength(..., news_composite=news_composite_val, ...)` → `week_scores[t]`. |
| 3 | Spine passes scores to PortfolioEngine | `src/core/target_weight_pipeline.py` (canonical spine): SignalEngine produces scores; PolicyEngine gates; PortfolioEngine.build(as_of_date, gated_scores, context) → Intent. |
| 4 | PortfolioEngine builds weights | `src/core/portfolio_engine.py` L34–60: `_build_backtest(gated_scores, context)` ranks by gated_scores, top_n, inverse-vol weights. |

So **intelligence** flows: Gemini → new_network_links → propagation → enriched news_composite → compute_signal_strength → week_scores (gated_scores) → PortfolioEngine → target weights. No separate “intelligence” field; intelligence is embedded in the enriched news composite and thus in the final score used for ranking and weighting.

---

## 3. Propagation Check (Summary)

- **SentimentPropagator** receives intelligence via `discovered_links` (same as `new_network_links` from `compute_news_composite`). Evidence: signal_engine.py L432–433; sentiment_propagator.py L125–128, L160–162, L264–278.
- **Format:** Each link is `{"source_ticker": ticker, "target_entity": entity, "direction": "upstream"|"downstream"}` (news_engine.py L551–553). Propagator accepts `entity` or `target_entity` (sentiment_propagator.py L268).
- **Effect:** Discovered upstream/downstream entities are merged into suppliers/customers for the primary ticker in `_get_relationships`, so propagation runs along both static DB and Gemini-discovered edges. Enriched composites then adjust the final score and thus **PortfolioEngine** target weights (ranking + inverse-vol).

---

## 4. Safety Gate (Gemini API Failure / Rate Limit)

**Requirement:** If the Gemini API fails or is rate-limited, the system must fall back to standard FinBERT/technical signals without crashing the rebalance.

| Layer | Behavior | Evidence |
|-------|----------|----------|
| news_engine.compute_news_composite | On any exception inside `if trigger_llm`, log and continue; LLM vars stay None/[]; composite still computed from FinBERT + strategies A–D. | news_engine.py L535–557: `try: ... GeminiAnalyzer(); ... deep_analyze(...); except Exception as exc: logger.warning("LLM gate failed (skipping): %s", exc)`. Return dict always includes llm_* and new_network_links (initialized L516–520); on exception they remain None/[], and L559–561 compute news_composite from comp_vals (FinBERT-based). |
| llm_bridge.GeminiAnalyzer.deep_analyze | On API or parse failure returns None; no raise. | llm_bridge.py L156–159 (API), L169–170 (JSON), L174–175 (validation): catch, log warning, return None. |
| SignalEngine Phase 1 | If compute_news_composite raises (e.g. before gate, in load/FinBERT), entire ticker news path caught; fallback 0.5. | signal_engine.py L222–224: `except Exception: news_composite_val = 0.5; buzz_by_ticker[t] = False`. So only failures *outside* the inner try in news_engine could bubble; the inner try in news_engine catches LLM. |
| Propagation | If propagator.propagate raises, that ticker’s propagation is skipped. | signal_engine.py L437–438: `except Exception as exc: logger.debug("Propagation from %s failed: %s", t, exc)`. |

**Conclusion:**  
- **Gemini unavailable (import/init error):** Caught in news_engine L556–557; no LLM keys set; composite is FinBERT-only.  
- **Gemini API failure / rate limit:** deep_analyze returns None; same as above.  
- **No code change required** for safety; existing try/except and None return provide graceful fallback. Optional hardening: in news_engine, catch `ImportError` and `ValueError` (missing API key) explicitly and log a single clear “LLM disabled” message so operators know why no LLM ran.

---

## 5. Step-by-Step Implementation Plan

### Phase A: Pre-flight (before enabling)

1. **Config and env**
   - Confirm `config/strategy_params.yaml` has `llm_analysis` block (already present).
   - Set `GOOGLE_API_KEY` or `GEMINI_API_KEY` in `.env`.
   - Confirm `google-genai` and `pydantic` in `requirements.txt`; install if needed.

2. **Optional comment**
   - In `strategy_params.yaml`, add a one-line comment that trigger_threshold is absolute sentiment delta in [0,1] and reference GEMINI_BRIDGE_DESIGN.md §2.2.

### Phase B: Enable Gemini for next rebalance

3. **Set enabled and threshold**
   - In `config/strategy_params.yaml`: set `llm_analysis.enabled` to `true`.
   - Leave `trigger_threshold` at `0.2` (or set to `0.15`–`0.25` per desired sensitivity). No new keys required.

4. **Run and validate**
   - Run weekly rebalance (e.g. `scripts/run_weekly_rebalance.py --tickers NVDA,AAPL,MSFT --dry-run` or with real watchlist).
   - Check logs for: `"LLM deep_analyze: category=... sentiment=... links=..."` when gate fires; and for `"LLM gate failed (skipping): ..."` if API fails (rebalance should still complete with FinBERT-only).
   - Confirm no crash; confirm target weights and orders are produced.

**Dry-run validation (high-impact news):** To verify the bridge is called, run a backtest over a date with high-impact news (e.g. NVDA earnings). Example:
   ```bash
   python scripts/backtest_technical_library.py --tickers NVDA,AAPL,MSFT --top-n 3 --news-dir data/news --start 2022-08-01 --end 2022-08-31
   ```
   Or use `scripts/run_execution.py --tickers NVDA,AAPL,MSFT --date 2022-08-25` with `data/news` containing NVDA news. Check logs for `"LLM Triggered:"` (news_engine.py) and `"LLM deep_analyze: category=... links=..."`; confirm `new_network_links` are passed to the propagator (signal_engine.py L432–433 → sentiment_propagator.propagate(..., discovered_links=...)).

### Phase C: Optional follow-ups (post activation)

5. **Blend Gemini sentiment into composite (design §2.2)**  
   - Currently the return dict includes `llm_sentiment` but it is not blended into `news_composite` (news_engine L559–561 use only comp_vals). To make rebalancing more “intelligence-driven,” add optional step: when `llm_sentiment` is not None, blend it with news_composite (e.g. replace or mix with FinBERT-based composite for that ticker). Document in STRATEGY_LOGIC or TECHNICAL_SPEC.

6. **Observability**  
   - Log when gate triggers (ticker, reason: supply_chain_keyword vs surprise), and when Gemini is skipped (API/parse failure). Eases debugging and cost control.

7. **Rate limiting**  
   - If rate limits are hit in production, add a simple in-memory throttle (e.g. max N Gemini calls per run or per minute) before calling GeminiAnalyzer; design doc does not mandate this for initial activation.

---

## 6. Validation Checklist

- [ ] `llm_analysis.enabled: true` and `trigger_threshold` set in `config/strategy_params.yaml`.
- [ ] `GOOGLE_API_KEY` or `GEMINI_API_KEY` in `.env`; `google-genai` and `pydantic` installed.
- [ ] One run with `run_weekly_rebalance.py` (or backtest) completes without crash.
- [ ] Logs show either LLM deep_analyze lines (when gate fires) or “LLM gate failed” (when API fails), and rebalance still completes.
- [ ] With API working and a ticker that has supply-chain keyword or high sentiment surprise, confirm `new_network_links` non-empty and propagation enriched composites (optional: log enriched_composites for one run).

---

## 7. File / Symbol Reference Summary

| Topic | File | Symbol / Section |
|-------|------|------------------|
| Config | config/strategy_params.yaml | llm_analysis (L13–18) |
| Gate & Gemini call | src/signals/news_engine.py | compute_news_composite (L451–575), L516–557 |
| LLM bridge | src/signals/llm_bridge.py | GeminiAnalyzer, deep_analyze (L148–175) |
| Cache & propagation | src/signals/signal_engine.py | L211–231 (cache), L387–467 (_propagate_sentiments), L432–433 (discovered_links) |
| Propagator | src/signals/sentiment_propagator.py | propagate (L125–241), _get_relationships (L243–283) |
| Target weights | src/core/portfolio_engine.py | build, _build_backtest |
| Design | docs/GEMINI_BRIDGE_DESIGN.md | §2.2 (gate), §2.3 (NEW_NETWORK_LINK), §3 (config) |

This plan is 1:1 with the current codebase and GEMINI_BRIDGE_DESIGN.md; no interface impact beyond enabling existing config and optional comment.
