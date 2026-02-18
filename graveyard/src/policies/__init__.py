"""Trading policies for entry and exit signals."""
from src.policies.exit_policies import (
    FixedThresholdPolicy,
    TrailingStopPolicy
)
from src.policies.signal_mapper import map_signals_to_trades

__all__ = [
    'FixedThresholdPolicy',
    'TrailingStopPolicy',
    'map_signals_to_trades'
]
