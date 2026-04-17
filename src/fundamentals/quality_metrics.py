"""
Quality metric derivations for quarterly fundamentals.

These metrics focus on cash generation, balance-sheet structure, and investment intensity,
which are generally less susceptible to accrual manipulation than earnings multiples like
P/E or simple operating cash flow multiples. They are used both as Layer 1 quality filters
and Layer 2 cross-sectional alpha signals in the layered engine, while all thresholds and
cutoffs are externalized in config/layered_signal_config.yaml.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_quality_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Append five quality metrics and remove underscore-prefixed intermediates."""
    out = df.copy()

    market_cap = out["_market_cap"].where(out["_market_cap"].notna() & out["_market_cap"].gt(0))
    out["fcf_yield"] = out["_fcf_ttm"] / market_cap

    current_liab_excess = (out["_current_liabilities"] - out["_short_term_debt"]).clip(lower=0)
    invested_capital = (out["_total_assets"] - out["_cash"] - current_liab_excess).clip(lower=1.0)
    roic = out["_net_income"] / invested_capital
    roic = roic.where(out["_total_assets"].notna() & out["_net_income"].notna())
    out["roic"] = roic.clip(lower=-5.0, upper=5.0)

    net_income_nonzero = out["_net_income"].where(out["_net_income"].notna() & out["_net_income"].ne(0))
    out["fcf_conversion"] = out["_fcf_ttm"] / net_income_nonzero

    valid_revenue = out["_revenue"].where(out["_revenue"].notna() & out["_revenue"].gt(0))
    out["net_capex_sales"] = (out["_capex"].abs() + out["_r_and_d"].fillna(0)) / valid_revenue

    valid_ebitda = out["_ebitda"].where(out["_ebitda"].notna() & out["_ebitda"].gt(0))
    out["net_debt_ebitda"] = (out["_short_term_debt"] + out["_long_term_debt"] - out["_cash"]) / valid_ebitda

    out = out[[c for c in out.columns if not c.startswith("_")]]
    return out
