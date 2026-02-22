"""
Fetch account NetLiquidation from IBKR paper account via ib_insync.
Returns float NAV on success, None on any failure (TWS not running, timeout, etc.).
Caller decides how to handle None (use last_nav fallback from portfolio_state.json).
"""
from __future__ import annotations

import os


def fetch_nav(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 20,
    timeout: float = 10,
) -> float | None:
    """
    Connect to TWS, read NetLiquidation for the paper account, disconnect.
    client_id=20 to avoid conflicts with existing connections (run_execution uses other IDs).
    Returns float or None.
    """
    try:
        import nest_asyncio
        nest_asyncio.apply()
        from ib_insync import IB
        from src.utils.client_id_rotation import next_client_id
        ib = IB()
        ib.connect(host, port, clientId=next_client_id(), timeout=timeout)
        account = os.getenv("IBKR_PAPER_ACCOUNT") or ""
        vals = ib.accountValues()
        ib.disconnect()
        # Prefer BASE currency (account's native denomination); fall back to first match
        base_nav = None
        first_nav = None
        for v in vals:
            if v.tag == "NetLiquidation":
                if account and v.account != account:
                    continue
                if v.currency == "BASE":
                    base_nav = float(v.value)
                elif first_nav is None and v.currency not in ("", None):
                    first_nav = float(v.value)
        return base_nav if base_nav is not None else first_nav
    except Exception:
        return None
