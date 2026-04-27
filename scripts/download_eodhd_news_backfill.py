"""
Download historical EODHD news sentiment for data_config watchlist tickers
into DATA_DIR/news/eodhd_global_backfill.parquet (Date, Ticker, Sentiment).

See docs/INDEX.md for canonical project layout. Evidence: unified_news_loader
and eodhd_news_loader expect this parquet path and column names.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
NEWS_DIR = DATA_DIR / "news"
OUT_FILE = NEWS_DIR / "eodhd_global_backfill.parquet"
TMP_FILE = NEWS_DIR / "eodhd_global_backfill.parquet.tmp"

DATA_CONFIG = ROOT / "config" / "data_config.yaml"
FROM_DATE = "2020-01-01"
TO_DATE = "2024-12-31"
NEWS_URL = "https://eodhd.com/api/news"
PAGE_LIMIT = 1000
SLEEP_SEC = 0.25


def _load_watchlist() -> list[str]:
    if not DATA_CONFIG.exists():
        raise FileNotFoundError(f"Missing {DATA_CONFIG}")
    with open(DATA_CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    wl = (cfg.get("universe_selection") or {}).get("watchlist", [])
    if not isinstance(wl, list):
        return []
    return [str(t).strip() for t in wl if str(t).strip()]


def _article_date_str(item: dict[str, Any]) -> str | None:
    raw = item.get("date") or item.get("datetime") or item.get("published_at")
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def _article_polarity(item: dict[str, Any]) -> float | None:
    sent = item.get("sentiment")
    if not isinstance(sent, dict):
        return None
    p = sent.get("polarity")
    if p is None:
        return None
    try:
        return float(p)
    except (TypeError, ValueError):
        return None


def _fetch_ticker_pages(
    api_key: str,
    universe_ticker: str,
    from_d: str,
    to_d: str,
    rows_out: list[dict[str, Any]],
) -> None:
    """Append rows for one watchlist symbol (pagination until < limit items)."""
    s_param = universe_ticker.strip()
    ticker_out = universe_ticker.strip().upper()
    offset = 0
    while True:
        time.sleep(SLEEP_SEC)
        try:
            r = requests.get(
                NEWS_URL,
                params={
                    "api_token": api_key,
                    "s": s_param,
                    "from": from_d,
                    "to": to_d,
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                    "fmt": "json",
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            print(
                f"[WARN] {ticker_out} offset={offset}: request error: {exc}", flush=True
            )
            break
        if r.status_code != 200:
            print(
                f"[WARN] {ticker_out} offset={offset}: HTTP {r.status_code} {r.text[:200]!r}",
                flush=True,
            )
            break
        try:
            data = r.json()
        except json.JSONDecodeError as exc:
            print(
                f"[WARN] {ticker_out} offset={offset}: invalid JSON: {exc}", flush=True
            )
            break
        if not isinstance(data, list):
            print(
                f"[WARN] {ticker_out} offset={offset}: expected list, got {type(data).__name__}",
                flush=True,
            )
            break
        for item in data:
            if not isinstance(item, dict):
                continue
            d_str = _article_date_str(item)
            pol = _article_polarity(item)
            if d_str is None or pol is None:
                continue
            rows_out.append(
                {
                    "Date": d_str,
                    "Ticker": ticker_out,
                    "Sentiment": pol,
                }
            )
        if len(data) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EODHD news backfill → eodhd_global_backfill.parquet"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if output parquet already exists",
    )
    args = parser.parse_args()

    api_key = (os.getenv("EODHD_API_KEY") or "").strip()
    if not api_key:
        print("ERROR: EODHD_API_KEY missing in environment (.env).", flush=True)
        return 1

    if OUT_FILE.exists() and not args.force:
        print(
            f"[SKIP] Already exists: {OUT_FILE} (use --force to re-download)",
            flush=True,
        )
        return 0

    tickers = _load_watchlist()
    if not tickers:
        print("ERROR: Empty watchlist in config/data_config.yaml", flush=True)
        return 1

    rows: list[dict[str, Any]] = []
    print(
        f"[EODHD] Backfill {FROM_DATE}..{TO_DATE} for {len(tickers)} tickers → {OUT_FILE}",
        flush=True,
    )
    for i, t in enumerate(tickers, start=1):
        print(f"[{i}/{len(tickers)}] Fetching {t!r} …", flush=True)
        _fetch_ticker_pages(api_key, t, FROM_DATE, TO_DATE, rows)

    df = pd.DataFrame(rows, columns=["Date", "Ticker", "Sentiment"])
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(TMP_FILE, index=False, engine="pyarrow")
    except Exception:
        df.to_parquet(TMP_FILE, index=False, engine="fastparquet")
    if not TMP_FILE.exists() or TMP_FILE.stat().st_size == 0:
        print("[ERROR] Temp parquet missing or empty", flush=True)
        return 1
    os.replace(TMP_FILE, OUT_FILE)

    n = len(df)
    if n == 0:
        print("[DONE] 0 rows written (empty DataFrame).", flush=True)
        return 0
    dmin = str(df["Date"].min())
    dmax = str(df["Date"].max())
    print(f"[DONE] {n} rows, Date range {dmin} .. {dmax} → {OUT_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
