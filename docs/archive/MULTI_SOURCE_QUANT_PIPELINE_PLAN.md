# Multi-Source Quant Pipeline — High-Level Plan

**Context:** This plan aligns the **ai_supply_chain_trading** project with your Multi-Source Quant Pipeline architecture. It uses the **physical folder** as the source of truth and reviews **wealth_signal_mvp_v1** for portable work. API credentials are assumed to live in `.env` in one or both project roots (TIINGO, MARKETAUX, GOOGLE_API / GEMINI).

---

## Principles / alignment

1. **Historical data (legacy + expansion)**  
   **Keep** existing historical data and analysis: **FNSPID** and **Polygon-based** workflows remain an integral part of the pipeline. **Expand** the data layer to include **Tiingo**, **yfinance**, and **Marketaux**. The system must support **seamless alternation** between the two modes: legacy (FNSPID + Polygon) and new (Tiingo + yfinance + Marketaux), e.g. via config or data-source selection, without dropping legacy paths.

2. **wealth_signal_mvp_v1 is read-only**  
   **Do not modify** wealth_signal_mvp_v1. It is only a **source** of existing code to recycle (port/copy) when useful. All implementation work is done in **ai_supply_chain_trading**.

3. **ai_supply_chain_trading: expand, do not reduce**  
   All **existing** contents of ai_supply_chain_trading (FNSPID scripts, Polygon processing, supply chain DB, signal combiner, backtest, execution, phases 1–3, etc.) are **integral** to the target workflow. Work is to **expand** this codebase (new sources, Warm-Up, rebalance runner, etc.), **not** to remove or replace existing modules.

---

## Your Architecture (4 Pillars)

| Pillar | Summary |
|--------|--------|
| **1. Data & Environment** | Keys in .env (TIINGO, MARKETAUX, GOOGLE_API). Legacy from wealth_signal_mvp_v1. **Warm-Up:** last 30 days “Recent” to bridge Historical CSVs ↔ Real-Time. **Self-Healing:** every live fetch appends new data to `/data/historical/`. |
| **2. Execution & Market Data (IBKR)** | IBKR TWS via ib_insync. **Volume:** reqMktData Tick ID 8 with **x100 multiplier** for US Equities. **Stability:** Client ID rotation starting @ 99; yfinance cache init to avoid SQLite crashes. |
| **3. Sentiment & Inference** | **Dual-stream news:** Marketaux (targeted) + Tiingo (broad). **LLM:** Google Gemini as “Quant Analyst” → strict JSON `{ticker, score, relevance, impact}`. **Scale:** sentiment normalized -1.0 to 1.0; live inference matches historical training (FNSPID). |
| **4. Operational Cadence** | **Weekly rebalance:** rank by Composite Score (Price Momentum + Weighted Sentiment) → BUY/SELL/HOLD. |

---

## Current State vs Architecture

### ai_supply_chain_trading (physical folder)

