"""
Fetch Tiingo news and write monthly parquets consumed by UnifiedNewsLoader.

Output schema (per parquet): Date (date), Ticker (str), Sentiment (float 0-1)
Files: trading_data/news/tiingo_{YYYY}_{MM}.parquet

Usage:
    # Full backfill (first run or new tickers):
    python scripts/fetch_tiingo_news.py --start 2025-01-01

    # Recurring incremental (cron / weekly rebalance):
    python scripts/fetch_tiingo_news.py --since-days 35

    # New ticker onboarding:
    python scripts/fetch_tiingo_news.py --start 2025-01-01 --tickers AI,SOUN
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import pandas as pd
import requests
import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
NEWS_DIR = DATA_DIR / "news"
UNIVERSE_PATH = ROOT / "config" / "universe.yaml"
LOG_PATH = ROOT / "outputs" / "tiingo_fetch_log.json"

TIINGO_BASE = "https://api.tiingo.com/tiingo/news"
TIINGO_PAGE_LIMIT = 100  # per-ticker per-month; no pagination loop
REQUEST_DELAY = 0.3  # seconds between ticker requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_universe_tickers() -> list[str]:
    with UNIVERSE_PATH.open("r", encoding="utf-8") as f:
        u = yaml.safe_load(f) or {}
    pillars = u.get("pillars") or {}
    tickers: list[str] = []
    for lst in pillars.values():
        if isinstance(lst, list):
            tickers.extend(
                str(t).strip() for t in lst if isinstance(t, str) and str(t).strip()
            )
    # ETFs are signals only — still need sentiment for layer_etf_gate
    etf_layers = u.get("layer_etfs") or {}
    for lst in etf_layers.values():
        if isinstance(lst, list):
            tickers.extend(
                str(t).strip() for t in lst if isinstance(t, str) and str(t).strip()
            )
    return sorted(set(tickers))


def _months_in_range(start: date, end: date) -> list[tuple[int, int]]:
    """Return list of (year, month) tuples covering [start, end]."""
    months: list[tuple[int, int]] = []
    cur = date(start.year, start.month, 1)
    end_m = date(end.year, end.month, 1)
    while cur <= end_m:
        months.append((cur.year, cur.month))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _parse_sentiment(raw) -> float | None:
    """Convert Tiingo sentiment field to [0, 1] float, or None if absent/invalid."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # Numeric: assume [-1, 1] scale
        v = float(raw)
        return float((v + 1.0) / 2.0)
    if isinstance(raw, str):
        mapping = {"positive": 0.75, "neutral": 0.5, "negative": 0.25}
        return mapping.get(raw.strip().lower())
    if isinstance(raw, dict):
        # Tiingo sometimes returns {"sentiment": "positive", "polarity": 0.8}
        polarity = raw.get("polarity")
        if polarity is not None:
            try:
                v = float(polarity)
                return float((v + 1.0) / 2.0)
            except (ValueError, TypeError):
                pass
        label = raw.get("sentiment") or raw.get("label")
        if label is not None:
            return _parse_sentiment(label)
    return None


