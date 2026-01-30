# Documentation Index

**Last Updated:** 2026-01-29

Single entry point for project documentation. Use this file to find where each topic lives; avoid creating overlapping docs.

---

## Start here

| Doc | Purpose |
|-----|--------|
| [README.md](README.md) | Doc index and quick reference (run commands, config paths). |
| [ARCHITECTURE.md](ARCHITECTURE.md) | **Target architecture:** 4 pillars, data flow, legacy vs new sources, principles. |
| [MULTI_SOURCE_QUANT_PIPELINE_PLAN.md](MULTI_SOURCE_QUANT_PIPELINE_PLAN.md) | Detailed build plan (phases A–E), what to port, what we are not changing. |

---

## Canonical reference docs (one topic each)

| Doc | Topic |
|-----|--------|
| [SYSTEM_SPEC.md](SYSTEM_SPEC.md) | What the system does, how to run, execution flow, limitations. |
| [STRATEGY_MATH.md](STRATEGY_MATH.md) | Signal formulas, combination, portfolio logic, metrics. |
| [DATA.md](DATA.md) | Price/news sources, paths (prices, raw, news), cache, FNSPID, validation. |
| [EXECUTION_IB.md](EXECUTION_IB.md) | IB setup, data provider/executor, config, safety. |
| [SUPPLY_CHAIN_DB.md](SUPPLY_CHAIN_DB.md) | Supply chain DB schema, build, freshness, research queue. |
| [CHANGELOG_BUGFIXES.md](CHANGELOG_BUGFIXES.md) | Recent fixes and behavioral changes. |

---

## Other active docs

| Doc | Purpose |
|-----|--------|
| [SEAMLESS_DATA_LOGIC_REVIEW.md](SEAMLESS_DATA_LOGIC_REVIEW.md) | Data schema and gap-fill logic (historical vs live). |
| [CONFIG_AUDIT.md](CONFIG_AUDIT.md) | Config file audit. |
| [DOCUMENTATION_AUDIT.md](DOCUMENTATION_AUDIT.md) | Doc audit. |
| [PROJECT_STATUS_2026-01-28.md](PROJECT_STATUS_2026-01-28.md) | Snapshot status. |
| [RESEARCH_QUEUE.txt](RESEARCH_QUEUE.txt) | Active research queue. |

---

## Archive

Older docs are in **`docs/archive/`**. They are kept for reference only; canonical docs above are the source of truth. When adding new content, add it to the appropriate canonical doc or to ARCHITECTURE / plan; do not add new one-off status docs.

---

## Logs and tests

- **Logs:** `logs/` (e.g. `logs/ai_supply_chain_YYYYMMDD.log`). Set via `src.utils.logger.setup_logger()`.
- **Backtest logs:** `outputs/backtest_log_*.txt` (when used by scripts).
- New scripts and tests should call `setup_logger()` so runs are recorded to file.
