# Documentation Index

**Last Updated:** 2026-01-29

**Single entry point:** [INDEX.md](INDEX.md) — use it to find where each topic lives and avoid overlapping docs.

---

## Start Here

| Doc | Purpose |
|-----|--------|
| [INDEX.md](INDEX.md) | **Entry point:** list of all canonical and active docs, archive, logs. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Target architecture (4 pillars, data flow, principles). |
| [MULTI_SOURCE_QUANT_PIPELINE_PLAN.md](MULTI_SOURCE_QUANT_PIPELINE_PLAN.md) | Build plan (phases A–E), porting, what we are not changing. |

This documentation is organized into 6 canonical documents:

### 1. [SYSTEM_SPEC.md](SYSTEM_SPEC.md)
**What the system is and how to run it**
- System architecture
- How to run backtest/paper/live
- Configuration files
- Current limitations

### 2. [STRATEGY_MATH.md](STRATEGY_MATH.md)
**Signals, formulas, weights, ranking, portfolio logic**
- Signal generation formulas
- Signal combination
- Portfolio construction
- Performance metrics

### 3. [DATA.md](DATA.md)
**Price/news sources, disk/cache handling, dataset workflow**
- Price data sources
- News data (FNSPID)
- Cache management
- Data quality checks

### 4. [EXECUTION_IB.md](EXECUTION_IB.md)
**IB integration, mode switching, config, safety notes**
- IB setup
- Data provider/executor abstractions
- Configuration
- Safety notes

### 5. [SUPPLY_CHAIN_DB.md](SUPPLY_CHAIN_DB.md)
**Database schema, freshness, incremental updates, research queue**
- Database structure
- Building/expanding database
- Freshness tracking
- Research queue

### 6. [CHANGELOG_BUGFIXES.md](CHANGELOG_BUGFIXES.md)
**Key fixes and behavioral changes**
- Recent bug fixes
- Behavioral changes
- Known issues

---

## Quick Reference

**Run backtest:**
```bash
python test_signals.py --universe-size 15 --top-n 10
```

**Configuration:**
- `config/signal_weights.yaml` - Signal weights
- `config/data_config.yaml` - Data paths
- `config/trading_config.yaml` - Trading config (exists but unused)

**Data:**
- Price: `data/prices/` (CSV files)
- News: `data/news/` (JSON files)
- Cache: `data/cache/` (Gemini API cache)
- Supply chain DB: `data/supply_chain_relationships.json`

---

## Archive

Older documentation has been moved to `docs/archive/` for reference.

---

**Questions?** Check the relevant canonical doc above.
