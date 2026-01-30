"""Quick check of date range for key tickers only (fast)."""
import json
from pathlib import Path

news_dir = Path(__file__).resolve().parent.parent / "data" / "news"
key_tickers = ["NVDA", "AMD", "TSM", "AAPL", "MSFT", "INTC", "QCOM", "MU", "AMAT"]
for t in key_tickers:
    path = news_dir / f"{t}_news.json"
    if not path.exists():
        print(f"  {t}: (no file)")
        continue
    try:
        with open(path, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except Exception as e:
        print(f"  {t}: error {e}")
        continue
    if not articles:
        print(f"  {t}: 0 articles")
        continue
    dates = []
    for a in articles:
        pub = a.get("publishedAt") or a.get("published_utc") or a.get("date") or ""
        if pub:
            try:
                d = pub[:10] if len(pub) >= 10 else pub
                if d.count("-") == 2:
                    dates.append(d)
            except Exception:
                pass
    if dates:
        start, end = min(dates), max(dates)
        print(f"  {t}: {start} to {end}  ({len(articles)} articles)")
    else:
        print(f"  {t}: no parseable dates  ({len(articles)} articles)")
