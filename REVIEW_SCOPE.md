# REVIEW_SCOPE — Codex Audit Boundaries

**Prepared:** 2026-04-27

---

## Must Inspect (High Priority)

### Core Logic

```
src/core/
├── portfolio_engine.py     # HRP + Alpha Tilt, position sizing, max weight cap
├── signal_engine.py        # Signal generation entry point
├── policy_engine.py        # Regime gates, policy filters
├── intent.py               # Intent data structure
├── state.py                # Pipeline state management
└── target_weight_pipeline.py  # Weight calculation pipeline

src/signals/
├── layered_signal_engine.py   # Three-layer signal combination
├── technical_library.py       # Master Score calculation
├── signal_engine.py           # Signal orchestration
├── llm_bridge.py              # LLM integration for signals
└── feature_factory.py         # Feature engineering

src/execution/
├── risk_manager.py            # RiskOverlay, regime checks
├── ibkr_bridge.py             # IBKR live integration
├── ib_executor.py             # Order execution
├── planner.py                 # Execution planning
└── regime_controller.py       # Regime-based exposure control

src/agents/
├── skeptic_gate.py            # Bear-flag detection, concentration alerts
├── taleb_auditor.py           # Tail risk audit
├── damodaran_anchor.py        # Valuation anchor
└── bull_bear_debate.py        # Sentiment debate
```

### Entry Points

```
scripts/
├── run_e2e_pipeline.py        # Full pipeline orchestration
├── run_weekly_rebalance.py    # Production weekly run
├── run_execution.py           # IBKR order submission
├── run_optimizer.py           # Hyperparameter search
├── run_factory.py             # ML model factory
└── train_ml_model.py          # CatBoost training
```

### Configuration

```
config/
├── optimizer_config.yaml      # Master tuning manifest
├── trading_config.yaml        # Execution settings
├── strategy_params.yaml       # Promoted params (machine-written)
├── universe.yaml              # Ticker universe
└── instruments.yaml           # Tradeable instruments
```

### Security-Sensitive

```
.env                          # Secrets (do NOT commit, verify usage)
src/execution/ibkr_bridge.py  # IBKR credentials handling
src/execution/ib_executor.py  # Order submission
src/utils/defensive.py        # Input validation utilities
```

### Data Handling

```
src/fundamentals/
├── semi_valuation.py          # FCFF, R&D capitalization
└── quality_metrics.py         # Quality metric calculation

src/data/
├── edgar_audit.py             # SEC EDGAR integration
└── fmp_ingest.py              # FMP data ingestion
```

---

## Can Ignore (Low Priority)

### Generated/Cache Files

```
__pycache__/
.pytest_cache/
*.pyc
catboost_info/
logs/
models/saved/
outputs/
```

### Documentation

```
docs/                          # Reference only if code conflicts
*.md files (except REVIEW_BRIEF.md, REVIEW_SCOPE.md)
```

### Research/Experimental

```
scripts/research/              # Experimental scripts, lower bar
pods/                          # Pod architecture (partially implemented)
```

### Build/Tooling

```
.claude/                       # Claude Code config (review ~/.claude separately)
.cursor/                       # Cursor IDE config
handoffs/                      # Task handoff logs
contracts/                     # Contract snapshots
verify.ps1                     # Verification script
```

### Test Fixtures

```
tests/fixtures/                # Test data files
```

---

## ~/.claude Review

**Should be reviewed:** YES

### Files to Inspect

```
~/.claude/
├── CLAUDE.md                  # Global persona and rules
├── mcp.json                   # MCP server configurations
├── settings.json              # Claude Code settings
├── agents/                    # Agent definitions
├── commands/                  # Skill/slash command definitions
└── rules/
    ├── autonomy.md            # Autonomy operating rules
    └── tools-governance.md    # Tool classification
```

### Focus Areas for ~/.claude

1. **MCP server configurations** — Check for exposed secrets
2. **Settings permissions** — Auto-allowed commands, tool permissions
3. **Agent prompts** — Any hardcoded credentials or sensitive paths
4. **Hook configurations** — Scripts that run automatically

---

## Security-Sensitive Areas

### Authentication/Secrets

| File | Risk | Check |
|------|------|-------|
| `.env` | API key storage | Never committed, loaded via `python-dotenv` |
| `config/trading_config.yaml` | IBKR client IDs | No hardcoded credentials |
| `src/execution/ibkr_bridge.py` | IBKR connection | Credential handling, TLS |

### Input Validation

| File | Risk | Check |
|------|------|-------|
| `src/signals/llm_bridge.py` | LLM API input | Prompt injection, output validation |
| `src/data/fmp_ingest.py` | External API | Response validation, rate limits |
| `src/data/edgar_audit.py` | SEC EDGAR | User-agent handling, response parsing |

### Financial Calculations

| File | Risk | Check |
|------|------|-------|
| `src/core/portfolio_engine.py` | Allocation math | Decimal usage, no float |
| `src/fundamentals/semi_valuation.py` | FCFF calculation | Decimal usage |
| `src/portfolio/position_sizer.py` | Position sizing | Decimal usage |

### Order Execution

| File | Risk | Check |
|------|------|-------|
| `src/execution/ib_executor.py` | Order submission | Input validation, idempotency |
| `scripts/run_execution.py` | Execution spine | Error handling, rollback |
| `src/execution/fill_ledger.py` | Fill recording | Atomic writes |

---

## Audit Methodology

### Phase 1: Static Analysis

1. Run linters (flake8, pylint) — already executed, findings in REVIEW_BRIEF.md
2. Check for hardcoded secrets (grep patterns)
3. Verify Decimal usage for monetary calculations
4. Identify unused imports/variables

### Phase 2: Security Review

1. OWASP Top 10 checklist
2. Input validation at boundaries
3. Secrets management
4. Error handling patterns

### Phase 3: Architecture Review

1. Coupling analysis
2. Dead code identification
3. Config/code separation
4. Test coverage assessment

### Phase 4: Integration Review

1. IBKR integration safety
2. API error handling
3. State management
4. Atomic write patterns

---

## Out of Scope

1. **Business logic changes** — Report findings, do not modify signal formulas
2. **Performance optimization** — Not a correctness issue
3. **Documentation updates** — Unless code conflicts
4. **Feature additions** — This is an audit, not enhancement
5. **Research scripts** — Lower priority, experimental code

---

## Reporting Format

For each finding, provide:

1. **Severity:** Critical / High / Medium / Low
2. **Category:** Security / Code Quality / Architecture / Testing
3. **File:Line:** Exact location
4. **Description:** What's wrong
5. **Impact:** Why it matters
6. **Recommendation:** How to fix (without modifying business logic)