| Your requirement | Current state | Gap |
|------------------|---------------|-----|
| Keys in .env | `.env`, `.env.example`, `.env.template` exist; template uses NEWS_API_KEY, ALPHAVANTAGE, FINNHUB, GEMINI_API_KEY, ALPACA | Standardize names: **TIINGO**, **MARKETAUX**, **GOOGLE_API** (or keep GEMINI_API_KEY) and document in one place. |
| Warm-Up 30 days | No explicit “last 30 days Recent” bridge between historical CSVs and live feed | Add **Warm-Up** layer: load historical, fetch last 30d from Tiingo/yfinance/IBKR, merge, pass to pipeline. |
| Self-healing append to /data/historical/ | Price fetcher appends/caches to `data/prices/` (parquet); no single “historical” path and no explicit “heal then append” contract | Define **data/historical/** (or equivalent) and a **heal** step: after any live fetch, append new bars to historical store. |
| IBKR volume (Tick 8, x100) | `src/data/ib_provider.py` has get_historical_data, get_current_price; **no reqMktData**, no Tick 8, no x100 volume | Add **real-time volume** path: reqMktData with genericTickList for Tick 8, apply x100 for US equities. |
| Client ID rotation @ 99 | wealth_signal: `randint(100, 999)`; ai_supply_chain: `randint(100, 999)` or config client_id | Implement **rotation starting @ 99** (e.g. 99, 100, 101…) and reuse in both data and execution to avoid conflicts. |
| yfinance cache init | Not present in ai_supply_chain | Port or add **yfinance cache initialization** to avoid SQLite issues (e.g. on first import or pipeline start). |
| Dual-stream news (Marketaux + Tiingo) | **Marketaux:** implemented (`src/data/news_sources/marketaux_source.py`, download_news_marketaux.py). **Tiingo:** not implemented; only mentioned in docs | Add **Tiingo news source** (e.g. `tiingo_source.py`), then a **unified text stream** that merges Marketaux + Tiingo. |
| Gemini strict JSON (-1 to 1) | `src/signals/gemini_analyzer.py` (and gemini_news_analyzer) exist; output schema may not be strict `{ticker, score, relevance, impact}` | Enforce **strict JSON schema** and **-1 to 1** normalization so live inference matches FNSPID/training scale. |
| FNSPID alignment | FNSPID scripts (download_fnspid, process_fnspid, data/raw) and sentiment pipeline exist | Ensure **sentiment scale and schema** in live path match FNSPID/historical (e.g. same normalisation and field names). |
| Weekly rebalance, composite score, BUY/SELL/HOLD | Signal combiner (momentum + sentiment) and backtest weekly logic exist; **no single “weekly rebalance → orders” script**; no explicit BUY/SELL/HOLD from composite rank | Add **weekly rebalance runner**: composite score (momentum + weighted sentiment) → rank → target weights → **BUY/SELL/HOLD** list → execution. |

### wealth_signal_mvp_v1 — Useful to port

| Component | Location | Use in pipeline |
|-----------|----------|------------------|
| **IBKR data loader** | `core/data/loader_ibkr.py` | Already ported conceptually to ai_supply_chain `src/data/ib_provider.py`. Optional: align cache keying, client_id handling, and contract logic (stocks/futures/crypto) if needed. |
| **IBKR executor** | `core/models/ibkr_executor.py` | place_order, connect, _create_contract, _create_order. ai_supply_chain has `src/execution/ib_executor.py` (submit_order, etc.). Prefer **enhancing** ai_supply_chain’s executor with volume/Tick 8 and client ID rotation rather than replacing. |
| **Signal → trade mapping** | `core/policies/target_to_trade_mapper.py` | **map_signals_to_trades(signal_series, upper_threshold, lower_threshold, regime_series)** → +1/-1/0 (BUY/SELL/HOLD). **Port:** same logic into ai_supply_chain (e.g. `src/policies/` or signal_mapper) for weekly composite signal → discrete actions. |
| **Position manager** | `core/portfolio/position_manager.py` | get_current_positions, get_account_value, positions_to_weights, **calculate_delta_trades(current_weights, optimal_weights, account_value, prices, min_trade_size, significance_threshold)**. **Port:** adapt to ai_supply_chain’s IB provider/executor and use in weekly rebalance (current vs optimal → delta orders). |
| **Simple portfolio optimizer** | `core/portfolio/portfolio_optimizer_simple.py` | **optimize(signals, prices, volatility)** → optimal weights with position limits and vol target. **Port:** use for “composite score → optimal weights” in weekly rebalance (or keep ai_supply_chain’s equal-weight and add this as an option). |
| **E2E run script** | `run/run_e2e_test.py` | Data → Features → Signals → map_signals_to_trades → PositionManager + SimplePortfolioOptimizer → delta_trades → IBKRExecutor. **Use as template:** one script in ai_supply_chain that runs: data (with warm-up) → sentiment (dual-stream + Gemini) → composite score → optimal weights → delta trades → executor. |
| **Feature engineering** | `core/features/feature_engineering.py`, `core/ta_lib/features.py` | ta_feature_pack, macro_feature_pack, “drop warmups”. Optional: reuse TA/macro patterns if we unify feature sets; otherwise keep ai_supply_chain’s technical_indicators and add only what’s missing. |
| **Regime suppression** | target_to_trade_mapper accepts regime_series; run_e2e uses regime in trade mapping | Optional: add regime overlay to BUY/SELL/HOLD so we suppress trades in hostile regimes (e.g. recession/volatile). |

---

## Credentials

- **wealth_signal_mvp_v1:** `.env` present at repo root (contents not read).
- **ai_supply_chain_trading:** `.env`, `.env.example`, `.env.template` present; template references NEWS_API_KEY, ALPHAVANTAGE, FINNHUB, GEMINI_API_KEY, ALPACA.

**Recommendation:** In ai_supply_chain_trading, standardize and document in `.env.example` / docs:

- `TIINGO_API_KEY` (or `TIINGO_TOKEN`)
- `MARKETAUX_API_KEY` (already used in code)
- `GOOGLE_API_KEY` or `GEMINI_API_KEY` (Gemini)

Use the same names in config/docs so the “single .env” approach works whether keys are in one or both project roots.

---

## High-Level Execution Plan (Phases)

### Phase A — Data & environment (Warm-Up + self-healing)

1. **Define data contract**
   - **Historical:** e.g. `data/historical/` (or keep `data/prices/` and document it as “historical”).
   - **Recent:** last 30 days from Tiingo/yfinance or IBKR.
   - **Warm-Up:** on pipeline start, load historical; fetch last 30d “Recent”; merge so there is no gap; use merged series for features/signals.
2. **Self-healing**
   - After any live fetch (IBKR or other), append new bars to the historical store (no duplicates, by date/ticker).
3. **.env and config**
   - Add TIINGO, MARKETAUX, GOOGLE_API (or GEMINI) to `.env.example` and a short “Data & environment” doc.

Deliverable: Warm-Up + heal logic in one place (e.g. `src/data/warmup.py` or inside price_fetcher), used by the main pipeline.

---

### Phase B — Execution & market data (IBKR volume + stability)

1. **Real-time volume**
   - In `src/data/ib_provider.py` (or a dedicated live feed module), add path using **reqMktData** with **genericTickList** for Tick ID 8 (volume); apply **x100** for US equities when exposing volume.
2. **Client ID rotation**
   - Implement rotation starting at 99 (99, 100, 101, …) and use it for both data and execution connections (config or small helper).
3. **yfinance cache init**
   - Port or add one-time yfinance cache init (e.g. on first use or pipeline bootstrap) to avoid SQLite crashes.

Deliverable: IBKR provider supports Tick 8 volume (x100); client ID rotation and yfinance init documented and used.

---

### Phase C — Sentiment & inference (dual-stream + Gemini)

1. **Tiingo news source**
   - Add `src/data/news_sources/tiingo_source.py` (or equivalent), key from .env, same interface as other news sources (e.g. fetch for tickers/dates, return unified article list).
2. **Unified text stream**
   - Single “news aggregator” that pulls from Marketaux + Tiingo and outputs one stream (e.g. list of articles with source tag) for downstream sentiment.
3. **Gemini strict JSON**
   - In `src/signals/gemini_analyzer.py` (or gemini_news_analyzer), enforce output schema: `{ticker, score, relevance, impact}` and normalize **score** to **-1.0 to 1.0** so live matches historical/FNSPID.
4. **FNSPID alignment**
   - Document and, if needed, add a small normalisation layer so that live sentiment scale and field names match FNSPID and any existing training code.

Deliverable: Dual-stream news (Marketaux + Tiingo) → Gemini → strict JSON scores in [-1, 1]; FNSPID alignment documented.

---

### Phase D — Weekly rebalance (composite score → BUY/SELL/HOLD)

1. **Composite score**
   - Single function or config-driven step: **Composite Score = f(Price Momentum, Weighted Sentiment)** using existing signal combiner and weights (e.g. from config).
2. **Ranking**
   - Rank tickers by composite score (e.g. weekly universe).
3. **Target weights**
   - From rank → target weights (e.g. equal weight top N, or port **SimplePortfolioOptimizer** for vol/position limits).
4. **BUY/SELL/HOLD**
   - Port **map_signals_to_trades** (or equivalent): current weights vs target → delta → list of (symbol, side, qty) with side in {BUY, SELL, HOLD}.
5. **Position manager**
   - Port **PositionManager** (or equivalent): get_current_positions, get_account_value, positions_to_weights, **calculate_delta_trades**. Wire to ai_supply_chain’s IB provider/executor.
6. **Weekly runner**
   - One script (e.g. `run_weekly_rebalance.py`): load config → Warm-Up data → dual-stream news → Gemini sentiment → composite score → rank → target weights → PositionManager.calculate_delta_trades → filter to BUY/SELL only → executor.submit_order (with dry-run option).

Deliverable: Single entrypoint for weekly rebalance that outputs and optionally executes BUY/SELL/HOLD.

---

### Phase E — Integration and ops

1. **E2E test**
   - One script that runs: data (with warm-up) → sentiment (dual-stream + Gemini) → composite → rebalance logic → dry-run execution (no real orders).
2. **Docs**
   - Update README and/or ARCHITECTURE.md with: 4 pillars, where .env keys are used, where Warm-Up and self-healing run, how to run weekly rebalance (including dry-run).
3. **Scheduling (optional)**
   - Document how to run the weekly script via cron/Task Scheduler; no code required in Phase E if manual run is acceptable.

---

## Dependency order

- **A** (Warm-Up, heal, .env) can be done first.
- **B** (IBKR volume, client ID, yfinance) can run in parallel with A or right after.
- **C** (Tiingo, dual-stream, Gemini JSON, FNSPID) depends on A only for “data available”; can follow A.
- **D** (rebalance) depends on A, B (for live data/execution), and C (for sentiment). Use mock/static data for rebalance logic without B/C if needed.
- **E** (E2E, docs) after D.

---

## What we are not changing (without your say-so)

- **wealth_signal_mvp_v1:** No edits; read-only source for code to port into ai_supply_chain_trading.
- **Legacy data paths:** FNSPID and Polygon-based analysis remain; we add Tiingo + yfinance + Marketaux and support seamless alternation between legacy and new.
- **ai_supply_chain_trading existing code:** No removal or reduction. Backtest engine, Phase 1/2/3, supply chain DB, signal combiner, execution, scripts, etc. stay; the plan **adds** Warm-Up, dual-stream, rebalance runner, and IBKR enhancements.
- Repo exclusions (data/, sensitive paths) stay; the plan references the physical folder and existing .env usage.

---

## Build status (2026-01-29)

Phases A–E implemented: Warm-Up (`src/data/warmup.py`), client ID rotation + IBKR volume + yfinance cache (Phase B), Tiingo + dual-stream (Phase C), PositionManager + `run_weekly_rebalance.py` (Phase D), `run_e2e_pipeline.py` + docs (Phase E). See CHANGELOG_BUGFIXES.md. Run Phase 2 then `run_weekly_rebalance.py --dry-run` or `run_e2e_pipeline.py`.

---

## Next step

Once you confirm this high-level plan (or specify changes), the next step is to break **Phase A** into concrete tasks and file-level changes (e.g. “add `src/data/warmup.py`”, “extend price_fetcher to call warmup”, “update .env.example”). No implementation of Phase B–E until you’re happy with the plan and Phase A scope.
