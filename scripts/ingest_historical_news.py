"""
Ingest EODHD historical news from trading_data/news/historical_archives/ into parquet.

Scans *.json in historical_archives/, normalizes articles (date, ticker, headline, sentiment),
dedupes, writes NEWS_DIR/eodhd_{YYYY}_{MM}.parquet by year-month. Uses fastparquet engine.
Read-only on pipeline; no signal or ML changes.

Usage:
  python scripts/ingest_historical_news.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _ticker_from_filename(filename: str) -> str:
    """Strip .json and known suffixes (_news, _articles, _eodhd); uppercase."""
    base = Path(filename).stem
    for suffix in ("_news", "_articles", "_eodhd"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
    return base.upper()


def _parse_date(val) -> str | None:
    """Coerce to YYYY-MM-DD string; return None if unparseable."""
    if val is None:
        return None
    try:
        import pandas as pd
        dt = pd.to_datetime(val)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def main() -> int:
    try:
        from src.core.config import NEWS_DIR
        import pandas as pd
    except ImportError as e:
        print(f"ERROR: Missing dependency: {e}", flush=True)
        return 1

    archive_dir = Path(NEWS_DIR) / "historical_archives"
    if not archive_dir.exists():
        print("No files in historical_archives/, nothing to ingest.", flush=True)
        return 0
    json_files = list(archive_dir.glob("*.json"))
    if not json_files:
        print("No files in historical_archives/, nothing to ingest.", flush=True)
        return 0

    rows = []
    for jpath in json_files:
        ticker = _ticker_from_filename(jpath.name)
        try:
            with open(jpath, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            print(f"[WARN] Skip {jpath.name}: {e}", flush=True)
            continue
        articles = raw if isinstance(raw, list) else (raw.get("articles") if isinstance(raw, dict) else [])
        if not articles:
            continue
        for art in articles:
            if not isinstance(art, dict):
                print("[WARN] Non-dict article skipped.", flush=True)
                continue
            date_val = art.get("date") or art.get("published_at") or art.get("publishedAt")
            date_str = _parse_date(date_val)
            if date_str is None and date_val is not None:
                print(f"[WARN] Unparseable date skipped: {date_val}", flush=True)
            headline = art.get("title") or art.get("headline") or ""
            if headline is None:
                headline = ""
            headline = str(headline).strip()
            sent = art.get("sentiment") or art.get("sentiment_score")
            try:
                sentiment = float(sent) if sent is not None else 0.0
            except (TypeError, ValueError):
                sentiment = 0.0
            rows.append({"Date": date_str or "", "Ticker": ticker, "Headline": headline, "Sentiment": sentiment})

    if not rows:
        print("No articles to ingest.", flush=True)
        return 0

    try:
        df = pd.DataFrame(rows)
    except Exception as e:
        print(f"ERROR: DataFrame build failed: {e}", flush=True)
        return 1
    df = df[df["Date"] != ""]
    if df.empty:
        print("No articles with valid dates.", flush=True)
        return 0
    df = df.drop_duplicates(subset=["Date", "Ticker", "Headline"])
    df = df.sort_values(["Ticker", "Date"]).reset_index(drop=True)

    out_dir = Path(NEWS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    df = df.copy()
    df["_year"] = df["Date"].str[:4]
    df["_month"] = df["Date"].str[5:7]
    for (year, month), group in df.groupby(["_year", "_month"]):
        fname = f"eodhd_{year}_{month}.parquet"
        out_path = out_dir / fname
        try:
            group[["Date", "Ticker", "Headline", "Sentiment"]].to_parquet(out_path, engine="fastparquet", index=False)
            written.append(out_path)
        except Exception as e:
            print(f"ERROR: Write failed for {fname}: {e}", flush=True)
            return 1

    for ticker in df["Ticker"].unique():
        sub = df[df["Ticker"] == ticker]
        dmin = sub["Date"].min()
        dmax = sub["Date"].max()
        n = len(sub)
        print(f"  {ticker}: {dmin} to {dmax}  ({n} articles)", flush=True)
    total_rows = len(df)
    n_tickers = df["Ticker"].nunique()
    n_files = len(written)
    print(
        f"Ingested {total_rows} articles across {n_tickers} tickers into {n_files} parquet files.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
