"""
Fetch quarterly fundamental signals for universe tickers.

Primary source: Financial Modeling Prep (FMP) when FMP_API_KEY is set; otherwise
yfinance, then EODHD fundamentals for earnings fields where applicable.

Output:
  trading_data/fundamentals/quarterly_signals.parquet

Atomic write:
  write .tmp -> validate -> rename
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import yaml
from dotenv import load_dotenv
from src.data.edgar_audit import audit_ticker
from src.data.fmp_ingest import load_fmp_quarters
from src.fundamentals.quality_metrics import compute_quality_metrics
from src.fundamentals.semi_valuation import SemiValuationEngine

load_dotenv(ROOT / ".env")

TOKEN = os.getenv("EODHD_API_KEY", "")
if not TOKEN:
    print(
        "[WARN] EODHD_API_KEY not set — EODHD fallback disabled, yfinance only",
        flush=True,
    )

FMP_KEY = os.getenv("FMP_API_KEY", "").strip()
if not FMP_KEY:
    print("[WARN] FMP_API_KEY not set — FMP disabled, yfinance/EODHD only", flush=True)

DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
OUT_DIR = DATA_DIR / "fundamentals"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "quarterly_signals.parquet"
TMP_FILE = OUT_DIR / "quarterly_signals.parquet.tmp"

UNIVERSE_PATH = ROOT / "config" / "universe.yaml"
INSTRUMENTS_PATH = ROOT / "config" / "instruments.yaml"

OUT_COLUMNS = [
    "ticker",
    "period_end",
    "filing_date",
    "gross_margin_pct",
    "inventory_days",
    "last_eps_surprise_pct",
    "earnings_revision_30d",
    "last_earnings_date",
    "next_earnings_date",
    "fcf_ttm",
    "debt_to_equity",
    "inventory_days_accel",
    "gross_margin_delta",
    "last_rev_surprise_pct",
    "fcf_yield",
    "roic",
    "fcf_conversion",
    "net_capex_sales",
    "net_debt_ebitda",
    "fcff_adjusted",
    "fcff_raw",
    "rd_cap_variance_pct",
    "sbc_pct_revenue",
    "edgar_audit_flag",
]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_fmp(v: Any) -> float:
    if v is None:
        return float("nan")
    try:
        from decimal import Decimal

        if isinstance(v, Decimal):
            return float(v)
    except Exception:
        pass
    x = _safe_float(v)
    return float("nan") if x is None else float(x)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    if not isinstance(obj, dict):
        return {}
    return obj


def _flatten_tickers(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, str):
                out.append(item.strip())
            else:
                out.extend(_flatten_tickers(item))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_flatten_tickers(v))
    return out


def _load_universe_tickers() -> list[str]:
    universe = _read_yaml(UNIVERSE_PATH)
    tickers: list[str] = []
    if "pillars" in universe:
        tickers.extend(_flatten_tickers(universe.get("pillars")))
    # Support alternate key naming without assuming one exact schema.
    if "global_equities" in universe:
        tickers.extend(_flatten_tickers(universe.get("global_equities")))
    # Fallback for legacy key from this repo.
    if "global" in (universe.get("pillars") or {}):
        tickers.extend(_flatten_tickers((universe.get("pillars") or {}).get("global")))
    tickers = [t for t in tickers if t and isinstance(t, str)]
    return sorted(set(tickers))


def _restrict_to_tickers(full: list[str], requested: list[str]) -> list[str]:
    want = {x.strip().upper() for x in requested if x and str(x).strip()}
    out = sorted([t for t in full if t.strip().upper() in want])
    missing = want - {t.upper() for t in out}
    if missing:
        print(
            f"[ERROR] --tickers not found in universe.yaml: {sorted(missing)}",
            flush=True,
        )
        sys.exit(1)
    return out


def _parse_cli(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quarterly fundamentals fetch")
    p.add_argument("--mode", default="quarterly", choices=("quarterly", "weekly"))
    p.add_argument("--tickers", nargs="+", default=None, metavar="SYM")
    return p.parse_args(argv)


def _load_suffix_mapping() -> dict[str, str]:
    instruments = _read_yaml(INSTRUMENTS_PATH)
    # Expected to exist in config/instruments.yaml; keep tolerant key matching.
    candidate_keys = (
        "eodhd_suffix_map",
        "exchange_suffix_map",
        "ticker_suffix_map",
        "suffix_map",
    )
    for key in candidate_keys:
        m = instruments.get(key)
        if isinstance(m, dict):
            return {str(k): str(v) for k, v in m.items()}
    # If mapping is absent, default to empty and preserve original tickers.
    return {}


def _normalize_eodhd_ticker(ticker: str, suffix_map: dict[str, str]) -> str:
    t = ticker.strip().upper()
    if "." in t:
        # Already exchange-qualified.
        return t

    # Optional map keyed by suffix labels (HK/T/DE/CO) or full market names.
    if not suffix_map:
        return t

    raw = suffix_map.get(t)
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    return t


def _fetch_fundamentals_one(ticker: str) -> dict[str, Any] | None:
    url = f"https://eodhd.com/api/fundamentals/{ticker}?api_token={TOKEN}&fmt=json"
    while True:
        try:
            resp = requests.get(url, timeout=30)
        except Exception as exc:
            print(f"[WARN] request error for {ticker}: {exc}", flush=True)
            return None

        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception as exc:
                print(f"[WARN] invalid JSON for {ticker}: {exc}", flush=True)
                return None
            return data if isinstance(data, dict) else None
        if resp.status_code == 429:
            print(f"[WARN] rate limited for {ticker}, sleeping 10s", flush=True)
            time.sleep(10.0)
            continue

        print(f"[WARN] HTTP {resp.status_code} for {ticker}", flush=True)
        return None


def _as_period_map(node: Any) -> dict[str, dict[str, Any]]:
    if isinstance(node, dict):
        # Common EODHD shape: { "2024-12-31": {...}, ... }
        if all(isinstance(k, str) and isinstance(v, dict) for k, v in node.items()):
            return node  # type: ignore[return-value]
        # Alternate shape: {"data": [...]} or nested dict.
        if "data" in node and isinstance(node["data"], list):
            out: dict[str, dict[str, Any]] = {}
            for item in node["data"]:
                if not isinstance(item, dict):
                    continue
                period = str(
                    item.get("date")
                    or item.get("reportedDate")
                    or item.get("period")
                    or ""
                )
                if period:
                    out[period] = item
            return out
    if isinstance(node, list):
        out: dict[str, dict[str, Any]] = {}
        for item in node:
            if not isinstance(item, dict):
                continue
            period = str(
                item.get("date") or item.get("reportedDate") or item.get("period") or ""
            )
            if period:
                out[period] = item
        return out
    return {}


def _extract_earnings_history_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    earnings = data.get("Earnings", {})
    if not isinstance(earnings, dict):
        return {}
    history = earnings.get("History", {})
    return _as_period_map(history)


def _extract_last_rev_surprise_pct(data: dict[str, Any]) -> float | None:
    earnings_hist = _extract_earnings_history_map(data)
    if not earnings_hist:
        return None
    candidates: list[tuple[pd.Timestamp, float]] = []
    for k, row in earnings_hist.items():
        if not isinstance(row, dict):
            continue
        ts = pd.to_datetime(k, errors="coerce")
        if pd.isna(ts):
            continue
        rev_actual = _safe_float(row.get("revenueActual"))
        rev_estimate = _safe_float(row.get("revenueEstimate"))
        if rev_actual is None or rev_estimate in (None, 0.0):
            continue
        candidates.append((ts, (rev_actual - rev_estimate) / abs(rev_estimate)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return float(candidates[-1][1])


def _extract_earnings_revision_30d_and_next_date(
    data: dict[str, Any],
) -> tuple[float | None, pd.Timestamp | None]:
    earnings = data.get("Earnings", {})
    if not isinstance(earnings, dict):
        return None, None
    trend = earnings.get("Trend")
    if not trend:
        return None, None

    # Try common shapes: list of trend points or dict keyed by horizon/period.
    if isinstance(trend, list):
        candidates = [x for x in trend if isinstance(x, dict)]
    elif isinstance(trend, dict):
        candidates = []
        for v in trend.values():
            if isinstance(v, dict):
                candidates.append(v)
            elif isinstance(v, list):
                candidates.extend([x for x in v if isinstance(x, dict)])
    else:
        return None, None

    best: dict[str, Any] | None = None
    best_date: pd.Timestamp | None = None
    today = pd.Timestamp.today().normalize()
    for item in candidates:
        period_str = item.get("period") or item.get("date") or item.get("endDate")
        ts = pd.to_datetime(period_str, errors="coerce")
        if pd.isna(ts):
            continue
        if ts < today:
            continue
        if best_date is None or ts < best_date:
            best = item
            best_date = ts
    if not best:
        return None, None

    next_earnings_date = pd.to_datetime(
        best.get("reportDate") or best.get("earningsDate") or best.get("date"),
        errors="coerce",
    )
    if pd.isna(next_earnings_date):
        next_earnings_date = None

    cur = _safe_float(best.get("earningsEstimateAvg"))
    prev = _safe_float(
        best.get("earningsEstimate30DaysAgo")
        or best.get("earningsEstimateAvg30DaysAgo")
        or best.get("estimate30DaysAgo")
    )
    if cur is None or prev is None or prev == 0.0:
        return None, next_earnings_date
    return (cur - prev) / abs(prev), next_earnings_date


def _extract_yfinance(
    ticker: str, market_cap: float | None = None
) -> pd.DataFrame | None:
    yf_ticker = yf.Ticker(ticker)
    try:
        income_raw = yf_ticker.quarterly_income_stmt
    except Exception:
        income_raw = pd.DataFrame()
    try:
        balance_raw = yf_ticker.quarterly_balance_sheet
    except Exception:
        balance_raw = pd.DataFrame()
    try:
        cash_raw = yf_ticker.quarterly_cashflow
    except Exception:
        cash_raw = pd.DataFrame()

    if (
        (income_raw is None or income_raw.empty)
        and (balance_raw is None or balance_raw.empty)
        and (cash_raw is None or cash_raw.empty)
    ):
        return None

    def _prep_quarters(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.T.copy()
        out.index = pd.to_datetime(out.index, errors="coerce")
        out = out[~out.index.isna()]
        return out.sort_index(ascending=False)

    income_q = _prep_quarters(income_raw)
    balance_q = _prep_quarters(balance_raw)
    cash_q = _prep_quarters(cash_raw)

    idx = income_q.index.union(balance_q.index).union(cash_q.index)
    idx = pd.DatetimeIndex(sorted(idx, reverse=True))
    if len(idx) == 0:
        return None

    income_q = income_q.reindex(idx)
    balance_q = balance_q.reindex(idx)
    cash_q = cash_q.reindex(idx)

    revenue = income_q.get("Total Revenue", pd.Series(np.nan, index=idx))
    gross_profit = income_q.get("Gross Profit", pd.Series(np.nan, index=idx))
    net_income = income_q.get("Net Income", pd.Series(np.nan, index=idx))
    ebitda = income_q.get("EBITDA", pd.Series(np.nan, index=idx))
    eps_basic = income_q.get("Basic EPS", pd.Series(np.nan, index=idx))
    eps_diluted = income_q.get("Diluted EPS", pd.Series(np.nan, index=idx))

    total_assets = balance_q.get("Total Assets", pd.Series(np.nan, index=idx))
    cash_equiv = balance_q.get(
        "Cash And Cash Equivalents", pd.Series(np.nan, index=idx)
    )
    short_term_debt = balance_q.get("Current Debt", pd.Series(np.nan, index=idx))
    long_term_debt = balance_q.get("Long Term Debt", pd.Series(np.nan, index=idx))
    current_liabilities = balance_q.get(
        "Current Liabilities", pd.Series(np.nan, index=idx)
    )
    inventory = balance_q.get("Inventory", pd.Series(np.nan, index=idx))

    fcf_q = cash_q.get("Free Cash Flow", pd.Series(np.nan, index=idx))
    capex = cash_q.get("Capital Expenditure", pd.Series(np.nan, index=idx))
    r_and_d = cash_q.get("Research And Development", pd.Series(np.nan, index=idx))

    gross_margin_pct = gross_profit / revenue.replace(0.0, np.nan)
    inventory_days = inventory / (revenue.replace(0.0, np.nan) / 90.0)
    inventory_days = inventory_days.where(~inventory.isna(), np.nan)

    eps_proxy = eps_basic.where(~eps_basic.isna(), eps_diluted)
    prev_eps_proxy = eps_proxy.shift(-1)
    last_eps_surprise_pct = (eps_proxy - prev_eps_proxy) / prev_eps_proxy.abs().replace(
        0.0, np.nan
    )

    try:
        earnings_history = yf_ticker.earnings_history
    except Exception:
        earnings_history = pd.DataFrame()
    last_rev_surprise_pct = pd.Series(np.nan, index=idx)
    if isinstance(earnings_history, pd.DataFrame) and not earnings_history.empty:
        candidates: list[tuple[pd.Timestamp, float]] = []
        for dt_col in ("quarter", "date", "asOfDate"):
            if dt_col in earnings_history.columns:
                ts_vals = pd.to_datetime(earnings_history[dt_col], errors="coerce")
                break
        else:
            ts_vals = pd.to_datetime(earnings_history.index, errors="coerce")
        for i, ts in enumerate(ts_vals):
            if pd.isna(ts):
                continue
            row = earnings_history.iloc[i]
            rev_actual = _safe_float(
                row.get("revenueActual")
                or row.get("revenue_actual")
                or row.get("Revenue Actual")
            )
            rev_est = _safe_float(
                row.get("revenueEstimate")
                or row.get("revenue_estimate")
                or row.get("Revenue Estimate")
            )
            if rev_actual is None or rev_est in (None, 0.0):
                continue
            candidates.append(
                (pd.Timestamp(ts).normalize(), (rev_actual - rev_est) / abs(rev_est))
            )
        if candidates:
            candidates.sort(key=lambda x: x[0])
            last_val = float(candidates[-1][1])
            last_rev_surprise_pct = pd.Series(last_val, index=idx)

    ydf = pd.DataFrame(
        {
            "ticker": ticker,
            "period_end": idx,
            "filing_date": idx + pd.Timedelta(days=45),
            "source_date": idx,
            "gross_margin_pct": gross_margin_pct.values,
            "inventory_days": inventory_days.values,
            "last_eps_surprise_pct": last_eps_surprise_pct.values,
            "earnings_revision_30d": np.nan,
            "last_earnings_date": pd.NaT,
            "next_earnings_date": pd.NaT,
            "fcf_ttm": np.nan,
            "debt_to_equity": np.nan,
            "inventory_days_accel": np.nan,
            "gross_margin_delta": np.nan,
            "last_rev_surprise_pct": last_rev_surprise_pct.values,
            "_net_income": net_income.values,
            "_ebitda": ebitda.values,
            "_r_and_d": r_and_d.values,
            "_capex": capex.values,
            "_total_assets": total_assets.values,
            "_cash": cash_equiv.values,
            "_short_term_debt": short_term_debt.values,
            "_long_term_debt": long_term_debt.values,
            "_current_liabilities": current_liabilities.values,
            "_market_cap": np.nan if market_cap is None else float(market_cap),
            "_fcf_ttm": fcf_q.rolling(window=4, min_periods=1).sum().values,
            "_revenue": revenue.values,
        }
    )

    ydf = ydf.sort_values("period_end", ascending=False).reset_index(drop=True)
    ydf = compute_quality_metrics(ydf)
    ydf["fcff_adjusted"] = np.nan
    ydf["fcff_raw"] = np.nan
    ydf["rd_cap_variance_pct"] = np.nan
    ydf["sbc_pct_revenue"] = np.nan
    ydf["edgar_audit_flag"] = True
    ydf = ydf.reindex(columns=OUT_COLUMNS)
    if ydf.empty:
        return None
    return ydf


def _extract_rows_from_fmp(ticker: str) -> list[dict[str, Any]] | None:
    """Build quarterly rows from FMP + SemiValuationEngine; None if unavailable."""
    if not FMP_KEY:
        return None
    try:
        wdf = load_fmp_quarters(ticker)
    except Exception as exc:
        print(f"[FMP] {ticker}: load failed ({exc})", flush=True)
        return None
    if wdf is None or wdf.empty:
        return None

    req = [
        "period_end",
        "ebit",
        "da",
        "sbc",
        "capex",
        "delta_nwc",
        "tax_rate",
        "r_and_d",
        "revenue",
    ]
    if any(c not in wdf.columns for c in req):
        print(f"[FMP] {ticker}: incomplete valuation columns", flush=True)
        return None

    try:
        semi_part = SemiValuationEngine().compute(ticker, wdf[req].copy())
        val_cols = [
            "fcff_raw",
            "rd_capitalized_asset",
            "rd_amortization",
            "fcff_adjusted",
            "rd_cap_variance_pct",
            "sbc_pct_revenue",
            "needs_edgar_audit",
        ]
        wdf["period_end"] = pd.to_datetime(wdf["period_end"], errors="coerce")
        semi_part["period_end"] = pd.to_datetime(
            semi_part["period_end"], errors="coerce"
        )
        wdf = wdf.merge(
            semi_part[["period_end", *val_cols]], on="period_end", how="left"
        )
    except Exception as exc:
        print(f"[FMP] {ticker}: semi valuation failed ({exc})", flush=True)
        return None

    needs_audit = bool(wdf["needs_edgar_audit"].fillna(False).any())
    edgar_audit_flag = True
    if needs_audit:
        try:
            fy = int(pd.to_datetime(wdf["period_end"], errors="coerce").max().year)
            audit = audit_ticker(ticker, fy)
            edgar_audit_flag = audit.get("audit_pass") is True
        except Exception as exc:
            print(f"[EDGAR] {ticker}: audit failed ({exc})", flush=True)
            edgar_audit_flag = False

    market_cap: float | None = None
    try:
        info = yf.Ticker(ticker).info
        if isinstance(info, dict):
            market_cap = _safe_float(info.get("marketCap"))
    except Exception:
        market_cap = None

    wch = wdf.sort_values("period_end", ascending=True).reset_index(drop=True)
    latest = wch.iloc[-1]
    debt = _num_fmp(latest.get("short_term_debt")) + _num_fmp(
        latest.get("long_term_debt")
    )
    eq = _num_fmp(latest.get("total_equity"))
    debt_to_equity = float("nan")
    if not np.isnan(debt) and not np.isnan(eq) and eq > 0:
        debt_to_equity = float(debt / eq)

    fcf_series = []
    for _, r in wch.iterrows():
        fcf_d = r.get("free_cash_flow")
        if fcf_d is not None:
            fcf_series.append(_num_fmp(fcf_d))
        else:
            cfo = _num_fmp(r.get("operating_cash_flow"))
            capx = _num_fmp(r.get("capex"))
            if not np.isnan(cfo) and not np.isnan(capx):
                fcf_series.append(float(cfo - capx))
            else:
                fcf_series.append(float("nan"))
    fcf_q = pd.Series(fcf_series, dtype="float64")
    fcf_ttm_vals = fcf_q.rolling(window=4, min_periods=1).sum().tolist()

    last_earnings_date = pd.NaT
    rows: list[dict[str, Any]] = []
    fcff_adj_l: list[float] = []
    fcff_raw_l: list[float] = []
    rd_var_l: list[float] = []
    sbc_pct_l: list[float] = []
    for i, (_, r) in enumerate(wch.iterrows()):
        pe = pd.to_datetime(r["period_end"], errors="coerce")
        fd = pd.to_datetime(r.get("filing_date"), errors="coerce")
        if pd.isna(fd):
            fd = pe + pd.Timedelta(days=45)

        rev = _num_fmp(r.get("revenue"))
        gp = _num_fmp(r.get("gross_profit"))
        gross_margin_pct = float("nan")
        if not np.isnan(gp) and not np.isnan(rev) and rev != 0.0:
            gross_margin_pct = float(gp / rev)

        inv = _num_fmp(r.get("inventory"))
        cor = _num_fmp(r.get("cost_of_revenue"))
        inventory_days = float("nan")
        if not np.isnan(inv) and not np.isnan(cor) and cor != 0.0:
            inventory_days = float((inv / cor) * 91.0)

        fcf_ttm = fcf_ttm_vals[i]

        rows.append(
            {
                "ticker": ticker,
                "period_end": pe,
                "filing_date": fd,
                "gross_margin_pct": gross_margin_pct,
                "inventory_days": inventory_days,
                "last_eps_surprise_pct": np.nan,
                "earnings_revision_30d": np.nan,
                "last_earnings_date": last_earnings_date,
                "next_earnings_date": pd.NaT,
                "fcf_ttm": fcf_ttm,
                "debt_to_equity": debt_to_equity,
                "inventory_days_accel": np.nan,
                "gross_margin_delta": np.nan,
                "last_rev_surprise_pct": np.nan,
                "_net_income": _num_fmp(r.get("net_income")),
                "_ebitda": _num_fmp(r.get("ebitda")),
                "_r_and_d": _num_fmp(r.get("r_and_d")),
                "_capex": _num_fmp(r.get("capex_signed")),
                "_total_assets": _num_fmp(r.get("total_assets")),
                "_cash": _num_fmp(r.get("cash")),
                "_short_term_debt": _num_fmp(r.get("short_term_debt")),
                "_long_term_debt": _num_fmp(r.get("long_term_debt")),
                "_current_liabilities": _num_fmp(r.get("current_liabilities")),
                "_market_cap": np.nan if market_cap is None else float(market_cap),
                "_fcf_ttm": fcf_ttm,
                "_revenue": rev,
            }
        )
        fcff_adj_l.append(_num_fmp(r.get("fcff_adjusted")))
        fcff_raw_l.append(_num_fmp(r.get("fcff_raw")))
        rd_var_l.append(_num_fmp(r.get("rd_cap_variance_pct")))
        sbc_pct_l.append(_num_fmp(r.get("sbc_pct_revenue")))

    for i in range(1, len(rows)):
        cur_inv = rows[i].get("inventory_days")
        prev_inv = rows[i - 1].get("inventory_days")
        if pd.notna(cur_inv) and pd.notna(prev_inv):
            rows[i]["inventory_days_accel"] = float(cur_inv) - float(prev_inv)
        cur_gm = rows[i].get("gross_margin_pct")
        prev_gm = rows[i - 1].get("gross_margin_pct")
        if pd.notna(cur_gm) and pd.notna(prev_gm):
            rows[i]["gross_margin_delta"] = float(cur_gm) - float(prev_gm)

    ticker_df = pd.DataFrame(rows)
    ticker_df = compute_quality_metrics(ticker_df)
    ticker_df["fcff_adjusted"] = fcff_adj_l
    ticker_df["fcff_raw"] = fcff_raw_l
    ticker_df["rd_cap_variance_pct"] = rd_var_l
    ticker_df["sbc_pct_revenue"] = sbc_pct_l
    ticker_df["edgar_audit_flag"] = edgar_audit_flag
    ticker_df = ticker_df.reindex(columns=OUT_COLUMNS)
    if ticker_df.empty:
        return None
    print(f"[FMP] {ticker}: {len(ticker_df)} quarters", flush=True)
    return _ensure_filing_date_on_rows(ticker_df.to_dict(orient="records"))


def _ensure_filing_date_on_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every row has filing_date (conservative proxy: period_end + 45d when missing)."""
    if not rows:
        return rows
    df = pd.DataFrame(rows)
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    if "filing_date" not in df.columns:
        df["filing_date"] = df["period_end"] + pd.Timedelta(days=45)
    else:
        df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
        na_mask = df["filing_date"].isna()
        df.loc[na_mask, "filing_date"] = df.loc[na_mask, "period_end"] + pd.Timedelta(
            days=45
        )
    return df.to_dict(orient="records")


