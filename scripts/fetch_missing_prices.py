"""
Fetch OHLCV price history from EODHD for tickers that lack local CSVs.

Loads universe from config/universe.yaml (all pillars), finds tickers where
find_csv_path returns None, maps to EODHD symbol, fetches EOD endpoint,
saves to data_dir/eodhd/csv/{ticker}.csv. Exit 0 always (per-ticker failures are non-fatal).

Usage:
  python scripts/fetch_missing_prices.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass


def _tickers_from_universe() -> list[str]:
    """Load all tickers from config/universe.yaml (all pillars)."""
    import yaml
    path = ROOT / "config" / "universe.yaml"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        universe = yaml.safe_load(f)
    pillars = universe.get("pillars") or {}
    out = []
    for _pname, pillar_list in pillars.items():
        if not isinstance(pillar_list, list):
            continue
        for t in pillar_list:
            if isinstance(t, str) and t.strip():
                out.append(t.strip())
    return out


def _ticker_to_eodhd_symbol(ticker: str) -> str:
    """Map canonical ticker to EODHD EOD endpoint symbol."""
    if "." in ticker:
        if ticker.upper().endswith(".DE"):
            return ticker[:-3] + ".XETRA"
        return ticker  # .HK, .CO, .T as-is
    return ticker + ".US"


def main() -> int:
    from src.data.csv_provider import find_csv_path, load_data_config

    tickers = _tickers_from_universe()
    if not tickers:
        print("No tickers in config/universe.yaml.", flush=True)
        return 0

    data_cfg = load_data_config()
    data_dir = Path(data_cfg["data_dir"])
    missing = []
    for t in tickers:
        if find_csv_path(data_dir, t) is None:
            missing.append(t)
    if not missing:
        print("All tickers already have local CSVs. Nothing to fetch.", flush=True)
        return 0

    key = os.environ.get("EODHD_API_KEY", "").strip()
    if not key:
        print("ERROR: EODHD_API_KEY not set. Set it in .env or environment.", flush=True)
        return 1

    import requests
    from datetime import date
    import pandas as pd

    out_dir = data_dir / "eodhd" / "csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_url = "https://eodhd.com/api/eod"
    from_str = "2010-01-01"
    to_str = date.today().isoformat()

    for ticker in missing:
        eodhd_symbol = _ticker_to_eodhd_symbol(ticker)
        try:
            r = requests.get(
                f"{base_url}/{eodhd_symbol}",
                params={
                    "api_token": key,
                    "fmt": "json",
                    "from": from_str,
                    "to": to_str,
                    "period": "d",
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            if not data or (isinstance(data, list) and len(data) == 0):
                print(f"[WARN] {ticker}: fetch failed (empty response)", flush=True)
                continue
            # EOD endpoint returns list of dicts: date, open, high, low, close, adjusted_close, volume
            df = pd.DataFrame(data)
            if df.empty:
                print(f"[WARN] {ticker}: fetch failed (empty DataFrame)", flush=True)
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            close_col = "adjusted_close" if "adjusted_close" in df.columns else "close"
            use = df[["open", "high", "low", close_col, "volume"]].copy()
            use.columns = ["open", "high", "low", "close", "volume"]
            use = use.dropna(subset=["close"])
            if use.empty:
                print(f"[WARN] {ticker}: fetch failed (no valid rows)", flush=True)
                continue
            out_path = out_dir / f"{ticker}.csv"
            use.to_csv(out_path)
            start = use.index.min().strftime("%Y-%m-%d")
            end = use.index.max().strftime("%Y-%m-%d")
            print(f"[OK] {ticker}: {len(use)} rows, {start} to {end} saved to eodhd/csv/", flush=True)
        except requests.RequestException as e:
            print(f"[WARN] {ticker}: fetch failed ({e})", flush=True)
        except Exception as e:
            print(f"[WARN] {ticker}: fetch failed ({e})", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
