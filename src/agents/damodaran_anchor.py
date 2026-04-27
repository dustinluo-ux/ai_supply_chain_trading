"""
Deterministic Damodaran-style valuation anchor (growth, risk, relative value, FCFF DCF).
No LLM. Data: yfinance only (Ticker.info + financials + cashflow).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional

import numpy as np
import pandas as pd


def safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, pd.Series):
        if len(value) == 1:
            value = value.iloc[0]
        else:
            return default
    if isinstance(value, np.ndarray):
        if value.size == 1:
            value = value.flat[0]
        else:
            return default
    try:
        if value is None:
            return default
        if isinstance(value, (float, np.floating)) and np.isnan(float(value)):
            return default
        if pd.isna(value):
            return default
        return float(value)
    except (ValueError, TypeError, OverflowError):
        return default


def estimate_cost_of_equity(beta: float | None) -> float:
    """CAPM: r_e = r_f + beta x ERP (Damodaran-style long-run averages)."""
    risk_free = 0.04
    erp = 0.05
    b = beta if beta is not None else 1.0
    return risk_free + b * erp


def analyze_growth_and_reinvestment(metrics: list, line_items: list) -> dict[str, Any]:
    """
    Growth score (0-4):
      +2  revenue CAGR > 8 %
      +1  revenue CAGR > 3 %
      +1  positive FCFF growth over available periods
      +1  ROIC > 10 %
    """
    max_score = 4
    if len(metrics) < 2:
        return {"score": 0, "max_score": max_score, "details": "Insufficient history"}

    revs = [
        m.revenue
        for m in reversed(metrics)
        if getattr(m, "revenue", None) is not None and m.revenue
    ]
    if len(revs) >= 2 and revs[0] > 0:
        cagr = (revs[-1] / revs[0]) ** (1 / (len(revs) - 1)) - 1
    else:
        cagr = None

    score, details = 0, []

    if cagr is not None:
        if cagr > 0.08:
            score += 2
            details.append(f"Revenue CAGR {cagr:.1%} (> 8 %)")
        elif cagr > 0.03:
            score += 1
            details.append(f"Revenue CAGR {cagr:.1%} (> 3 %)")
        else:
            details.append(f"Sluggish revenue CAGR {cagr:.1%}")
    else:
        details.append("Revenue data incomplete")

    fcfs = [
        li.free_cash_flow
        for li in reversed(line_items)
        if getattr(li, "free_cash_flow", None)
    ]
    fcfs = [f for f in fcfs if f]
    if len(fcfs) >= 2 and fcfs[-1] > fcfs[0]:
        score += 1
        details.append("Positive FCFF growth")
    else:
        details.append("Flat or declining FCFF")

    latest = metrics[0]
    roic = getattr(latest, "return_on_invested_capital", None)
    if roic is not None and roic > 0.10:
        score += 1
        details.append(f"ROIC {roic:.1%} (> 10 %)")
    elif roic is not None:
        details.append(f"ROIC {roic:.1%} (<= 10 %)")

    return {"score": score, "max_score": max_score, "details": "; ".join(details)}


def analyze_risk_profile(metrics: list, line_items: list) -> dict[str, Any]:
    """
    Risk score (0-3):
      +1  Beta < 1.3
      +1  Debt/Equity < 1
      +1  Interest coverage > 3x
    """
    max_score = 3
    if not metrics:
        return {"score": 0, "max_score": max_score, "details": "No metrics"}

    latest = metrics[0]
    score, details = 0, []

    beta = getattr(latest, "beta", None)
    if beta is not None:
        if beta < 1.3:
            score += 1
            details.append(f"Beta {beta:.2f}")
        else:
            details.append(f"High beta {beta:.2f}")
    else:
        details.append("Beta NA")

    dte = getattr(latest, "debt_to_equity", None)
    if dte is not None:
        if dte < 1:
            score += 1
            details.append(f"D/E {dte:.1f}")
        else:
            details.append(f"High D/E {dte:.1f}")
    else:
        details.append("D/E NA")

    ebit = getattr(latest, "ebit", None)
    interest = getattr(latest, "interest_expense", None)
    if ebit is not None and interest is not None and interest != 0:
        coverage = ebit / abs(interest)
        if coverage > 3:
            score += 1
            details.append(f"Interest coverage x {coverage:.1f}")
        else:
            details.append(f"Weak coverage x {coverage:.1f}")
    else:
        details.append("Interest coverage NA")

    cost_of_equity = estimate_cost_of_equity(
        beta if isinstance(beta, (int, float)) else None
    )

    return {
        "score": score,
        "max_score": max_score,
        "details": "; ".join(details),
        "beta": beta,
        "cost_of_equity": cost_of_equity,
    }


def analyze_relative_valuation(metrics: list) -> dict[str, Any]:
    """
    P/E vs historical median on available periods (proxy; needs >=3 finite P/Es).
      +1 if TTM P/E < 70 % of median
      -1 if > 130 %
      0 otherwise
    """
    max_score = 1
    if not metrics or len(metrics) < 3:
        return {
            "score": 0,
            "max_score": max_score,
            "details": "Insufficient P/E history",
        }

    pes = [
        m.price_to_earnings_ratio
        for m in metrics
        if getattr(m, "price_to_earnings_ratio", None) is not None
    ]
    pes = [
        p
        for p in pes
        if p is not None and p > 0 and not (isinstance(p, float) and np.isnan(p))
    ]
    if len(pes) < 3:
        return {"score": 0, "max_score": max_score, "details": "P/E data sparse"}

    ttm_pe = pes[0]
    median_pe = sorted(pes)[len(pes) // 2]

    if ttm_pe < 0.7 * median_pe:
        score, desc = 1, f"P/E {ttm_pe:.1f} vs. median {median_pe:.1f} (cheap)"
    elif ttm_pe > 1.3 * median_pe:
        score, desc = -1, f"P/E {ttm_pe:.1f} vs. median {median_pe:.1f} (expensive)"
    else:
        score, desc = 0, "P/E inline with history"

    return {"score": score, "max_score": max_score, "details": desc}


def calculate_intrinsic_value_dcf(
    metrics: list, line_items: list, risk_analysis: dict
) -> dict[str, Any]:
    """
    FCFF DCF (equity value ~ firm value here); base FCFF and equity_value stored as Decimal in output.
    """
    if not metrics or not line_items:
        return {
            "intrinsic_value": None,
            "intrinsic_per_share": None,
            "assumptions": {},
            "details": ["Insufficient data"],
        }

    latest_m = metrics[0]
    fcff0 = getattr(latest_m, "free_cash_flow", None)
    shares = getattr(line_items[0], "outstanding_shares", None)
    if not fcff0 or not shares:
        return {
            "intrinsic_value": None,
            "intrinsic_per_share": None,
            "assumptions": {},
            "details": ["Missing FCFF or share count"],
        }

    revs = [
        m.revenue
        for m in reversed(metrics)
        if getattr(m, "revenue", None) and m.revenue
    ]
    if len(revs) >= 2 and revs[0] > 0:
        base_growth = min((revs[-1] / revs[0]) ** (1 / (len(revs) - 1)) - 1, 0.12)
    else:
        base_growth = 0.04

    terminal_growth = 0.025
    years = 10
    discount = risk_analysis.get("cost_of_equity") or 0.09

    pv_sum = 0.0
    g = base_growth
    g_step = (terminal_growth - base_growth) / (years - 1) if years > 1 else 0.0
    for yr in range(1, years + 1):
        fcff_t = float(fcff0) * (1 + g)
        pv = fcff_t / (1 + discount) ** yr
        pv_sum += pv
        g += g_step

    fcff0_f = float(fcff0)
    tv = (
        fcff0_f
        * (1 + terminal_growth)
        / (discount - terminal_growth)
        / (1 + discount) ** years
    )

    equity_value_f = pv_sum + tv
    intrinsic_per_share = equity_value_f / float(shares)

    fcff0_dec = Decimal(str(fcff0_f))
    equity_dec = Decimal(str(equity_value_f))

    return {
        "intrinsic_value": equity_dec,
        "intrinsic_per_share": intrinsic_per_share,
        "assumptions": {
            "base_fcff": fcff0_dec,
            "base_growth": base_growth,
            "terminal_growth": terminal_growth,
            "discount_rate": discount,
            "projection_years": years,
            "equity_value": equity_dec,
        },
        "details": ["FCFF DCF completed"],
    }


def _fin_row(df: pd.DataFrame, *names: str) -> Optional[str]:
    if df is None or df.empty:
        return None
    for n in names:
        for idx in df.index:
            s = str(idx).strip().lower()
            if s == n.lower():
                return str(idx)
            if n.lower() in s:
                return str(idx)
    return None


def _dec_from_info(info: dict, key: str) -> Decimal | None:
    v = info.get(key)
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _build_snapshots(
    financials: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    info: dict,
) -> tuple[list[Any], list[Any]]:
    """Metrics and line_items (newest first) for Damodaran analyses."""
    metrics: list[Any] = []
    line_items: list[Any] = []

    mc = _dec_from_info(info, "marketCap")

    if financials is None or financials.empty:
        ni0 = (
            safe_float(info.get("netIncomeToCommon"))
            if info.get("netIncomeToCommon") is not None
            else None
        )
        pe0 = (
            safe_float(info.get("trailingPE"))
            if info.get("trailingPE") is not None
            else None
        )
        if pe0 is None and mc is not None and ni0 is not None and abs(ni0) > 1e-9:
            pe0 = float(mc / abs(ni0))
        m0 = SimpleNamespace(
            debt_to_equity=(
                safe_float(info.get("debtToEquity"))
                if info.get("debtToEquity") is not None
                else None
            ),
            interest_expense=None,
            earnings_growth=None,
            revenue=(
                safe_float(info.get("totalRevenue"))
                if info.get("totalRevenue") is not None
                else None
            ),
            operating_margin=(
                safe_float(info.get("operatingMargins"))
                if info.get("operatingMargins") is not None
                else None
            ),
            return_on_invested_capital=(
                safe_float(info.get("returnOnEquity"))
                if info.get("returnOnEquity") is not None
                else None
            ),
            price_to_earnings_ratio=pe0,
            free_cash_flow=(
                safe_float(info.get("freeCashflow"))
                if info.get("freeCashflow") is not None
                else None
            ),
            beta=safe_float(info.get("beta")),
            ebit=None,
        )
        li0 = SimpleNamespace(
            free_cash_flow=m0.free_cash_flow,
            outstanding_shares=safe_float(info.get("sharesOutstanding")),
            net_income=ni0,
        )
        return [m0], [li0]

    cols = list(financials.columns)
    rev_key = _fin_row(financials, "Total Revenue", "Operating Revenue")
    op_key = _fin_row(financials, "Operating Income")
    ni_key = _fin_row(financials, "Net Income")

    ni_series: list[float] = []
    for c in cols:
        if ni_key:
            ni_series.append(safe_float(financials.loc[ni_key, c], float("nan")))
    eg_list: list[Optional[float]] = []
    for i in range(len(ni_series)):
        if (
            i + 1 < len(ni_series)
            and ni_series[i + 1] not in (0, float("nan"))
            and not np.isnan(ni_series[i + 1])
        ):
            eg_list.append((ni_series[i] - ni_series[i + 1]) / abs(ni_series[i + 1]))
        else:
            eg_list.append(None)

    for j, c in enumerate(cols):
        rev = safe_float(financials.loc[rev_key, c]) if rev_key else None
        op_inc = safe_float(financials.loc[op_key, c]) if op_key else None
        ni = ni_series[j] if j < len(ni_series) else None
        if ni is not None and np.isnan(ni):
            ni = None
        om = (op_inc / rev) if (rev and rev != 0 and op_inc is not None) else None
        eg = eg_list[j] if j < len(eg_list) else None

        fcf_v = None
        if cashflow is not None and not cashflow.empty:
            fcf_k = _fin_row(cashflow, "Free Cash Flow")
            if fcf_k and c in cashflow.columns:
                fcf_v = safe_float(cashflow.loc[fcf_k, c], float("nan"))
                if np.isnan(fcf_v):
                    fcf_v = None

        pe_proxy = None
        if mc is not None and ni is not None and abs(ni) > 1e-9:
            pe_proxy = float(mc) / abs(ni)

        m = SimpleNamespace(
            debt_to_equity=(
                safe_float(info.get("debtToEquity"))
                if j == 0 and info.get("debtToEquity") is not None
                else None
            ),
            interest_expense=None,
            earnings_growth=eg,
            revenue=rev,
            operating_margin=om,
            return_on_invested_capital=(
                safe_float(info.get("returnOnEquity")) if j == 0 else None
            ),
            price_to_earnings_ratio=pe_proxy,
            free_cash_flow=fcf_v,
            beta=safe_float(info.get("beta")) if j == 0 else None,
            ebit=op_inc,
        )
        if j == 0 and op_inc is not None:
            int_key = _fin_row(
                financials, "Interest Expense", "Interest And Debt Expense"
            )
            if int_key:
                inter = safe_float(financials.loc[int_key, c])
                if inter is not None and abs(inter) > 0:
                    m = SimpleNamespace(**{**m.__dict__, "interest_expense": inter})
        metrics.append(m)
        li = SimpleNamespace(
            free_cash_flow=fcf_v,
            outstanding_shares=(
                safe_float(info.get("sharesOutstanding")) if j == 0 else None
            ),
            net_income=ni,
        )
        line_items.append(li)

    return metrics, line_items


@dataclass
class DamodaranAnchorResult:
    ticker: str
    intrinsic_value: Decimal | None
    market_cap: Decimal | None
    margin_of_safety: float | None
    signal: str
    score: int
    max_score: int
    details: dict[str, str]
    analysis_date: str


def anchor_ticker(ticker: str, analysis_date: str) -> DamodaranAnchorResult:
    """Run Damodaran-style sub-analyses. Never raises."""
    neutral = DamodaranAnchorResult(
        ticker=ticker,
        intrinsic_value=None,
        market_cap=None,
        margin_of_safety=None,
        signal="FAIR",
        score=0,
        max_score=1,
        details={"error": "anchor failed"},
        analysis_date=analysis_date,
    )
    try:
        import yfinance as yf

        ytk = yf.Ticker(ticker)
        info = ytk.info or {}
        fin = ytk.financials
        cf = ytk.cashflow
        if fin is None or getattr(fin, "empty", True):
            fin = None
        if cf is None or getattr(cf, "empty", True):
            cf = None

        metrics, line_items = _build_snapshots(fin, cf, info)

        growth_analysis = analyze_growth_and_reinvestment(metrics, line_items)
        risk_analysis = analyze_risk_profile(metrics, line_items)
        relative_val_analysis = analyze_relative_valuation(metrics)
        intrinsic_val_analysis = calculate_intrinsic_value_dcf(
            metrics, line_items, risk_analysis
        )

        total_score = (
            growth_analysis["score"]
            + risk_analysis["score"]
            + relative_val_analysis["score"]
        )
        max_score = (
            growth_analysis["max_score"]
            + risk_analysis["max_score"]
            + relative_val_analysis["max_score"]
        )

        intrinsic_dec = intrinsic_val_analysis.get("intrinsic_value")
        if intrinsic_dec is not None and not isinstance(intrinsic_dec, Decimal):
            intrinsic_dec = Decimal(str(intrinsic_dec))

        market_cap = _dec_from_info(info, "marketCap")

        margin_of_safety: float | None = None
        if (
            intrinsic_dec is not None
            and market_cap is not None
            and market_cap != Decimal("0")
        ):
            margin_of_safety = float((intrinsic_dec - market_cap) / market_cap)

        if margin_of_safety is not None and margin_of_safety >= 0.25:
            signal = "UNDERVALUED"
        elif margin_of_safety is not None and margin_of_safety <= -0.25:
            signal = "OVERVALUED"
        else:
            signal = "FAIR"

        details = {
            "growth": str(growth_analysis.get("details", "")),
            "risk": str(risk_analysis.get("details", "")),
            "relative": str(relative_val_analysis.get("details", "")),
            "dcf": "; ".join(str(x) for x in intrinsic_val_analysis.get("details", [])),
        }

        return DamodaranAnchorResult(
            ticker=ticker,
            intrinsic_value=intrinsic_dec,
            market_cap=market_cap,
            margin_of_safety=margin_of_safety,
            signal=signal,
            score=int(total_score),
            max_score=int(max_score),
            details=details,
            analysis_date=analysis_date,
        )
    except Exception as exc:
        neutral.details = {"error": str(exc)}
        return neutral
