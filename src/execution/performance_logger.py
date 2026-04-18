"""Execution-side hooks for performance / regime logging (re-exports signals module)."""
from __future__ import annotations

from src.signals.performance_logger import update_regime_ledger

__all__ = ["update_regime_ledger"]
