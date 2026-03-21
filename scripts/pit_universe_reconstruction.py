"""
Point-in-time (PIT) universe reconstruction — one-time research tool.

Reconstructs which tickers co-appeared in EODHD news with seed names (NVDA, AMD, TSM, ASML)
per calendar quarter 2022–2024. Not BAU: no scheduling, no execution spine integration.

Usage:
  python scripts/pit_universe_reconstruction.py
"""
from __future__ import annotations

import csv
import os
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

import requests
import yaml

SEED_SYMBOLS = ("NVDA.US", "AMD.US", "TSM.US", "ASML.US")
SEED_TO_LABEL = {"NVDA.US": "NVDA", "AMD.US": "AMD", "TSM.US": "TSM", "ASML.US": "ASML"}
INDEX_BASES = frozenset({"GSPC", "IXIC", "DJI", "RUT", "VIX"})
EVAL_DATES: tuple[date, ...] = (
    date(2022, 1, 1),
    date(2022, 4, 1),
    date(2022, 7, 1),
    date(2022, 10, 1),
    date(2023, 1, 1),
    date(2023, 4, 1),
    date(2023, 7, 1),
    date(2023, 10, 1),
    date(2024, 1, 1),
    date(2024, 4, 1),
    date(2024, 7, 1),
    date(2024, 10, 1),
)
NEWS_URL = "https://eodhd.com/api/news"
LIMIT = 100
RATE_SLEEP_SEC = 0.5
LOOKBACK_DAYS = 90


def _load_current_universe_tickers() -> set[str]:
    """Flatten list values under config/universe.yaml (pillars and any other top-level lists)."""
    path = ROOT / "config" / "universe.yaml"
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    out: set[str] = set()
    for _key, val in raw.items():
        if isinstance(val, list):
            for t in val:
                if isinstance(t, str) and t.strip():
                    out.add(t.strip().upper())
        elif isinstance(val, dict):
            for _sub, subval in val.items():
                if isinstance(subval, list):
                    for t in subval:
                        if isinstance(t, str) and t.strip():
                            out.add(t.strip().upper())
    return out


def _article_symbols(article: dict) -> list[str]:
    """Extract symbol strings from EODHD news article (list or comma-separated)."""
    sym = article.get("symbols")
    if sym is None:
        sym = article.get("symbol")
    if sym is None:
        return []
    if isinstance(sym, str):
        parts = [p.strip() for p in sym.replace(";", ",").split(",") if p.strip()]
        return parts
    if isinstance(sym, list):
        out = []
        for x in sym:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, dict):
                s = x.get("name") or x.get("symbol") or x.get("code")
                if isinstance(s, str) and s.strip():
                    out.append(s.strip())
        return out
    return []


def _normalize_us_base(symbol: str) -> str | None:
    s = symbol.strip().upper()
    if not s.endswith(".US"):
        return None
    base = s[:-3]
    if not base or base in INDEX_BASES:
        return None
    return base


