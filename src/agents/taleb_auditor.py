"""
Deterministic Taleb-style audit (tail risk, antifragility, convexity, etc.).
No LLM. Data: yfinance + caller-supplied prices_df only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional

import numpy as np
import pandas as pd


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, handling NaN cases."""
    try:
        if pd.isna(value) or np.isnan(value):
            return default
        return float(value)
    except (ValueError, TypeError, OverflowError):
        return default


def analyze_tail_risk(prices_df: pd.DataFrame) -> dict[str, Any]:
    """Assess fat tails, skewness, tail ratio, and max drawdown."""
    if prices_df.empty or len(prices_df) < 20:
        return {"score": 0, "max_score": 8, "details": "Insufficient price data for tail risk analysis"}

    score = 0
    reasoning = []

    returns = prices_df["close"].pct_change().dropna()

    # Excess kurtosis (use rolling 63-day if enough data, else full series)
    if len(returns) >= 63:
        kurt = safe_float(returns.rolling(63).kurt().iloc[-1])
    else:
        kurt = safe_float(returns.kurt())

    if kurt > 5:
        score += 2
        reasoning.append(f"Extremely fat tails (kurtosis {kurt:.1f})")
    elif kurt > 2:
        score += 1
        reasoning.append(f"Moderate fat tails (kurtosis {kurt:.1f})")
    else:
        reasoning.append(f"Near-Gaussian tails (kurtosis {kurt:.1f}) — suspiciously thin")

    # Skewness
    if len(returns) >= 63:
        skew = safe_float(returns.rolling(63).skew().iloc[-1])
    else:
        skew = safe_float(returns.skew())

    if skew > 0.5:
        score += 2
        reasoning.append(f"Positive skew ({skew:.2f}) favors long convexity")
    elif skew > -0.5:
        score += 1
        reasoning.append(f"Symmetric distribution (skew {skew:.2f})")
    else:
        reasoning.append(f"Negative skew ({skew:.2f}) — crash-prone")

    # Tail ratio (95th percentile gains / abs(5th percentile losses))
    positive_returns = returns[returns > 0]
    negative_returns = returns[returns < 0]

    if len(positive_returns) > 20 and len(negative_returns) > 20:
        right_tail = np.percentile(positive_returns, 95)
        left_tail = abs(np.percentile(negative_returns, 5))
        tail_ratio = right_tail / left_tail if left_tail > 0 else 1.0

        if tail_ratio > 1.2:
            score += 2
            reasoning.append(f"Asymmetric upside (tail ratio {tail_ratio:.2f})")
        elif tail_ratio > 0.8:
            score += 1
            reasoning.append(f"Balanced tails (tail ratio {tail_ratio:.2f})")
        else:
            reasoning.append(f"Asymmetric downside (tail ratio {tail_ratio:.2f})")
    else:
        reasoning.append("Insufficient data for tail ratio")

    # Max drawdown
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_dd = safe_float(drawdown.min())

    if max_dd > -0.15:
        score += 2
        reasoning.append(f"Resilient (max drawdown {max_dd:.1%})")
    elif max_dd > -0.30:
        score += 1
        reasoning.append(f"Moderate drawdown ({max_dd:.1%})")
    else:
        reasoning.append(f"Severe drawdown ({max_dd:.1%}) — fragile")

    return {"score": score, "max_score": 8, "details": "; ".join(reasoning)}


