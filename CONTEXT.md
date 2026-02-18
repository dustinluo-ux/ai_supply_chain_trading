# CONTEXT.md — Project State & Handoff Guide

**Last Updated:** 2025-02-18  
**Purpose:** Orient Claude Code (CLI) to the AI Supply Chain Trading System without reading full conversation history.

---

## 1. Project Overview

### What This System Does
This is an **AI-powered quantitative trading system** focused on **supply chain sentiment analysis for AI infrastructure stocks** (semiconductors: NVDA, TSM, AMD, ASML, MU, AMAT). The system extracts trading signals by:

1. **Analyzing sentiment propagation** through supply chain relationships using LLM-powered news analysis (Gemini 2.0 Flash)
2. **Combining technical indicators** (Master Score from expanded technical library) with news sentiment
3. **Using ML regression frameworks** to identify market opportunities via sentiment-to-price correlation

### Core Architecture Pattern
Three-phase pipeline with **sentiment propagation capabilities**:
- **Phase 1:** Data centralization (price data + news ingestion)
- **Phase 2:** Signal extraction (technical indicators + LLM sentiment analysis)
- **Phase 3:** Execution (portfolio construction + risk management)

The system emphasizes **Evidence Discipline** throughout — every decision must be traceable to data or documented logic.

---

## 2. File Structure

### 2.1 Canonical Documentation (11 Files)
These are the **authoritative blueprint** for the system. All code must align with these specs.

| File | Purpose | Stage Coverage |
|------|---------|----------------|
| `ARCHITECTURE.md` | System design, component interactions, data flows | All stages |
| `WORKFLOW.md` | Development lifecycle, stage definitions, acceptance criteria | All stages |
| `TECHNICAL_SPEC.md` | Implementation details, class signatures, data schemas | Stage 2-3 |
| `STRATEGY_LOGIC.md` | Trading rules, regime detection, position sizing | Stage 3 |
| `SENTIMENT_PROPAGATION.md` | Supply chain graph logic, tier weights, decay factors | Stage 2 |
| `LLM_INTEGRATION.md` | Gemini bridge design, prompt templates, trigger conditions | Stage 2 |
| `TESTING_PROTOCOLS.md` | Determinism checks, parity testing, validation criteria | All stages |
| `NEWS_ENGINE.md` | News ingestion, deduplication, baseline vs event sentiment | Stage 2 |
| `SIGNAL_ENGINE.md` | Technical library, Master Score calculation, regime HMM | Stage 2 |
| `PORTFOLIO_ENGINE.md` | Position sizing (ATR-based), rebalancing, risk gates | Stage 3 |
| `DATA_SCHEMAS.md` | YAML configs, CSV formats, regime ledger schema | All stages |

### 2.2 Root Documentation (3 Files)
- `INDEX.md` — Navigation hub linking to all canonical docs + explanatory context
- `README.md` — Quick-start guide for developers
- `CHANGELOG.md` — Version history, major milestones

### 2.3 Archive Structure
```
archive/
├── consolidated/          # Old markdown files organized by consolidation batch
│   ├── batch_001_core/    # ARCHITECTURE, WORKFLOW, TECHNICAL_SPEC sources
│   ├── batch_002_strategy/ # STRATEGY_LOGIC, regime/policy sources
│   ├── batch_003_signals/  # SIGNAL_ENGINE, NEWS_ENGINE sources
│   └── ...                 # (11 batches total completed)
└── legacy/                 # Pre-consolidation state (130+ files)
```

**Rule:** Never reference archived files directly. If content is needed, it must first be promoted to canonical docs.

### 2.4 Key Directories
```
config/
├── data_config.yaml           # Data source paths
├── strategy_params.yaml       # Propagation weights, LLM triggers, entity map
├── technical_master_score.yaml # Indicator weights, regime thresholds
└── risk_limits.yaml           # Circuit breaker, drawdown limits

src/
├── core/                      # Spine: SignalEngine, PolicyEngine, PortfolioEngine
├── signals/                   # Technical library, news engine, sentiment propagator
├── data/                      # CSV provider, news ingestion
├── portfolio/                 # Position sizer, rebalancer
└── utils/                     # Config manager, defensive YAML loading

scripts/
├── backtest_technical_library.py  # Main backtest harness
└── ...

data/
├── stock_market_data/
│   ├── nasdaq/csv/
│   ├── sp500/csv/
│   └── nyse/csv/
└── news/                      # LLM-analyzed news JSON files
```

