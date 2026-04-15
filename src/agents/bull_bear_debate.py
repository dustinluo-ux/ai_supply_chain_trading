"""
Deterministic advisory-only Bull vs Bear debate scorer.

This module enriches audit trails and never raises from public entry points.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

from src.agents.skeptic_gate import _audit_bear, fetch_bear_fundamentals


@dataclass
class TickerDebate:
    ticker: str
    bull_score: float
    bear_score: float
    net_score: float
    verdict: str


@dataclass
class DebateResult:
    per_ticker: dict[str, TickerDebate]
    overall_bias: float
    as_of_date: str
    tickers_screened: int


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_bull_score(info: dict[str, object]) -> float:
    score = 0.0

    revenue_growth = _safe_float(info.get("revenueGrowth"))
    if revenue_growth is not None and revenue_growth > 0.10:
        score += 0.2

    earnings_growth = _safe_float(info.get("earningsGrowth"))
    if earnings_growth is not None and earnings_growth > 0.05:
        score += 0.2

    return_on_equity = _safe_float(info.get("returnOnEquity"))
    if return_on_equity is not None and return_on_equity > 0.10:
        score += 0.2

    gross_margins = _safe_float(info.get("grossMargins"))
    if gross_margins is not None and gross_margins > 0.30:
        score += 0.2

    free_cashflow = _safe_float(info.get("freeCashflow"))
    if free_cashflow is not None and free_cashflow > 0.0:
        score += 0.2

    return score


def _verdict_from_net(net_score: float) -> str:
    if net_score > 0.2:
        return "BULLISH"
    if net_score < -0.2:
        return "BEARISH"
    return "NEUTRAL"


def _score_ticker(ticker: str) -> TickerDebate:
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        bull_score = _compute_bull_score(info)

        bear_findings = fetch_bear_fundamentals(ticker)
        bear_findings = _audit_bear(bear_findings)
        bear_score = float(len(bear_findings.flags)) / 5.0
    except Exception:
        bull_score = 0.5
        bear_score = 0.0

    net_score = bull_score - bear_score
    return TickerDebate(
        ticker=ticker,
        bull_score=bull_score,
        bear_score=bear_score,
        net_score=net_score,
        verdict=_verdict_from_net(net_score),
    )


def run_debate(weights: dict[str, float], as_of_date: str) -> DebateResult:
    """
    Screen all tickers with position weight > 0.05 and compute advisory debate scores.

    Never raises; on unexpected errors returns a neutral empty result.
    """
    try:
        screened = sorted(
            {
                str(ticker)
                for ticker, weight in (weights or {}).items()
                if _safe_float(weight) is not None and float(weight) > 0.05
            }
        )
        per_ticker: dict[str, TickerDebate] = {
            ticker: _score_ticker(ticker) for ticker in screened
        }
        overall_bias = fmean([d.net_score for d in per_ticker.values()]) if per_ticker else 0.0
        return DebateResult(
            per_ticker=per_ticker,
            overall_bias=float(overall_bias),
            as_of_date=str(as_of_date),
            tickers_screened=len(per_ticker),
        )
    except Exception:
        return DebateResult(
            per_ticker={},
            overall_bias=0.0,
            as_of_date=str(as_of_date),
            tickers_screened=0,
        )
