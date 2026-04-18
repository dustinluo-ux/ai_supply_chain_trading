"""
Fetch quarterly fundamental signals for universe tickers from EODHD.

Output:
  trading_data/fundamentals/quarterly_signals.parquet

Atomic write:
  write .tmp -> validate -> rename
"""
from __future__ import annotations

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
from src.fundamentals.quality_metrics import compute_quality_metrics

load_dotenv(ROOT / ".env")

TOKEN = os.getenv("EODHD_API_KEY", "")
if not TOKEN:
    print("[WARN] EODHD_API_KEY not set — EODHD fallback disabled, yfinance only", flush=True)

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
]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
                period = str(item.get("date") or item.get("reportedDate") or item.get("period") or "")
                if period:
                    out[period] = item
            return out
    if isinstance(node, list):
        out: dict[str, dict[str, Any]] = {}
        for item in node:
            if not isinstance(item, dict):
                continue
            period = str(item.get("date") or item.get("reportedDate") or item.get("period") or "")
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


def _extract_earnings_revision_30d_and_next_date(data: dict[str, Any]) -> tuple[float | None, pd.Timestamp | None]:
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


def _extract_yfinance(ticker: str, market_cap: float | None = None) -> pd.DataFrame | None:
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
    cash_equiv = balance_q.get("Cash And Cash Equivalents", pd.Series(np.nan, index=idx))
    short_term_debt = balance_q.get("Current Debt", pd.Series(np.nan, index=idx))
    long_term_debt = balance_q.get("Long Term Debt", pd.Series(np.nan, index=idx))
    current_liabilities = balance_q.get("Current Liabilities", pd.Series(np.nan, index=idx))
    inventory = balance_q.get("Inventory", pd.Series(np.nan, index=idx))

    fcf_q = cash_q.get("Free Cash Flow", pd.Series(np.nan, index=idx))
    capex = cash_q.get("Capital Expenditure", pd.Series(np.nan, index=idx))
    r_and_d = cash_q.get("Research And Development", pd.Series(np.nan, index=idx))

    gross_margin_pct = gross_profit / revenue.replace(0.0, np.nan)
    inventory_days = inventory / (revenue.replace(0.0, np.nan) / 90.0)
    inventory_days = inventory_days.where(~inventory.isna(), np.nan)

    eps_proxy = eps_basic.where(~eps_basic.isna(), eps_diluted)
    prev_eps_proxy = eps_proxy.shift(-1)
    last_eps_surprise_pct = (eps_proxy - prev_eps_proxy) / prev_eps_proxy.abs().replace(0.0, np.nan)

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
            candidates.append((pd.Timestamp(ts).normalize(), (rev_actual - rev_est) / abs(rev_est)))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            last_val = float(candidates[-1][1])
            last_rev_surprise_pct = pd.Series(last_val, index=idx)

    ydf = pd.DataFrame(
        {
            "ticker": ticker,
            "period_end": idx,
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
    ydf = ydf.reindex(columns=OUT_COLUMNS)
    if ydf.empty:
        return None
    return ydf


def _extract_rows_for_ticker_eodhd(ticker: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    financials = data.get("Financials", {})
    if not isinstance(financials, dict):
        return []

    income_q = _as_period_map((financials.get("Income_Statement") or {}).get("quarterly"))
    balance_q = _as_period_map((financials.get("Balance_Sheet") or {}).get("quarterly"))
    cash_q = _as_period_map((financials.get("Cash_Flow") or {}).get("quarterly"))
    earnings_hist = _extract_earnings_history_map(data)
    earnings_revision_30d, next_earnings_date = _extract_earnings_revision_30d_and_next_date(data)
    last_rev_surprise_pct = _extract_last_rev_surprise_pct(data)
    highlights = data.get("Highlights", {})
    valuation = data.get("Valuation", {})
    _market_cap = None
    if isinstance(highlights, dict):
        _market_cap = _safe_float(highlights.get("MarketCapitalization"))
    if _market_cap is None and isinstance(valuation, dict):
        _market_cap = _safe_float(valuation.get("EnterpriseValue"))

    period_keys = sorted(set(income_q.keys()) | set(balance_q.keys()) | set(cash_q.keys()) | set(earnings_hist.keys()))
    if not period_keys:
        return []

    period_ts = [pd.to_datetime(p, errors="coerce") for p in period_keys]
    valid_periods = sorted([p for p in period_ts if not pd.isna(p)])
    if not valid_periods:
        return []

    # Last reported earnings date (latest period with non-null epsActual).
    last_earnings_date: pd.Timestamp | None = None
    last_earnings_candidates = sorted(
        [pd.to_datetime(k, errors="coerce") for k, v in earnings_hist.items() if _safe_float(v.get("epsActual")) is not None]
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

        gross_profit = _safe_float(income.get("grossProfit"))
        total_revenue = _safe_float(income.get("totalRevenue"))
        gross_margin_pct = np.nan
        if gross_profit is not None and total_revenue is not None and total_revenue != 0.0:
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
                "gross_margin_pct": gross_margin_pct,
                "inventory_days": inventory_days,
                "last_eps_surprise_pct": last_eps_surprise_pct,
                "earnings_revision_30d": np.nan if earnings_revision_30d is None else float(earnings_revision_30d),
                "last_earnings_date": last_earnings_date,
                "next_earnings_date": next_earnings_date,
                "fcf_ttm": fcf_ttm,
                "debt_to_equity": np.nan if debt_to_equity is None else float(debt_to_equity),
                "inventory_days_accel": np.nan,
                "gross_margin_delta": np.nan,
                "last_rev_surprise_pct": np.nan if last_rev_surprise_pct is None else float(last_rev_surprise_pct),
                "_net_income": np.nan if net_income is None else float(net_income),
                "_ebitda": np.nan if ebitda is None else float(ebitda),
                "_r_and_d": np.nan if r_and_d is None else float(r_and_d),
                "_capex": np.nan if capex is None else float(capex),
                "_total_assets": np.nan if total_assets is None else float(total_assets),
                "_cash": np.nan if cash_bal is None else float(cash_bal),
                "_short_term_debt": np.nan if short_term_debt is None else float(short_term_debt),
                "_long_term_debt": np.nan if long_term_debt is None else float(long_term_debt),
                "_current_liabilities": np.nan if current_liabilities is None else float(current_liabilities),
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
    ticker_df = ticker_df.reindex(columns=OUT_COLUMNS)
    return ticker_df.to_dict(orient="records")


def _extract_rows_for_ticker(ticker: str, suffix_map: dict[str, str]) -> list[dict[str, Any]]:
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
        return ydf.to_dict(orient="records")

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
    return rows


def _validate_output_frame(df: pd.DataFrame) -> None:
    if list(df.columns) != OUT_COLUMNS:
        raise ValueError(f"Unexpected output columns: {df.columns.tolist()}")
    for col in ("inventory_days_accel", "gross_margin_delta", "last_rev_surprise_pct"):
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    for col in ("fcf_yield", "roic", "fcf_conversion", "net_capex_sales", "net_debt_ebitda"):
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    if not pd.api.types.is_datetime64_any_dtype(df["period_end"]):
        raise ValueError("period_end must be datetime64")
    if not pd.api.types.is_datetime64_any_dtype(df["last_earnings_date"]):
        raise ValueError("last_earnings_date must be datetime64")
    if not pd.api.types.is_datetime64_any_dtype(df["next_earnings_date"]):
        raise ValueError("next_earnings_date must be datetime64")


def _parse_mode(argv: list[str]) -> str:
    mode = "quarterly"
    if "--mode" in argv:
        i = argv.index("--mode")
        if i + 1 < len(argv):
            mode = str(argv[i + 1]).strip().lower()
    if mode not in {"quarterly", "weekly"}:
        print(f"[ERROR] invalid --mode: {mode}. expected quarterly|weekly", flush=True)
        sys.exit(1)
    return mode


def main() -> None:
    mode = _parse_mode(sys.argv[1:])
    tickers = _load_universe_tickers()
    suffix_map = _load_suffix_mapping()
    if not tickers:
        print("[ERROR] no tickers found in config/universe.yaml", flush=True)
        sys.exit(1)

    if mode == "weekly":
        if not OUT_FILE.exists():
            print("[WARN] weekly mode skipped: quarterly_signals.parquet not found", flush=True)
            sys.exit(0)

        df = pd.read_parquet(OUT_FILE)
        for col in ("inventory_days_accel", "gross_margin_delta", "last_rev_surprise_pct"):
            if col not in df.columns:
                df[col] = np.nan
        for col in ("fcf_yield", "roic", "fcf_conversion", "net_capex_sales", "net_debt_ebitda"):
            if col not in df.columns:
                df[col] = np.nan
        for col in ("earnings_revision_30d", "next_earnings_date"):
            if col not in df.columns:
                print(f"[WARN] weekly mode skipped: missing column {col} in existing parquet", flush=True)
                sys.exit(0)

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
                df.loc[mask, "earnings_revision_30d"] = np.nan if rev_30d is None else float(rev_30d)
                df.loc[mask, "next_earnings_date"] = next_date
                updated += 1

        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
        df["last_earnings_date"] = pd.to_datetime(df.get("last_earnings_date"), errors="coerce")
        df["next_earnings_date"] = pd.to_datetime(df["next_earnings_date"], errors="coerce")
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
            }
        )
        df = df[OUT_COLUMNS]
        df.to_parquet(TMP_FILE, index=False)
        check_df = pd.read_parquet(TMP_FILE)
        _validate_output_frame(check_df)
        os.replace(TMP_FILE, OUT_FILE)
        print(f"[WEEKLY] updated earnings_revision_30d + next_earnings_date for {updated} tickers", flush=True)
        sys.exit(0)

    print(f"[INFO] universe tickers: {len(tickers)}", flush=True)
    all_rows: list[dict[str, Any]] = []

    tickers_full = 0
    tickers_partial = 0
    tickers_zero = 0

    for idx, base_ticker in enumerate(tickers, start=1):
        ticker = base_ticker.strip().upper()
        rows = _extract_rows_for_ticker(ticker, suffix_map)
        if not rows:
            tickers_zero += 1
            print(f"[WARN] {idx}/{len(tickers)} {ticker}: zero data", flush=True)
            continue

        ticker_df = pd.DataFrame(rows, columns=OUT_COLUMNS)
        measure_cols = [c for c in OUT_COLUMNS if c not in ("ticker", "period_end")]
        if ticker_df[measure_cols].isna().any().any():
            tickers_partial += 1
        else:
            tickers_full += 1

        all_rows.extend(rows)
        print(f"[INFO] {idx}/{len(tickers)} {ticker}: {len(rows)} periods", flush=True)

    df = pd.DataFrame(all_rows, columns=OUT_COLUMNS)
    if not df.empty:
        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
        df["last_earnings_date"] = pd.to_datetime(df["last_earnings_date"], errors="coerce")
        df["next_earnings_date"] = pd.to_datetime(df["next_earnings_date"], errors="coerce")
    else:
        df = pd.DataFrame(columns=OUT_COLUMNS)
        df["period_end"] = pd.to_datetime(df["period_end"])
        df["last_earnings_date"] = pd.to_datetime(df["last_earnings_date"])
        df["next_earnings_date"] = pd.to_datetime(df["next_earnings_date"])

    # Enforce requested schema.
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
        }
    )
    df = df.sort_values(["ticker", "period_end"], ascending=[True, True]).reset_index(drop=True)

    # Atomic write: .tmp -> validate -> rename
    df.to_parquet(TMP_FILE, index=False)
    check_df = pd.read_parquet(TMP_FILE)
    _validate_output_frame(check_df)
    os.replace(TMP_FILE, OUT_FILE)

    print("[DONE] quarterly signals written", flush=True)
    print(f"[DONE] output: {OUT_FILE}", flush=True)
    print(
        f"[SUMMARY] tickers fetched={len(tickers)} full={tickers_full} partial={tickers_partial} zero={tickers_zero}",
        flush=True,
    )


if __name__ == "__main__":
    main()
