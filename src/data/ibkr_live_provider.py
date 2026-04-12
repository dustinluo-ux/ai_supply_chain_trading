"""
Live IBKR account and snapshot pricing helpers (ib_insync).

Default connection parameters match ``config/trading_config.yaml`` → ``trading.ib``
(host, port, client_id). ``connect()`` takes explicit arguments so callers can
override; load YAML in the caller when you want file-driven settings.

This module is not imported elsewhere yet (standalone build).
"""
from __future__ import annotations

import sys
import time
from typing import Any

from ib_insync import IB, util

# IB account summary tag names → normalized keys returned by get_account_summary
_ACCOUNT_SUMMARY_TAGS: dict[str, str] = {
    "NetLiquidation": "net_liquidation",
    "AvailableFunds": "available_funds",
    "MaintMarginReq": "maint_margin_req",
    "InitMarginReq": "init_margin_req",
    "BuyingPower": "buying_power",
    "GrossPositionValue": "gross_position_value",
}

_SUMMARY_WAIT_S = 15.0
_POSITIONS_WAIT_S = 10.0
_SNAPSHOT_WAIT_S = 10.0


def _warn(msg: str) -> None:
    print(f"[IBKR][WARN] {msg}", file=sys.stderr)


def _float_from_ib_value(raw: Any) -> float:
    if raw is None or raw == "":
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _symbol_from_contract(contract: Any) -> str:
    sym = getattr(contract, "symbol", None) or ""
    if sym:
        return str(sym)
    loc = getattr(contract, "localSymbol", None)
    return str(loc or "")


def _price_from_ticker(ticker: Any) -> float | None:
    """Return last if valid, else close if valid, else marketPrice if valid."""
    for attr in ("last", "close"):
        v = getattr(ticker, attr, None)
        if v is not None and not util.isNan(v):
            return float(v)
    mp = ticker.marketPrice()
    if mp is not None and not util.isNan(mp):
        return float(mp)
    return None


def _historical_last_close(ib: IB, contract: Any, symbol: str) -> float | None:
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
            keepUpToDate=False,
        )
        if not bars:
            return None
        last = getattr(bars[-1], "close", None)
        if last is None or util.isNan(last):
            return None
        return float(last)
    except ConnectionError:
        raise
    except Exception as exc:
        _warn(f"{symbol}: historical fallback failed: {exc}")
        return None


def connect(host: str, port: int, client_id: int) -> IB:
    """
    Connect to TWS / IB Gateway. Caller must disconnect.

    Typical defaults (see ``config/trading_config.yaml`` → ``trading.ib``):
    host 127.0.0.1, port 7497 (paper) or 7496 (live), client_id 1.
    """
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=15)
    except ConnectionError:
        raise
    except Exception as exc:
        raise ConnectionError(
            f"Failed to connect to IBKR at {host}:{port} (clientId={client_id}): {exc}"
        ) from exc
    if not ib.isConnected():
        raise ConnectionError(
            f"Failed to connect to IBKR at {host}:{port} (clientId={client_id}): not connected after connect()"
        )
    return ib


def get_account_summary(ib: IB) -> dict[str, float]:
    """
    Return account summary fields as floats (display/sizing).

    Uses ib.accountValues() — synchronous, no request/cancel cycle needed.
    Falls back to a waitOnUpdate pass if the first read returns nothing.
    """
    out = {v: 0.0 for v in _ACCOUNT_SUMMARY_TAGS.values()}
    try:
        rows = ib.accountValues()
        if not rows:
            ib.waitOnUpdate(timeout=_SUMMARY_WAIT_S)
            rows = ib.accountValues()
        for row in rows:
            if row.tag in _ACCOUNT_SUMMARY_TAGS:
                key = _ACCOUNT_SUMMARY_TAGS[row.tag]
                out[key] = _float_from_ib_value(row.value)
        if not any(v > 0 for v in out.values()):
            _warn("account summary: all values zero — account may not be subscribed")
    except ConnectionError:
        raise
    except Exception as exc:
        _warn(f"account summary failed: {exc}")
    return out


def get_positions(ib: IB) -> list[dict[str, Any]]:
    """
    Return open positions from reqPositions().

    Each dict: symbol, position, avg_cost, market_value, asset_class.
    market_value uses snapshot last (or historical close) * position when possible.
    """
    result: list[dict[str, Any]] = []
    try:
        ib.reqPositions()
        ib.waitOnUpdate(timeout=_POSITIONS_WAIT_S)
    except ConnectionError:
        raise
    except Exception as exc:
        _warn(f"reqPositions failed: {exc}")
        return result

    try:
        for pos in ib.positions():
            contract = pos.contract
            symbol = _symbol_from_contract(contract)
            if not symbol:
                _warn("position with empty symbol skipped")
                continue
            qty = float(pos.position)
            avg_cost = float(pos.avgCost) if pos.avgCost is not None else 0.0
            sec_type = getattr(contract, "secType", None) or "UNKNOWN"
            px: float | None = None
            try:
                ticker = ib.reqMktData(contract, "", True, False)
                try:
                    ib.sleep(2)
                    px = _price_from_ticker(ticker)
                    if px is None:
                        px = _historical_last_close(ib, contract, symbol)
                finally:
                    try:
                        ib.cancelMktData(contract)
                    except ConnectionError:
                        raise
                    except Exception:
                        pass
            except ConnectionError:
                raise
            except Exception as exc:
                _warn(f"{symbol}: snapshot for market_value failed: {exc}")
                px = _historical_last_close(ib, contract, symbol)

            if px is None:
                market_value = 0.0
            else:
                market_value = qty * px

            result.append(
                {
                    "symbol": symbol,
                    "position": qty,
                    "avg_cost": avg_cost,
                    "market_value": float(market_value),
                    "asset_class": str(sec_type),
                }
            )
    except ConnectionError:
        raise
    except Exception as exc:
        _warn(f"get_positions iteration failed: {exc}")
    return result


def get_live_prices(ib: IB, contracts: list) -> dict[str, float]:
    """
    Snapshot market data per contract; map symbol -> last, else close, else hist close.

    Requests delayed market data (type 3 = 15-min delayed, free) so paper accounts
    without a live subscription still receive prices. Falls back to reqHistoricalData
    if the snapshot yields no usable price.

    Failed contracts are omitted; warnings go to stderr. Never raises for bad contracts.
    """
    prices: dict[str, float] = {}
    try:
        # 1=live, 2=frozen, 3=delayed, 4=delayed-frozen.
        # Delayed is free and works on paper accounts without a live data subscription.
        ib.reqMarketDataType(3)
    except Exception as exc:
        _warn(f"reqMarketDataType(3) failed: {exc}; continuing (prices may be unavailable)")

    for contract in contracts:
        symbol = _symbol_from_contract(contract)
        if not symbol:
            _warn("contract missing symbol; skipped")
            continue
        try:
            ticker = ib.reqMktData(contract, "", True, False)
            px: float | None = None
            try:
                # ib.sleep() drives the ib_insync event loop; updateEvent.wait() is
                # an eventkit pattern that does not work in synchronous (non-async) code.
                ib.sleep(2)
                px = _price_from_ticker(ticker)
                if px is None:
                    px = _historical_last_close(ib, contract, symbol)
            finally:
                try:
                    ib.cancelMktData(contract)
                except ConnectionError:
                    raise
                except Exception:
                    pass
            if px is None:
                _warn(f"{symbol}: no price from snapshot or historical; excluded")
                continue
            prices[symbol] = float(px)
        except ConnectionError:
            raise
        except Exception as exc:
            _warn(f"{symbol}: get_live_prices failed: {exc}")
    return prices
