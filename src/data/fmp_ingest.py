"""
Financial Modeling Prep (FMP) quarterly fundamentals ingest.

Caches raw JSON per ticker under trading_data/fundamentals/fmp_raw_{ticker}.parquet
with atomic write (.tmp -> validate -> replace).
"""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

_FMP_BASE = "https://financialmodelingprep.com/stable"
_STATEMENTS: tuple[tuple[str, str], ...] = (
    ("income_statement", "income-statement"),
    ("balance_sheet_statement", "balance-sheet-statement"),
    ("cash_flow_statement", "cash-flow-statement"),
)

_DEFAULT_DATA = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
_FUND_DIR = _DEFAULT_DATA / "fundamentals"


def _sleep_between_calls() -> None:
    time.sleep(0.25)


def _atomic_write_parquet(df: pd.DataFrame, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    chk = pd.read_parquet(tmp)
    if chk.empty:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"refuse empty parquet write: {dest}")
    os.replace(tmp, dest)


def _to_decimal(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _fmp_api_key() -> str | None:
    k = os.getenv("FMP_API_KEY", "").strip()
    return k or None


def _fmp_symbol_candidates(ticker: str) -> list[str]:
    t = ticker.strip().upper()
    out = [t]
    if "." in t:
        base = t.split(".", 1)[0]
        if base and base not in out:
            out.append(base)
    return list(dict.fromkeys(out))


def _fetch_statement_json(
    symbol: str, path_suffix: str, api_key: str
) -> list[dict[str, Any]]:
    url = f"{_FMP_BASE}/{path_suffix}?symbol={symbol}&period=quarter&limit=20&apikey={api_key}"
    _sleep_between_calls()
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    if isinstance(data, dict) and data.get("Error Message"):
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def fetch_and_cache_fmp_raw(ticker: str) -> Path | None:
    """
    Pull three quarterly statements (20 periods) and write fmp_raw_{ticker}.parquet.
    Returns path on success, None if no API key or no usable data.
    """
    api_key = _fmp_api_key()
    if not api_key:
        return None

    _FUND_DIR.mkdir(parents=True, exist_ok=True)
    dest = _FUND_DIR / f"fmp_raw_{ticker.strip().upper()}.parquet"

    rows: list[dict[str, Any]] = []
    used_symbol: str | None = None
    for sym in _fmp_symbol_candidates(ticker):
        ok = True
        candidate_rows: list[dict[str, Any]] = []
        for stmt_key, path_suf in _STATEMENTS:
            payload = _fetch_statement_json(sym, path_suf, api_key)
            if not payload:
                ok = False
                break
            candidate_rows.append(
                {
                    "statement": stmt_key,
                    "raw_json": json.dumps(payload, separators=(",", ":")),
                }
            )
        if ok and len(candidate_rows) == 3:
            used_symbol = sym
            rows = candidate_rows
            break

    if not rows or used_symbol is None:
        return None

    df = pd.DataFrame(rows)
    _atomic_write_parquet(df, dest)
    return dest


def _read_cache_rows(ticker: str) -> pd.DataFrame | None:
    path = _FUND_DIR / f"fmp_raw_{ticker.strip().upper()}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    if df.empty or "statement" not in df.columns or "raw_json" not in df.columns:
        return None
    return df


def _list_by_statement(cache: pd.DataFrame, key: str) -> list[dict[str, Any]]:
    sub = cache.loc[cache["statement"] == key, "raw_json"]
    if sub.empty:
        return []
    try:
        data = json.loads(str(sub.iloc[0]))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _get_decimal(row: dict[str, Any], *keys: str) -> Decimal | None:
    for k in keys:
        if k in row and row[k] is not None:
            return _to_decimal(row.get(k))
    return None


def load_fmp_quarters(ticker: str) -> pd.DataFrame:
    """
    Return merged 20-quarter panel for valuation inputs.

    Core valuation columns (currency as Decimal, dates as datetime64):
      period_end, filing_date, ebit, da, sbc, capex, delta_nwc, tax_rate, r_and_d, revenue

    Additional accounting columns (Decimal or None) for fundamentals row assembly:
      gross_profit, cost_of_revenue, net_income, ebitda, total_assets, cash,
      short_term_debt, long_term_debt, current_liabilities, inventory,
      operating_cash_flow, free_cash_flow, capex_signed, total_equity
    """
    t = ticker.strip().upper()
    cache = _read_cache_rows(t)
    if cache is None:
        p = fetch_and_cache_fmp_raw(t)
        if p is None:
            return pd.DataFrame()
        cache = _read_cache_rows(t)
    if cache is None:
        return pd.DataFrame()

    income = _list_by_statement(cache, "income_statement")
    balance = _list_by_statement(cache, "balance_sheet_statement")
    cash = _list_by_statement(cache, "cash_flow_statement")
    if not income or not balance or not cash:
        return pd.DataFrame()

    def _by_date(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            d = r.get("date") or r.get("endDate") or r.get("fillingDate")
            if not d:
                continue
            out[str(d)[:10]] = r
        return out

    inc_m = _by_date(income)
    bal_m = _by_date(balance)
    cash_m = _by_date(cash)
    dates = sorted(
        set(inc_m.keys()) & set(bal_m.keys()) & set(cash_m.keys()), reverse=True
    )

    nwc_series: dict[str, Decimal | None] = {}
    for d in sorted(dates, reverse=False):
        b = bal_m[d]
        ca = _get_decimal(b, "totalCurrentAssets")
        cl = _get_decimal(b, "totalCurrentLiabilities")
        if ca is None or cl is None:
            nwc_series[d] = None
        else:
            nwc_series[d] = ca - cl

    rows_out: list[dict[str, Any]] = []
    prev_nwc: Decimal | None = None
    for d in sorted(dates, reverse=False):
        inc = inc_m[d]
        bal = bal_m[d]
        cf = cash_m[d]

        revenue = _get_decimal(inc, "revenue")
        ebit = _get_decimal(inc, "operatingIncome", "ebit")
        da = _get_decimal(inc, "depreciationAndAmortization") or _get_decimal(
            cf, "depreciationAndAmortization"
        )
        sbc = _get_decimal(cf, "stockBasedCompensation")
        capex_raw = _get_decimal(cf, "capitalExpenditure", "capitalExpenditures")
        r_and_d = _get_decimal(
            inc, "researchAndDevelopmentExpenses", "researchAndDevelopment"
        )

        tax_exp = _get_decimal(inc, "incomeTaxExpense")
        pre_tax = _get_decimal(inc, "incomeBeforeTax")
        tax_rate: Decimal | None
        if tax_exp is not None and pre_tax is not None and pre_tax > 0:
            tax_rate = tax_exp / pre_tax
        elif tax_exp is not None and pre_tax is not None and pre_tax < 0:
            tax_rate = Decimal(0)
        else:
            tax_rate = None

        nwc = nwc_series.get(d)
        if nwc is None:
            delta_nwc: Decimal | None = None
        elif prev_nwc is None:
            delta_nwc = None
        else:
            delta_nwc = nwc - prev_nwc
        prev_nwc = nwc if nwc is not None else prev_nwc

        capex_out: Decimal | None
        if capex_raw is None:
            capex_out = None
        else:
            # FMP convention: negative capitalExpenditure = cash outflow (spend).
            capex_out = -capex_raw if capex_raw < 0 else capex_raw

        filing_raw = inc.get("filingDate") or inc.get("acceptedDate") or d
        filing_dt = pd.to_datetime(filing_raw, errors="coerce")
        if pd.isna(filing_dt):
            filing_dt = pd.Timestamp(d) + pd.Timedelta(days=45)

        gross_profit = _get_decimal(inc, "grossProfit")
        cost_of_revenue = _get_decimal(inc, "costOfRevenue")
        net_income = _get_decimal(inc, "netIncome")
        ebitda_m = _get_decimal(inc, "ebitda")
        if ebitda_m is None:
            ebitda_m = ebit

        total_assets = _get_decimal(bal, "totalAssets")
        cash_bal = _get_decimal(bal, "cashAndCashEquivalents", "cash")
        std = _get_decimal(bal, "shortTermDebt")
        ltd = _get_decimal(bal, "longTermDebt")
        cur_liab = _get_decimal(bal, "totalCurrentLiabilities")
        inventory = _get_decimal(bal, "inventory")
        total_equity = _get_decimal(
            bal, "totalStockholdersEquity", "totalStockholderEquity"
        )

        cfo = _get_decimal(cf, "operatingCashFlow")
        fcf = _get_decimal(cf, "freeCashFlow")

        fiscal_year_str = str(inc.get("fiscalYear") or "")

        rows_out.append(
            {
                "period_end": pd.Timestamp(d),
                "filing_date": filing_dt,
                "fiscal_year": fiscal_year_str,
                "ebit": ebit,
                "da": da if da is not None else Decimal(0),
                "sbc": sbc if sbc is not None else Decimal(0),
                "capex": capex_out if capex_out is not None else Decimal(0),
                "delta_nwc": delta_nwc if delta_nwc is not None else Decimal(0),
                "tax_rate": tax_rate if tax_rate is not None else Decimal(0),
                "r_and_d": r_and_d if r_and_d is not None else Decimal(0),
                "revenue": revenue if revenue is not None else Decimal(0),
                "gross_profit": gross_profit,
                "cost_of_revenue": cost_of_revenue,
                "net_income": net_income,
                "ebitda": ebitda_m,
                "total_assets": total_assets,
                "cash": cash_bal,
                "short_term_debt": std,
                "long_term_debt": ltd,
                "current_liabilities": cur_liab,
                "inventory": inventory,
                "total_equity": total_equity,
                "operating_cash_flow": cfo,
                "free_cash_flow": fcf,
                "capex_signed": capex_raw if capex_raw is not None else Decimal(0),
            }
        )

    df = pd.DataFrame(rows_out)
    if df.empty:
        return df
    df = df.sort_values("period_end", ascending=False).reset_index(drop=True)
    return df
