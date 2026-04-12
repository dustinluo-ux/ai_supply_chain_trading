# Staged: not yet wired into active pipelines. Entry point is get_prices(). Do not delete — tests pass, future integration planned.
"""
Price fetch with vendor fallback: local CSV → Marketaux → YFinance → Alpha Vantage.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

import pandas as pd
import requests

if TYPE_CHECKING:
    from src.core.state import PipelineState

logger = logging.getLogger(__name__)

_ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
_MARKETAUX_EOD_URL = "https://api.marketaux.com/v1/eod"


def _log_success(ticker: str, vendor: str) -> None:
    logger.info("[resilience] %s: served by %s", ticker, vendor)


def _log_failure(ticker: str, vendor: str, exc: BaseException | str) -> None:
    logger.warning("[resilience] %s: %s failed — %s", ticker, vendor, exc)


def _record_state(
    state: Optional["PipelineState"],
    ticker: str,
    vendor: str,
    success: bool,
    t0: float,
    error: Optional[str] = None,
) -> None:
    if state is None:
        return
    latency_ms = (time.perf_counter() - t0) * 1000.0
    state.add_vendor_event(ticker, vendor, success, error=error, latency_ms=latency_ms)


def _cast_ohlc_to_decimal(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["open", "high", "low", "close"]:
        if col not in out.columns:
            continue
        out[col] = out[col].map(
            lambda x: Decimal(str(float(x))) if pd.notna(x) else Decimal("NaN")
        )
    return out


def _slice_date_range(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s = df.copy()
    s.index = idx
    return s[(s.index >= start_ts) & (s.index <= end_ts)].sort_index()


def _try_csv(
    ticker: str,
    start: str,
    end: str,
    data_dir: Path,
) -> pd.DataFrame | None:
    from src.data import csv_provider

    loaded = csv_provider.load_prices(data_dir, [ticker])
    raw = loaded.get(ticker)
    if raw is None or raw.empty:
        return None
    sliced = _slice_date_range(raw, start, end)
    if len(sliced) < 5:
        return None
    return csv_provider.ensure_ohlcv(sliced)


def _try_marketaux(
    ticker: str,
    start: str,
    end: str,
    api_key: str,
) -> pd.DataFrame | None:
    try:
        params = {
            "api_token": api_key,
            "symbols": ticker,
            "date_from": start,
            "date_to": end,
        }
        r = requests.get(_MARKETAUX_EOD_URL, params=params, timeout=60)
        if r.status_code == 429:
            return None
        text_lower = (r.text or "").lower()
        if "rate" in text_lower and "limit" in text_lower:
            return None
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            return None
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            return None
        records = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            d = row.get("date") or row.get("Date")
            if not d:
                continue
            records.append(
                {
                    "date": d,
                    "open": float(row.get("open", row.get("o", 0)) or 0),
                    "high": float(row.get("high", row.get("h", 0)) or 0),
                    "low": float(row.get("low", row.get("l", 0)) or 0),
                    "close": float(row.get("close", row.get("c", 0)) or 0),
                    "volume": float(row.get("volume", row.get("v", 0)) or 0),
                }
            )
        if len(records) < 5:
            return None
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.dropna(subset=["date"])
        df = df.set_index("date").sort_index()
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df.columns = [c.lower() for c in df.columns]
        return _slice_date_range(df, start, end)
    except Exception:
        return None


def _try_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf

        end_exclusive = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        d = yf.download(
            ticker,
            start=start,
            end=end_exclusive,
            auto_adjust=True,
            progress=False,
        )
        if d is None or d.empty:
            return None
        d = d.copy()
        d.index = pd.to_datetime(d.index)
        if getattr(d.index, "tz", None) is not None:
            d.index = d.index.tz_localize(None)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [str(c[0]).lower() for c in d.columns]
        else:
            d.columns = [str(c).lower() for c in d.columns]
        d = _slice_date_range(d, start, end)
        if len(d) < 5:
            return None
        for col in ["open", "high", "low", "close"]:
            if col not in d.columns and "close" in d.columns:
                d[col] = d["close"]
        if "volume" not in d.columns:
            d["volume"] = 0.0
        return d
    except Exception:
        return None


def _try_alphavantage(ticker: str, start: str, end: str, api_key: str) -> pd.DataFrame | None:
    try:
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": ticker,
            "outputsize": "full",
            "apikey": api_key,
        }
        r = requests.get(_ALPHAVANTAGE_URL, params=params, timeout=120)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None
        if "Information" in data:
            return None
        ts = data.get("Time Series (Daily)")
        if not isinstance(ts, dict):
            return None
        rows = []
        for date_str, bar in ts.items():
            if not isinstance(bar, dict):
                continue
            rows.append(
                {
                    "date": date_str,
                    "open": float(bar.get("1. open", 0) or 0),
                    "high": float(bar.get("2. high", 0) or 0),
                    "low": float(bar.get("3. low", 0) or 0),
                    "close": float(bar.get("5. adjusted close") or bar.get("4. close", 0) or 0),
                    "volume": float(bar.get("6. volume", 0) or 0),
                }
            )
        if len(rows) < 5:
            return None
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = _slice_date_range(df, start, end)
        if len(df) < 5:
            return None
        return df
    except Exception:
        return None


def _run_vendor(
    ticker: str,
    vendor: str,
    fn: Callable[[], pd.DataFrame | None],
    state: Optional["PipelineState"],
) -> pd.DataFrame | None:
    t0 = time.perf_counter()
    try:
        df = fn()
    except Exception as exc:
        _log_failure(ticker, vendor, exc)
        _record_state(state, ticker, vendor, False, t0, error=str(exc))
        return None
    if df is None or df.empty or len(df) < 5:
        err = "empty_or_short" if df is None or df.empty else "fewer_than_5_rows"
        _log_failure(ticker, vendor, err)
        _record_state(state, ticker, vendor, False, t0, error=err)
        return None
    _log_success(ticker, vendor)
    _record_state(state, ticker, vendor, True, t0)
    return df


def get_prices(
    tickers: list[str],
    start: str,
    end: str,
    data_dir: Path,
    *,
    marketaux_api_key: Optional[str] = None,
    alphavantage_api_key: Optional[str] = None,
    state: Optional["PipelineState"] = None,
) -> dict[str, pd.DataFrame]:
    """
    Per-ticker fallback: CSV → Marketaux → YFinance → Alpha Vantage.

    Never raises; omits tickers that fail all vendors. OHLC columns are Decimal after success.
    """
    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        df: pd.DataFrame | None = None

        df = _run_vendor(
            ticker,
            "csv",
            lambda: _try_csv(ticker, start, end, Path(data_dir)),
            state,
        )
        if df is not None:
            out[ticker] = _cast_ohlc_to_decimal(df)
            continue

        if marketaux_api_key:
            df = _run_vendor(
                ticker,
                "marketaux",
                lambda: _try_marketaux(ticker, start, end, marketaux_api_key),
                state,
            )
        if df is not None:
            out[ticker] = _cast_ohlc_to_decimal(df)
            continue

        df = _run_vendor(
            ticker,
            "yfinance",
            lambda: _try_yfinance(ticker, start, end),
            state,
        )
        if df is not None:
            out[ticker] = _cast_ohlc_to_decimal(df)
            continue

        if alphavantage_api_key:
            df = _run_vendor(
                ticker,
                "alphavantage",
                lambda: _try_alphavantage(ticker, start, end, alphavantage_api_key),
                state,
            )
        if df is not None:
            out[ticker] = _cast_ohlc_to_decimal(df)
            continue

        logger.error("[resilience] %s: all vendors failed — omitting from result", ticker)

    return out
