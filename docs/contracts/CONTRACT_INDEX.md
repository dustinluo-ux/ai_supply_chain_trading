# Contract Index — AI Supply Chain Trading System

All module contracts live in `docs/contracts/`. This index is the source of truth for module status.

| Module | Status | Upstream | Downstream | Contract |
|--------|--------|----------|------------|---------|
| core | draft | data, signals | portfolio, execution | — |
| data | draft | external APIs, DATA_DIR | core, signals, fundamentals | — |
| signals | draft | data | core | — |
| fundamentals | draft | data (FMP, EDGAR) | core | — |
| portfolio | draft | core, signals | execution | — |
| execution | draft | portfolio | outputs/ (fills, weights) | — |
| models | draft | data | core | — |
| risk | draft | core, portfolio | execution | — |
| monitoring | draft | all modules | logs/ | — |
| hedging | draft | portfolio, risk | execution | — |
| agents | draft | signals, core | portfolio | — |
| utils | draft | — | all modules | — |
| scripts | draft | all src modules | outputs/, config/ | — |

## Notes

- All modules are `draft` — contracts have not been formally written yet.
- To formalize a contract, create `docs/contracts/<module>.md` using the template at `docs/contracts/CONTRACT_TEMPLATE.md` and update the Status and Contract columns here.
- `Status` lifecycle: `draft` → `approved` → `implemented` → `deprecated`