def analyze_volatility_regime(prices_df: pd.DataFrame) -> dict[str, Any]:
    """Volatility regime analysis. Key Taleb insight: low vol is dangerous (turkey problem)."""
    if prices_df.empty or len(prices_df) < 30:
        return {"score": 0, "max_score": 6, "details": "Insufficient price data for volatility analysis"}

    score = 0
    reasoning = []

    returns = prices_df["close"].pct_change().dropna()

    # Historical volatility (annualized, 21-day rolling)
    hist_vol = returns.rolling(21).std() * math.sqrt(252)

    # Vol regime ratio (current vol / 63-day avg vol)
    if len(hist_vol.dropna()) >= 63:
        vol_ma = hist_vol.rolling(63).mean()
        current_vol = safe_float(hist_vol.iloc[-1])
        avg_vol = safe_float(vol_ma.iloc[-1])
        vol_regime = current_vol / avg_vol if avg_vol > 0 else 1.0
    elif len(hist_vol.dropna()) >= 21:
        # Fallback: compare current to overall mean
        current_vol = safe_float(hist_vol.iloc[-1])
        avg_vol = safe_float(hist_vol.mean())
        vol_regime = current_vol / avg_vol if avg_vol > 0 else 1.0
    else:
        return {"score": 0, "max_score": 6, "details": "Insufficient data for volatility regime analysis"}

    # Vol regime scoring (max 4)
    if vol_regime < 0.7:
        reasoning.append(f"Dangerously low vol (regime {vol_regime:.2f}) — turkey problem")
    elif vol_regime < 0.9:
        score += 1
        reasoning.append(f"Below-average vol (regime {vol_regime:.2f}) — approaching complacency")
    elif vol_regime <= 1.3:
        score += 3
        reasoning.append(f"Normal vol regime ({vol_regime:.2f}) — fair pricing")
    elif vol_regime <= 2.0:
        score += 4
        reasoning.append(f"Elevated vol (regime {vol_regime:.2f}) — opportunity for the antifragile")
    else:
        score += 2
        reasoning.append(f"Extreme vol (regime {vol_regime:.2f}) — crisis mode")

    # Vol-of-vol scoring (max 2)
    if len(hist_vol.dropna()) >= 42:
        vol_of_vol = hist_vol.rolling(21).std()
        vol_of_vol_clean = vol_of_vol.dropna()
        if len(vol_of_vol_clean) > 0:
            current_vov = safe_float(vol_of_vol_clean.iloc[-1])
            median_vov = safe_float(vol_of_vol_clean.median())
            if median_vov > 0:
                if current_vov > 2 * median_vov:
                    score += 2
                    reasoning.append(
                        f"Highly unstable vol (vol-of-vol {current_vov:.4f} vs median {median_vov:.4f}) — regime change likely"
                    )
                elif current_vov > median_vov:
                    score += 1
                    reasoning.append(f"Elevated vol-of-vol ({current_vov:.4f} vs median {median_vov:.4f})")
                else:
                    reasoning.append(f"Stable vol-of-vol ({current_vov:.4f})")
            else:
                reasoning.append("Vol-of-vol median is zero — unusual")
        else:
            reasoning.append("Insufficient vol-of-vol data")
    else:
        reasoning.append("Insufficient history for vol-of-vol analysis")

    return {"score": score, "max_score": 6, "details": "; ".join(reasoning)}


