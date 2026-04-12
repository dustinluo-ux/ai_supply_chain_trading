# Strategy Vision — The Leopold State Machine

## Overview
The alpha_scout_pipeline implements a deterministic, three-phase capital allocation machine. Each phase is a distinct module. No phase can execute without receiving a cryptographically verified handoff from the prior phase. The lifecycle is immutable and append-only.

## The State Machine

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LEOPOLD STATE MACHINE                            │
│                                                                     │
│   Phase 1: DISCOVERY        Phase 2: VALIDATION    Phase 3: EXECUTION
│                                                                     │
│   ┌──────────────┐          ┌──────────────┐       ┌────────────┐  │
│   │   alpha_scout │──TDO──▶ │   Auditor    │──TDO─▶│   Pulse   │  │
│   │  (Exa + Gemini│ SCOUTED │ (SEC + Gemini │AUDITED│ (IBKR +  │  │
│   │   macro-blind)│         │  + TES Score)│       │  Regime)  │  │
│   └──────────────┘          └──────────────┘       └────────────┘  │
│          │                        │                      │         │
│          ▼                        ▼                      ▼         │
│      data/*.json            data/*.json           outputs/audit/   │
│      phase=SCOUTED          phase=AUDITED         phase=EXECUTED   │
│                                                                     │
│   BLOCKED if:               BLOCKED if:           BLOCKED if:      │
│   • < 3 findings            • 4+ core failures    • cap > $50B     │
│   • score < 0.30            • AUDIT_FAILED        • hash mismatch  │
│                                                   • regime=BEAR    │
│                                                   • age > 90 days  │
└─────────────────────────────────────────────────────────────────────┘
```

## Phase 1: Discovery (alpha_scout)
The Scout module is deliberately **macro-blind**. It does not know portfolio weights, regime state, or IBKR margin. Its sole function is to answer: *"Is there an emerging physical scarcity in this supply chain that the market hasn't priced yet?"*

- Input: A natural-language research query
- Process: Exa semantic search → Gemini synthesis → composite scoring
- Output: A SCOUTED TDO with `scout.*` fields populated
- Gate: Circuit breaker (≥3 findings, composite_score ≥ 0.30)

## Phase 2: Validation (Auditor)
The Auditor module is the **conviction filter**. It asks: *"Is this scarcity real, physical, and investable?"* It operates on company-level evidence — SEC filings, BOM decomposition, revenue concentration — not sentiment.

- Input: SCOUTED TDO from `data/`
- Process: BOM decomposition → SEC supply chain scraping → financial fetch → TES scoring → market cap check → SHA-256 seal
- Output: AUDITED TDO with `auditor.*` fields populated and `audit_hash` sealed
- Gate: Fails if 4+ core audit stages fail (BOM, supply chain, financial, TES)

## Phase 3: Execution (Pulse)
The Pulse module is the **macro-aware executor**. It asks: *"Is now the right time to deploy capital, and how much?"* It consults regime state, ML signals, and IBKR margin before submitting orders.

- Input: AUDITED TDO (execution gate: 7 checks)
- Process: Regime check → signal scoring → ML blend → portfolio construction → IBKR execution
- Output: Fill records, audit log, Telegram alert
- Gate: 7-check TDO execution gate (see RED_TEAM_CONSTRAINTS.md)

## Design Principles
1. **No backwards contamination** — Pulse cannot modify Scout output. TDOs are append-only.
2. **No skipping phases** — An AUDITED TDO cannot be created without passing through AUDIT_PENDING.
3. **Cryptographic integrity** — The SHA-256 `audit_hash` is verified at execution time. Any tampering halts the pipeline.
4. **Time-bounded validity** — A TDO is valid for 90 days. After that, re-audit is required.
5. **Single command** — `python pipeline_runner.py --query "..."` runs all three phases deterministically.
