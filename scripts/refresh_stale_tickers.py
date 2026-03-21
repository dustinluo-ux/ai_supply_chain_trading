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
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.data.csv_provider import find_csv_path

TOKEN = os.getenv("EODHD_API_KEY", "").strip()
if not TOKEN:
    raise SystemExit("EODHD_API_KEY not found in .env")

DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
FALLBACK_DIR = DATA_DIR / "stock_market_data" / "eodhd" / "csv"
FROM_DATE = "2019-01-01"

DEFAULT_TICKERS = ["CSCO", "IBM", "QCOM", "SMCI", "TXN"]


def download_ticker(ticker: str) -> None:
    url = f"https://eodhd.com/api/eod/{ticker}.US"
    params = {"api_token": TOKEN, "fmt": "csv", "from": FROM_DATE}
    print(f"  Downloading {ticker}.US from EODHD ...", end=" ", flush=True)
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    rows = r.text.strip().splitlines()
    print(f"{len(rows)} rows", end=" ", flush=True)

    # Find existing CSV to overwrite, else fall back to eodhd/csv/
    existing = find_csv_path(DATA_DIR, ticker)
    if existing:
        out = Path(existing)
    else:
        FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        out = FALLBACK_DIR / f"{ticker}.csv"

    out.write_text(r.text, encoding="utf-8")
    print(f"-> {out}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS,
                        help="Tickers to refresh (default: CSCO IBM QCOM SMCI TXN)")
    args = parser.parse_args()

    print(f"Refreshing {len(args.tickers)} tickers from EODHD (from={FROM_DATE}):")
    errors = []
    for ticker in args.tickers:
        try:
            download_ticker(ticker)
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
