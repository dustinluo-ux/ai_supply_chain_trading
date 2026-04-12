"""
Resolve ib_insync contracts from config/instruments.yaml (equity, future, option).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml
from ib_insync import Contract, Future, Option, Stock

_INSTRUMENTS_FILENAME = "instruments.yaml"


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / _INSTRUMENTS_FILENAME


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid instruments config (expected mapping): {path}")
    return data


def _parse_expiry_to_date(raw: str) -> dt.date | None:
    s = str(raw).strip().split()[0]
    if not s:
        return None
    for fmt, ln in (("%Y%m%d", 8), ("%Y%m", 6)):
        if len(s) >= ln:
            try:
                d = dt.datetime.strptime(s[:ln], fmt).date()
                if fmt == "%Y%m":
                    # last calendar day of month
                    nxt = d.replace(day=28) + dt.timedelta(days=4)
                    return nxt - dt.timedelta(days=nxt.day)
                return d
            except ValueError:
                continue
    return None


def _dte(expiry_date: dt.date, today: dt.date) -> int:
    return (expiry_date - today).days


def _resolve_equity(
    full_cfg: dict[str, Any],
    symbol: str,
    ib: Any,
    instruments_path: Path,
) -> Stock:
    eq = full_cfg.get("equities") or {}
    if not isinstance(eq, dict):
        raise ValueError("instruments.yaml: missing or invalid 'equities' block")
    exchange = str(eq.get("exchange", "SMART"))
    currency = str(eq.get("currency", "USD"))
    if eq.get("use_watchlist"):
        dc_path = instruments_path.parent / "data_config.yaml"
        if not dc_path.exists():
            raise ValueError(f"use_watchlist is true but data_config not found: {dc_path}")
        with open(dc_path, encoding="utf-8") as f:
            dc = yaml.safe_load(f) or {}
        wl = (dc.get("universe_selection") or {}).get("watchlist") or []
        if symbol not in wl:
            raise ValueError(
                f"equity symbol {symbol!r} not in data_config universe_selection.watchlist"
            )
    c = Stock(symbol, exchange, currency)
    qc = ib.qualifyContracts(c)
    if not qc:
        raise ValueError(f"qualifyContracts failed for equity {symbol!r} ({exchange}, {currency})")
    return qc[0]


def _future_expiry_key(contract: Any) -> str:
    return str(getattr(contract, "lastTradeDateOrContractMonth", "") or "").strip().split()[0]


def _resolve_future(full_cfg: dict[str, Any], symbol: str, ib: Any) -> Future:
    fut_root = full_cfg.get("futures") or {}
    if symbol not in fut_root or not isinstance(fut_root[symbol], dict):
        raise ValueError(f"future symbol {symbol!r} not in instruments.yaml futures block")
    fc: dict[str, Any] = fut_root[symbol]
    exchange = str(fc.get("exchange", "CME"))
    currency = str(fc.get("currency", "USD"))
    front_month_offset = int(fc.get("front_month_offset", 1))
    roll_warning_dte = int(fc.get("roll_warning_dte", 5))
    if front_month_offset < 1:
        raise ValueError("front_month_offset must be >= 1")

    probe = Future(symbol=symbol, exchange=exchange, currency=currency)
    details = ib.reqContractDetails(probe)
    if not details:
        raise ValueError(f"reqContractDetails returned no contracts for future {symbol!r}")

    # Unique expiries ascending (preserve first detail per expiry for full contract template)
    seen: dict[str, Any] = {}
    for d in details:
        c = d.contract
        key = _future_expiry_key(c)
        if not key:
            continue
        if key not in seen:
            seen[key] = c

    sorted_keys = sorted(seen.keys())
    if len(sorted_keys) < front_month_offset:
        raise ValueError(
            f"future {symbol!r}: only {len(sorted_keys)} expiries available; "
            f"need at least {front_month_offset} for front_month_offset"
        )
    chosen_key = sorted_keys[front_month_offset - 1]
    chosen = seen[chosen_key]

    exp_date = _parse_expiry_to_date(chosen_key)
    today = dt.date.today()
    if exp_date is not None:
        dte = _dte(exp_date, today)
        if dte < roll_warning_dte:
            print(
                f"[CONTRACT][WARN] {symbol} futures: {dte} DTE — approaching roll date.",
                flush=True,
            )

    qc = ib.qualifyContracts(chosen)
    if not qc:
        raise ValueError(f"qualifyContracts failed for future {symbol!r} expiry {chosen_key!r}")
    return qc[0]


def _normalize_right(cfg_right: Any) -> str:
    if isinstance(cfg_right, list) and cfg_right:
        r = str(cfg_right[0]).strip().upper()
    else:
        r = str(cfg_right or "C").strip().upper()
    if r not in ("C", "P"):
        raise ValueError(f"invalid option right in config: {cfg_right!r}")
    return r


def _underlying_mid(ib: Any, stock: Stock) -> float:
    t = ib.reqMktData(stock, "", True, False)
    try:
        if hasattr(t, "updateEvent"):
            t.updateEvent.wait(10.0)
        else:
            ib.sleep(0.2)
        bid = getattr(t, "bid", None)
        ask = getattr(t, "ask", None)
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            return float((bid + ask) / 2.0)
        mp = t.marketPrice()
        if mp is not None and mp > 0:
            return float(mp)
        last = getattr(t, "last", None)
        if last is not None and last > 0:
            return float(last)
    finally:
        try:
            ib.cancelMktData(stock)
        except Exception:
            pass
    raise ValueError("could not obtain underlying mid price for option resolution")


def _resolve_option(full_cfg: dict[str, Any], symbol: str, ib: Any) -> Option:
    opt_root = full_cfg.get("options") or {}
    if symbol not in opt_root or not isinstance(opt_root[symbol], dict):
        raise ValueError(f"option symbol {symbol!r} not in instruments.yaml options block")
    oc: dict[str, Any] = opt_root[symbol]
    exchange = str(oc.get("exchange", "SMART"))
    currency = str(oc.get("currency", "USD"))
    target_dte = int(oc.get("expiry_dte_target", 30))
    strike_offset = int(oc.get("strike_atm_offset", 0))
    right = _normalize_right(oc.get("right", "C"))

    stock = Stock(symbol, exchange, currency)
    sq = ib.qualifyContracts(stock)
    if not sq:
        raise ValueError(f"qualifyContracts failed for underlying stock {symbol!r}")
    stock_q = sq[0]

    mid = _underlying_mid(ib, stock_q)

    wildcard = Option(
        symbol,
        "",
        0.0,
        "",
        exchange,
        currency=currency,
    )
    details = ib.reqContractDetails(wildcard)
    if not details:
        raise ValueError(
            f"reqContractDetails returned no option chain for {symbol!r}; "
            "cannot resolve expiry/strike"
        )

    today = dt.date.today()
    expiries_dte: list[tuple[str, int, dt.date]] = []
    for d in details:
        c = d.contract
        ek = _future_expiry_key(c)
        if not ek:
            continue
        ed = _parse_expiry_to_date(ek)
        if ed is None:
            continue
        expiries_dte.append((ek, _dte(ed, today), ed))

    if not expiries_dte:
        raise ValueError(f"no parseable option expiries from reqContractDetails for {symbol!r}")

    # nearest to target DTE (minimize abs(dte - target)); tie-break: earlier expiry
    best = min(expiries_dte, key=lambda x: (abs(x[1] - target_dte), x[2]))
    chosen_exp = best[0]

    strikes = sorted(
        {
            float(getattr(d.contract, "strike", 0) or 0)
            for d in details
            if _future_expiry_key(d.contract) == chosen_exp and float(getattr(d.contract, "strike", 0) or 0) > 0
        }
    )
    if not strikes:
        raise ValueError(f"no strikes for {symbol!r} expiry {chosen_exp!r}")

    atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - mid))
    pick_idx = atm_idx + strike_offset
    if pick_idx < 0 or pick_idx >= len(strikes):
        raise ValueError(
            f"strike_atm_offset {strike_offset} out of range for {symbol!r} "
            f"(atm_idx={atm_idx}, n_strikes={len(strikes)})"
        )
    strike = strikes[pick_idx]

    opt = Option(
        symbol,
        chosen_exp,
        strike,
        right,
        exchange,
        currency=currency,
    )
    qc = ib.qualifyContracts(opt)
    if not qc:
        raise ValueError(
            f"qualifyContracts failed for Option({symbol!r}, {chosen_exp!r}, {strike}, {right}, ...)"
        )
    return qc[0]


def resolve(
    symbol: str,
    instrument_type: str,
    ib: Any,
    config_path: Path | None = None,
) -> Contract:
    """
    Return a qualified ib_insync.Contract for the given symbol and type.

    instrument_type: "equity" | "future" | "option"
    config_path: defaults to project config/instruments.yaml
    """
    path = config_path if config_path is not None else _default_config_path()
    if not path.exists():
        raise ValueError(f"instruments config not found: {path}")

    full_cfg = _load_yaml(path)
    it = instrument_type.strip().lower()
    if it == "equity":
        return _resolve_equity(full_cfg, symbol, ib, path)
    if it == "future":
        return _resolve_future(full_cfg, symbol, ib)
    if it == "option":
        return _resolve_option(full_cfg, symbol, ib)
    raise ValueError(f"unrecognised instrument_type: {instrument_type!r}")
