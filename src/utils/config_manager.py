"""
Centralized Configuration Manager.

Loads and merges the three canonical YAML config files:
  - config/data_config.yaml        (data paths, watchlist, universe)
  - config/technical_master_score.yaml  (indicator weights, news_weight)
  - config/strategy_params.yaml    (propagation, warmup, execution)

Provides:
  - get_param(dotted_key, default)  — deep lookup with dotted keys
  - get_watchlist()                 — shortcut for universe_selection.watchlist

Per AI_RULES.md §10.4: if a required key is missing and no default is
supplied, raises KeyError with an explanation of which YAML file to update.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Project root: src/utils/config_manager.py -> utils -> src -> project_root
_ROOT = Path(__file__).resolve().parent.parent.parent

# Canonical config files (AI_RULES.md §10.2)
_CONFIG_FILES = {
    "data_config": _ROOT / "config" / "data_config.yaml",
    "technical_master_score": _ROOT / "config" / "technical_master_score.yaml",
    "strategy_params": _ROOT / "config" / "strategy_params.yaml",
    "trading_config": _ROOT / "config" / "trading_config.yaml",
}

_SENTINEL = object()  # distinguishes "no default" from None


class ConfigManager:
    """
    Unified, read-only view over the three canonical YAML configs.

    Usage::

        cfg = ConfigManager()
        news_w = cfg.get_param("technical_master_score.news_weight")
        min_days = cfg.get_param("strategy_params.warmup.min_required_days")
        tickers = cfg.get_watchlist()
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def _load_all(self) -> None:
        """Load (or reload) all canonical YAML files into the cache."""
        for name, path in _CONFIG_FILES.items():
            if path.exists():
                self._cache[name] = self._read_yaml(path)
                logger.debug("ConfigManager loaded %s (%d keys)", name, len(self._cache[name]))
            else:
                logger.warning("ConfigManager: %s not found at %s", name, path)
                self._cache[name] = {}

    @staticmethod
    def _read_yaml(path: Path) -> dict:
        import yaml

        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_param(self, dotted_key: str, default: Any = _SENTINEL) -> Any:
        """
        Retrieve a parameter using a dotted key path.

        The first segment is the config-file name (without .yaml), followed
        by nested keys.

        Examples::

            cfg.get_param("strategy_params.warmup.min_required_days")
            cfg.get_param("technical_master_score.news_weight")
            cfg.get_param("data_config.universe_selection.watchlist")

        Raises ``KeyError`` when the key is missing and no *default* is
        given (AI_RULES.md §10.4).
        """
        parts = dotted_key.split(".")
        if len(parts) < 2:
            if default is not _SENTINEL:
                return default
            raise KeyError(
                f"ConfigManager: key '{dotted_key}' must be prefixed with a "
                f"config file name ({', '.join(_CONFIG_FILES)})"
            )

        file_key = parts[0]
        remainder = parts[1:]

        cfg = self._cache.get(file_key)
        if cfg is None:
            if default is not _SENTINEL:
                return default
            raise KeyError(
                f"ConfigManager: config file '{file_key}' not loaded. "
                f"Expected YAML at {_CONFIG_FILES.get(file_key, 'UNKNOWN')}"
            )

        node: Any = cfg
        for i, segment in enumerate(remainder):
            if not isinstance(node, dict) or segment not in node:
                if default is not _SENTINEL:
                    return default
                traversed = ".".join([file_key] + remainder[: i + 1])
                raise KeyError(
                    f"ConfigManager: key '{traversed}' not found. "
                    f"Add '{segment}' to {_CONFIG_FILES[file_key]}"
                )
            node = node[segment]
        return node

    def get_watchlist(self) -> list[str]:
        """
        Return the watchlist from ``data_config.yaml → universe_selection.watchlist``.

        Raises ``KeyError`` if the key is missing (AI_RULES.md §10.4).
        """
        wl = self.get_param("data_config.universe_selection.watchlist")
        if not isinstance(wl, list):
            raise KeyError(
                "ConfigManager: 'universe_selection.watchlist' in "
                "config/data_config.yaml must be a list of ticker strings"
            )
        return [str(t) for t in wl]


# ------------------------------------------------------------------
# Module-level singleton for convenience
# ------------------------------------------------------------------
_instance: ConfigManager | None = None


def get_config() -> ConfigManager:
    """Return (and lazily create) the module-level ConfigManager singleton."""
    global _instance
    if _instance is None:
        _instance = ConfigManager()
    return _instance