def analyze_black_swan_sentinel(news: list, prices_df: pd.DataFrame) -> dict[str, Any]:
    """Monitor for crisis signals: abnormal news sentiment, volume spikes, price dislocations."""
    score = 2  # Default: normal conditions
    reasoning = []

    # News sentiment analysis
    neg_ratio = 0.0
    if news:
        total = len(news)
        neg_count = sum(1 for n in news if n.sentiment and n.sentiment.lower() in ["negative", "bearish"])
        neg_ratio = neg_count / total if total > 0 else 0
    else:
        reasoning.append("No recent news data")

    # Volume spike detection
    volume_spike = 1.0
    recent_return = 0.0
    if not prices_df.empty and len(prices_df) >= 10:
        if "volume" in prices_df.columns:
            recent_vol = prices_df["volume"].iloc[-5:].mean()
            avg_vol = prices_df["volume"].iloc[-63:].mean() if len(prices_df) >= 63 else prices_df["volume"].mean()
            volume_spike = recent_vol / avg_vol if avg_vol > 0 else 1.0

        if len(prices_df) >= 5:
            recent_return = safe_float(prices_df["close"].iloc[-1] / prices_df["close"].iloc[-5] - 1)

    # Scoring
    if neg_ratio > 0.7 and volume_spike > 2.0:
        score = 0
        reasoning.append(f"Black swan warning — {neg_ratio:.0%} negative news, {volume_spike:.1f}x volume spike")
    elif neg_ratio > 0.5 or volume_spike > 2.5:
        score = 1
        reasoning.append(f"Elevated stress signals (neg news {neg_ratio:.0%}, volume {volume_spike:.1f}x)")
    elif neg_ratio > 0.3 and abs(recent_return) > 0.10:
        score = 1
        reasoning.append(
            f"Moderate stress with price dislocation ({recent_return:.1%} move, {neg_ratio:.0%} negative news)"
        )
    elif neg_ratio < 0.3 and volume_spike < 1.5:
        score = 3
        reasoning.append("No black swan signals detected")
    else:
        reasoning.append(f"Normal conditions (neg news {neg_ratio:.0%}, volume {volume_spike:.1f}x)")

    # Contrarian bonus: high negative news but no volume panic could be opportunity
    if neg_ratio > 0.4 and volume_spike < 1.5 and score < 4:
        score = min(score + 1, 4)
        reasoning.append("Contrarian opportunity — negative sentiment without panic selling")

    return {"score": score, "max_score": 4, "details": "; ".join(reasoning)}


def analyze_fragility(metrics: list, line_items: list) -> dict[str, Any]:
    """Via Negativa: detect fragile companies. High score = NOT fragile."""
    if not metrics:
        return {"score": 0, "max_score": 8, "details": "Insufficient data for fragility analysis"}

    score = 0
    reasoning = []
    latest_metrics = metrics[0]

    # Leverage fragility
    debt_to_equity = getattr(latest_metrics, "debt_to_equity", None)
    if debt_to_equity is not None:
        if debt_to_equity > 2.0:
            reasoning.append(f"Extremely fragile balance sheet (D/E {debt_to_equity:.2f})")
        elif debt_to_equity > 1.0:
            score += 1
            reasoning.append(f"Elevated leverage (D/E {debt_to_equity:.2f})")
        elif debt_to_equity > 0.5:
            score += 2
            reasoning.append(f"Moderate leverage (D/E {debt_to_equity:.2f})")
        else:
            score += 3
            reasoning.append(f"Low leverage (D/E {debt_to_equity:.2f}) — not fragile")
    else:
        reasoning.append("Debt-to-equity data not available")

    # Interest coverage
    interest_coverage = getattr(latest_metrics, "interest_coverage", None)
    if interest_coverage is not None:
        if interest_coverage > 10:
            score += 2
            reasoning.append(f"Interest coverage {interest_coverage:.1f}x — debt is irrelevant")
        elif interest_coverage > 5:
            score += 1
            reasoning.append(f"Comfortable interest coverage ({interest_coverage:.1f}x)")
        else:
            reasoning.append(f"Low interest coverage ({interest_coverage:.1f}x) — fragile to rate changes")
    else:
        reasoning.append("Interest coverage data not available")

    # Earnings volatility
    earnings_growth_values = [m.earnings_growth for m in metrics if m.earnings_growth is not None]
    if len(earnings_growth_values) >= 3:
        mean_eg = sum(earnings_growth_values) / len(earnings_growth_values)
        variance = sum((e - mean_eg) ** 2 for e in earnings_growth_values) / len(earnings_growth_values)
        std_eg = variance**0.5

        if std_eg < 0.20:
            score += 2
            reasoning.append(f"Stable earnings (growth std {std_eg:.2f}) — robust")
        elif std_eg < 0.50:
            score += 1
            reasoning.append(f"Moderate earnings volatility (growth std {std_eg:.2f})")
        else:
            reasoning.append(f"Highly volatile earnings (growth std {std_eg:.2f}) — fragile")
    else:
        reasoning.append("Insufficient earnings history for volatility analysis")

    # Net margin buffer
    net_margin = getattr(latest_metrics, "net_margin", None)
    if net_margin is not None:
        if net_margin > 0.15:
            score += 1
            reasoning.append(f"Fat margins ({net_margin:.1%}) buffer shocks")
        elif net_margin >= 0.05:
            reasoning.append(f"Moderate margins ({net_margin:.1%})")
        else:
            reasoning.append(f"Paper-thin margins ({net_margin:.1%}) — one shock away from loss")
    else:
        reasoning.append("Net margin data not available")

    # Clamp score at minimum 0
    score = max(score, 0)

    return {"score": score, "max_score": 8, "details": "; ".join(reasoning)}


