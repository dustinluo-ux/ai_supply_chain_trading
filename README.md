# AI Supply Chain Quantitative Trading System

**A quantitative trading system combining technical signals (Master Score), news sentiment analysis (FinBERT + event detection), and 3-state market regime detection (HMM) for weekly stock rebalancing.**

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env from .env.example
# Add: GOOGLE_API_KEY (or GEMINI_API_KEY), MARKETAUX_API_KEY, IBKR_PORT (optional), and others as needed
```

**Minimal install** (if full install fails, e.g. Python 3.14 + numba issues):
```bash
pip install pandas numpy pyyaml python-dotenv
pip install pandas-ta scikit-learn PyPortfolioOpt hmmlearn  # For backtest
```

**Run backtest** (Master Score, technical-only):
```bash
python scripts/backtest_technical_library.py \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3 \
    --start 2022-01-01 \
    --end 2022-12-31
```

**Backtest with regime detection**:
```bash
python scripts/backtest_technical_library.py \
    --weight-mode regime \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3
```

**Backtest with news overlay**:
```bash
python scripts/backtest_technical_library.py \
    --news-dir data/news \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3
```

---

## Deterministic Testing

**Verify reproducibility** before commits:

```bash
# Verify environment setup
python scripts/verify_environment.py

# If exit 0, run determinism tests:
python scripts/test_execution_parity.py --date 2024-01-08
python scripts/test_target_weight_regression.py
```

**Expected results:**
- **Parity:** Backtest and execution paths produce identical target weights (tolerance 1e-12)
- **Regression:** Target weights match snapshot in `contracts/target_weight_snapshot_2024-01-08.json`

**Pre-commit gate** (ensures backtest produces identical outputs on two runs):
```bash
# Linux/Mac
./scripts/check_spine_integrity.sh