def _extract_rows_for_ticker_eodhd(
    ticker: str, data: dict[str, Any]
) -> list[dict[str, Any]]:
    financials = data.get("Financials", {})
    if not isinstance(financials, dict):
        return []

    income_q = _as_period_map(
        (financials.get("Income_Statement") or {}).get("quarterly")
    )
    balance_q = _as_period_map((financials.get("Balance_Sheet") or {}).get("quarterly"))
    cash_q = _as_period_map((financials.get("Cash_Flow") or {}).get("quarterly"))
    earnings_hist = _extract_earnings_history_map(data)
    earnings_revision_30d, next_earnings_date = (
        _extract_earnings_revision_30d_and_next_date(data)
    )
    last_rev_surprise_pct = _extract_last_rev_surprise_pct(data)
    highlights = data.get("Highlights", {})
    valuation = data.get("Valuation", {})
    _market_cap = None
    if isinstance(highlights, dict):
        _market_cap = _safe_float(highlights.get("MarketCapitalization"))
    if _market_cap is None and isinstance(valuation, dict):
        _market_cap = _safe_float(valuation.get("EnterpriseValue"))

    period_keys = sorted(
        set(income_q.keys())
        | set(balance_q.keys())
        | set(cash_q.keys())
        | set(earnings_hist.keys())
    )
    if not period_keys:
        return []

    period_ts = [pd.to_datetime(p, errors="coerce") for p in period_keys]
    valid_periods = sorted([p for p in period_ts if not pd.isna(p)])
    if not valid_periods:
        return []

    # Last reported earnings date (latest period with non-null epsActual).
    last_earnings_date: pd.Timestamp | None = None
    last_earnings_candidates = sorted(
        [
            pd.to_datetime(k, errors="coerce")
            for k, v in earnings_hist.items()
            if _safe_float(v.get("epsActual")) is not None
        ]
    )
    last_earnings_candidates = [x for x in last_earnings_candidates if not pd.isna(x)]
    if last_earnings_candidates:
        last_earnings_date = last_earnings_candidates[-1]

    # Most recent quarter debt_to_equity.
    most_recent_key = valid_periods[-1].strftime("%Y-%m-%d")
    bs_recent = balance_q.get(most_recent_key, {})
    debt = _safe_float(bs_recent.get("shortLongTermDebtTotal"))
    equity = _safe_float(bs_recent.get("totalStockholderEquity"))
    debt_to_equity = None
    if debt is not None and equity is not None and equity > 0:
        debt_to_equity = debt / equity

    # Precompute quarter-level free cash flow.
    fcf_quarter: dict[str, float] = {}
    for key, row in cash_q.items():
        cfo = _safe_float(row.get("totalCashFromOperatingActivities"))
        capex = _safe_float(row.get("capitalExpenditures"))
        if cfo is None or capex is None:
            continue
        fcf_quarter[key] = cfo - capex

    # Rolling TTM FCF by period.
    sorted_cash_periods = sorted(
        [(pd.to_datetime(k, errors="coerce"), k) for k in fcf_quarter.keys()],
        key=lambda x: x[0],
    )
    fcf_ttm_by_period: dict[str, float] = {}
    vals: list[tuple[pd.Timestamp, str, float]] = [
        (ts, key, fcf_quarter[key])
        for ts, key in sorted_cash_periods
        if not pd.isna(ts)
    ]
    for idx in range(len(vals)):
        if idx < 3:
            continue
        window = vals[idx - 3 : idx + 1]
        fcf_ttm_by_period[vals[idx][1]] = float(sum(x[2] for x in window))

    rows: list[dict[str, Any]] = []
    for ts in valid_periods:
        key = ts.strftime("%Y-%m-%d")
        income = income_q.get(key, {})
        balance = balance_q.get(key, {})
        cash = cash_q.get(key, {})
        earn = earnings_hist.get(key, {})
        filing_date = pd.to_datetime(
            earn.get("reportDate") or earn.get("report_date"), errors="coerce"
        )
        if pd.isna(filing_date):
            filing_date = ts + pd.Timedelta(days=45)

        gross_profit = _safe_float(income.get("grossProfit"))
        total_revenue = _safe_float(income.get("totalRevenue"))
        gross_margin_pct = np.nan
        if (
            gross_profit is not None
            and total_revenue is not None
            and total_revenue != 0.0
        ):
            gross_margin_pct = gross_profit / total_revenue

        inventory = _safe_float(balance.get("inventory"))
        cost_of_revenue = _safe_float(income.get("costOfRevenue"))
        inventory_days = np.nan
        if inventory is not None and cost_of_revenue not in (None, 0.0):
            inventory_days = (inventory / cost_of_revenue) * 91.0

        eps_est = _safe_float(earn.get("epsEstimate"))
        eps_act = _safe_float(earn.get("epsActual"))
        last_eps_surprise_pct = np.nan
        if eps_est not in (None, 0.0) and eps_act is not None:
            last_eps_surprise_pct = (eps_act - eps_est) / abs(eps_est)

        net_income = _safe_float(income.get("netIncome"))
        ebitda = _safe_float(income.get("ebitda"))
        if ebitda in (None, 0.0):
            ebitda = _safe_float(income.get("operatingIncome"))
        r_and_d = _safe_float(income.get("researchAndDevelopment"))
        capex = _safe_float(cash.get("capitalExpenditures"))
        total_assets = _safe_float(balance.get("totalAssets"))
        cash_bal = _safe_float(balance.get("cash"))
        if cash_bal is None:
            cash_bal = _safe_float(balance.get("cashAndShortTermInvestments"))
        short_term_debt = _safe_float(balance.get("shortTermDebt"))
        long_term_debt = _safe_float(balance.get("longTermDebt"))
        current_liabilities = _safe_float(balance.get("totalCurrentLiabilities"))
        fcf_ttm = np.nan if key not in fcf_ttm_by_period else fcf_ttm_by_period[key]

        rows.append(
            {
                "ticker": ticker,
                "period_end": ts,
                "filing_date": filing_date,
                "gross_margin_pct": gross_margin_pct,
                "inventory_days": inventory_days,
                "last_eps_surprise_pct": last_eps_surprise_pct,
                "earnings_revision_30d": (
                    np.nan
                    if earnings_revision_30d is None
                    else float(earnings_revision_30d)
                ),
                "last_earnings_date": last_earnings_date,
                "next_earnings_date": next_earnings_date,
                "fcf_ttm": fcf_ttm,
                "debt_to_equity": (
                    np.nan if debt_to_equity is None else float(debt_to_equity)
                ),
                "inventory_days_accel": np.nan,
                "gross_margin_delta": np.nan,
                "last_rev_surprise_pct": (
                    np.nan
                    if last_rev_surprise_pct is None
                    else float(last_rev_surprise_pct)
                ),
                "_net_income": np.nan if net_income is None else float(net_income),
                "_ebitda": np.nan if ebitda is None else float(ebitda),
                "_r_and_d": np.nan if r_and_d is None else float(r_and_d),
                "_capex": np.nan if capex is None else float(capex),
                "_total_assets": (
                    np.nan if total_assets is None else float(total_assets)
                ),
                "_cash": np.nan if cash_bal is None else float(cash_bal),
                "_short_term_debt": (
                    np.nan if short_term_debt is None else float(short_term_debt)
                ),
                "_long_term_debt": (
                    np.nan if long_term_debt is None else float(long_term_debt)
                ),
                "_current_liabilities": (
                    np.nan
                    if current_liabilities is None
                    else float(current_liabilities)
                ),
                "_market_cap": np.nan if _market_cap is None else float(_market_cap),
                "_fcf_ttm": fcf_ttm,
                "_revenue": np.nan if total_revenue is None else float(total_revenue),
            }
        )
    for i in range(1, len(rows)):
        cur_inv = rows[i].get("inventory_days")
        prev_inv = rows[i - 1].get("inventory_days")
        if pd.notna(cur_inv) and pd.notna(prev_inv):
            rows[i]["inventory_days_accel"] = float(cur_inv) - float(prev_inv)
        cur_gm = rows[i].get("gross_margin_pct")
        prev_gm = rows[i - 1].get("gross_margin_pct")
        if pd.notna(cur_gm) and pd.notna(prev_gm):
            rows[i]["gross_margin_delta"] = float(cur_gm) - float(prev_gm)
    ticker_df = pd.DataFrame(rows)
    ticker_df = compute_quality_metrics(ticker_df)
    ticker_df["fcff_adjusted"] = np.nan
    ticker_df["fcff_raw"] = np.nan
    ticker_df["rd_cap_variance_pct"] = np.nan
    ticker_df["sbc_pct_revenue"] = np.nan
    ticker_df["edgar_audit_flag"] = True
    ticker_df = ticker_df.reindex(columns=OUT_COLUMNS)
    return ticker_df.to_dict(orient="records")