def analyze_skin_in_game(insider_trades: list) -> dict[str, Any]:
    """Assess insider alignment: net insider buying signals trust."""
    if not insider_trades:
        return {"score": 1, "max_score": 4, "details": "No insider trade data — neutral assumption"}

    score = 0
    reasoning = []

    shares_bought = sum(t.transaction_shares or 0 for t in insider_trades if (t.transaction_shares or 0) > 0)
    shares_sold = abs(sum(t.transaction_shares or 0 for t in insider_trades if (t.transaction_shares or 0) < 0))
    net = shares_bought - shares_sold

    if net > 0:
        buy_sell_ratio = net / max(shares_sold, 1)
        if buy_sell_ratio > 2.0:
            score = 4
            reasoning.append(
                f"Strong skin in the game — net insider buying {net:,} shares (ratio {buy_sell_ratio:.1f}x)"
            )
        elif buy_sell_ratio > 0.5:
            score = 3
            reasoning.append(f"Moderate insider conviction — net buying {net:,} shares")
        else:
            score = 2
            reasoning.append(f"Net insider buying of {net:,} shares")
    else:
        reasoning.append(f"Insiders selling — no skin in the game (net {net:,} shares)")

    return {"score": score, "max_score": 4, "details": "; ".join(reasoning)}


def _dec_from_info(info: dict, *keys: str) -> Optional[Decimal]:
    for k in keys:
        v = info.get(k)
        if v is not None and v != "":
            try:
                return Decimal(str(v))
            except Exception:
                continue
    return None


