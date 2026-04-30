# Case Facts — AI Supply Chain Trading System

<!--
Subagents must prepend this file verbatim to their context — no summarizing, no paraphrasing.
Source of truth for project identity, decisions made, and constraints in force.
-->

## Project Identity

**Name:** ai_supply_chain_trading
**One-line description:** Autonomous end-to-end quantitative trading pipeline: dynamic data ingestion → rolling ML training → OOS backtest → portfolio construction → autonomous parameter optimization → scheduled re-runs.
**Owner:** dustinluo@gmail.com
**Initialized:** 2026-04-30 (factory alignment retroactive)

## Business Context

Single-developer quantitative trading system targeting supply-chain-exposed equities, futures (NQ/MNQ), and options (SMH). The system autonomously refreshes data, trains a rolling ML model on a 4-year window, runs OOS backtests, constructs a portfolio via HRP + ATR with a hard position cap, and promotes the winning parameter set to a live config. Execution connects to IBKR via ib_insync for paper and live trading. The optimizer runs on a weekly Windows Task Scheduler schedule with no manual intervention between data refresh and config promotion.

## Decisions Made (binding)

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | Python environment: `wealth` conda env | Matches existing Anaconda setup; all scripts use absolute path `C:\Users\dusro\anaconda3\envs\wealth\python.exe` | pre-2026 |
| 2 | Trading data outside repo at `C:\ai_supply_chain_trading\trading_data\` | Avoids OneDrive sync of large parquet/CSV files; scripts read via `DATA_DIR` env var | pre-2026 |
| 3 | No historical news before 2025 | No usable backfill available; pre-2025 `news_supply`/`news_sentiment` default to 0.5 (neutral) | pre-2026 |
| 4 | Tiingo for 2025-present news; Marketaux for live weekly rebalance | Tiingo has valid publication dates; Marketaux flat files are operational source | pre-2026 |
| 5 | Atomic writes everywhere | All output files written via `.tmp` → validate → `os.replace()` — Windows NTFS lock safety | pre-2026 |
| 6 | IBKR via ib_insync; paper port 7497 | Established broker integration; paper mode requires TWS running | pre-2026 |
| 7 | R&D capitalized over 20 quarters (5-year straight-line) | Treats R&D as investment-like for FCFF calculation | pre-2026 |
| 8 | Agents intentionally NOT repo-local (pipeline agents copied 2026-04-30) | Single developer, same machine; pipeline agents now in `.claude/agents/` | 2026-04-30 |

## Open Questions (human-gate required)

| # | Question | Why it matters |
|---|----------|---------------|
| 1 | Real-time streaming prices (currently snapshots) | Required before going fully live; not implemented yet |
| 2 | First live paper run validation | Requires TWS running; deferred |

## Key Constraints

- **Data sources approved:** Tiingo (news 2025+), Marketaux (live rebalance), EODHD (backfill + non-US prices), FMP (fundamentals), SEC EDGAR (10-K XBRL audit), Yahoo Finance (price fallback)
- **APIs approved:** TIINGO_API_KEY, GOOGLE_API_KEY/GEMINI_API_KEY, MARKETAUX_API_KEY, EODHD_API_KEY, FMP_API_KEY, EDGAR_IDENTITY
- **History / training window:** Rolling 4 years; train_start = today − 4yr, train_end = today − 365d, test = train_end → today. `model_config.yaml` is machine-written — never edit dates by hand.
- **Budget ceiling:** Not set
- **Compliance requirements:** SEC EDGAR requires user-agent identification via `EDGAR_IDENTITY` env var

## Out of Scope (explicit)

- Real-time streaming prices (snapshot-only until explicitly approved)
- Multi-account or multi-user support
- Non-IBKR brokers
- Cryptocurrency or non-equity asset classes beyond NQ/MNQ futures and SMH options
- Any external paid service adoption without explicit user approval
