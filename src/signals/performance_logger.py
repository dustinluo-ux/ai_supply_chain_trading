"""
Performance logger: record strategy performance (Return, Drawdown, Regime, news_weight_used)
at the end of every backtest week into a persistent CSV for AdaptiveSelector.
Also maintains regime_ledger.csv for strategy "memory" and Sortino-based audit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

CSV_COLUMNS = ["week_date", "return", "drawdown", "regime", "news_weight_used"]

# Regime ledger: persistent memory by market state (for audit_past_performance / Historical Amnesia prevention)
REGIME_LEDGER_COLUMNS = ["Timestamp", "Regime", "Strategy_ID", "Return", "Max_Drawdown"]
_DEFAULT_LEDGER_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "logs"


def _default_ledger_path() -> Path:
    return _DEFAULT_LEDGER_DIR / "regime_ledger.csv"


def ensure_header(csv_path: Path) -> None:
    """Create CSV with header if file does not exist."""
    if not csv_path.exists():
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=CSV_COLUMNS).to_csv(csv_path, index=False, encoding="utf-8")


def append_row(
    csv_path: Path,
    week_date: str | pd.Timestamp,
    return_pct: float,
    drawdown: float,
    regime: Optional[str] = None,
    news_weight_used: float = 0.0,
) -> None:
    """
    Append one row to the performance CSV.
    week_date: end of week (e.g. Friday or Monday of rebalance).
    return_pct: weekly return (e.g. 0.01 for 1%).
    drawdown: max drawdown over that week (negative, e.g. -0.02).
    regime: BULL / BEAR / SIDEWAYS or None.
    news_weight_used: news weight used that week (e.g. 0.2).
    """
    ensure_header(csv_path)
    row = pd.DataFrame(
        [{
            "week_date": pd.to_datetime(week_date).strftime("%Y-%m-%d"),
            "return": float(return_pct),
            "drawdown": float(drawdown),
            "regime": regime if regime is not None else "",
            "news_weight_used": float(news_weight_used),
        }]
    )
    row.to_csv(csv_path, mode="a", header=False, index=False, encoding="utf-8")


def ensure_regime_ledger_header(ledger_path: Path) -> None:
    """Create regime_ledger.csv with headers if it does not exist."""
    if not ledger_path.exists():
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=REGIME_LEDGER_COLUMNS).to_csv(ledger_path, index=False, encoding="utf-8")


def update_regime_ledger(
    regime: str,
    combination_id: str,
    weekly_return: float,
    weekly_drawdown: float,
    ledger_path: Optional[Path] = None,
    timestamp: Optional[datetime] = None,
) -> None:
    """
    Append one row to data/logs/regime_ledger.csv for strategy "memory" by market state.
    Columns: Timestamp, Regime, Strategy_ID, Return, Max_Drawdown.
    Creates the CSV with headers if it does not exist.
    """
    path = Path(ledger_path) if ledger_path is not None else _default_ledger_path()
    ensure_regime_ledger_header(path)
    ts = timestamp or datetime.now(timezone.utc)
    if hasattr(ts, "isoformat"):
        ts_str = ts.isoformat()
    else:
        ts_str = pd.Timestamp(ts).isoformat()
    row = pd.DataFrame(
        [{
            "Timestamp": ts_str,
            "Regime": str(regime).strip(),
            "Strategy_ID": str(combination_id).strip(),
            "Return": float(weekly_return),
            "Max_Drawdown": float(weekly_drawdown),
        }]
    )
    row.to_csv(path, mode="a", header=False, index=False, encoding="utf-8")