def analyze_antifragility(
    info: dict,
    metrics: list,
    line_items: list,
    market_cap: Decimal | None,
) -> dict[str, Any]:
    """Antifragility using yfinance info + optional multi-period metrics/line_items (SimpleNamespace lists)."""
    if not info and not metrics and not line_items:
        return {"score": 0, "max_score": 10, "details": "Insufficient data for antifragility analysis"}

    score = 0
    reasoning = []
    latest_metrics = metrics[0] if metrics else None
    latest_item = line_items[0] if line_items else None

    cash_dec = _dec_from_info(info, "totalCash")
    debt_dec = _dec_from_info(info, "totalDebt")
    total_assets_dec = _dec_from_info(info, "totalAssets")

    if latest_item is not None:
        cash = getattr(latest_item, "cash_and_equivalents", None)
        total_debt = getattr(latest_item, "total_debt", None)
        total_assets = getattr(latest_item, "total_assets", None)
    else:
        cash = float(cash_dec) if cash_dec is not None else None
        total_debt = float(debt_dec) if debt_dec is not None else None
        total_assets = float(total_assets_dec) if total_assets_dec is not None else None

    mc_f = float(market_cap) if market_cap is not None else None

    if cash is not None and total_debt is not None:
        net_cash = cash - total_debt
        if net_cash > 0 and mc_f and cash > 0.20 * mc_f:
            score += 3
            reasoning.append(f"War chest: net cash ${net_cash:,.0f}, cash is {cash / mc_f:.0%} of market cap")
        elif net_cash > 0:
            score += 2
            reasoning.append(f"Net cash positive (${net_cash:,.0f})")
        elif total_assets and total_debt < 0.30 * total_assets:
            score += 1
            reasoning.append("Net debt but manageable relative to assets")
        else:
            reasoning.append("Leveraged position — not antifragile")
    else:
        reasoning.append("Cash/debt data not available")

    debt_to_equity = getattr(latest_metrics, "debt_to_equity", None) if latest_metrics else None
    if debt_to_equity is None and info.get("debtToEquity") is not None:
        debt_to_equity = safe_float(info.get("debtToEquity"))
    if debt_to_equity is not None:
        if debt_to_equity < 0.3:
            score += 2
            reasoning.append(f"Taleb-approved low leverage (D/E {debt_to_equity:.2f})")
        elif debt_to_equity < 0.7:
            score += 1
            reasoning.append(f"Moderate leverage (D/E {debt_to_equity:.2f})")
        else:
            reasoning.append(f"High leverage (D/E {debt_to_equity:.2f}) — fragile")
    else:
        reasoning.append("Debt-to-equity data not available")

    op_margins = [m.operating_margin for m in metrics if getattr(m, "operating_margin", None) is not None]
    if len(op_margins) >= 3:
        mean_margin = sum(op_margins) / len(op_margins)
        variance = sum((m - mean_margin) ** 2 for m in op_margins) / len(op_margins)
        std_margin = variance**0.5
        cv = std_margin / abs(mean_margin) if mean_margin != 0 else float("inf")

        if cv < 0.15 and mean_margin > 0.15:
            score += 3
            reasoning.append(f"Stable high margins (avg {mean_margin:.1%}, CV {cv:.2f}) — antifragile pricing power")
        elif cv < 0.30 and mean_margin > 0.10:
            score += 2
            reasoning.append(f"Reasonable margin stability (avg {mean_margin:.1%}, CV {cv:.2f})")
        elif cv < 0.30:
            score += 1
            reasoning.append(f"Margins somewhat stable (CV {cv:.2f}) but low (avg {mean_margin:.1%})")
        else:
            reasoning.append(f"Volatile margins (CV {cv:.2f}) — fragile pricing power")
    else:
        reasoning.append("Insufficient margin history for stability analysis")

    fcf_values = [getattr(item, "free_cash_flow", None) for item in line_items] if line_items else []
    fcf_values = [v for v in fcf_values if v is not None]
    if fcf_values:
        positive_count = sum(1 for v in fcf_values if v > 0)
        if positive_count == len(fcf_values):
            score += 2
            reasoning.append(f"Consistent FCF generation ({positive_count}/{len(fcf_values)} periods positive)")
        elif positive_count > len(fcf_values) / 2:
            score += 1
            reasoning.append(f"Majority positive FCF ({positive_count}/{len(fcf_values)} periods)")
        else:
            reasoning.append(f"Inconsistent FCF ({positive_count}/{len(fcf_values)} periods positive)")
    else:
        reasoning.append("FCF data not available")

    return {"score": score, "max_score": 10, "details": "; ".join(reasoning)}


