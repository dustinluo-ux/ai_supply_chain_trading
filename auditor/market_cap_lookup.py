"""
Auditor — Market Cap Lookup
Resolves ticker (or company name stub) to market cap in USD via yfinance.
Used for cap_rule_passed: market_cap_usd < 50_000_000_000.
Never raises; returns None on any exception or when company name cannot be resolved.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "auditor_config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_market_cap_usd(ticker_or_company: str) -> float | None:
    """
    Return market cap in USD for a ticker symbol, or None if not found / not a ticker.

    1. If input looks like a ticker (≤ 5 chars, uppercase or uppercased): try yfinance.
    2. Else: return None (stub for company name → ticker resolution); log a warning.

    Never raises — returns None on any exception.
    """
    if not ticker_or_company or not isinstance(ticker_or_company, str):
        logger.warning("market_cap_lookup: empty or invalid input → None")
        return None
    _cfg = _load_config()
    ticker_max_length = _cfg.get("ticker_max_length", 5)
    s = ticker_or_company.strip().upper()
    # Ticker heuristic: ≤ ticker_max_length chars, alphabetic (or with dots for some symbols)
    looks_like_ticker = len(s) <= ticker_max_length and s.isalpha()
    if not looks_like_ticker:
        logger.warning(
            "market_cap_lookup: %s does not look like a ticker (company name resolution stub) → None",
            ticker_or_company[:40],
        )
        return None
    try:
        import yfinance as yf
        info = yf.Ticker(s).info
        value = info.get("marketCap")
        if value is not None:
            logger.info("market_cap_lookup: %s → %s", s, value)
            return float(value)
        logger.info("market_cap_lookup: %s → None (not found)", s)
        return None
    except Exception as exc:
        logger.warning(
            "market_cap_lookup: %s → None (%s: %s)",
            s,
            type(exc).__name__,
            exc,
        )
        return None
