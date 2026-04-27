"""
SEC EDGAR 10-K XBRL audit vs FMP (ResearchAndDevelopmentExpense, ShareBasedCompensation).
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import pandas as pd

from src.data.fmp_ingest import load_fmp_quarters


def _d(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _fmp_annual_rd_sbc(
    ticker: str, calendar_year: int
) -> tuple[Decimal | None, Decimal | None]:
    df = load_fmp_quarters(ticker)
    if df is None or df.empty:
        return None, None
    if "period_end" not in df.columns:
        return None, None
    # Prefer FMP's own fiscalYear field to avoid calendar/fiscal mismatch
    # (e.g. NVDA FY ends Jan — calendar year filter picks wrong quarters)
    if "fiscal_year" in df.columns:
        mask = df["fiscal_year"].astype(str) == str(int(calendar_year))
    else:
        pe = pd.to_datetime(df["period_end"], errors="coerce")
        mask = pe.dt.year == int(calendar_year)
    sub = df.loc[mask]
    if sub.empty:
        return None, None

    def _sum_col(name: str) -> Decimal | None:
        if name not in sub.columns:
            return None
        total = Decimal(0)
        any_v = False
        for x in sub[name].tolist():
            if x is None or (isinstance(x, float) and pd.isna(x)):
                continue
            try:
                total += Decimal(str(x))
                any_v = True
            except Exception:
                continue
        return total if any_v else None

    rd = _sum_col("r_and_d")
    sbc = _sum_col("sbc")
    return rd, sbc


def _pick_10k_for_year(company: Any, fiscal_year: int) -> Any | None:
    try:
        filings = company.get_filings(form="10-K")
    except Exception:
        return None
    if filings is None:
        return None

    candidates: list[Any] = []
    try:
        it = list(filings.head(40))
    except Exception:
        it = []

    for f in it:
        fy = getattr(f, "fiscal_year", None)
        if fy is not None and int(fy) == int(fiscal_year):
            return f
        candidates.append(f)

    for f in candidates:
        try:
            fd = getattr(f, "filing_date", None) or getattr(f, "filed_at", None)
            if fd is None:
                continue
            ts = pd.to_datetime(fd, errors="coerce")
            if pd.isna(ts):
                continue
            if int(ts.year) in (fiscal_year, fiscal_year + 1):
                xb = f.xbrl()
                if xb is not None:
                    return f
        except Exception:
            continue

    for f in candidates:
        try:
            if f.xbrl() is not None:
                return f
        except Exception:
            continue
    return None


def _filter_annual_period(df: "pd.DataFrame", fiscal_year: int) -> "pd.DataFrame":
    """
    Narrow XBRL fact rows to the annual period for the target fiscal year.
    Filters for fiscal_period == "FY" and period_end.year == fiscal_year.
    Falls back to unfiltered df if no match found.
    """
    import pandas as _pd

    try:
        working = df.copy()
        if "fiscal_period" in working.columns:
            annual = working[working["fiscal_period"] == "FY"]
            if not annual.empty:
                working = annual
        if "period_end" in working.columns:
            pe = _pd.to_datetime(working["period_end"], errors="coerce")
            match = working[pe.dt.year == fiscal_year]
            if not match.empty:
                return match
    except Exception:
        pass
    return df


def _fact_annual_amount(
    xbrl: Any, concept_fragments: tuple[str, ...], fiscal_year: int | None = None
) -> Decimal | None:
    try:
        facts = xbrl.facts
    except Exception:
        return None
    if facts is None:
        return None

    best: Decimal | None = None

    try:
        q = facts.query()
        for frag in concept_fragments:
            for prefix in ("us-gaap:", ""):
                concept = f"{prefix}{frag}" if prefix else frag
                try:
                    res = q.by_concept(concept)
                    df = res.to_dataframe() if hasattr(res, "to_dataframe") else None
                except Exception:
                    df = None
                if df is None or getattr(df, "empty", True):
                    continue
                if fiscal_year is not None:
                    df = _filter_annual_period(df, fiscal_year)
                val_col = None
                for c in ("value", "numeric_value", "amount", "Value"):
                    if c in df.columns:
                        val_col = c
                        break
                if val_col is None:
                    continue
                vals = pd.to_numeric(df[val_col], errors="coerce").dropna()
                if vals.empty:
                    continue
                v = float(vals.iloc[0])
                best = Decimal(str(v))
                return best
    except Exception:
        pass

    try:
        raw = facts.to_dataframe() if hasattr(facts, "to_dataframe") else None
    except Exception:
        raw = None
    if raw is None or getattr(raw, "empty", True):
        return best

    if fiscal_year is not None:
        raw = _filter_annual_period(raw, fiscal_year)

    concept_col = None
    for c in ("concept", "tag", "name", "element"):
        if c in raw.columns:
            concept_col = c
            break
    if concept_col is None:
        return best

    val_col = None
    for c in ("value", "numeric_value", "amount", "Value"):
        if c in raw.columns:
            val_col = c
            break
    if val_col is None:
        return best

    for frag in concept_fragments:
        m = raw[raw[concept_col].astype(str).str.contains(frag, case=False, na=False)]
        if m.empty:
            continue
        vals = pd.to_numeric(m[val_col], errors="coerce").dropna()
        if vals.empty:
            continue
        return Decimal(str(float(vals.iloc[0])))
    return best


def audit_ticker(ticker: str, fiscal_year: int) -> dict[str, Any]:
    """
    Compare FMP annual aggregates to 10-K XBRL facts for a calendar-aligned fiscal year.

    Returns keys including audit_pass (True if both variances < 15%), or
    {"audit_pass": None, "error": str} on failure (never raises).
    """
    out_base: dict[str, Any] = {
        "ticker": ticker,
        "year": int(fiscal_year),
        "rd_fmp": None,
        "rd_edgar": None,
        "rd_variance_pct": None,
        "sbc_fmp": None,
        "sbc_edgar": None,
        "sbc_variance_pct": None,
        "audit_pass": None,
    }

    try:
        try:
            from edgar import Company, set_identity  # type: ignore[import-untyped]
        except Exception as exc:
            return {
                **out_base,
                "audit_pass": None,
                "error": f"edgartools import failed: {exc}",
            }

        ident = (
            os.getenv("EDGAR_IDENTITY", "").strip()
            or os.getenv("EDGAR_EMAIL", "").strip()
            or os.getenv("SEC_USER_AGENT_EMAIL", "").strip()
        )
        if ident:
            try:
                set_identity(ident)
            except Exception:
                pass

        rd_fmp, sbc_fmp = _fmp_annual_rd_sbc(ticker, fiscal_year)
        out_base["rd_fmp"] = rd_fmp
        out_base["sbc_fmp"] = sbc_fmp

        sym = ticker.strip().upper()
        try:
            company = Company(sym)
        except Exception as exc:
            return {
                **out_base,
                "audit_pass": None,
                "error": f"Company({sym}) failed: {exc}",
            }

        filing = _pick_10k_for_year(company, fiscal_year)
        if filing is None:
            return {**out_base, "audit_pass": None, "error": "no 10-K filing located"}

        xbrl = filing.xbrl()
        if xbrl is None:
            return {**out_base, "audit_pass": None, "error": "10-K has no XBRL"}

        rd_edgar = _fact_annual_amount(
            xbrl,
            (
                "ResearchAndDevelopmentExpense",
                "ResearchAndDevelopmentExpenseSoftwareExcludingAcquired",
            ),
            fiscal_year=int(fiscal_year),
        )
        sbc_edgar = _fact_annual_amount(
            xbrl,
            (
                "ShareBasedCompensation",
                "SharebasedCompensationArrangementBySharebasedPaymentAwardExpenseRequisiteServicePeriodRecognitionAmount",
            ),
            fiscal_year=int(fiscal_year),
        )
        out_base["rd_edgar"] = rd_edgar
        out_base["sbc_edgar"] = sbc_edgar

        def _var(a: Decimal | None, b: Decimal | None) -> Decimal | None:
            if a is None or b is None:
                return None
            if b == 0:
                return None
            return abs(a - b) / abs(b)

        rd_var = _var(rd_fmp, rd_edgar)
        sbc_var = _var(sbc_fmp, sbc_edgar)
        out_base["rd_variance_pct"] = rd_var
        out_base["sbc_variance_pct"] = sbc_var

        thresh = Decimal("0.15")
        ok_rd = rd_var is not None and rd_var < thresh
        ok_sbc = sbc_var is not None and sbc_var < thresh
        out_base["audit_pass"] = bool(ok_rd and ok_sbc)
        return out_base
    except Exception as exc:
        return {**out_base, "audit_pass": None, "error": str(exc)}
