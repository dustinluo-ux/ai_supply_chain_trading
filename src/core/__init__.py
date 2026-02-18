"""
Core layer: single call spine for research and execution.
PolicyEngine, PortfolioEngine, Intent, types, target_weight_pipeline.

NOTE: SignalEngine lives in src.signals.signal_engine (not re-exported here
to avoid circular import through src.core.types).
"""
from src.core.intent import Intent
from src.core.policy_engine import PolicyEngine
from src.core.portfolio_engine import PortfolioEngine
from src.core.target_weight_pipeline import compute_target_weights
from src.core.types import Context, DataContext

__all__ = [
    "Context",
    "DataContext",
    "Intent",
    "PolicyEngine",
    "PortfolioEngine",
    "compute_target_weights",
]
