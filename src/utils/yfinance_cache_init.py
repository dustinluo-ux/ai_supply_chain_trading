"""
yfinance cache initialization to avoid SQLite crashes on first use.

Call init_yfinance_cache() once at pipeline start (e.g. in run scripts or main).
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger("ai_supply_chain")


def init_yfinance_cache(cache_dir: str = None) -> str:
    """
    Initialize yfinance cache directory so first use does not trigger SQLite issues.

    If cache_dir is None, uses project data/cache/yfinance or env YFINANCE_CACHE_DIR.

    Returns:
        Path to cache directory used.
    """
    if cache_dir is None:
        cache_dir = os.environ.get("YFINANCE_CACHE_DIR")
    if cache_dir is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        cache_dir = str(project_root / "data" / "cache" / "yfinance")
    os.makedirs(cache_dir, exist_ok=True)
    # Trigger a minimal yfinance import so cache is primed (optional)
    try:
        import yfinance as yf
        if hasattr(yf, "set_tz_cache_location"):
            yf.set_tz_cache_location(cache_dir)
    except Exception as e:
        logger.debug(f"yfinance cache init: {e}")
    logger.info(f"yfinance cache dir: {cache_dir}")
    return cache_dir
