"""
Refresh EODHD price CSVs for tickers whose data has gone stale on this machine.
Overwrites the existing CSV in-place (auto-discovered via find_csv_path).
If no existing CSV is found, writes to trading_data/stock_market_data/eodhd/csv/<TICKER>.csv.

Usage:
  python scripts/refresh_stale_tickers.py
  python scripts/refresh_stale_tickers.py --tickers CSCO IBM QCOM SMCI TXN
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import requests
import yfinance as yf
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.data.csv_provider import find_csv_path

TOKEN = os.getenv("EODHD_API_KEY", "").strip()

DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
FALLBACK_DIR = DATA_DIR / "stock_market_data" / "eodhd" / "csv"
FROM_DATE = "2019-01-01"

DEFAULT_TICKERS = ["CSCO", "IBM", "QCOM", "SMCI", "TXN"]


def _resolve_output_path(ticker: str) -> Path:
    # Find existing CSV to overwrite, else fall back to eodhd/csv/
    existing = find_csv_path(DATA_DIR, ticker)
    if existing:
        return Path(existing)
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    return FALLBACK_DIR / f"{ticker}.csv"


def _atomic_write_csv(out: Path, content: str) -> None:
    tmp = out.with_suffix(f"{out.suffix}.tmp")
    tmp.write_text(content, encoding="utf-8")
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise ValueError(f"Atomic write failed, empty temp file: {tmp}")
    os.replace(tmp, out)


def download_ticker(ticker: str) -> None:
    url = f"https://eodhd.com/api/eod/{ticker}.US"
    params = {"api_token": TOKEN, "fmt": "csv", "from": FROM_DATE}
    print(f"  Downloading {ticker}.US from EODHD ...", end=" ", flush=True)
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    rows = r.text.strip().splitlines()
    print(f"{len(rows)} rows", end=" ", flush=True)

    out = _resolve_output_path(ticker)
    _atomic_write_csv(out, r.text)
    print(f"-> {out}", flush=True)


def refresh_ticker(ticker: str) -> None:
    out = _resolve_output_path(ticker)
    df = None
    try:
        # end date exclusive in yfinance; use today's date for current window.
        today = str(dt.date.today())
        df = yf.download(
            ticker,
            start=FROM_DATE,
            end=today,
            auto_adjust=True,
            progress=False,
        )
    except Exception:
        df = None

    if df is not None and not df.empty:
        df.columns = [str(c).lower() for c in df.columns]
    if df is not None and not df.empty and len(df) >= 5:
        csv_text = df.to_csv()
        if not csv_text.strip():
            raise ValueError("yfinance returned empty CSV content")
        _atomic_write_csv(out, csv_text)
        print(f"  {ticker}: OK via yfinance ({len(df)} rows). -> {out}", flush=True)
        return

    print("  yfinance empty/failed, falling back to EODHD...", flush=True)
    if not TOKEN:
        print("  WARNING: EODHD_API_KEY missing; skipping EODHD fallback.", flush=True)
        return
    download_ticker(ticker)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS,
                        help="Tickers to refresh (default: CSCO IBM QCOM SMCI TXN)")
    args = parser.parse_args()

    print(f"Refreshing {len(args.tickers)} tickers (from={FROM_DATE}):")
    errors = []
    for ticker in args.tickers:
        try:
            refresh_ticker(ticker)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            errors.append(ticker)

    if errors:
        print(f"\nFailed: {errors}")
        sys.exit(1)
    else:
        print("\nDone.")


if __name__ == "__main__":
    main()
