"""
SemiValuationEngine: FCFF with optional R&D capitalization adjustment (Decimal math).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd


def _d(x: Any) -> Decimal:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return Decimal(0)
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal(0)


class SemiValuationEngine:
    """Append FCFF and R&D capitalization diagnostics to a quarterly FMP panel."""

    def compute(self, ticker: str, quarters_df: pd.DataFrame) -> pd.DataFrame:
        """
        Input columns: period_end, ebit, da, sbc, capex, delta_nwc, tax_rate, r_and_d, revenue.
        Appends: fcff_raw, rd_capitalized_asset, rd_amortization, fcff_adjusted,
                 rd_cap_variance_pct, sbc_pct_revenue, needs_edgar_audit.
        """
        _ = ticker
        if quarters_df is None or quarters_df.empty:
            return quarters_df.copy() if quarters_df is not None else pd.DataFrame()

        required = [
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
        for c in required:
            if c not in quarters_df.columns:
                return quarters_df.copy()

        asc = quarters_df.sort_values("period_end", ascending=True).reset_index(
            drop=True
        )
        n = len(asc)

        rd_amort: list[float] = []
        rd_asset: list[float] = []
        fcff_raw_l: list[float] = []
        fcff_adj_l: list[float] = []
        rd_var_l: list[float] = []
        sbc_pct_l: list[float] = []
        needs_audit_l: list[bool] = []

        for i in range(n):
            ebit = _d(asc.at[i, "ebit"])
            tr = _d(asc.at[i, "tax_rate"])
            da = _d(asc.at[i, "da"])
            sbc = _d(asc.at[i, "sbc"])
            capex = _d(asc.at[i, "capex"])
            dnwc = _d(asc.at[i, "delta_nwc"])
            rd_exp = _d(asc.at[i, "r_and_d"])
            rev = _d(asc.at[i, "revenue"])

            fcff_raw = (ebit * (Decimal(1) - tr)) + da + sbc - capex - dnwc
            fcff_raw_l.append(float(fcff_raw))

            amort = Decimal(0)
            for j in range(max(0, i - 19), i + 1):
                rd_j = _d(asc.at[j, "r_and_d"])
                amort += rd_j / Decimal(20)

            asset = Decimal(0)
            for j in range(max(0, i - 19), i + 1):
                rd_j = _d(asc.at[j, "r_and_d"])
                q_age = i - j + 1
                if q_age > 20:
                    continue
                amortized = min(q_age, 20) * (rd_j / Decimal(20))
                asset += rd_j - amortized

            rd_amort.append(float(amort))
            rd_asset.append(float(asset))

            fcff_adj = fcff_raw + sbc - rd_exp + amort
            fcff_adj_l.append(float(fcff_adj))

            if fcff_raw != 0:
                var_f = float(abs(fcff_adj - fcff_raw) / abs(fcff_raw))
            else:
                var_f = float("nan")

            rd_var_l.append(var_f)
            sbc_pct_l.append(float(sbc / rev) if rev != 0 else float("nan"))
            needs_audit_l.append((not np.isnan(var_f)) and var_f > 0.15)

        asc["fcff_raw"] = fcff_raw_l
        asc["rd_capitalized_asset"] = rd_asset
        asc["rd_amortization"] = rd_amort
        asc["fcff_adjusted"] = fcff_adj_l
        asc["rd_cap_variance_pct"] = rd_var_l
        asc["sbc_pct_revenue"] = sbc_pct_l
        asc["needs_edgar_audit"] = needs_audit_l

        patch_cols = [
            "period_end",
            "fcff_raw",
            "rd_capitalized_asset",
            "rd_amortization",
            "fcff_adjusted",
            "rd_cap_variance_pct",
            "sbc_pct_revenue",
            "needs_edgar_audit",
        ]
        asc["period_end"] = pd.to_datetime(asc["period_end"], errors="coerce")
        base = quarters_df.copy()
        base["period_end"] = pd.to_datetime(base["period_end"], errors="coerce")
        return base.merge(asc[patch_cols], on="period_end", how="left")
