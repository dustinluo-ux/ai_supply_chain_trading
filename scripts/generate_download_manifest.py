"""
Emit outputs/download_manifest.json + .txt listing universe tickers missing price CSVs on disk.

Checks actual price CSV presence in DATA_DIR (from .env) so it remains accurate even after
universe.yaml is updated. Falls back to tickers-not-in-universe comparison if DATA_DIR
is not accessible (e.g. running on dev machine without the data drive mounted).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "outputs" / "download_manifest.json"
OUT_TXT = ROOT / "outputs" / "download_manifest.txt"
TICKERS_CSV = ROOT / "data" / "tickers.csv"
UNIVERSE_PATH = ROOT / "config" / "universe.yaml"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))


def _price_csv_exists(ticker: str, data_dir: Path) -> bool:
    """Check all known price CSV locations for this ticker."""
    subdirs = ["eodhd", "nasdaq", "sp500", "nyse", "forbes2000"]
    for sub in subdirs:
        p = data_dir / "stock_market_data" / sub / "csv" / f"{ticker}.csv"
        if p.exists():
            return True
    return False


def _flatten_pillars(pillars: dict) -> set[str]:
    out: set[str] = set()
    for lst in pillars.values():
        if isinstance(lst, list):
            for x in lst:
                if isinstance(x, str) and x.strip():
                    out.add(x.strip().upper())
    return out


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if len(tmp.read_text(encoding="utf-8")) == 0:
        tmp.unlink(missing_ok=True)
        raise SystemExit(1)
    os.replace(tmp, path)


def _atomic_write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    if len(tmp.read_text(encoding="utf-8")) == 0:
        tmp.unlink(missing_ok=True)
        raise SystemExit(1)
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def main() -> int:
    today = date.today().isoformat()
    u = yaml.safe_load(UNIVERSE_PATH.read_text(encoding="utf-8")) or {}
    uni = _flatten_pillars(u.get("pillars") or {})

    data_dir = _data_dir()
    disk_check = data_dir.exists()
    if not disk_check:
        print(
            f"[WARN] DATA_DIR not accessible ({data_dir}); falling back to universe diff mode",
            flush=True,
        )

    df = pd.read_csv(TICKERS_CSV)
    df.columns = [str(c).lower() for c in df.columns]

    stocks: list[dict[str, object]] = []
    etfs: list[dict[str, object]] = []

    for _, row in df.iterrows():
        sym = str(row.get("ticker", "")).strip().upper()
        if not sym:
            continue
        typ = str(row.get("type", "")).strip().lower()
        layer = str(row.get("supply_chain_layer", "")).strip()

        # In disk-check mode: list tickers in universe that have no price CSV
        # In fallback mode: list tickers not yet in universe.yaml
        if disk_check:
            needs_download = sym in uni and not _price_csv_exists(sym, data_dir)
        else:
            needs_download = sym not in uni

        if not needs_download:
            continue

        if typ == "stock":
            stocks.append(
                {
                    "ticker": sym,
                    "supply_chain_layer": layer,
                    "needs_price_csv": True,
                    "needs_eodhd_news": True,
                    "needs_fundamentals": True,
                    "eodhd_date_range": ["2020-01-01", "2024-12-31"],
                    "price_date_range": ["2020-01-01", today],
                }
            )
        elif typ == "etf":
            etfs.append(
                {
                    "ticker": sym,
                    "supply_chain_layer": layer,
                    "needs_price_csv": True,
                    "needs_eodhd_news": False,
                    "needs_fundamentals": False,
                    "price_date_range": ["2020-01-01", today],
                }
            )

    mode = "disk-check" if disk_check else "universe-diff (fallback)"
    manifest = {"generated": today, "mode": mode, "stocks": stocks, "etfs": etfs}
    _atomic_write_json(OUT_JSON, manifest)
    txt = (
        f"mode={mode} stocks={len(stocks)} etfs={len(etfs)}\n"
        "Run scripts/run_download_manifest.py on the target machine (data drive must be C:).\n"
    )
    _atomic_write_text(OUT_TXT, txt)
    print(f"[OK] wrote {OUT_JSON} and {OUT_TXT}", flush=True)
    print(f"     mode={mode} new_stocks={len(stocks)} new_etfs={len(etfs)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
