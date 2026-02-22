"""
Update News JSON — config-driven news fetcher.

Reads the watchlist from config (same as update_price_data.py), fetches
articles via the configured news source (config/config.yaml news.source),
and writes per-ticker JSON to the news directory.

Usage:
    python scripts/update_news_data.py                     # defaults from config
    python scripts/update_news_data.py --start 2024-01-01  # override start
    python scripts/update_news_data.py --tickers NVDA,AMD  # override watchlist
"""
from __future__ import annotations

import argparse
import datetime
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.news_fetcher import NewsFetcher


def _get_news_dir() -> str:
    """News directory from data_config.yaml or default."""
    path = ROOT / "config" / "data_config.yaml"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data.get("news_data", {}).get("directory", "data/news")
        except Exception:
            pass
    return "data/news"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update news JSON from configured source using config/config.yaml",
    )
    parser.add_argument(
        "--tickers", type=str, default=None,
        help="Comma-separated tickers (default: watchlist from config)",
    )
    parser.add_argument(
        "--start", type=str,
        default=(datetime.date.today() - datetime.timedelta(days=7)).isoformat(),
    )
    parser.add_argument("--end", type=str, default=datetime.date.today().isoformat())
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between tickers (rate-limit courtesy)",
    )
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        from src.utils.config_manager import get_config
        tickers = get_config().get_watchlist()

    if not tickers:
        print("ERROR: No tickers. Set --tickers or config watchlist.", file=sys.stderr)
        return 1

    news_dir = _get_news_dir()
    print("Update News Data", flush=True)
    print(f"  News dir: {news_dir}", flush=True)
    print(f"  Tickers:  {tickers}", flush=True)
    print(f"  Period:   {args.start} to {args.end}", flush=True)
    print(f"  Delay:    {args.delay}s between tickers", flush=True)
    print("=" * 60, flush=True)

    fetcher = NewsFetcher()
    success = 0
    failed = 0
    for i, ticker in enumerate(tickers, 1):
        try:
            articles = fetcher.fetch_articles_for_ticker(
                ticker, args.start, args.end, use_cache=True
            )
            n = len(articles) if articles else 0
            print(
                f"  [{i}/{len(tickers)}] OK {ticker}: {n} articles",
                flush=True,
            )
            success += 1
            try:
                from src.data.news_sources.tiingo_provider import TiingoProvider
                tiingo = TiingoProvider(data_dir=news_dir)
                tiingo_articles = tiingo.fetch_articles_for_ticker(
                    ticker, args.start, args.end, use_cache=True
                )
                k = len(tiingo_articles) if tiingo_articles else 0
                print(
                    f"  [{i}/{len(tickers)}] TIINGO OK {ticker}: {k} articles",
                    flush=True,
                )
            except Exception as tiingo_err:
                print(
                    f"  [{i}/{len(tickers)}] TIINGO SKIP {ticker}: {tiingo_err}",
                    flush=True,
                )
        except Exception as e:
            print(
                f"  [{i}/{len(tickers)}] FAIL {ticker}: {e}",
                flush=True,
                file=sys.stderr,
            )
            failed += 1
        if i < len(tickers):
            time.sleep(args.delay)

    print("=" * 60, flush=True)
    print(
        f"  Done: {success} ok, {failed} failed, {len(tickers)} total",
        flush=True,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
