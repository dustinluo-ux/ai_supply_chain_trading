"""
BAU unified data update — single entry point for all data types.

Runs on the data machine (C:\\ai_supply_chain_trading\\trading_data must exist).

What it does:
  1. Reads tickers.csv (in_latest=1) and detects new tickers not yet downloaded
  2. Adds new tickers to universe.yaml + syncs data_config.yaml
  3. Prices        — incremental for all universe tickers (yfinance, from last CSV date)
  4. EODHD news    — full 2020-2024 backfill for new tickers only
  5. Tiingo news   — last 35 days for all + full 2025-to-today for new tickers
  6. Fundamentals  — refresh all tickers (merge/replace per ticker, FMP API)
  7. Writes outputs/update_all_log.json

Usage:
    python scripts/update_all.py                  # full BAU run
    python scripts/update_all.py --skip-prices    # skip price update
    python scripts/update_all.py --skip-news      # skip all news steps
    python scripts/update_all.py --skip-fundamentals
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import pandas as pd
import yaml

WEALTH_PY = Path(r"C:\Users\dusro\anaconda3\envs\wealth\python.exe")
DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
UNIVERSE_PATH = ROOT / "config" / "universe.yaml"
DATA_CONFIG_PATH = ROOT / "config" / "data_config.yaml"
TICKERS_CSV = ROOT / "data" / "tickers.csv"
LOG_PATH = ROOT / "outputs" / "update_all_log.json"

LAYER_MAP = {
    "infrastructure": "infra",
    "compute": "compute",
    "energy": "energy",
    "application": "application",
    "model": "model",
    "adoption": "adoption",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        yaml.safe_dump(
            data, sort_keys=False, default_flow_style=False, allow_unicode=True
        ),
        encoding="utf-8",
    )
    assert yaml.safe_load(tmp.read_text(encoding="utf-8")), "invalid yaml"
    os.replace(tmp, path)


def _write_log(log: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, LOG_PATH)


def _stream(cmd: list[str]) -> int:
    print(f"  [cmd] {' '.join(str(c) for c in cmd)}", flush=True)
    p = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    assert p.stdout
    for line in p.stdout:
        print("  " + line, end="", flush=True)
    p.wait()
    return int(p.returncode or 0)


def _price_csv_exists(ticker: str) -> bool:
    subdirs = ["eodhd", "nasdaq", "sp500", "nyse", "forbes2000"]
    for sub in subdirs:
        if (DATA_DIR / "stock_market_data" / sub / "csv" / f"{ticker}.csv").exists():
            return True
    return False


def _universe_tickers() -> set[str]:
    u = _read_yaml(UNIVERSE_PATH)
    out: set[str] = set()
    for lst in (u.get("pillars") or {}).values():
        if isinstance(lst, list):
            out.update(
                str(t).strip().upper() for t in lst if isinstance(t, str) and t.strip()
            )
    return out


# ---------------------------------------------------------------------------
# Stage 0: Detect & onboard new tickers from tickers.csv
# ---------------------------------------------------------------------------


def _detect_and_onboard_new_tickers() -> list[str]:
    """
    Read tickers.csv (in_latest=1), find tickers with no price CSV on disk.
    Add them to universe.yaml + ticker_meta, sync data_config.yaml.
    Returns list of genuinely new ticker symbols.
    """
    if not TICKERS_CSV.exists():
        print("[S0] tickers.csv not found — skipping new ticker detection", flush=True)
        return []

    with open(TICKERS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    u = _read_yaml(UNIVERSE_PATH)
    pillars = u.setdefault("pillars", {})
    ticker_meta = u.setdefault("ticker_meta", {})

    new_tickers: list[str] = []
    meta_changes = 0

    for r in rows:
        t = r.get("ticker", "").strip().upper()
        if not t:
            continue
        csv_stance = r.get("stance", "").strip()
        csv_layer = r.get("supply_chain_layer", "").strip()
        csv_type = r.get("type", "").strip()
        in_latest = str(r.get("in_latest", "")).strip()

        # Sync stance drift for existing tickers regardless of in_latest
        if (
            t in ticker_meta
            and csv_stance
            and ticker_meta[t].get("stance") != csv_stance
        ):
            ticker_meta[t]["stance"] = csv_stance
            meta_changes += 1

        if in_latest != "1":
            continue

        pillar = LAYER_MAP.get(csv_layer, csv_layer)

        # Add to pillar if missing
        if pillar not in pillars:
            pillars[pillar] = []
        existing_in_pillar = {
            str(x).strip().upper() for x in pillars[pillar] if isinstance(x, str)
        }
        if t not in existing_in_pillar:
            pillars[pillar].append(t)

        # Add to ticker_meta if missing
        if t not in ticker_meta:
            ticker_meta[t] = {
                "stance": csv_stance,
                "supply_chain_layer": csv_layer,
                "type": csv_type,
            }

        # New if no price CSV on disk
        if not _price_csv_exists(t):
            new_tickers.append(t)

    u["pillars"] = pillars
    u["ticker_meta"] = ticker_meta
    _write_yaml(UNIVERSE_PATH, u)

    # Sync to data_config.yaml
    try:
        from sync_universe import sync_universe

        sync_universe(UNIVERSE_PATH, DATA_CONFIG_PATH)
    except Exception as e:
        print(f"[S0] sync_universe warning: {e}", flush=True)

    print(
        f"[S0] stance updates={meta_changes} new_tickers={len(new_tickers)}: {new_tickers}",
        flush=True,
    )
    return new_tickers


# ---------------------------------------------------------------------------
# Stage 1: Prices (incremental for all universe tickers)
# ---------------------------------------------------------------------------


def _update_prices() -> int:
    print("[S1] price update start (incremental, all universe tickers)", flush=True)
    rc = _stream([str(WEALTH_PY), str(ROOT / "scripts" / "update_price_data.py")])
    # Also update benchmarks
    try:
        _stream([str(WEALTH_PY), str(ROOT / "scripts" / "update_benchmarks.py")])
    except Exception:
        pass
    print(f"[S1] price update end exit={rc}", flush=True)
    return rc


# ---------------------------------------------------------------------------
# Stage 2: EODHD news (new tickers only, 2020-2024 historical)
# ---------------------------------------------------------------------------


def _backfill_eodhd_news(new_tickers: list[str]) -> int:
    if not new_tickers:
        print("[S2] EODHD news — no new tickers, skip", flush=True)
        return 0

    api_key = (os.getenv("EODHD_API_KEY") or "").strip()
    if not api_key:
        print(
            "[S2] EODHD_API_KEY not set — skipping EODHD backfill for new tickers",
            flush=True,
        )
        return 0

    news_parquet = DATA_DIR / "news" / "eodhd_global_backfill.parquet"
    spec = importlib.util.spec_from_file_location(
        "eodhd_news_backfill", ROOT / "scripts" / "download_eodhd_news_backfill.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)

    all_rows: list[dict] = []
    for t in new_tickers:
        print(f"[S2] EODHD fetching {t} 2020-2024 ...", flush=True)
        mod._fetch_ticker_pages(api_key, t, "2020-01-01", "2024-12-31", all_rows)

    if not all_rows:
        print("[S2] EODHD — 0 articles fetched", flush=True)
        return 0

    before = (
        pd.read_parquet(news_parquet)
        if news_parquet.exists()
        else pd.DataFrame(columns=["Date", "Ticker", "Sentiment"])
    )
    add_df = pd.DataFrame(all_rows)
    merged = pd.concat([before, add_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["Date", "Ticker"], keep="first")
    net_new = len(merged) - len(before)

    news_parquet.parent.mkdir(parents=True, exist_ok=True)
    tmp = news_parquet.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    chk = pd.read_parquet(tmp)
    if len(chk) == 0:
        tmp.unlink(missing_ok=True)
        print("[S2] EODHD parquet validation failed", flush=True)
        return 1
    os.replace(tmp, news_parquet)
    print(
        f"[S2] EODHD news end articles={len(all_rows)} net_new_rows={net_new}",
        flush=True,
    )
    return 0


# ---------------------------------------------------------------------------
# Stage 3: Tiingo news
# ---------------------------------------------------------------------------


def _update_tiingo_news(new_tickers: list[str]) -> int:
    print("[S3] Tiingo news start", flush=True)
    # Incremental for all (last 35 days)
    rc1 = _stream(
        [
            str(WEALTH_PY),
            str(ROOT / "scripts" / "fetch_tiingo_news.py"),
            "--since-days",
            "35",
        ]
    )
    # Full 2025 backfill for new tickers
    rc2 = 0
    if new_tickers:
        print(f"[S3] Tiingo full backfill for new tickers: {new_tickers}", flush=True)
        rc2 = _stream(
            [
                str(WEALTH_PY),
                str(ROOT / "scripts" / "fetch_tiingo_news.py"),
                "--start",
                "2025-01-01",
                "--tickers",
                ",".join(new_tickers),
            ]
        )
    print(
        f"[S3] Tiingo news end rc_incremental={rc1} rc_new_backfill={rc2}", flush=True
    )
    return max(rc1, rc2)


# ---------------------------------------------------------------------------
# Stage 4: Fundamentals
# ---------------------------------------------------------------------------


def _update_fundamentals() -> int:
    print("[S4] fundamentals start (all universe tickers)", flush=True)
    rc = _stream(
        [str(WEALTH_PY), str(ROOT / "scripts" / "fetch_quarterly_fundamentals.py")]
    )
    print(f"[S4] fundamentals end exit={rc}", flush=True)
    return rc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="BAU unified data update")
    parser.add_argument("--skip-prices", action="store_true")
    parser.add_argument("--skip-news", action="store_true")
    parser.add_argument("--skip-fundamentals", action="store_true")
    args = parser.parse_args()

    if not DATA_DIR.exists():
        print(
            f"[ERROR] DATA_DIR not found: {DATA_DIR} — run this on the data machine",
            flush=True,
        )
        return 1

    started = datetime.now().isoformat()
    print(f"[update_all] start {started}", flush=True)
    log: dict = {"started": started, "stages": {}, "exit_code": 0}

    # Stage 0: new ticker detection & onboarding
    new_tickers = _detect_and_onboard_new_tickers()
    log["stages"]["s0_new_tickers"] = new_tickers

    # Stage 1: prices
    if not args.skip_prices:
        rc = _update_prices()
        log["stages"]["s1_prices"] = {"exit_code": rc}
        if rc != 0:
            log["exit_code"] = rc
    else:
        print("[S1] prices skipped", flush=True)

    # Stage 2: EODHD news (new tickers only)
    if not args.skip_news:
        rc = _backfill_eodhd_news(new_tickers)
        log["stages"]["s2_eodhd_news"] = {"exit_code": rc, "new_tickers": new_tickers}
        if rc != 0:
            log["exit_code"] = rc
    else:
        print("[S2] EODHD news skipped", flush=True)

    # Stage 3: Tiingo news
    if not args.skip_news:
        rc = _update_tiingo_news(new_tickers)
        log["stages"]["s3_tiingo_news"] = {"exit_code": rc}
        if rc != 0:
            log["exit_code"] = rc
    else:
        print("[S3] Tiingo news skipped", flush=True)

    # Stage 4: fundamentals
    if not args.skip_fundamentals:
        rc = _update_fundamentals()
        log["stages"]["s4_fundamentals"] = {"exit_code": rc}
        if rc != 0:
            log["exit_code"] = rc
    else:
        print("[S4] fundamentals skipped", flush=True)

    log["finished"] = datetime.now().isoformat()
    _write_log(log)
    print(f"[update_all] done exit_code={log['exit_code']} log={LOG_PATH}", flush=True)
    return int(log["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
