"""
Fetch news from EODHD API for all universe tickers; save to one Parquet file.

Loads tickers from config/universe.yaml (all pillars), paginates EODHD news API
per ticker (from 2021-01-01 to today), extracts Date/Ticker/Headline/Sentiment,
dedupes and writes NEWS_DIR/eodhd_global_backfill.parquet (fastparquet). Overwrites on each run.

Usage:
  python scripts/ingest_eodhd_news.py
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
    """Map canonical ticker to EODHD symbol (news and EOD use same convention)."""
    if "." in ticker:
        if ticker.upper().endswith(".DE"):
            return ticker[:-3] + ".XETRA"
        return ticker
    return ticker + ".US"


def main() -> int:
    from src.core.config import NEWS_DIR
    import requests
    import pandas as pd
    from datetime import date

    tickers = _tickers_from_universe()
    if not tickers:
        print("No tickers in config/universe.yaml.", flush=True)
        return 1

    key = os.environ.get("EODHD_API_KEY", "").strip()
    if not key:
        print("ERROR: EODHD_API_KEY not set. Set it in .env or environment.", flush=True)
        return 1

    base_url = "https://eodhd.com/api/news"
    from_str = "2021-01-01"
    to_str = date.today().isoformat()
    limit = 1000
    max_pages = 20
    all_rows = []

    for ticker in tickers:
        eodhd_symbol = _ticker_to_eodhd_symbol(ticker)
        page = 0
        ticker_articles = []
        while page < max_pages:
            offset = page * limit
            try:
                r = requests.get(
                    base_url,
                    params={
                        "s": eodhd_symbol,
                        "api_token": key,
                        "limit": limit,
                        "offset": offset,
                        "from": from_str,
                        "to": to_str,
                    },
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(f"[WARN] {ticker}: request failed ({e})", flush=True)
                break
            if not isinstance(data, list):
                break
            if len(data) == 0:
                break
            for article in data:
                date_val = (article.get("date") or "")[:10]
                headline = article.get("title", "")
                sent = article.get("sentiment") or {}
                polarity = sent.get("polarity", 0.0)
                sentiment = (float(polarity) + 1) / 2
                if not date_val or len(date_val) < 10:
                    continue
                ticker_articles.append({
                    "Date": date_val,
                    "Ticker": ticker,
                    "Headline": headline,
                    "Sentiment": sentiment,
                })
            if len(data) < limit:
                break
            page += 1
        all_rows.extend(ticker_articles)
        if ticker_articles:
            dates = [x["Date"] for x in ticker_articles]
            start, end = min(dates), max(dates)
            print(f"{ticker}: {len(ticker_articles)} articles ({start} to {end})", flush=True)
        else:
            print(f"{ticker}: 0 articles", flush=True)

    if not all_rows:
        print("No articles collected.", flush=True)
        df = pd.DataFrame(columns=["Date", "Ticker", "Headline", "Sentiment"])
    else:
        df = pd.DataFrame(all_rows)
        df = df.drop_duplicates(subset=["Date", "Ticker", "Headline"])
        df = df.sort_values(["Ticker", "Date"]).reset_index(drop=True)
    out_path = Path(NEWS_DIR) / "eodhd_global_backfill.parquet"
    try:
        Path(NEWS_DIR).mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, index=False, engine="fastparquet")
    except Exception as e:
        print(f"ERROR: Failed to write parquet: {e}", flush=True)
        return 1
    total = len(df)
    n_tickers = df["Ticker"].nunique() if not df.empty else 0
    print(f"Total: {total} articles across {n_tickers} tickers → eodhd_global_backfill.parquet", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