def analyze_convexity(
    info: dict,
    metrics: list,
    line_items: list,
    prices_df: pd.DataFrame,
    market_cap: Decimal | None,
) -> dict[str, Any]:
    """Convexity using yfinance-derived line items + prices."""
    if not metrics and not line_items and prices_df.empty:
        return {"score": 0, "max_score": 10, "details": "Insufficient data for convexity analysis"}

    score = 0
    reasoning = []
    latest_item = line_items[0] if line_items else None

    rd = getattr(latest_item, "research_and_development", None) if latest_item else None
    revenue = getattr(latest_item, "revenue", None) if latest_item else None
    if revenue is None and info.get("totalRevenue") is not None:
        revenue = safe_float(info.get("totalRevenue"))

    if rd is not None and revenue and revenue > 0:
        rd_ratio = abs(rd) / revenue
        if rd_ratio > 0.15:
            score += 3
            reasoning.append(f"Significant embedded optionality via R&D ({rd_ratio:.1%} of revenue)")
        elif rd_ratio > 0.08:
            score += 2
            reasoning.append(f"Meaningful R&D investment ({rd_ratio:.1%} of revenue)")
        elif rd_ratio > 0.03:
            score += 1
            reasoning.append(f"Modest R&D ({rd_ratio:.1%} of revenue)")
        else:
            reasoning.append(f"Minimal R&D ({rd_ratio:.1%} of revenue)")
    else:
        reasoning.append("R&D data not available — no penalty for non-R&D sectors")

    if not prices_df.empty and len(prices_df) >= 20:
        returns = prices_df["close"].pct_change().dropna()
        upside = returns[returns > 0]
        downside = returns[returns < 0]

        if len(upside) > 10 and len(downside) > 10:
            avg_up = upside.mean()
            avg_down = abs(downside.mean())
            up_down_ratio = avg_up / avg_down if avg_down > 0 else 1.0

            if up_down_ratio > 1.3:
                score += 2
                reasoning.append(f"Convex return profile (up/down ratio {up_down_ratio:.2f})")
            elif up_down_ratio > 1.0:
                score += 1
                reasoning.append(f"Slight positive asymmetry (up/down ratio {up_down_ratio:.2f})")
            else:
                reasoning.append(f"Concave returns (up/down ratio {up_down_ratio:.2f}) — unfavorable")
        else:
            reasoning.append("Insufficient return data for asymmetry analysis")
    else:
        reasoning.append("Insufficient price data for return asymmetry analysis")

    cash = getattr(latest_item, "cash_and_equivalents", None) if latest_item else None
    if cash is None and info.get("totalCash") is not None:
        cash = safe_float(info.get("totalCash"))
    mc_f = float(market_cap) if market_cap is not None else None
    if cash is not None and mc_f and mc_f > 0:
        cash_ratio = cash / mc_f
        if cash_ratio > 0.30:
            score += 3
            reasoning.append(f"Cash is a call option on future opportunities ({cash_ratio:.0%} of market cap)")
        elif cash_ratio > 0.15:
            score += 2
            reasoning.append(f"Strong cash position ({cash_ratio:.0%} of market cap)")
        elif cash_ratio > 0.05:
            score += 1
            reasoning.append(f"Moderate cash buffer ({cash_ratio:.0%} of market cap)")
        else:
            reasoning.append(f"Low cash relative to market cap ({cash_ratio:.0%})")
    else:
        reasoning.append("Cash/market cap data not available")

    latest_metrics = metrics[0] if metrics else None
    fcf_yield = None
    if latest_item and mc_f and mc_f > 0:
        fcf = getattr(latest_item, "free_cash_flow", None)
        if fcf is not None:
            fcf_yield = fcf / mc_f
    if fcf_yield is None and latest_metrics:
        fcf_yield = getattr(latest_metrics, "free_cash_flow_yield", None)
    if fcf_yield is None and info.get("freeCashflow") is not None and mc_f and mc_f > 0:
        fcf_yield = safe_float(info.get("freeCashflow")) / mc_f

    if fcf_yield is not None:
        if fcf_yield > 0.10:
            score += 2
            reasoning.append(f"High FCF yield ({fcf_yield:.1%}) provides margin for convex bet")
        elif fcf_yield > 0.05:
            score += 1
            reasoning.append(f"Decent FCF yield ({fcf_yield:.1%})")
        else:
            reasoning.append(f"Low FCF yield ({fcf_yield:.1%})")
    else:
        reasoning.append("FCF yield data not available")

    return {"score": score, "max_score": 10, "details": "; ".join(reasoning)}


def _fin_row(df: pd.DataFrame, *names: str) -> Optional[str]:
    if df is None or df.empty:
        return None
    for n in names:
        for idx in df.index:
            if str(idx).strip().lower() == n.lower():
                return str(idx)
            if n.lower() in str(idx).lower():
                return str(idx)
    return None