def _extract_rows_for_ticker(
    ticker: str, suffix_map: dict[str, str]
) -> list[dict[str, Any]]:
    fmp_rows = _extract_rows_from_fmp(ticker)
    if fmp_rows is not None and len(fmp_rows) > 0:
        return fmp_rows

    market_cap = None
    try:
        info = yf.Ticker(ticker).info
        if isinstance(info, dict):
            market_cap = _safe_float(info.get("marketCap"))
    except Exception:
        market_cap = None

    ydf = _extract_yfinance(ticker, market_cap)
    if ydf is not None and len(ydf) >= 1:
        print(f"[yfinance] {ticker}: {len(ydf)} quarters", flush=True)
        return _ensure_filing_date_on_rows(ydf.to_dict(orient="records"))

    print(f"[EODHD fallback] {ticker}", flush=True)
    eod_ticker = _normalize_eodhd_ticker(ticker, suffix_map)
    data = _fetch_fundamentals_one(eod_ticker)
    time.sleep(0.25)
    if not data:
        print(f"[WARN] {ticker}: no data from yfinance or EODHD", flush=True)
        return []
    rows = _extract_rows_for_ticker_eodhd(eod_ticker, data)
    if not rows:
        print(f"[WARN] {ticker}: no rows from yfinance or EODHD", flush=True)
        return []
    return _ensure_filing_date_on_rows(rows)


