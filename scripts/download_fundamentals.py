"""
One-time bulk download of EODHD fundamentals for PIT Scouting Module.

Downloads sector, industry, IPO date, and market cap for all Common Stock
tickers across target exchanges. Saves to:
  trading_data/fundamentals/eodhd_fundamentals_PIT.csv

Usage (CMD):
  C:\\Users\\dusro\\anaconda3\\envs\\wealth\\python.exe scripts\\download_fundamentals.py

Runtime: ~5-15 minutes depending on exchange sizes and API rate limits.
Output: ~50k-200k rows covering US, HK, JP, DE, CO, NL exchanges.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("EODHD_API_KEY", "")
if not TOKEN:
    print("[ERROR] EODHD_API_KEY not found in .env — aborting.", flush=True)
    sys.exit(1)

DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
OUT_DIR = DATA_DIR / "fundamentals"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "eodhd_fundamentals_PIT.csv"

# Target exchanges: (eodhd_code, label)
# Covers US (NASDAQ/NYSE), HK, Japan, Germany, Denmark, Netherlands
EXCHANGES = [
    ("US",    "United States"),
    ("HK",    "Hong Kong"),
    ("TSE",   "Japan (Tokyo)"),
    ("XETRA", "Germany"),
    ("CO",    "Denmark (Copenhagen)"),
    ("AS",    "Netherlands (Amsterdam)"),
    ("STO",   "Sweden (Stockholm)"),
]

COMMON_STOCK_TYPES = {"Common Stock", "cs", "stock"}
PAGE_SIZE = 500
RATE_LIMIT_DELAY = 0.5  # seconds between requests


def fetch_page(exchange: str, offset: int) -> list[dict]:
    url = (
        f"https://eodhd.com/api/bulk-fundamentals/{exchange}"
        f"?api_token={TOKEN}&fmt=json&offset={offset}&limit={PAGE_SIZE}"
    )
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            # API may return list or dict with nested list
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Some endpoints return {"data": [...]} or just the dict keyed by ticker
                if "data" in data:
                    return data["data"]
                # Dict keyed by ticker code — convert to list
                return list(data.values())
        elif resp.status_code == 429:
            print(f"  [RATE LIMIT] Waiting 10s before retry...", flush=True)
            time.sleep(10)
            return fetch_page(exchange, offset)
        else:
            print(f"  [WARN] HTTP {resp.status_code} for {exchange} offset={offset}", flush=True)
            return []
    except Exception as e:
        print(f"  [ERROR] {exchange} offset={offset}: {e}", flush=True)
        return []


def extract_fields(record: dict, exchange_label: str) -> dict | None:
    """Extract PIT-relevant fields from a bulk fundamentals record."""
    general = record.get("General", {})
    if not general:
        return None

    ticker_type = general.get("Type", "")
    if ticker_type not in COMMON_STOCK_TYPES:
        return None

    highlights = record.get("Highlights", {})
    market_cap = highlights.get("MarketCapitalization") or general.get("MarketCapitalization")

    return {
        "code":         general.get("Code", ""),
        "name":         general.get("Name", ""),
        "exchange":     general.get("Exchange", exchange_label),
        "country":      general.get("CountryISO", ""),
        "currency":     general.get("CurrencyCode", ""),
        "type":         ticker_type,
        "sector":       general.get("Sector", ""),
        "industry":     general.get("Industry", ""),
        "ipo_date":     general.get("IPODate", ""),
        "market_cap":   market_cap or "",
        "gic_sector":   general.get("GicSector", ""),
        "gic_group":    general.get("GicGroup", ""),
        "gic_industry": general.get("GicIndustry", ""),
        "description_keywords": "",  # filled later by scouting module keyword scan
    }


FIELDNAMES = [
    "code", "name", "exchange", "country", "currency", "type",
    "sector", "industry", "ipo_date", "market_cap",
    "gic_sector", "gic_group", "gic_industry", "description_keywords",
]


def main():
    print(f"[DOWNLOAD] EODHD Bulk Fundamentals — PIT Scouting Data", flush=True)
    print(f"[DOWNLOAD] Output: {OUT_CSV}", flush=True)
    print(f"[DOWNLOAD] Started: {datetime.now().isoformat()}", flush=True)
    print("=" * 60, flush=True)

    total_written = 0
    exchange_summary: dict[str, int] = {}

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()

        for ex_code, ex_label in EXCHANGES:
            print(f"\n[{ex_code}] Fetching {ex_label}...", flush=True)
            offset = 0
            ex_count = 0

            while True:
                print(f"  offset={offset}...", end=" ", flush=True)
                page = fetch_page(ex_code, offset)

                if not page:
                    print("empty — done.", flush=True)
                    break

                written_this_page = 0
                for record in page:
                    row = extract_fields(record, ex_label)
                    if row and row["code"]:
                        writer.writerow(row)
                        written_this_page += 1

                ex_count += written_this_page
                print(f"{written_this_page} common stocks written.", flush=True)

                if len(page) < PAGE_SIZE:
                    break  # last page

                offset += PAGE_SIZE
                time.sleep(RATE_LIMIT_DELAY)

            exchange_summary[ex_code] = ex_count
            total_written += ex_count
            print(f"  [{ex_code}] Total: {ex_count} tickers", flush=True)

    # Write metadata sidecar
    meta = {
        "downloaded_at": datetime.now().isoformat(),
        "total_tickers": total_written,
        "by_exchange": exchange_summary,
        "output_file": str(OUT_CSV),
        "note": "Common Stock only. Use for PIT Scouting Module Pillars 1 and 2.",
    }
    meta_path = OUT_DIR / "eodhd_fundamentals_PIT_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\n" + "=" * 60, flush=True)
    print(f"[DONE] {total_written} tickers written to {OUT_CSV}", flush=True)
    print(f"[DONE] Metadata: {meta_path}", flush=True)
    print(f"[DONE] Exchange breakdown: {exchange_summary}", flush=True)
    print(f"[DONE] Finished: {datetime.now().isoformat()}", flush=True)


if __name__ == "__main__":
    main()