def _build_period_snapshots(
    financials: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    info: dict,
) -> tuple[list[Any], list[Any]]:
    """Build metrics and line_items as lists of SimpleNamespace (newest first)."""
    metrics: list[Any] = []
    line_items: list[Any] = []
    if financials is None or financials.empty:
        m0 = SimpleNamespace(
            debt_to_equity=safe_float(info.get("debtToEquity")) if info.get("debtToEquity") is not None else None,
            interest_coverage=None,
            earnings_growth=None,
            net_margin=safe_float(info.get("profitMargins")) if info.get("profitMargins") is not None else None,
            revenue=safe_float(info.get("totalRevenue")) if info.get("totalRevenue") is not None else None,
            operating_margin=safe_float(info.get("operatingMargins")) if info.get("operatingMargins") is not None else None,
            return_on_invested_capital=safe_float(info.get("returnOnEquity")) if info.get("returnOnEquity") is not None else None,
            price_to_earnings_ratio=safe_float(info.get("trailingPE")) if info.get("trailingPE") is not None else None,
            free_cash_flow=None,
            beta=safe_float(info.get("beta")),
            ebit=None,
            interest_expense=None,
        )
        li0 = SimpleNamespace(
            cash_and_equivalents=float(_dec_from_info(info, "totalCash") or 0) or None,
            total_debt=float(_dec_from_info(info, "totalDebt") or 0) or None,
            total_assets=float(_dec_from_info(info, "totalAssets") or 0) or None,
            revenue=m0.revenue,
            research_and_development=None,
            free_cash_flow=safe_float(info.get("freeCashflow")),
            outstanding_shares=safe_float(info.get("sharesOutstanding")),
            net_income=safe_float(info.get("netIncomeToCommon")) if info.get("netIncomeToCommon") else None,
        )
        return [m0], [li0]

    cols = list(financials.columns)
    rev_key = _fin_row(financials, "Total Revenue", "Operating Revenue")
    op_key = _fin_row(financials, "Operating Income")
    ni_key = _fin_row(financials, "Net Income")
    rd_key = _fin_row(financials, "Research And Development", "Research Development")

    ni_series: list[float] = []
    for c in cols:
        if ni_key:
            v = financials.loc[ni_key, c]
            ni_series.append(safe_float(v, float("nan")))
    eg_list: list[Optional[float]] = []
    for i in range(len(ni_series)):
        if i + 1 < len(ni_series) and ni_series[i + 1] not in (0, float("nan")) and not np.isnan(ni_series[i + 1]):
            eg_list.append((ni_series[i] - ni_series[i + 1]) / abs(ni_series[i + 1]))
        else:
            eg_list.append(None)

    for j, c in enumerate(cols):
        rev = safe_float(financials.loc[rev_key, c]) if rev_key else None
        op_inc = safe_float(financials.loc[op_key, c]) if op_key else None
        ni = ni_series[j] if j < len(ni_series) else None
        om = (op_inc / rev) if (rev and rev != 0 and op_inc is not None) else None
        eg = eg_list[j] if j < len(eg_list) else None
        rdv = safe_float(financials.loc[rd_key, c]) if rd_key else None
        fcf_v = None
        if cashflow is not None and not cashflow.empty:
            fcf_k = _fin_row(cashflow, "Free Cash Flow")
            if fcf_k and c in cashflow.columns:
                fcf_v = safe_float(cashflow.loc[fcf_k, c], float("nan"))
                if np.isnan(fcf_v):
                    fcf_v = None
        m = SimpleNamespace(
            debt_to_equity=safe_float(info.get("debtToEquity")) if j == 0 and info.get("debtToEquity") is not None else None,
            interest_coverage=None,
            earnings_growth=eg,
            net_margin=(ni / rev) if (rev and rev != 0 and ni is not None) else None,
            revenue=rev,
            operating_margin=om,
            return_on_invested_capital=safe_float(info.get("returnOnEquity")) if j == 0 else None,
            price_to_earnings_ratio=safe_float(info.get("trailingPE")) if j == 0 else None,
            free_cash_flow=fcf_v,
            beta=safe_float(info.get("beta")) if j == 0 else None,
            ebit=op_inc,
            interest_expense=None,
        )
        if j == 0 and op_inc is not None:
            int_key = _fin_row(financials, "Interest Expense", "Interest And Debt Expense")
            if int_key:
                inter = safe_float(financials.loc[int_key, c])
                if inter and abs(inter) > 0:
                    m = SimpleNamespace(**{**m.__dict__, "interest_coverage": op_inc / abs(inter)})
        metrics.append(m)
        li = SimpleNamespace(
            cash_and_equivalents=float(_dec_from_info(info, "totalCash") or 0) or None if j == 0 else None,
            total_debt=float(_dec_from_info(info, "totalDebt") or 0) or None if j == 0 else None,
            total_assets=float(_dec_from_info(info, "totalAssets") or 0) or None if j == 0 else None,
            revenue=rev,
            research_and_development=rdv,
            free_cash_flow=fcf_v,
            outstanding_shares=safe_float(info.get("sharesOutstanding")) if j == 0 else None,
            net_income=ni,
        )
        line_items.append(li)

    return metrics, line_items


