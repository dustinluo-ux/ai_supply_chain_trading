Contract: regime ledger persistence

Requirement:
update_regime_ledger(regime, strategy_id, weekly_return, weekly_drawdown)
must be called from canonical research spine.

Definition of done:
- Called once per completed backtest run.
- Writes to data/logs/regime_ledger.csv.
- No duplicate rows per week.
- No call during dry-run modes.