---

## 3. Current State

### 3.1 Documentation Consolidation Progress

**Completed:**
- ✅ All 11 batches consolidated (130+ markdown files → 11 canonical docs + 3 root files)
- ✅ Archive organized by batch in `archive/consolidated/`
- ✅ INDEX.md serves as navigation hub with context

**Status:** Documentation is **canonical-complete**. The 11 files now serve as the single source of truth.

### 3.2 Development Stage Progress

**Stage 1 (Data Centralization):** ✅ Complete
- CSV provider with recursive path resolution (Windows-compatible)
- News ingestion pipeline functional
- Data schemas defined in `DATA_SCHEMAS.md`

**Stage 2 (Signal Extraction):** ✅ Complete
- SignalEngine operational with technical + news compositing
- LLM integration (Gemini) working with gated trigger logic
- Sentiment propagation enabled (5/1 enrichment achieved: NVDA → TSM, AMD, ASML, MU, AMAT)
- Initial LLM accuracy: supplier 32.7%, competitor 80%

**Stage 3 (Execution):** 🔄 In Progress
- ATR-based position sizing implemented
- Weekly rebalancing functional
- Circuit breaker logic defined but not fully integrated
- Live execution bridge pending

### 3.3 Recent Critical Findings

#### Semiconductor Strategy Bridge (2025-02-18)
- **Achievement:** Successfully triggered "5/1 enriched" propagation (1 seed ticker → 6 total after adding peers)
- **Mechanism:** Pre-propagation expansion in `backtest_technical_library.py` reads `entity_ticker_map` from `strategy_params.yaml` and loads peer price data before backtest loop
- **Known Issue:** SSNLF (Samsung OTC stock) is data quality outlier, should be removed from `entity_ticker_map`

#### Path Resolution Fix (Windows Compatibility)
- **Issue:** `find_csv_path()` in `csv_provider.py` had case-sensitivity bug on Windows
- **Fix:** Changed to `return os.path.join(root, f)` using actual filename from disk, not synthetic uppercase version
- **Impact:** Enabled recursive CSV discovery across `nasdaq/csv`, `sp500/csv`, `nyse/csv` subdirectories

#### Strategy Selector Logic
- Regime-based strategy selection operational
- Performance ledger (`regime_ledger.csv`) tracks strategy performance by regime
- Winning profile override: news_weight, signal_horizon_days, sideways_risk_scale

#### Dual Signal Backend
- Technical Master Score (0.8 weight) + News Composite (0.2 weight)
- AdaptiveSelector evolves news weights from last 3 regime occurrences
- DynamicSelector overrides all params from historical best profile

### 3.4 Known Gaps & Issues

**High Priority:**
- SSNLF (Samsung) in entity_ticker_map is causing portfolio allocation errors (remove it)
- NVDA scoring 0.000 weight when it should dominate (investigate scoring logic in SignalEngine)
- Regime detection defaults to `None` when SPY data insufficient (needs fallback logic)

**Medium Priority:**
- Circuit breaker integration incomplete (defined in config but not wired to execution)
- Live execution bridge design exists but not implemented
- Regime transition smoothing (1-week delay before BEAR→BULL confirmed) not validated

**Low Priority:**
- Pandas FutureWarning in `pct_change()` (cosmetic, use `fill_method=None`)
- Date parsing warning in csv_provider (cosmetic, use `dayfirst=False`)

---

## 4. Conventions & Standards

### 4.1 Documentation Style

**Tone:**
- Technical but accessible (assume reader has Python + finance background)
- Imperative mood for procedures ("Run X", "Configure Y")
- Declarative for architecture ("The system uses X to achieve Y")

