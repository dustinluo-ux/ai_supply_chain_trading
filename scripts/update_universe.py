"""
CLI: add/remove universe tickers, sync data_config, optional price/news/fundamentals pipelines.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sync_universe import _collect_universe_watchlist, sync_universe

WEALTH_PY = Path(r"C:\Users\dusro\anaconda3\envs\wealth\python.exe")
UNIVERSE_PATH = ROOT / "config" / "universe.yaml"
DATA_CONFIG_PATH = ROOT / "config" / "data_config.yaml"
FILLS_PATH = ROOT / "outputs" / "fills" / "fills.jsonl"
OPT_RESULTS = ROOT / "outputs" / "optimizer_results.json"


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    return obj if isinstance(obj, dict) else {}


def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    tmp.write_text(text, encoding="utf-8")
    if len(tmp.read_text(encoding="utf-8")) == 0:
        tmp.unlink(missing_ok=True)
        raise ValueError("empty yaml")
    loaded = yaml.safe_load(tmp.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        tmp.unlink(missing_ok=True)
        raise ValueError("invalid yaml")
    os.replace(tmp, path)


def _load_eodhd_fetch() -> Any:
    path = SCRIPT_DIR / "download_eodhd_news_backfill.py"
    spec = importlib.util.spec_from_file_location("eodhd_news_backfill", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))


def _price_csv_path(ticker: str) -> Path:
    return (
        _data_dir()
        / "stock_market_data"
        / "eodhd"
        / "csv"
        / f"{ticker.strip().upper()}.csv"
    )


def _fundamentals_path() -> Path:
    return _data_dir() / "fundamentals" / "quarterly_signals.parquet"


def _news_parquet_path() -> Path:
    return _data_dir() / "news" / "eodhd_global_backfill.parquet"


def _pillar_tickers_map() -> dict[str, list[str]]:
    u = _read_yaml(UNIVERSE_PATH)
    pillars = u.get("pillars") or {}
    out: dict[str, list[str]] = {}
    if not isinstance(pillars, dict):
        return out
    for name, lst in pillars.items():
        if isinstance(lst, list):
            out[str(name)] = [
                str(x).strip() for x in lst if isinstance(x, str) and str(x).strip()
            ]
    return out


def _find_pillar_for_ticker(ticker: str) -> str | None:
    t = ticker.strip().upper()
    for pillar, lst in _pillar_tickers_map().items():
        if t in {x.upper() for x in lst}:
            return pillar
    return None


def _cmd_stream(args: list[str]) -> int:
    print(f"[SUBPROC] {' '.join(args)}", flush=True)
    p = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    assert p.stdout
    for line in p.stdout:
        print(line, end="", flush=True)
    p.wait()
    return int(p.returncode or 0)


def cmd_list() -> int:
    m = _pillar_tickers_map()
    total = 0
    for name in sorted(m.keys()):
        lst = m[name]
        total += len(lst)
        print(f"{name}: {len(lst)} tickers", flush=True)
        print("  " + ", ".join(sorted(lst)), flush=True)
    print(f"total unique (across pillars): {total}", flush=True)
    return 0


def cmd_check_add(ticker: str) -> int:
    t = ticker.strip().upper()
    print(f"[CHECK] ticker={t}", flush=True)
    m = _pillar_tickers_map()
    found = _find_pillar_for_ticker(t)
    print(f"  universe.yaml pillar: {found or '(not present)'}", flush=True)
    p = _price_csv_path(t)
    print(f"  price CSV {p}: {'exists' if p.exists() else 'missing'}", flush=True)
    npq = _news_parquet_path()
    if npq.exists():
        df = pd.read_parquet(npq)
        n = (
            int((df["Ticker"].astype(str).str.upper() == t).sum())
            if "Ticker" in df.columns
            else 0
        )
        print(f"  news parquet rows for {t}: {n}", flush=True)
    else:
        print(f"  news parquet: missing ({npq})", flush=True)
    fq = _fundamentals_path()
    if fq.exists():
        df = pd.read_parquet(fq)
        n = (
            int((df["ticker"].astype(str).str.upper() == t).sum())
            if "ticker" in df.columns
            else 0
        )
        print(f"  fundamentals parquet rows for {t}: {n}", flush=True)
    else:
        print(f"  fundamentals parquet: missing ({fq})", flush=True)
    try:
        wl = _collect_universe_watchlist(UNIVERSE_PATH)
        print(
            f"  [dry-run] watchlist would have len={len(wl)} (not writing data_config.yaml)",
            flush=True,
        )
    except Exception as exc:
        print(f"  collect_universe_watchlist would fail: {exc}", flush=True)
    return 0


def _fills_has_ticker(ticker: str) -> bool:
    t = ticker.strip().upper()
    if not FILLS_PATH.exists():
        return False
    with FILLS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym = str(obj.get("ticker") or obj.get("symbol") or "").strip().upper()
            if sym == t:
                return True
    return False


def cmd_remove(ticker: str, force: bool) -> int:
    t = ticker.strip().upper()
    print(f"[REMOVE] start ticker={t}", flush=True)
    if _fills_has_ticker(t):
        msg = f"open fills reference {t} in {FILLS_PATH}"
        if not force:
            print(
                f"[ERROR] {msg}; use --force to remove from universe anyway", flush=True
            )
            return 1
        print(f"[WARN] {msg} (proceeding due to --force)", flush=True)
    u = _read_yaml(UNIVERSE_PATH)
    pillars = u.get("pillars")
    if not isinstance(pillars, dict):
        print("[ERROR] universe.yaml missing pillars", flush=True)
        return 1
    removed = False
    for k, lst in list(pillars.items()):
        if not isinstance(lst, list):
            continue
        new_lst = [
            x for x in lst if not (isinstance(x, str) and x.strip().upper() == t)
        ]
        if len(new_lst) != len(lst):
            pillars[k] = new_lst
            removed = True
    if not removed:
        print(f"[WARN] {t} not found in any pillar", flush=True)
    u["pillars"] = pillars
    _atomic_write_yaml(UNIVERSE_PATH, u)
    sync_universe(UNIVERSE_PATH, DATA_CONFIG_PATH)
    print(f"[REMOVE] done; retained price/news/fundamentals rows for {t}", flush=True)
    return 0


def _download_price_yfinance(ticker: str) -> int:
    print(f"[STAGE 2] price CSV start {ticker}", flush=True)
    import yfinance as yf

    end = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    raw = yf.Ticker(ticker).history(start="2020-01-01", end=end, auto_adjust=False)
    if raw is None or len(raw) == 0:
        print(f"[ERROR] yfinance returned zero rows for {ticker}", flush=True)
        return 1
    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in raw.columns]
    if len(cols) < 5:
        print(
            f"[ERROR] missing OHLCV columns from yfinance for {ticker}: {list(raw.columns)}",
            flush=True,
        )
        return 1
    out = raw[cols].copy()
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()]
    if len(out) < 60:
        print(f"[ERROR] fewer than 60 rows for {ticker} (got {len(out)})", flush=True)
        return 1
    out_dir = _price_csv_path(ticker).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = _price_csv_path(ticker)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    out.index.name = "Date"
    out.to_csv(tmp, index_label="Date")
    chk = pd.read_csv(tmp, index_col=0, parse_dates=False)
    if len(chk) < 60:
        tmp.unlink(missing_ok=True)
        print("[ERROR] price tmp validation failed", flush=True)
        return 1
    os.replace(tmp, dest)
    print(f"[STAGE 2] price CSV end rows={len(out)} path={dest}", flush=True)
    return 0


def cmd_add(
    ticker: str, pillar: str, exchange: str | None, currency: str | None
) -> int:
    t = ticker.strip().upper()
    pillar = pillar.strip().lower()
    print(f"[ADD] start ticker={t} pillar={pillar}", flush=True)
    if "." in t:
        ex = (exchange or "").strip()
        cc = (currency or "").strip()
        if not ex or not cc:
            print(
                "[ERROR] non-US ticker requires --exchange and --currency", flush=True
            )
            return 1
    pillars_raw = _read_yaml(UNIVERSE_PATH).get("pillars") or {}
    if pillar not in pillars_raw:
        print(f"[ERROR] unknown pillar {pillar}", flush=True)
        return 1
    pre_universe = UNIVERSE_PATH.read_text(encoding="utf-8")
    u = _read_yaml(UNIVERSE_PATH)
    pillars = u.get("pillars")
    if not isinstance(pillars, dict):
        print("[ERROR] universe pillars missing", flush=True)
        return 1
    plst = pillars.get(pillar)
    if not isinstance(plst, list):
        plst = []
    if t in {str(x).strip().upper() for x in plst if isinstance(x, str)}:
        print(f"[WARN] {t} already in pillar {pillar}", flush=True)
    else:
        plst.append(t)
        pillars[pillar] = plst
    u["pillars"] = pillars
    if "." in t:
        ibkr = u.get("ibkr_symbols")
        if not isinstance(ibkr, dict):
            ibkr = {}
        sym_part = t.split(".")[0]
        ibkr[t] = f"{sym_part} STK {ex.strip().upper()}"
        u["ibkr_symbols"] = ibkr
    try:
        _atomic_write_yaml(UNIVERSE_PATH, u)
    except Exception as exc:
        print(f"[ERROR] universe write failed: {exc}", flush=True)
        return 1
    try:
        sync_universe(UNIVERSE_PATH, DATA_CONFIG_PATH)
    except Exception as exc:
        UNIVERSE_PATH.write_text(pre_universe, encoding="utf-8")
        print(
            f"[ERROR] sync_universe failed ({exc}); restored universe.yaml", flush=True
        )
        return 1
    print("[STAGE 1] config end", flush=True)

    if _download_price_yfinance(t) != 0:
        return 1

    api_key = (os.getenv("EODHD_API_KEY") or "").strip()
    news_n = 0
    if not api_key:
        print("[WARN] EODHD_API_KEY unset; skipping news backfill stage", flush=True)
    else:
        print("[STAGE 3] news backfill start", flush=True)
        mod = _load_eodhd_fetch()
        rows_out: list[dict[str, Any]] = []
        mod._fetch_ticker_pages(api_key, t, "2020-01-01", "2024-12-31", rows_out)
        news_n = len(rows_out)
        npq = _news_parquet_path()
        npq.parent.mkdir(parents=True, exist_ok=True)
        before = (
            pd.read_parquet(npq)
            if npq.exists()
            else pd.DataFrame(columns=["Date", "Ticker", "Sentiment"])
        )
        counts_before = (
            before.groupby(before["Ticker"].astype(str).str.upper()).size().to_dict()
            if len(before)
            else {}
        )
        add_df = (
            pd.DataFrame(rows_out)
            if rows_out
            else pd.DataFrame(columns=["Date", "Ticker", "Sentiment"])
        )
        merged = pd.concat([before, add_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["Date", "Ticker"], keep="first")
        counts_after = (
            merged.groupby(merged["Ticker"].astype(str).str.upper()).size().to_dict()
        )
        for sym, c in counts_before.items():
            if sym == t:
                continue
            if int(counts_after.get(sym, 0)) != int(c):
                print(
                    f"[ERROR] news row count drift for {sym}: {c} -> {counts_after.get(sym)}; abort",
                    flush=True,
                )
                return 1
        tmp = npq.with_suffix(npq.suffix + ".tmp")
        merged.to_parquet(tmp, index=False)
        chk = pd.read_parquet(tmp)
        if len(chk) == 0:
            tmp.unlink(missing_ok=True)
            print("[ERROR] news parquet tmp empty", flush=True)
            return 1
        os.replace(tmp, npq)
        print(f"[STAGE 3] news backfill end articles={news_n}", flush=True)

    print("[STAGE 3b] Tiingo 2025+ news backfill start", flush=True)
    tiingo_rc = _cmd_stream(
        [
            str(WEALTH_PY),
            str(ROOT / "scripts" / "fetch_tiingo_news.py"),
            "--start",
            "2025-01-01",
            "--tickers",
            t,
        ]
    )
    if tiingo_rc != 0:
        print(f"[WARN] Tiingo fetch exit {tiingo_rc}; continuing", flush=True)
    print("[STAGE 3b] Tiingo 2025+ news backfill end", flush=True)

    print("[STAGE 4] fundamentals start", flush=True)
    fq = _fundamentals_path()
    counts_f_before: dict[str, int] = {}
    if fq.exists():
        ef = pd.read_parquet(fq)
        counts_f_before = (
            ef.groupby(ef["ticker"].astype(str).str.upper()).size().to_dict()
        )
    rc = _cmd_stream(
        [
            str(WEALTH_PY),
            str(ROOT / "scripts" / "fetch_quarterly_fundamentals.py"),
            "--tickers",
            t,
        ]
    )
    if rc != 0:
        print(f"[ERROR] fetch_quarterly_fundamentals exit {rc}", flush=True)
        return 1
    if not fq.exists():
        print("[ERROR] fundamentals parquet missing after fetch", flush=True)
        return 1
    ef2 = pd.read_parquet(fq)
    counts_f_after = ef2.groupby(ef2["ticker"].astype(str).str.upper()).size().to_dict()
    if int(counts_f_after.get(t, 0)) < 1:
        print(f"[ERROR] no fundamentals rows for {t}", flush=True)
        return 1
    for sym, c in counts_f_before.items():
        if sym == t:
            continue
        if int(counts_f_after.get(sym, 0)) != int(c):
            print(f"[ERROR] fundamentals row drift for {sym}", flush=True)
            return 1
    print("[STAGE 4] fundamentals end", flush=True)

    print("[STAGE 5] train_ml_model start", flush=True)
    trc = _cmd_stream([str(WEALTH_PY), str(ROOT / "scripts" / "train_ml_model.py")])
    print(f"[STAGE 5] train_ml_model end exit={trc}", flush=True)

    print("[STAGE 6] run_optimizer start", flush=True)
    orc = _cmd_stream(
        [
            str(WEALTH_PY),
            str(ROOT / "scripts" / "run_optimizer.py"),
            "--n-trials",
            "10",
            "--skip-data",
        ]
    )
    print(f"[STAGE 6] run_optimizer end exit={orc}", flush=True)

    print("[STAGE 7] run_promoter start", flush=True)
    prc = _cmd_stream([str(WEALTH_PY), str(ROOT / "scripts" / "run_promoter.py")])
    print(f"[STAGE 7] run_promoter end exit={prc}", flush=True)

    comp = ""
    if OPT_RESULTS.exists():
        try:
            data = json.loads(OPT_RESULTS.read_text(encoding="utf-8"))
            comp = str((data.get("winner") or {}).get("composite", ""))
        except Exception:
            comp = "(unreadable)"
    price_rows = 0
    pc = _price_csv_path(t)
    if pc.exists():
        price_rows = len(pd.read_csv(pc, index_col=0))
    fund_q = int(counts_f_after.get(t, 0))
    news_label = str(news_n) if api_key else "skipped (no EODHD key)"
    tiingo_label = "ok" if tiingo_rc == 0 else f"warn exit={tiingo_rc}"
    print("[STAGE 8] summary", flush=True)
    rows_tab = [
        ("ticker_added", t),
        ("price_rows_downloaded", str(price_rows)),
        ("news_articles_fetched_eodhd", news_label),
        ("news_tiingo_2025_backfill", tiingo_label),
        ("fundamental_quarters_loaded", str(fund_q)),
        ("retrain_exit_code", str(trc)),
        ("optimizer_best_composite", comp if comp else "(n/a)"),
        ("optimizer_exit_code", str(orc)),
        ("promotion_exit_code", str(prc)),
    ]
    w = max(len(a) for a, _ in rows_tab)
    for k, v in rows_tab:
        print(f"{k:<{w}} | {v}", flush=True)
    return 0 if trc == 0 and orc == 0 and prc == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--add", type=str, default=None, metavar="TICKER")
    p.add_argument("--remove", type=str, default=None, metavar="TICKER")
    p.add_argument("--pillar", type=str, default=None)
    p.add_argument("--exchange", type=str, default=None)
    p.add_argument("--currency", type=str, default=None)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    if args.list:
        if args.add or args.remove or args.check:
            print(
                "[ERROR] --list cannot combine with --add/--remove/--check", flush=True
            )
            return 1
        return cmd_list()
    if args.remove:
        if args.add or args.list or args.check:
            print(
                "[ERROR] --remove cannot combine with --add/--list/--check", flush=True
            )
            return 1
        return cmd_remove(args.remove, args.force)
    if args.check:
        if not args.add:
            print("[ERROR] --check requires --add TICKER", flush=True)
            return 1
        if args.pillar:
            print("[ERROR] --check dry-run does not use --pillar", flush=True)
            return 1
        return cmd_check_add(args.add)
    if args.add:
        if not args.pillar:
            print(
                "[ERROR] full --add requires --pillar PILLAR (use --check --add for dry-run)",
                flush=True,
            )
            return 1
        return cmd_add(args.add, args.pillar, args.exchange, args.currency)
    print(
        "[ERROR] specify --list, --check --add TICKER, --add TICKER --pillar P, or --remove TICKER",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