def _fetch_ticker_month(
    api_key: str,
    ticker: str,
    year: int,
    month: int,
) -> list[dict]:
    """Fetch Tiingo articles for a single ticker and month — one request, no pagination.

    Tiingo's /news offset parameter is not reliably supported; one request per ticker
    per month avoids the infinite-loop risk and keeps each call fast (<15s).
    """
    start_d, end_d = _month_bounds(year, month)
    params = {
        "tickers": ticker,
        "startDate": start_d.isoformat(),
        "endDate": end_d.isoformat(),
        "limit": TIINGO_PAGE_LIMIT,
    }
    try:
        resp = requests.get(
            TIINGO_BASE,
            params=params,
            headers={"Authorization": f"Token {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        articles = resp.json()
        if not isinstance(articles, list):
            articles = articles.get("data", articles.get("results", []))
        if not isinstance(articles, list):
            return []
    except Exception as e:
        logger.warning("Tiingo fetch error %s %s-%02d: %s", ticker, year, month, e)
        return []

    rows: list[dict] = []
    for a in articles:
        pub = a.get("publishedDate") or a.get("published_at") or ""
        try:
            dt = pd.to_datetime(pub, errors="coerce")
            if pd.isna(dt):
                continue
            if getattr(dt, "tz", None) is not None:
                dt = dt.tz_convert("UTC").tz_localize(None)
            article_date = dt.date()
        except Exception:
            continue

        raw_sent = a.get("sentiment")
        sentiment = _parse_sentiment(raw_sent)

        rows.append(
            {
                "Date": article_date,
                "Ticker": ticker.upper(),
                "Sentiment": sentiment,
                "Title": str(a.get("title", "")),
                "Source": "tiingo",
            }
        )

    return rows


def _fetch_month(
    api_key: str,
    tickers: list[str],
    year: int,
    month: int,
) -> list[dict]:
    """Fetch all tickers for a month sequentially, one ticker per request."""
    rows: list[dict] = []
    for ticker in tickers:
        t_rows = _fetch_ticker_month(api_key, ticker, year, month)
        print(f"  {ticker}: {len(t_rows)} articles", flush=True)
        rows.extend(t_rows)
        time.sleep(REQUEST_DELAY)
    return rows


def _merge_and_write(year: int, month: int, new_rows: list[dict]) -> dict:
    """Merge new rows with existing parquet, atomic write. Returns stats dict."""
    parquet_path = NEWS_DIR / f"tiingo_{year}_{month:02d}.parquet"
    new_df = (
        pd.DataFrame(new_rows)
        if new_rows
        else pd.DataFrame(columns=["Date", "Ticker", "Sentiment", "Title", "Source"])
    )
    new_df["Date"] = pd.to_datetime(new_df["Date"], errors="coerce").dt.date
    new_df["Sentiment"] = pd.to_numeric(new_df["Sentiment"], errors="coerce")

    if parquet_path.exists():
        existing = pd.read_parquet(parquet_path)
        existing["Date"] = pd.to_datetime(existing["Date"], errors="coerce").dt.date
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df.copy()

    before_rows = len(merged)
    merged = merged.dropna(subset=["Date", "Ticker", "Sentiment"])
    merged["Ticker"] = merged["Ticker"].astype(str).str.strip().str.upper()
    merged = merged.drop_duplicates(subset=["Date", "Ticker"], keep="first")
    merged = merged.sort_values(["Date", "Ticker"]).reset_index(drop=True)

    parquet_cols = ["Date", "Ticker", "Sentiment"]
    extra_cols = [c for c in merged.columns if c not in parquet_cols]
    out = merged[parquet_cols + extra_cols]

    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = parquet_path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False)
    chk = pd.read_parquet(tmp)
    if len(chk) == 0 and len(merged) > 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Parquet tmp validation failed for {year}-{month:02d}")
    os.replace(tmp, parquet_path)

    tickers_covered = int(merged["Ticker"].nunique())
    return {
        "rows_total": len(merged),
        "rows_with_sentiment": int(merged["Sentiment"].notna().sum()),
        "tickers_covered": tickers_covered,
        "new_rows_added": max(0, len(merged) - (before_rows - len(new_df))),
    }


def _write_log(log: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, LOG_PATH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start",
        type=str,
        default="2025-01-01",
        help="Start date for backfill (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", type=str, default=None, help="End date (default: today)"
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Shorthand: fetch last N days (overrides --start)",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Comma-separated tickers (default: full universe)",
    )
    args = parser.parse_args()

    api_key = (os.getenv("TIINGO_API_KEY") or "").strip()
    if not api_key:
        print("[ERROR] TIINGO_API_KEY not set in .env", flush=True)
        return 1

    today = date.today()
    end_d = today if args.end is None else date.fromisoformat(args.end)

    if args.since_days is not None:
        start_d = today - timedelta(days=args.since_days)
    else:
        start_d = date.fromisoformat(args.start)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = _load_universe_tickers()

    if not tickers:
        print("[ERROR] No tickers resolved", flush=True)
        return 1

    months = _months_in_range(start_d, end_d)
    print(
        f"[TIINGO] tickers={len(tickers)} months={len(months)} range={start_d}..{end_d}",
        flush=True,
    )

    log: dict = {
        "run_at": pd.Timestamp.now().isoformat(),
        "tickers": tickers,
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "months": {},
        "exit_code": 0,
    }

    for year, month in months:
        label = f"{year}-{month:02d}"
        print(f"[TIINGO] fetching {label} ...", flush=True)
        try:
            rows = _fetch_month(api_key, tickers, year, month)
            stats = _merge_and_write(year, month, rows)
            print(
                f"[TIINGO] {label} ok rows={stats['rows_total']} "
                f"sentiment={stats['rows_with_sentiment']} "
                f"tickers={stats['tickers_covered']}",
                flush=True,
            )
            log["months"][label] = {"status": "ok", **stats}
        except Exception as e:
            print(f"[TIINGO] {label} ERROR: {e}", flush=True)
            log["months"][label] = {"status": "error", "error": str(e)}
            log["exit_code"] = 1
        time.sleep(REQUEST_DELAY)

    _write_log(log)
    print(f"[TIINGO] done exit_code={log['exit_code']} log={LOG_PATH}", flush=True)
    return int(log["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
