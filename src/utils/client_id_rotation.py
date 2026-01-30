"""
Client ID rotation for IBKR connections.

Uses IBKR_CLIENT_ID_START from env (default 99) and rotates 99, 100, 101, ...
to avoid conflicts when multiple connections (data + execution) are used.
"""
import os
import threading
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger()

# Default start from .env or 99
_DEFAULT_START = 99
_lock = threading.Lock()
_next_id: Optional[int] = None


def _get_start() -> int:
    try:
        v = os.environ.get("IBKR_CLIENT_ID_START", str(_DEFAULT_START))
        return int(v)
    except ValueError:
        return _DEFAULT_START


def next_client_id() -> int:
    """
    Return next client ID for IBKR (99, 100, 101, ...).

    Thread-safe. Reads IBKR_CLIENT_ID_START from env (default 99).
    """
    global _next_id
    with _lock:
        if _next_id is None:
            _next_id = _get_start()
        cid = _next_id
        _next_id += 1
        # Wrap after 900 to avoid huge IDs (99–998)
        if _next_id > 998:
            _next_id = _get_start()
    logger.debug(f"IBKR client_id assigned: {cid}")
    return cid


def reset_client_id_sequence():
    """Reset the sequence to start again from IBKR_CLIENT_ID_START (for tests)."""
    global _next_id
    with _lock:
        _next_id = None
