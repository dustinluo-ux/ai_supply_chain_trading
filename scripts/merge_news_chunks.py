"""
One-shot script: merge historical news chunks into flat ticker files.

Loads {ticker}_news.json (if present) and all {ticker}_20*.json chunk files
in --news-dir, deduplicates on title, sorts by publishedAt ascending,
and overwrites {ticker}_news.json. Chunk files are left in place.

Usage:
  python scripts/merge_news_chunks.py [--tickers NVDA,AMD] [--news-dir data/news]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.signals.news_engine import deduplicate_articles


def _root_to_articles(root: list | dict) -> list[dict]:
    """Normalize JSON root to list of article dicts (same logic as load_ticker_news)."""
    if isinstance(root, list):
        return root
    if isinstance(root, dict):
        if "articles" in root and isinstance(root["articles"], list):
            return root["articles"]
        return [root]
    return []


def load_articles_from_path(path: Path) -> list[dict]:
    """Load and normalize articles from a single JSON file. encoding=utf-8."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _root_to_articles(data)
    except Exception as e:
        print(f"  [WARN] Load {path}: {e}")
        return []


def merge_ticker(news_dir: Path, ticker: str) -> None:
    """Load flat + chunks, dedupe, sort by publishedAt, write flat file."""
    news_dir = Path(news_dir)
    flat_path = news_dir / f"{ticker}_news.json"

    # 1. Flat file if present
    flat_articles: list[dict] = []
    if flat_path.exists():
        flat_articles = load_articles_from_path(flat_path)

    # 2. All {ticker}_20*.json chunks
    chunk_paths = sorted(news_dir.glob(f"{ticker}_20*.json"))
    chunk_articles: list[dict] = []
    for p in chunk_paths:
        chunk_articles.extend(load_articles_from_path(p))

    merged = flat_articles + chunk_articles
    n_flat = len(flat_articles)
    n_chunks = len(chunk_articles)

    if not merged:
        print(f"{ticker}: flat={n_flat} chunk={n_chunks} after_dedup=0 (nothing to write)")
        return

    # 3. Deduplicate on title (reuse news_engine helper)
    deduped = deduplicate_articles(merged, headline_key="title")
    n_dedup = len(deduped)

    # 4. Sort by publishedAt ascending
    def _sort_key(a: dict) -> str:
        return (a.get("publishedAt") or "")

    deduped.sort(key=_sort_key)

    # 5. Write back to flat file
    news_dir.mkdir(parents=True, exist_ok=True)
    with open(flat_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)

    print(f"{ticker}: flat={n_flat} chunk={n_chunks} after_dedup={n_dedup} -> {flat_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge historical news chunks into flat ticker files (data/news/{ticker}_news.json)."
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default="NVDA,AMD",
        help="Comma-separated tickers (default: NVDA,AMD)",
    )
    parser.add_argument(
        "--news-dir",
        type=str,
        default="data/news",
        help="News directory (default: data/news)",
    )
    args = parser.parse_args()
    news_dir = Path(args.news_dir)
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    for ticker in tickers:
        merge_ticker(news_dir, ticker)


if __name__ == "__main__":
    main()