**Structure:**
- Always start with Purpose/Overview
- Use hierarchical headings (max depth: ####)
- Include concrete examples for complex logic
- Cross-reference other canonical docs explicitly (e.g., "See ARCHITECTURE.md § 3.2")

**Technical Depth:**
- Include class names, function signatures when relevant
- Show data schemas in YAML/JSON format
- Provide command-line examples for CLI tools
- Document failure modes and error handling

**Formatting:**
- Use tables for parameter lists, data schemas
- Code blocks must specify language (```python, ```yaml)
- Use `**bold**` for critical concepts, `*italic*` for emphasis
- Use `> Note:` or `> Warning:` for callouts

### 4.2 File Naming Patterns

**Canonical Docs:**
- All caps with underscores: `STRATEGY_LOGIC.md`
- Noun-focused: describe what the file *is* (e.g., `ARCHITECTURE.md` not `HOW_TO_ARCHITECT.md`)

**Archive:**
- Batch prefix: `batch_001_core/`, `batch_002_strategy/`
- Original filenames preserved within batch folders

**Code:**
- Snake case: `signal_engine.py`, `csv_provider.py`
- Classes: PascalCase (`SignalEngine`, `PolicyEngine`)
- Functions: snake_case (`compute_target_weights`, `find_csv_path`)

**Config:**
- Snake case: `strategy_params.yaml`, `data_config.yaml`

### 4.3 Testing Protocols

**Determinism Checks:**
- Same input (date, ticker, config) must produce identical output
- Test with frozen timestamps: `as_of = pd.Timestamp("2022-08-22")`
- No reliance on `datetime.now()` in signal generation

**Hardcoded Value Detection:**
- Grep for numeric literals in signal logic: `0.2`, `0.5`, `0.7`
- All thresholds must trace to YAML config or be explicitly justified
- Exception: Mathematical constants (e.g., `252` trading days) allowed if documented

**YAML Configuration Verification:**
- Every configurable parameter must exist in one of: `strategy_params.yaml`, `technical_master_score.yaml`, `risk_limits.yaml`, `data_config.yaml`
- Use `src/utils/defensive.py::safe_read_yaml()` for all YAML loading (handles missing files gracefully)

**Canonical Compliance Validation:**
- Before code integration, verify alignment with canonical docs
- Use agent validation: VALIDATOR checks implementation against TECHNICAL_SPEC.md, STRATEGY_LOGIC.md
- Acceptance criteria from WORKFLOW.md must be met before stage completion

**Parity Testing:**
- Compare backtest results between runs with identical params
- Sharpe, total return, max drawdown must match to 4 decimal places
- Regime assignments must be identical across runs

### 4.4 Design Principles

**Evidence Discipline:**
- Every decision requires traceable evidence (data, paper citation, backtest result)
- No "gut feel" parameter choices
- Document *why* a threshold was chosen (e.g., "0.2 sentiment delta triggers LLM per GEMINI_BRIDGE_DESIGN.md § 2.2")

**Integration Over Rewrite:**
- Prefer connecting existing code clusters to rewriting from scratch
- Use canonical docs as integration guide
- Archive old code; don't delete until replacement is validated

**Canonical Docs as Single Source of Truth:**
- Code conflicts with docs → update code, not docs (unless doc is provably wrong)
- Docs must be updated *before* implementing new features
- Never say "we'll document it later" — design-first, code-second

**Agent-Specific Roles:**
- ENGINEER: implements code per specs
- ARCHITECT: designs system structure, updates canonical docs
- VALIDATOR: checks compliance with acceptance criteria

---

## 5. Workflow Patterns

### 5.1 How Batch Reviews Work

**Legacy Pattern (Consolidation Phase — Now Complete):**
1. Identify thematic cluster (e.g., "all regime detection docs")
2. Extract valuable content (unique logic, data schemas, examples)
3. Merge into relevant canonical doc
4. Move originals to `archive/consolidated/batch_NNN_theme/`
5. Update INDEX.md with cross-references

**Current Pattern (Post-Consolidation):**
- No more batch reviews needed (130+ files already processed)
- New content goes directly into canonical docs
- If canonical doc becomes too large (>500 lines), consider splitting (rare)

### 5.2 When to Update Which Canonical Docs

| Change Type | Update These Docs |
|-------------|-------------------|
| New data source | `ARCHITECTURE.md` (data flows), `DATA_SCHEMAS.md` (format spec) |
| New indicator | `SIGNAL_ENGINE.md` (calculation logic), `TECHNICAL_SPEC.md` (function signature) |
| Trading rule change | `STRATEGY_LOGIC.md` (rule definition), `PORTFOLIO_ENGINE.md` (execution impact) |
| Config parameter added | `DATA_SCHEMAS.md` (YAML schema), relevant domain doc (e.g., `LLM_INTEGRATION.md` for `trigger_threshold`) |
| Bug fix (logic) | Relevant domain doc (add to "Known Issues" or update affected section) |
| Bug fix (implementation) | Code only (no doc update unless design flaw) |
| New test protocol | `TESTING_PROTOCOLS.md` |
| Regime logic change | `STRATEGY_LOGIC.md` (regime definitions), `SIGNAL_ENGINE.md` (HMM params if applicable) |

### 5.3 Criteria for "Valuable Content" vs Deletion

**Keep if:**
- Describes unique logic not present in canonical docs
- Contains data schemas, parameter definitions, or thresholds
- Provides concrete examples or edge case handling
- Documents rationale for design decisions (Evidence Discipline)
- Includes validation results, backtest stats, or performance metrics

**Delete if:**
- Duplicates content already in canonical docs verbatim
- Contains only TODO notes without actionable detail
- Outdated by subsequent design iterations (and no historical value)
- Implementation-specific code snippets (code lives in `src/`, not docs)
- Vague aspirational statements without concrete specs

**Archive if:**
- Historical value for understanding design evolution
- Contains interim experimental results
- Part of consolidation batch (preserve provenance)

### 5.4 Code Integration Workflow

**Phase 1: Discovery Mapping**
1. Read INDEX.md to understand canonical doc structure
2. Identify which canonical docs cover the feature area
3. Map existing code clusters to canonical components (e.g., "this 200-line script aligns with SIGNAL_ENGINE.md § 3.1-3.4")

**Phase 2: Prioritized Integration**
1. Follow WORKFLOW.md stage order (Data → Signals → Execution)
2. Wire up existing code to canonical interfaces (don't rewrite unless necessary)
3. Reference INDEX.md and specific canonical doc sections in code comments

**Phase 3: Validation**
1. Run determinism checks (same input → same output)
2. Verify YAML compliance (no hardcoded values)
3. Check acceptance criteria from WORKFLOW.md
4. Use VALIDATOR agent to audit against canonical docs

**Phase 4: Documentation Update**
1. If implementation reveals design gap, update canonical doc *first*
2. Add example usage to relevant canonical doc if complex
3. Update CHANGELOG.md with integration milestone

### 5.5 Cursor AI Agent Prompts

**ENGINEER Preamble:**
```
You are ENGINEER. Your role: implement code per TECHNICAL_SPEC.md.
- Always reference INDEX.md to locate relevant canonical docs
- Maintain Evidence Discipline: cite config params, don't hardcode
- Use existing code clusters from discovery mapping; integrate, don't rewrite
- Validate against acceptance criteria in WORKFLOW.md before claiming completion
```

**ARCHITECT Preamble:**
```
You are ARCHITECT. Your role: design system structure, update canonical docs.
- Read INDEX.md first to understand doc organization
- Update canonical docs BEFORE implementing new features
- Use tables for data schemas, hierarchical headings for structure
- Cross-reference related docs explicitly (e.g., "See STRATEGY_LOGIC.md § 2.1")
```

**VALIDATOR Preamble:**
```
You are VALIDATOR. Your role: audit code against canonical docs + acceptance criteria.
Checklist:
1. Determinism: same input → same output (no datetime.now() in signals)
2. Hardcoded values: grep for magic numbers, verify YAML config source
3. YAML compliance: all params in strategy_params.yaml / technical_master_score.yaml / risk_limits.yaml
4. Canonical compliance: implementation matches TECHNICAL_SPEC.md, STRATEGY_LOGIC.md
5. Acceptance criteria: Stage N goals from WORKFLOW.md achieved
Report violations with file:line references.
```

---

## 6. Quick Reference

### 6.1 Key Commands

**Run Backtest (Semiconductor Strategy):**
```bash
python scripts/backtest_technical_library.py \
  --tickers "NVDA" \
  --top-n 5 \
  --news-dir data/news \
  --start 2022-08-22 \
  --end 2022-08-29
```

**Expected Output (5/1 Enrichment):**
```
[OK] Found NVDA at: .../nasdaq/csv/NVDA.csv
[PROPAGATION] Added price-verified propagated ticker AMD
[PROPAGATION] Added price-verified propagated ticker ASML
[PROPAGATION] Added price-verified propagated ticker AMAT
[PROPAGATION] Added price-verified propagated ticker MU
[PROPAGATION] Added price-verified propagated ticker TSM
[PROPAGATION] Propagation enriched 6 sources (seed + 5 peers)
Backtest: 6 tickers, 2 rebalances, top_n=5
```

**Verify Determinism:**
```bash
# Run twice with identical params
python scripts/backtest_technical_library.py --tickers "NVDA" --start 2022-08-22 --end 2022-08-29 > run1.txt
python scripts/backtest_technical_library.py --tickers "NVDA" --start 2022-08-22 --end 2022-08-29 > run2.txt
diff run1.txt run2.txt  # Should be empty
```

### 6.2 Critical File Paths

| Component | File Path |
|-----------|-----------|
| Main backtest | `scripts/backtest_technical_library.py` |
| CSV data loader | `src/data/csv_provider.py` |
| Signal spine | `src/core/target_weight_pipeline.py` |
| SignalEngine | `src/signals/signal_engine.py` |
| News engine | `src/signals/news_engine.py` |
| Sentiment propagator | `src/signals/sentiment_propagator.py` |
| LLM bridge | `src/signals/llm_bridge.py` |
| Entity map config | `config/strategy_params.yaml` |
| Technical weights | `config/technical_master_score.yaml` |

### 6.3 Common Debugging Patterns

**Issue:** "No CSV found for NVDA"
- **Check:** `find_csv_path()` receives `str(data_dir)`, not `Path` object (Windows compatibility)
- **Check:** CSV file case matches search (use actual filename from `os.walk`, not synthetic uppercase)

**Issue:** "top_n=5 but only 1 tickers loaded"
- **Check:** Pre-propagation expansion ran (should see `[PROPAGATION]` logs)
- **Check:** `entity_ticker_map` in `strategy_params.yaml` under `llm_analysis`, not `propagation`

**Issue:** NVDA gets 0.000 weight
- **Check:** Master Score calculation in `signal_engine.py` (news composite might be inverting sentiment)
- **Check:** Regime state (BEAR mode halves weights, CASH_OUT zeros them)

**Issue:** SSNLF dominates portfolio
- **Fix:** Remove `"SAMSUNG ELECTRONICS": "SSNLF"` from `entity_ticker_map` (OTC stock, low data quality)

---

## 7. Next Steps for Claude Code

### Immediate Priorities (2025-02-18)
1. **Fix SSNLF allocation bug:** Remove Samsung from `entity_ticker_map` in `strategy_params.yaml`
2. **Investigate NVDA scoring:** Debug why seed ticker scores 0.000 weight (should dominate with sentiment=0.70, links=7)
3. **Validate regime fallback:** Ensure system handles `regime_state=None` gracefully when SPY data insufficient

### Medium-Term Tasks
1. **Circuit breaker integration:** Wire `risk_limits.yaml` circuit breaker logic to execution engine
2. **Live execution bridge:** Implement design from `docs/LIVE_EXECUTION_BRIDGE_DESIGN.md` (if exists in archive)
3. **Regime transition smoothing:** Validate 1-week delay before BEAR→BULL confirmed (see `STRATEGY_LOGIC.md`)

### Long-Term Goals
- Expand universe beyond semiconductors (consumer tech, cloud infrastructure)
- Multi-horizon signal blending (daily + weekly rebalancing)
- Production deployment with Alpaca/Interactive Brokers integration

---

## 8. Contact & Escalation

**Owner:** Luo (dusro)  
**Primary Tool:** Claude Code (CLI) for planning/prompting, Cursor AI for implementation  
**Escalation:** For ambiguous design decisions or canonical doc conflicts, flag for Luo review rather than making assumptions  

**Evidence Discipline Reminder:** If unsure whether a parameter choice is justified, search canonical docs for rationale. If not found, it's a design gap — update docs first, implement second.

---

## 9. Claude Code Usage Rules

- **Role**: Planning, strategizing, prompt generation ONLY
- **No code generation**: Draft instructions for Cursor, not code snippets
- **Output format**: Cursor prompts, analysis, recommendations
- **Cursor handles**: All code writing, refactoring, file manipulation
---

**End of Context Document**
