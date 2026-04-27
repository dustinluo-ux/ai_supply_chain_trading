"""
Execute outputs/download_manifest.json on the machine with C:\\ai_supply_chain_trading\\trading_data.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATA_ROOT = Path(r"C:\ai_supply_chain_trading\trading_data")
NEWS_PARQUET = DATA_ROOT / "news" / "eodhd_global_backfill.parquet"
CSV_DIR = DATA_ROOT / "stock_market_data" / "eodhd" / "csv"
ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "outputs" / "download_manifest.json"
WEALTH_PY = Path(r"C:\Users\dusro\anaconda3\envs\wealth\python.exe")


def _load_fetch_pages():
    p = ROOT / "scripts" / "download_eodhd_news_backfill.py"
    spec = importlib.util.spec_from_file_location("eodhd_news_backfill", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _atomic_parquet(df: pd.DataFrame, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    chk = pd.read_parquet(tmp)
    if len(chk) == 0:
        tmp.unlink(missing_ok=True)
        raise ValueError("empty parquet")
    os.replace(tmp, dest)


def _download_price_csv(sym: str) -> tuple[int, int]:
    import yfinance as yf

    sym = sym.strip().upper()
    dest = CSV_DIR / f"{sym}.csv"
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    end = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    if dest.exists():
        old = pd.read_csv(dest, index_col=0, parse_dates=False)
        old.index = pd.to_datetime(old.index, errors="coerce")
        old = old[~old.index.isna()]
        old.columns = [str(c).lower() for c in old.columns]
        if len(old) < 1:
            start = "2020-01-01"
        else:
            last = old.index.max().normalize()
            start = (last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        raw = yf.Ticker(sym).history(start=start, end=end, auto_adjust=False)
    else:
        raw = yf.Ticker(sym).history(start="2020-01-01", end=end, auto_adjust=False)
    if raw is None or len(raw) == 0:
        print(f"[WARN] yfinance empty for {sym}", flush=True)
        return 0, 1
    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in raw.columns]
    if len(cols) < 5:
        print(f"[WARN] incomplete OHLCV for {sym}", flush=True)
        return 0, 1
    out = raw[cols].copy()
    out.columns = [str(c).lower() for c in out.columns]
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()]
    if dest.exists():
        old = pd.read_csv(dest, index_col=0, parse_dates=False)
        old.index = pd.to_datetime(old.index, errors="coerce")
        old = old[~old.index.isna()]
        old.columns = [str(c).lower() for c in old.columns]
        out2 = pd.concat([old, out], axis=0)
        out2 = out2[~out2.index.duplicated(keep="last")].sort_index()
        out = out2
    if len(out) < 60:
        print(f"[WARN] {sym} has {len(out)} rows (<60)", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    out.index.name = "Date"
    out.to_csv(tmp, index_label="Date")
    chk = pd.read_csv(tmp, index_col=0, parse_dates=False)
    if len(chk) < 60:
        print(f"[WARN] {sym} validated rows={len(chk)}", flush=True)
    os.replace(tmp, dest)
    return len(chk), 0


LOG_FILE = ROOT / "outputs" / "download_run_log.json"


def _write_log(log: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(log, indent=2), encoding="utf-8")
    os.replace(tmp, LOG_FILE)


def main() -> int:
    if not MANIFEST.exists():
        print(f"[ERROR] missing {MANIFEST}", flush=True)
        return 1
    import datetime

    log: dict = {
        "run_at": datetime.datetime.now().isoformat(),
        "stocks": {},
        "etfs": {},
        "steps": {},
    }
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stocks = manifest.get("stocks") or []
    etfs = manifest.get("etfs") or []
    api_key = (os.getenv("EODHD_API_KEY") or "").strip()
    all_rows: list[dict] = []
    if not api_key:
        print(
            "[WARN] EODHD_API_KEY not set — skipping EODHD news backfill (URGENT if key expiring)",
            flush=True,
        )
    else:
        print("[STEP 1] EODHD news backfill start", flush=True)
        mod = _load_fetch_pages()
        for s in stocks:
            t = str(s.get("ticker", "")).strip().upper()
            if not t:
                continue
            print(f"  [news] {t}", flush=True)
            mod._fetch_ticker_pages(api_key, t, "2020-01-01", "2024-12-31", all_rows)
        before = (
            pd.read_parquet(NEWS_PARQUET)
            if NEWS_PARQUET.exists()
            else pd.DataFrame(columns=["Date", "Ticker", "Sentiment"])
        )
        _counts_before = (  # noqa: F841
            before.groupby(before["Ticker"].astype(str).str.upper()).size().to_dict()
            if len(before)
            else {}
        )
        add_df = (
            pd.DataFrame(all_rows)
            if all_rows
            else pd.DataFrame(columns=["Date", "Ticker", "Sentiment"])
        )
        merged = pd.concat([before, add_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["Date", "Ticker"], keep="first")
        new_rows = len(merged) - len(before)
        print(f"  [news] {new_rows} net new rows added across all tickers", flush=True)
        _atomic_parquet(merged, NEWS_PARQUET)
        log["steps"]["eodhd_news"] = {"status": "ok", "net_new_rows": new_rows}
        print("[STEP 1] EODHD news backfill end", flush=True)

    print("[STEP 2] stock price CSVs start", flush=True)
    price_fail = 0
    news_counts: dict[str, int] = {}
    if NEWS_PARQUET.exists():
        ndf = pd.read_parquet(NEWS_PARQUET)
        if "Ticker" in ndf.columns:
            news_counts = (
                ndf.groupby(ndf["Ticker"].astype(str).str.upper()).size().to_dict()
            )
    stock_rows: dict[str, int] = {}
    for s in stocks:
        t = str(s.get("ticker", "")).strip().upper()
        if not t:
            continue
        print(f"  [price stock] {t}", flush=True)
        n, rc = _download_price_csv(t)
        stock_rows[t] = n
        price_fail += rc
        log["stocks"].setdefault(t, {})["price_rows"] = n
        log["stocks"][t]["price_status"] = "ok" if n >= 60 else "fail"
    print("[STEP 2] stock price CSVs end", flush=True)

    print("[STEP 3] ETF price CSVs start", flush=True)
    etf_rows: dict[str, int] = {}
    for s in etfs:
        t = str(s.get("ticker", "")).strip().upper()
        if not t:
            continue
        print(f"  [price etf] {t}", flush=True)
        n, rc = _download_price_csv(t)
        etf_rows[t] = n
        price_fail += rc
        log["etfs"].setdefault(t, {})["price_rows"] = n
        log["etfs"][t]["price_status"] = "ok" if n >= 60 else "fail"
    print("[STEP 3] ETF price CSVs end", flush=True)

    print("[STEP 4] fundamentals start", flush=True)
    stock_syms = [
        str(s.get("ticker", "")).strip().upper() for s in stocks if s.get("ticker")
    ]
    stock_syms = [x for x in stock_syms if x]
    if stock_syms:
        cmd = [
            str(WEALTH_PY),
            str(ROOT / "scripts" / "fetch_quarterly_fundamentals.py"),
            "--tickers",
            *stock_syms,
        ]
        print(f"  [subproc] {' '.join(cmd)}", flush=True)
        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        assert p.stdout
        for line in p.stdout:
            print(line, end="", flush=True)
        p.wait()
        log["steps"]["fundamentals"] = {"exit_code": p.returncode}
        if p.returncode != 0:
            print(f"[WARN] fundamentals exit code {p.returncode}", flush=True)
    print("[STEP 4] fundamentals end", flush=True)

    fq = DATA_ROOT / "fundamentals" / "quarterly_signals.parquet"
    fund_counts: dict[str, int] = {}
    if fq.exists():
        fd = pd.read_parquet(fq)
        if "ticker" in fd.columns:
            fund_counts = (
                fd.groupby(fd["ticker"].astype(str).str.upper()).size().to_dict()
            )

    print("[STEP 5] summary", flush=True)
    w = 8
    for s in stocks:
        t = str(s.get("ticker", "")).strip().upper()
        pr = stock_rows.get(t, 0)
        nw = int(news_counts.get(t, 0))
        fq_n = int(fund_counts.get(t, 0))
        st = "ok" if pr >= 60 else "price_short"
        print(
            f"{t:<{w}} | price_rows={pr} | news_articles={nw} | fundamentals_quarters={fq_n} | {st}",
            flush=True,
        )
        log["stocks"].setdefault(t, {}).update(
            {"news_articles": nw, "fundamentals_quarters": fq_n, "status": st}
        )
    for s in etfs:
        t = str(s.get("ticker", "")).strip().upper()
        pr = etf_rows.get(t, 0)
        st = "ok" if pr >= 60 else "price_short"
        print(
            f"{t:<{w}} | price_rows={pr} | news_articles=0 | fundamentals_quarters=0 | {st}",
            flush=True,
        )
        log["etfs"].setdefault(t, {})["status"] = st

    log["exit_code"] = 0 if price_fail == 0 else 1
    _write_log(log)
    print(f"[LOG] written to {LOG_FILE}", flush=True)
    return log["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
