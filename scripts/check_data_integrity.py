"""
Read-only data integrity checker for the 40-ticker universe.

Reads config/universe.yaml (all pillars), checks price CSV presence/start date/gaps
and news JSON article counts. Outputs a table and summary. Never fatal (exit 0).

Usage:
  python scripts/check_data_integrity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd


def main() -> int:
    try:
        import yaml
        from src.data.csv_provider import find_csv_path, load_data_config
        from src.core.config import NEWS_DIR
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return 0

    universe_path = ROOT / "config" / "universe.yaml"
    if not universe_path.exists():
        print("config/universe.yaml not found.", flush=True)
        return 0
    with open(universe_path, "r", encoding="utf-8") as f:
        universe = yaml.safe_load(f)
    pillars = universe.get("pillars") or {}
    ticker_to_pillar = {}
    for pname, pillar_list in pillars.items():
        if not isinstance(pillar_list, list):
            continue
        for t in pillar_list:
            if isinstance(t, str) and t.strip():
                ticker_to_pillar[t.strip().upper()] = pname

    data_cfg = load_data_config()
    data_dir = data_cfg["data_dir"]

    rows = []
    for pname, pillar_list in pillars.items():
        if not isinstance(pillar_list, list):
            continue
        for ticker in pillar_list:
            if not isinstance(ticker, str) or not ticker.strip():
                continue
            t = ticker.strip().upper()
            pillar = pname

            # PRICE
            csv_path = find_csv_path(data_dir, t)
            if csv_path is None:
                price_start = "MISSING"
                gaps = "N/A"
            else:
                try:
                    df = pd.read_csv(csv_path, index_col=0, parse_dates=False)
                    df.index = pd.to_datetime(df.index, format="mixed", dayfirst=True)
                    if df.empty or len(df.index) == 0:
                        price_start = "MISSING"
                        gaps = "N/A"
                    else:
                        idx = df.index.sort_values()
                        price_start = idx.min().strftime("%Y-%m-%d")
                        diffs = idx.to_series().diff().dropna()
                        gap_count = int((diffs > pd.Timedelta(days=5)).sum())
                        gaps = str(gap_count)
                except Exception:
                    price_start = "MISSING"
                    gaps = "N/A"

            # NEWS
            news_path = Path(NEWS_DIR) / f"{t}_news.json"
            if not news_path.exists():
                news_count = 0
            else:
                try:
                    with open(news_path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, list):
                        news_count = len(raw)
                    elif isinstance(raw, dict) and "articles" in raw:
                        news_count = len(raw["articles"])
                    else:
                        news_count = 0
                except Exception:
                    news_count = 0

            rows.append((t, pillar, price_start, news_count, gaps))

    total = len(rows)
    n_with_prices = sum(1 for r in rows if r[2] != "MISSING")
    n_with_news = sum(1 for r in rows if r[3] > 0)

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="Data Integrity")
        table.add_column("Ticker")
        table.add_column("Pillar")
        table.add_column("Price_Start_Date")
        table.add_column("News_Article_Count")
        table.add_column("Gaps_Detected")
        for r in rows:
            table.add_row(r[0], r[1], r[2], str(r[3]), r[4])
        console.print(table)
    except ImportError:
        sep = "-" * 70
        print(sep, flush=True)
        print(f"{'Ticker':<8} {'Pillar':<10} {'Price_Start_Date':<16} {'News_Article_Count':>18}  Gaps_Detected", flush=True)
        print(sep, flush=True)
        for r in rows:
            print(f"{r[0]:<8} {r[1]:<10} {r[2]:<16} {r[3]:>18}  {r[4]}", flush=True)

    print(
        f"Data ready: {n_with_prices}/{total} tickers have price data, {n_with_news}/{total} have news.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
