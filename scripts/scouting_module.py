from __future__ import annotations

import json
import math
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
import yaml

DATA_DIR = Path(os.environ.get("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
NEWS_DIR = DATA_DIR / "news"
EODHD_PARQUET = NEWS_DIR / "eodhd_global_backfill.parquet"
UNIVERSE_PATH = Path(__file__).resolve().parent.parent / "config" / "universe.yaml"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
PIT_CSV_PATH = OUTPUT_DIR / "pit_candidates.csv"
PIT_HISTORY_PATH = OUTPUT_DIR / "pit_scores_history.json"

SEED_TICKERS = ["NVDA", "AMD", "TSM", "ASML"]
ETF_LIST = ["SMH", "SOXX", "AIQ", "ROBO"]
KEYWORDS = [
    "AI supply chain",
    "semiconductor",
    "HBM",
    "datacenter",
    "NVDA customer",
    "inference",
    "GPU cluster",
    "hyperscaler",
]

PILLAR1_WEIGHT = 0.50
PILLAR2_WEIGHT = 0.30
PILLAR3_WEIGHT = 0.20
LOOKBACK_DAYS = 90
ENTRY_THRESHOLD = 0.25
ENTRY_MIN_MONTHS = 2


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: dict) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2))


def _load_universe_exclusion() -> set[str]:
    if not UNIVERSE_PATH.exists():
        return set()
    with open(UNIVERSE_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    pillars = data.get("pillars") or {}
    out: set[str] = set()
    for _, tickers in pillars.items():
        if isinstance(tickers, list):
            for t in tickers:
                ts = str(t).strip().upper()
                if ts:
                    out.add(ts)
    return out


def _load_eodhd_tickers() -> set[str]:
    if not EODHD_PARQUET.exists():
        return set()
    try:
        df = pd.read_parquet(EODHD_PARQUET, engine="fastparquet")
    except Exception:
        return set()
    if "Ticker" not in df.columns:
        return set()
    return {str(t).strip().upper() for t in df["Ticker"].dropna().unique() if str(t).strip()}


def _load_etf_constituents() -> tuple[dict[str, set[str]], set[str]]:
    per_etf: dict[str, set[str]] = {}
    union_set: set[str] = set()
    for etf in ETF_LIST:
        members: set[str] = set()
        try:
            fd = yf.Ticker(etf).get_funds_data()
            if fd is None:
                per_etf[etf] = set()
                continue
            th = fd.top_holdings
            if th is not None and len(th) > 0:
                # top_holdings index contains ticker symbols
                members = {str(x).strip().upper() for x in th.index.tolist() if str(x).strip()}
        except Exception:
            members = set()
        per_etf[etf] = members
        union_set.update(members)
    return per_etf, union_set


def _is_valid_equity_symbol(t: str) -> bool:
    ts = str(t).strip().upper()
    if not ts:
        return False
    if " " in ts:
        return False
    if len(ts) > 10:
        return False
    return True


def _iter_window_months(start_d: date, end_d: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    cur = date(start_d.year, start_d.month, 1)
    end_m = date(end_d.year, end_d.month, 1)
    while cur <= end_m:
        months.append((cur.year, cur.month))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


def _load_seed_articles(today_d: date) -> list[dict]:
    start_d = today_d - timedelta(days=LOOKBACK_DAYS)
    months = _iter_window_months(start_d, today_d)
    dedup: dict[str, dict] = {}

    def _ingest(items: list) -> None:
        for art in items:
            if not isinstance(art, dict):
                continue
            pub = str(art.get("publishedAt") or art.get("published_at") or "").strip()
            if not pub:
                continue
            try:
                pub_date = pd.to_datetime(pub).date()
            except Exception:
                continue
            if pub_date < start_d or pub_date > today_d:
                continue
            title = str(art.get("title") or "")
            desc = str(art.get("description") or "")
            url = str(art.get("url") or "").strip()
            key = url if url else f"{title}||{pub}"
            dedup[key] = {
                "title": title,
                "description": desc,
                "publishedAt": pub,
            }

    for seed in SEED_TICKERS:
        consolidated = NEWS_DIR / f"{seed}_news.json"
        if consolidated.exists():
            try:
                with open(consolidated, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, list):
                    _ingest(payload)
            except Exception:
                pass
        for y, m in months:
            monthly = NEWS_DIR / f"{seed}_{y}_{m:02d}.json"
            if not monthly.exists():
                continue
            try:
                with open(monthly, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, list):
                    _ingest(payload)
            except Exception:
                pass
    return list(dedup.values())


def _minmax_normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    vals = list(values.values())
    mn = min(vals)
    mx = max(vals)
    out: dict[str, float] = {}
    if mx - mn <= 1e-12:
        for k, v in values.items():
            out[k] = 1.0 if v > 0 else 0.0
        return out
    for k, v in values.items():
        out[k] = (v - mn) / (mx - mn)
    return out


def _count_whole_word_mentions(text: str, ticker: str) -> int:
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", re.IGNORECASE)
    return len(pattern.findall(text))


def _pillar1_comention(candidates: set[str], seed_articles: list[dict]) -> tuple[dict[str, float], dict[str, int]]:
    raw_counts: dict[str, int] = {t: 0 for t in candidates}
    log_scores: dict[str, float] = {t: 0.0 for t in candidates}
    for t in candidates:
        cnt = 0
        for art in seed_articles:
            text = f"{art.get('title', '')} {art.get('description', '')}"
            if _count_whole_word_mentions(text, t) > 0:
                cnt += 1
        raw_counts[t] = cnt
        log_scores[t] = math.log1p(cnt)
    norm = _minmax_normalize(log_scores)
    for t in candidates:
        if raw_counts[t] == 0:
            norm[t] = 0.0
    return norm, raw_counts


def _pillar2_etf(candidates: set[str], etf_members: dict[str, set[str]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in candidates:
        cnt = 0
        for etf in ETF_LIST:
            if t in etf_members.get(etf, set()):
                cnt += 1
        out[t] = cnt / 4.0
    return out


def _pillar3_keyword(candidates: set[str]) -> dict[str, float]:
    raw: dict[str, float] = {t: 0.0 for t in candidates}
    kw_lower = [k.lower() for k in KEYWORDS]
    for t in candidates:
        path = NEWS_DIR / f"{t}_news.json"
        if not path.exists():
            raw[t] = 0.0
            continue
        count = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, list):
                for art in items:
                    if not isinstance(art, dict):
                        continue
                    text = f"{art.get('title', '')} {art.get('description', '')}".lower()
                    for kw in kw_lower:
                        if kw in text:
                            count += 1
        except Exception:
            count = 0
        raw[t] = math.log1p(count)
    norm = _minmax_normalize(raw)
    for t in candidates:
        if raw[t] <= 0:
            norm[t] = 0.0
    return norm


def _load_history() -> dict[str, list[dict]]:
    if not PIT_HISTORY_PATH.exists():
        return {}
    try:
        with open(PIT_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _months_above_threshold(history_entries: list[dict], threshold: float) -> int:
    month_to_score: dict[str, float] = {}
    for e in history_entries:
        if not isinstance(e, dict):
            continue
        m = str(e.get("month") or "").strip()
        try:
            s = float(e.get("composite"))
        except Exception:
            continue
        if m:
            month_to_score[m] = s
    if not month_to_score:
        return 0
    months_sorted = sorted(month_to_score.keys())
    latest = months_sorted[-1]
    try:
        cur = datetime.strptime(latest, "%Y-%m").date().replace(day=1)
    except Exception:
        return 0
    run = 0
    while True:
        key = cur.strftime("%Y-%m")
        if key not in month_to_score:
            break
        if month_to_score[key] < threshold:
            break
        run += 1
        if cur.month == 1:
            cur = cur.replace(year=cur.year - 1, month=12)
        else:
            cur = cur.replace(month=cur.month - 1)
    return run


def main() -> int:
    today_d = date.today()
    as_of_date = today_d.strftime("%Y-%m-%d")
    as_of_month = today_d.strftime("%Y-%m")

    exclusion = _load_universe_exclusion()
    eodhd_tickers = _load_eodhd_tickers()
    etf_members, etf_tickers = _load_etf_constituents()

    candidate_pool = (eodhd_tickers | etf_tickers) - exclusion
    candidate_pool = {t for t in candidate_pool if _is_valid_equity_symbol(t)}
    print(
        f"[SCOUT] Candidate pool: {len(candidate_pool)} tickers (EODHD: {len(eodhd_tickers)}, ETF: {len(etf_tickers)}, deduped).",
        flush=True,
    )

    seed_articles = _load_seed_articles(today_d)
    pillar1, raw_comention_counts = _pillar1_comention(candidate_pool, seed_articles)
    p1_nonzero = sum(1 for t in candidate_pool if raw_comention_counts.get(t, 0) > 0)
    print(f"[SCOUT] Pillar 1 complete: {p1_nonzero} candidates with co-mention > 0.", flush=True)

    pillar2 = _pillar2_etf(candidate_pool, etf_members)
    p2_nonzero = sum(1 for t in candidate_pool if pillar2.get(t, 0.0) > 0.0)
    print(f"[SCOUT] Pillar 2 complete: {p2_nonzero} candidates in at least one ETF.", flush=True)

    pillar3 = _pillar3_keyword(candidate_pool)
    print("[SCOUT] Pillar 3 complete.", flush=True)

    rows: list[dict] = []
    for t in candidate_pool:
        p1 = float(pillar1.get(t, 0.0))
        p2 = float(pillar2.get(t, 0.0))
        p3 = float(pillar3.get(t, 0.0))
        composite = PILLAR1_WEIGHT * p1 + PILLAR2_WEIGHT * p2 + PILLAR3_WEIGHT * p3
        if composite <= 0.0:
            continue
        rows.append(
            {
                "ticker": t,
                "composite_score": composite,
                "pillar1_comention": p1,
                "pillar2_etf": p2,
                "pillar3_keyword": p3,
            }
        )

    rows.sort(key=lambda x: x["composite_score"], reverse=True)

    history = _load_history()
    for r in rows:
        t = r["ticker"]
        history.setdefault(t, [])
        months = {str(e.get("month", "")) for e in history[t] if isinstance(e, dict)}
        if as_of_month not in months:
            history[t].append({"month": as_of_month, "composite": float(r["composite_score"])})

    for r in rows:
        t = r["ticker"]
        run_len = _months_above_threshold(history.get(t, []), ENTRY_THRESHOLD)
        r["months_above_threshold"] = int(run_len)
        r["entry_candidate"] = bool(run_len >= ENTRY_MIN_MONTHS)
        r["as_of_date"] = as_of_date

    _atomic_write_json(PIT_HISTORY_PATH, history)

    cols = [
        "ticker",
        "composite_score",
        "pillar1_comention",
        "pillar2_etf",
        "pillar3_keyword",
        "months_above_threshold",
        "entry_candidate",
        "as_of_date",
    ]
    df_out = pd.DataFrame(rows, columns=cols)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_csv = PIT_CSV_PATH.with_name(PIT_CSV_PATH.name + ".tmp")
    df_out.to_csv(tmp_csv, index=False)
    tmp_csv.replace(PIT_CSV_PATH)

    n_entry = sum(1 for r in rows if r.get("entry_candidate"))
    print("[SCOUT] === PIT SCOUTING RESULTS ===", flush=True)
    print(f"[SCOUT] Candidates scored: {len(rows)}", flush=True)
    print(f"[SCOUT] Entry candidates (>=2 months above threshold): {n_entry}", flush=True)
    print("[SCOUT] Top 5:", flush=True)
    for i, r in enumerate(rows[:5], start=1):
        print(
            f"[SCOUT]   {i}. {r['ticker']}  composite={r['composite_score']:.3f}  "
            f"(comention={r['pillar1_comention']:.2f} etf={r['pillar2_etf']:.2f} kw={r['pillar3_keyword']:.2f})",
            flush=True,
        )
    print(f"[SCOUT] Results written to {PIT_CSV_PATH}", flush=True)

    # Self-schedule next run: 1st of next month at 06:00
    try:
        import subprocess
        import sys
        _next = (today_d.replace(day=1) if today_d.month == 12
                 else today_d.replace(day=1, month=today_d.month + 1))
        if today_d.month == 12:
            _next = date(today_d.year + 1, 1, 1)
        else:
            _next = date(today_d.year, today_d.month + 1, 1)
        _sd_str = _next.strftime("%m/%d/%Y")
        _root = Path(__file__).resolve().parent.parent
        _py = sys.executable
        _script = str(Path(__file__).resolve())
        _tr = f'cmd /c cd /d "{_root}" && "{_py}" "{_script}"'
        _sch = [
            "schtasks", "/Create", "/F",
            "/TN", "AITrading_MonthlyScouting",
            "/TR", _tr,
            "/SC", "MONTHLY",
            "/D", "1",
            "/ST", "06:00",
            "/SD", _sd_str,
        ]
        _sr = subprocess.run(_sch, capture_output=True, text=True)
        if _sr.returncode != 0:
            print(
                f"[SCOUT][WARN] schtasks exit {_sr.returncode}: "
                f"{(_sr.stderr or _sr.stdout or '').strip()}",
                flush=True,
            )
        else:
            print(f"[SCOUT] Next run scheduled: {_next} 06:00 (AITrading_MonthlyScouting)", flush=True)
    except Exception as _se:
        print(f"[SCOUT][WARN] Scheduler registration failed: {_se}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