@dataclass
class TalebAuditResult:
    ticker: str
    score: int
    max_score: int
    normalized_score: float
    verdict: str
    details: dict[str, str]
    analysis_date: str


def audit_ticker(ticker: str, prices_df: pd.DataFrame, analysis_date: str) -> TalebAuditResult:
    """Run all Taleb sub-analyses. Never raises."""
    neutral = TalebAuditResult(
        ticker=ticker,
        score=0,
        max_score=1,
        normalized_score=0.5,
        verdict="NEUTRAL",
        details={"error": "audit failed"},
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

        mc_dec = _dec_from_info(info, "marketCap")
        metrics, line_items = _build_period_snapshots(fin, cf, info)

        tail_risk_analysis = analyze_tail_risk(prices_df)
        antifragility_analysis = analyze_antifragility(info, metrics, line_items, mc_dec)
        convexity_analysis = analyze_convexity(info, metrics, line_items, prices_df, mc_dec)
        fragility_analysis = analyze_fragility(metrics, line_items)
        skin_in_game_analysis = analyze_skin_in_game([])
        volatility_regime_analysis = analyze_volatility_regime(prices_df)
        black_swan_analysis = analyze_black_swan_sentinel([], prices_df)

        total_score = (
            tail_risk_analysis["score"]
            + antifragility_analysis["score"]
            + convexity_analysis["score"]
            + fragility_analysis["score"]
            + skin_in_game_analysis["score"]
            + volatility_regime_analysis["score"]
            + black_swan_analysis["score"]
        )
        max_possible_score = (
            tail_risk_analysis["max_score"]
            + antifragility_analysis["max_score"]
            + convexity_analysis["max_score"]
            + fragility_analysis["max_score"]
            + skin_in_game_analysis["max_score"]
            + volatility_regime_analysis["max_score"]
            + black_swan_analysis["max_score"]
        )
        norm = float(total_score) / float(max_possible_score) if max_possible_score else 0.5
        if norm >= 0.65:
            verdict = "ANTIFRAGILE"
        elif norm <= 0.35:
            verdict = "FRAGILE"
        else:
            verdict = "NEUTRAL"

        details = {
            "tail_risk": str(tail_risk_analysis.get("details", "")),
            "antifragility": str(antifragility_analysis.get("details", "")),
            "convexity": str(convexity_analysis.get("details", "")),
            "fragility": str(fragility_analysis.get("details", "")),
            "skin_in_game": str(skin_in_game_analysis.get("details", "")),
            "volatility_regime": str(volatility_regime_analysis.get("details", "")),
            "black_swan": str(black_swan_analysis.get("details", "")),
        }
        return TalebAuditResult(
            ticker=ticker,
            score=int(total_score),
            max_score=int(max_possible_score),
            normalized_score=norm,
            verdict=verdict,
            details=details,
            analysis_date=analysis_date,
        )
    except Exception as exc:
        neutral.details = {"error": str(exc)}
        return neutral