# Windows (PowerShell)
.\scripts\check_spine_integrity.ps1
```

**Exit 0 = PASS, 1 = FAIL (do not merge)**

To re-pin versions: `pip freeze > requirements.txt`

---

## Project Structure

```
ai_supply_chain_trading/
├── config/
│   ├── data_config.yaml               # Data sources, paths, universe
│   ├── technical_master_score.yaml    # Master Score: category weights, indicators
│   ├── signal_weights.yaml            # Legacy composite signal weights
│   └── trading_config.yaml            # Execution settings (planned, not wired)
├── data/
│   ├── stock_market_data/             # CSV price data by source
│   │   ├── nasdaq/csv/
│   │   ├── sp500/csv/
│   │   ├── nyse/csv/
│   │   └── forbes2000/csv/
│   ├── news/                          # JSON news files per ticker
│   └── cache/                         # Gemini API cache, etc.
├── src/
│   ├── core/                          # Single spine architecture
│   │   ├── signal_engine.py           # Signal generation orchestration
│   │   ├── policy_engine.py           # Regime & policy gates
│   │   └── portfolio_engine.py        # Portfolio construction
│   ├── signals/
│   │   ├── technical_library.py       # Master Score (canonical)
│   │   ├── news_engine.py             # News Alpha (4 strategies)
│   │   ├── weight_model.py            # Dynamic weighting (regime/rolling/ml)
│   │   └── signal_combiner.py         # Legacy combined signals
│   ├── portfolio/
│   │   ├── sizing.py                  # Position sizing
│   │   └── position_manager.py        # Position tracking
│   ├── execution/                     # IBKR integration (exists, not wired)
│   └── data/                          # Data providers & fetchers
├── scripts/
│   └── backtest_technical_library.py  # Canonical backtest entry point
├── outputs/                           # Backtest results
├── logs/                              # Application logs
├── graveyard/                         # Archived legacy code (read-only)
└── wealth_signal_mvp_v1/              # Reference implementation (read-only)
```

---

## Canonical Documentation

**All docs in project root** (consolidated 2026-02-14):

| Document | Purpose |
|----------|---------|
| **ARCHITECTURE.md** | System design, data flow, module organization, key paths |
| **WORKFLOW.md** | Execution stages (what happens, in order) |
| **SYSTEM_MAP.md** | Code mapping (workflow → modules, entry points) |
| **STRATEGY_LOGIC.md** | Capital decision spine (how decisions are made) |
| **DECISIONS.md** | Architectural decision records (why choices were made) |
| **TECHNICAL_SPEC.md** | Indicator math, Master Score, News Alpha strategies |
| **BACKTEST_JOURNAL.md** | Execution assumptions, safety audits, results |
| **PROJECT_STATUS.md** | Current state, readiness assessment, action items |

**For AI agents:** See `AI_RULES.md` and `.cursorrules` for development guardrails.

---

## System Features

### Signal Generation

**Master Score (Technical):**
- 40% Trend (MACD, ADX, PSAR, Aroon, moving averages)
- 30% Momentum (Stochastic, CCI, Williams %R, ROC, RSI, momentum)
- 20% Volume (OBV, CMF, VWAP, volume ratio)
- 10% Volatility (Bollinger Bands, ATR, Keltner Channels)

**News Alpha (4 Strategies):**
- **A: Buzz** — Z-score of article volume (rising media attention)
- **B: Surprise** — Sentiment delta vs 30-day baseline (1-day lag)
- **C: Sector Relative** — Cross-sectional ranking within sector
- **D: Event-Driven** — Catalyst detection (earnings, M&A, FDA, etc.)

**Composite:** 80% technical + 20% news (configurable via `news_weight`)

### Dynamic Weighting

**Modes** (via `--weight-mode`):
- `fixed` — Static category weights from config
- `regime` — 3-State HMM (BULL/BEAR/SIDEWAYS) → adaptive weights
- `rolling` — PyPortfolioOpt (max_sharpe or HRP)
- `ml` — Random Forest + TimeSeriesSplit CV

### Risk Management

**3-State Regime (HMM):**
- **BULL** (high mean, low vol) → aggressive weights
- **BEAR** (low mean, high vol) → defensive weights + CASH_OUT if SPY < 200-SMA
- **SIDEWAYS** (mean ≈ 0) → balanced weights, position × 0.5

**Policy Gates:**
- Dual-confirmation kill-switch (BEAR + SPY < 200-SMA → 100% cash)
- Sideways scaling (position × 0.5 in choppy markets)
- Daily risk exit (≤ threshold → exit without reallocation)

### Execution Model

- **Weekly rebalance** (Mondays)
- **Next-Day Open execution** (no look-ahead)
- **Inverse-volatility sizing** (ATR from T−1)
- **Transaction costs:** 15 bps per trade
- **Mid-week exits** without reallocating to other positions

---

## Current Status

**Research Phase:** ✅ 95% Complete
- Canonical workflow end-to-end
- Master Score with dynamic weighting
- News Alpha overlay
- 3-state regime detection
- Backtest infrastructure validated

**Paper Trading:** ⚠️ 30% Complete
- IBKR components exist but not wired
- Need: orchestration script, fill reconciliation, scheduling

**Live Trading:** ⚠️ 20% Complete
- Same as paper + real-time data feeds, monitoring, safety limits

See **PROJECT_STATUS.md** for detailed readiness assessment and action items.

---

## Development Workflow

### For Developers

1. **Read canonical docs** (ARCHITECTURE → WORKFLOW → SYSTEM_MAP)
2. **Check operating mode** (currently P0 Fix Mode — see DECISIONS.md)
3. **Plan before coding** (see AI_RULES.md for guardrails)
4. **Search read-only folders** (graveyard/, wealth_signal_mvp_v1/) for reuse
5. **Run determinism tests** before committing

### For AI Agents

**Mandatory reading:**
- `AI_RULES.md` — development guardrails
- `.cursorrules` — Cursor-specific rules
- All 8 canonical docs in project root

**Critical rules:**
- Plan-first (never jump to coding)
- Interface freeze (no silent changes)
- Evidence discipline (cite file + symbol)
- Reuse-first (search graveyard/ and wealth_signal_mvp_v1/)

---

## Key Dependencies

**Core:**
- pandas, numpy, pyyaml, python-dotenv

**Technical indicators:**
- pandas-ta

**Dynamic weighting & regime:**
- PyPortfolioOpt (max_sharpe, HRP)
- hmmlearn (3-state Gaussian HMM)
- scikit-learn (Random Forest, TimeSeriesSplit)

**News Alpha:**
- transformers, ProsusAI/finbert (sentiment)
- spacy en_core_web_md (NER, event detection)
- python-Levenshtein (deduplication)

**Execution (planned):**
- ib_insync (IBKR TWS)

**Installation:**
```bash
pip install pandas-ta PyPortfolioOpt hmmlearn scikit-learn transformers spacy python-Levenshtein
python -m spacy download en_core_web_md
```

---

## Backtest Results

### Full Year 2022

| Metric | Strategy | SPY (benchmark) |
|--------|----------|-----------------|
| Sharpe Ratio | −0.75 | ~−0.72 |
| Total Return | −33.64% | ~−18.1% |
| Max Drawdown | −48.25% | ~−25.3% |

**Universe:** NVDA, AMD, TSM, AAPL, MSFT  
**Selection:** Top 3  
**Period:** Bear market year

See **BACKTEST_JOURNAL.md** for detailed results and safety audits.

---

## Known Limitations

1. **Single year validation:** 2022 only; need multi-year
2. **No position limits:** Single stock can get 100% weight
3. **Simple transaction costs:** 15 bps fixed; no dynamic slippage
4. **News dependency:** STOP if news ERROR (by design, see DECISIONS.md)
5. **No live feeds:** Historical data only
6. **No scheduling:** Manual runs only

---

## Next Steps

**High priority** (Week 1-2):
1. Create `run_paper_rebalance.py` orchestration script
2. Wire Phase 3 to weekly in-memory signals
3. Add audit logging to backtest runs
4. Enforce execution limits from config
5. Implement simple fill check

**Medium priority:**
6. Multi-year backtest (2020-2024)
7. Statistical validation (confidence intervals, p-values)
8. Parameter sensitivity sweep
9. Update regime ledger post-run
10. Wire ML pipeline to main flow

See **PROJECT_STATUS.md** for complete action items and two-week execution plan.

---

## Contributing

**Before making changes:**
1. Read `AI_RULES.md` (mandatory guardrails)
2. Load all canonical docs
3. Verify P0 Fix Mode constraints (DECISIONS.md)
4. Plan-first (never jump to coding)
5. Run determinism tests before committing

**Operating mode:** P0 Fix Mode (LOCKED)
- Only fix documented but broken features
- No new features or interface changes without approval

---

## License

[Your License Here]

---

**For questions or clarifications, consult the canonical documentation in project root.**