def _fetch_seed_window(
    api_token: str,
    seed_symbol: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    """Paginate EODHD news for one seed; 0.5s sleep after each HTTP request."""
    all_rows: list[dict] = []
    offset = 0
    while True:
        try:
            r = requests.get(
                NEWS_URL,
                params={
                    "s": seed_symbol,
                    "api_token": api_token,
                    "limit": LIMIT,
                    "offset": offset,
                    "from": date_from,
                    "to": date_to,
                },
                timeout=60,
            )
            time.sleep(RATE_SLEEP_SEC)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    [WARN] {seed_symbol} offset={offset}: {e}", flush=True)
            break
        if not isinstance(data, list) or len(data) == 0:
            break
        all_rows.extend(data)
        if len(data) < LIMIT:
            break
        offset += LIMIT
    return all_rows


def _process_eval_date(
    eval_d: date,
    api_token: str,
) -> tuple[dict[str, int], dict[str, set[str]], dict[str, int]]:
    """
    Returns:
      counts: base_ticker -> co-mention count (once per article per ticker)
      seeds_by: base_ticker -> set of seed labels (NVDA, AMD, ...)
      articles_per_seed: seed_symbol -> article count fetched
    """
    window_end = eval_d
    window_start = eval_d - timedelta(days=LOOKBACK_DAYS)
    date_from = window_start.isoformat()
    date_to = window_end.isoformat()

    counts: dict[str, int] = defaultdict(int)
    seeds_by: dict[str, set[str]] = defaultdict(set)
    articles_per_seed: dict[str, int] = {}

    seed_label = SEED_TO_LABEL

    for seed_sym in SEED_SYMBOLS:
        articles = _fetch_seed_window(api_token, seed_sym, date_from, date_to)
        articles_per_seed[seed_sym] = len(articles)
        label = seed_label[seed_sym]
        for article in articles:
            if not isinstance(article, dict):
                continue
            bases_in_article: set[str] = set()
            for sym in _article_symbols(article):
                b = _normalize_us_base(sym)
                if b is None:
                    continue
                bases_in_article.add(b)
            for b in bases_in_article:
                counts[b] += 1
                seeds_by[b].add(label)

    return dict(counts), {k: v for k, v in seeds_by.items()}, articles_per_seed


def main() -> int:
    api_token = os.environ.get("EODHD_API_KEY", "").strip()
    if not api_token:
        print("ERROR: EODHD_API_KEY not set. Add it to .env at project root.", flush=True)
        return 1

    current = _load_current_universe_tickers()
    print(f"Loaded {len(current)} tickers from config/universe.yaml", flush=True)

    out_dir = ROOT / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    recon_path = out_dir / "pit_universe_reconstruction.csv"
    discoveries_path = out_dir / "pit_new_discoveries.csv"

    all_rows: list[dict] = []
    discoveries_rows: list[dict] = []

    for eval_d in EVAL_DATES:
        print(f"\n=== eval_date={eval_d.isoformat()} (lookback {LOOKBACK_DAYS}d -> { (eval_d - timedelta(days=LOOKBACK_DAYS)).isoformat() } .. {eval_d.isoformat()}) ===", flush=True)
        counts, seeds_by, per_seed = _process_eval_date(eval_d, api_token)
        for sym, n in per_seed.items():
            print(f"  seed {sym}: {n} articles fetched", flush=True)
        print(f"  unique .US co-mention candidates: {len(counts)}", flush=True)

        for ticker, co_cnt in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            seeds_str = ",".join(sorted(seeds_by.get(ticker, set())))
            in_uni = ticker.upper() in current
            row = {
                "eval_date": eval_d.isoformat(),
                "ticker": ticker,
                "co_mention_count": co_cnt,
                "seeds_mentioned_by": seeds_str,
                "in_current_universe": in_uni,
            }
            all_rows.append(row)
            if not in_uni and co_cnt >= 5:
                discoveries_rows.append(row)

    with open(recon_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["eval_date", "ticker", "co_mention_count", "seeds_mentioned_by", "in_current_universe"],
        )
        w.writeheader()
        for row in all_rows:
            w.writerow(
                {
                    **row,
                    "in_current_universe": row["in_current_universe"],
                }
            )

    discoveries_sorted = sorted(
        discoveries_rows,
        key=lambda r: (r["eval_date"], -r["co_mention_count"]),
    )
    with open(discoveries_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["eval_date", "ticker", "co_mention_count", "seeds_mentioned_by", "in_current_universe"],
        )
        w.writeheader()
        for row in discoveries_sorted:
            w.writerow(
                {
                    **row,
                    "in_current_universe": row["in_current_universe"],
                }
            )

    print(f"\nWrote {recon_path}", flush=True)
    print(f"Wrote {discoveries_path} ({len(discoveries_sorted)} new-discovery rows)", flush=True)

    # Final summary: new discoveries by quarter (eval_date)
    print("\n--- New discoveries (not in current universe, co_mention_count >= 5) by quarter ---", flush=True)
    by_q: dict[str, int] = defaultdict(int)
    for r in discoveries_sorted:
        by_q[r["eval_date"]] += 1
    for ed in [e.isoformat() for e in EVAL_DATES]:
        n = by_q.get(ed, 0)
        print(f"  {ed}: {n}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
