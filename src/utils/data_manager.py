"""
Resolve canonical data paths by key. Uses DATA_DIR from src.core.config.
"""
from pathlib import Path

from src.core.config import DATA_DIR

_PATH_MAP = {
    "news": DATA_DIR / "news",
    "prices": DATA_DIR / "prices",
    "extractions": DATA_DIR / "extractions",
    "raw": DATA_DIR / "raw",
}


def get_path(key: str) -> Path:
    """Return the Path for a given key. Raises KeyError with a clear message on unknown key."""
    if key not in _PATH_MAP:
        raise KeyError(f"Unknown data key: {key!r}. Known keys: {list(_PATH_MAP.keys())}")
    return _PATH_MAP[key]


class DataManager:
    """Convenience class for resolving canonical data paths by key."""

    @staticmethod
    def get_path(key: str) -> Path:
        """Return the Path for a given key. Raises KeyError with a clear message on unknown key."""
        return get_path(key)