def _validate_output_frame(df: pd.DataFrame) -> None:
    if list(df.columns) != OUT_COLUMNS:
        raise ValueError(f"Unexpected output columns: {df.columns.tolist()}")
    for col in ("inventory_days_accel", "gross_margin_delta", "last_rev_surprise_pct"):
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    for col in (
        "fcf_yield",
        "roic",
        "fcf_conversion",
        "net_capex_sales",
        "net_debt_ebitda",
    ):
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    for col in (
        "fcff_adjusted",
        "fcff_raw",
        "rd_cap_variance_pct",
        "sbc_pct_revenue",
        "edgar_audit_flag",
    ):
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    if not pd.api.types.is_datetime64_any_dtype(df["period_end"]):
        raise ValueError("period_end must be datetime64")
    if not pd.api.types.is_datetime64_any_dtype(df["last_earnings_date"]):
        raise ValueError("last_earnings_date must be datetime64")
    if not pd.api.types.is_datetime64_any_dtype(df["next_earnings_date"]):
        raise ValueError("next_earnings_date must be datetime64")
    if not pd.api.types.is_datetime64_any_dtype(df["filing_date"]):
        raise ValueError("filing_date must be datetime64")


def _finalize_quarterly_df(
    all_rows: list[dict[str, Any]],
    tickers_filter: list[str] | None,
) -> pd.DataFrame:
    new_df = pd.DataFrame(all_rows, columns=OUT_COLUMNS)
    if not new_df.empty:
        new_df["period_end"] = pd.to_datetime(new_df["period_end"], errors="coerce")
        new_df["filing_date"] = pd.to_datetime(new_df["filing_date"], errors="coerce")
        new_df["last_earnings_date"] = pd.to_datetime(
            new_df["last_earnings_date"], errors="coerce"
        )
        new_df["next_earnings_date"] = pd.to_datetime(
            new_df["next_earnings_date"], errors="coerce"
        )
    else:
        new_df = pd.DataFrame(columns=OUT_COLUMNS)
        new_df["period_end"] = pd.to_datetime(new_df["period_end"])
        new_df["filing_date"] = pd.to_datetime(new_df["filing_date"])
        new_df["last_earnings_date"] = pd.to_datetime(new_df["last_earnings_date"])
        new_df["next_earnings_date"] = pd.to_datetime(new_df["next_earnings_date"])

    new_df = new_df.astype(
        {
            "ticker": "string",
            "gross_margin_pct": "float64",
            "inventory_days": "float64",
            "last_eps_surprise_pct": "float64",
            "earnings_revision_30d": "float64",
            "fcf_ttm": "float64",
            "debt_to_equity": "float64",
            "inventory_days_accel": "float64",
            "gross_margin_delta": "float64",
            "last_rev_surprise_pct": "float64",
            "fcf_yield": "float64",
            "roic": "float64",
            "fcf_conversion": "float64",
            "net_capex_sales": "float64",
            "net_debt_ebitda": "float64",
            "fcff_adjusted": "float64",
            "fcff_raw": "float64",
            "rd_cap_variance_pct": "float64",
            "sbc_pct_revenue": "float64",
            "edgar_audit_flag": "bool",
        }
    )
    new_df = new_df.sort_values(
        ["ticker", "period_end"], ascending=[True, True]
    ).reset_index(drop=True)

    if tickers_filter and new_df.empty:
        print("[ERROR] --tickers fetch produced zero rows", flush=True)
        sys.exit(1)

    if tickers_filter and OUT_FILE.exists():
        sub_u = {t.upper() for t in tickers_filter}
        existing = pd.read_parquet(OUT_FILE)
        counts_before = (
            existing.groupby(existing["ticker"].astype(str).str.upper())
            .size()
            .to_dict()
        )
        rest = existing[~existing["ticker"].astype(str).str.upper().isin(sub_u)].copy()
        combined = pd.concat([rest, new_df], ignore_index=True)
        combined = combined.sort_values(
            ["ticker", "period_end"], ascending=[True, True]
        ).reset_index(drop=True)
        counts_after = (
            combined.groupby(combined["ticker"].astype(str).str.upper())
            .size()
            .to_dict()
        )
        for t, c_before in counts_before.items():
            if t in sub_u:
                continue
            if int(counts_after.get(t, 0)) != int(c_before):
                print(
                    f"[ERROR] row count drift for {t}: was {c_before} now {counts_after.get(t, 0)}; abort write",
                    flush=True,
                )
                sys.exit(1)
        for t in sub_u:
            if t not in counts_after or counts_after[t] < 1:
                print(f"[ERROR] merged parquet missing rows for {t}", flush=True)
                sys.exit(1)
        return combined
    return new_df


