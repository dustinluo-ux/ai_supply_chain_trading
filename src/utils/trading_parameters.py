"""
Trading Parameters Manager — DEPRECATED.

Legacy CSV-based watchlist/parameter loader.
Superseded by ``src.utils.config_manager.ConfigManager`` which reads YAML configs.

This thin wrapper exists for backward compatibility only.
New code should use ``ConfigManager`` directly.
"""
from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

from src.utils.config_manager import get_config

_DEPRECATION_MSG = (
    "TradingParameters is deprecated. "
    "Use src.utils.config_manager.ConfigManager instead."
)


class TradingParameters:
    """
    Deprecated thin wrapper around ConfigManager.

    All parameters now come from YAML configs
    (``config/data_config.yaml``, ``config/strategy_params.yaml``, etc.).
    """

    def __init__(
        self,
        base_path: Optional[str] = None,
        assets_dir: Optional[str] = None,
    ) -> None:
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        self._cfg = get_config()

    # ------------------------------------------------------------------
    # Watchlist (was CSV-based, now reads data_config.yaml)
    # ------------------------------------------------------------------
    @property
    def watchlist_symbols(self) -> List[str]:
        """Return the canonical watchlist from data_config.yaml."""
        return self._cfg.get_watchlist()

    # ------------------------------------------------------------------
    # Generic parameter access
    # ------------------------------------------------------------------
    def get_param(self, key: str, default: Any = None) -> Any:
        """Proxy to ConfigManager.get_param with a default."""
        return self._cfg.get_param(key, default)

    # ------------------------------------------------------------------
    # Legacy convenience methods (return safe defaults)
    # ------------------------------------------------------------------
    @property
    def parameters(self) -> Dict[str, Any]:
        """Return an empty dict — parameters are now in YAML."""
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        return {}

    def get_assets_by_type(self, asset_type: str) -> List[str]:
        """Deprecated. Returns empty list."""
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        return []

    def get_asset_params(self, symbol: str) -> Dict[str, Any]:
        """Deprecated. Returns empty dict."""
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        return {}

    def get_timeframe(self, symbol: str) -> str:
        """Deprecated. Returns execution.default_timeframe from strategy_params."""
        return str(
            self._cfg.get_param(
                "strategy_params.execution.default_timeframe", "1d"
            )
        )

    def get_rolling_window(self, symbol: str) -> str:
        """Deprecated. Returns warmup.rolling_normalization from strategy_params."""
        return str(
            self._cfg.get_param(
                "strategy_params.warmup.rolling_normalization", "252"
            )
        )