def main() -> None:
    args = _parse_cli(sys.argv[1:])
    mode = args.mode
    tickers_filter = [t.strip().upper() for t in args.tickers] if args.tickers else None
    universe_full = _load_universe_tickers()
    tickers = (
        _restrict_to_tickers(universe_full, tickers_filter)
        if tickers_filter
        else universe_full
    )
    suffix_map = _load_suffix_mapping()
    if not tickers:
        print("[ERROR] no tickers found in config/universe.yaml", flush=True)
        sys.exit(1)

    if mode == "weekly":
        if not OUT_FILE.exists():
            print(
                "[WARN] weekly mode skipped: quarterly_signals.parquet not found",
                flush=True,
            )
            sys.exit(0)

        df = pd.read_parquet(OUT_FILE)
        for col in (
            "inventory_days_accel",
            "gross_margin_delta",
            "last_rev_surprise_pct",
        ):
            if col not in df.columns:
                df[col] = np.nan
        for col in (
            "fcf_yield",
            "roic",
            "fcf_conversion",
            "net_capex_sales",
            "net_debt_ebitda",
        ):
            if col not in df.columns:
                df[col] = np.nan
        for col in (
            "fcff_adjusted",
            "fcff_raw",
            "rd_cap_variance_pct",
            "sbc_pct_revenue",
        ):
            if col not in df.columns:
                df[col] = np.nan
        if "edgar_audit_flag" not in df.columns:
            df["edgar_audit_flag"] = True
        for col in ("earnings_revision_30d", "next_earnings_date"):
            if col not in df.columns:
                print(
                    f"[WARN] weekly mode skipped: missing column {col} in existing parquet",
                    flush=True,
                )
                sys.exit(0)
        if "filing_date" not in df.columns:
            df["filing_date"] = pd.to_datetime(
                df["period_end"], errors="coerce"
            ) + pd.Timedelta(days=45)
        else:
            df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
            _fd_na = df["filing_date"].isna()
            df.loc[_fd_na, "filing_date"] = pd.to_datetime(
                df.loc[_fd_na, "period_end"], errors="coerce"
            ) + pd.Timedelta(days=45)

        updated = 0
        for base_ticker in tickers:
            ticker = _normalize_eodhd_ticker(base_ticker, suffix_map)
            data = _fetch_fundamentals_one(ticker)
            time.sleep(0.25)
            if not data:
                continue
            rev_30d, next_date = _extract_earnings_revision_30d_and_next_date(data)
            mask = df["ticker"].astype(str).str.upper() == ticker
            if mask.any():
                df.loc[mask, "earnings_revision_30d"] = (
                    np.nan if rev_30d is None else float(rev_30d)
                )
                df.loc[mask, "next_earnings_date"] = next_date
                updated += 1

        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
        df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
        df["last_earnings_date"] = pd.to_datetime(
            df.get("last_earnings_date"), errors="coerce"
        )
        df["next_earnings_date"] = pd.to_datetime(
            df["next_earnings_date"], errors="coerce"
        )
        df = df.astype(
            {
                "ticker": "string",
                "gross_margin_pct": "float64",
                "inventory_days": "float64",
                "last_eps_surprise_pct": "float64",
                "earnings_revision_30d": "float64",
                "fcf_ttm": "float64",
                "debt_to_equity": "float64",
                "inventory_days_accel": "float64",
                "gross_margin_delta": "float64",
                "last_rev_surprise_pct": "float64",
                "fcf_yield": "float64",
                "roic": "float64",
                "fcf_conversion": "float64",
                "net_capex_sales": "float64",
                "net_debt_ebitda": "float64",
                "fcff_adjusted": "float64",
                "fcff_raw": "float64",
                "rd_cap_variance_pct": "float64",
                "sbc_pct_revenue": "float64",
                "edgar_audit_flag": "bool",
            }
        )
        df = df[OUT_COLUMNS]
        df.to_parquet(TMP_FILE, index=False)
        check_df = pd.read_parquet(TMP_FILE)
        _validate_output_frame(check_df)
        os.replace(TMP_FILE, OUT_FILE)
        print(
            f"[WEEKLY] updated earnings_revision_30d + next_earnings_date for {updated} tickers",
            flush=True,
        )
        sys.exit(0)

    print(f"[INFO] universe tickers: {len(tickers)}", flush=True)
    all_rows: list[dict[str, Any]] = []

    # Build lookup: ticker -> latest period_end already on disk
    existing_latest: dict[str, pd.Timestamp] = {}
    existing_rows_by_ticker: dict[str, list[dict[str, Any]]] = {}
    if OUT_FILE.exists() and not tickers_filter:
        try:
            _ex = pd.read_parquet(OUT_FILE)
            _ex["period_end"] = pd.to_datetime(_ex["period_end"], errors="coerce")
            for _t, _grp in _ex.groupby(_ex["ticker"].astype(str).str.upper()):
                existing_latest[_t] = _grp["period_end"].max()
                existing_rows_by_ticker[_t] = _grp.to_dict("records")
        except Exception as _e:
            print(
                f"[WARN] could not read existing parquet for incremental check: {_e}",
                flush=True,
            )

    # A ticker is current if its latest quarter end is within the last 100 days
    _cutoff = pd.Timestamp.today() - pd.Timedelta(days=100)

    tickers_full = 0
    tickers_partial = 0
    tickers_zero = 0
    tickers_skipped = 0

    for idx, base_ticker in enumerate(tickers, start=1):
        ticker = base_ticker.strip().upper()

        # Skip if already current
        if ticker in existing_latest and existing_latest[ticker] >= _cutoff:
            all_rows.extend(existing_rows_by_ticker[ticker])
            tickers_skipped += 1
            print(
                f"[SKIP] {idx}/{len(tickers)} {ticker}: latest={existing_latest[ticker].date()} (current)",
                flush=True,
            )
            continue

        rows = _extract_rows_for_ticker(ticker, suffix_map)
        if not rows:
            tickers_zero += 1
            print(f"[WARN] {idx}/{len(tickers)} {ticker}: zero data", flush=True)
            # Preserve existing rows if any
            if ticker in existing_rows_by_ticker:
                all_rows.extend(existing_rows_by_ticker[ticker])
            continue

        ticker_df = pd.DataFrame(rows, columns=OUT_COLUMNS)
        measure_cols = [
            c for c in OUT_COLUMNS if c not in ("ticker", "period_end", "filing_date")
        ]
        if ticker_df[measure_cols].isna().any().any():
            tickers_partial += 1
        else:
            tickers_full += 1

        all_rows.extend(rows)
        print(f"[INFO] {idx}/{len(tickers)} {ticker}: {len(rows)} periods", flush=True)

    df = _finalize_quarterly_df(all_rows, tickers_filter)

    # Atomic write: .tmp -> validate -> rename
    df.to_parquet(TMP_FILE, index=False)
    check_df = pd.read_parquet(TMP_FILE)
    _validate_output_frame(check_df)
    os.replace(TMP_FILE, OUT_FILE)

    print("[DONE] quarterly signals written", flush=True)
    print(f"[DONE] output: {OUT_FILE}", flush=True)
    print(
        f"[SUMMARY] tickers={len(tickers)} fetched={tickers_full+tickers_partial} skipped={tickers_skipped} partial={tickers_partial} zero={tickers_zero}",
        flush=True,
    )


if __name__ == "__main__":
    main()
