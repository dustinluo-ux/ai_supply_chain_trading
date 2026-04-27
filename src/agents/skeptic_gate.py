"""
Skeptic gate: concentrated positions screened with bear-style fundamentals (yfinance only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

WEIGHT_TRIGGER = Decimal("0.15")
_DISTRESS_FLAGS = {"DISTRESSED_DEBT", "DISTRESSED_LIQUIDITY", "DISTRESSED_DRAWDOWN"}


@dataclass
class BearFindings:
    ticker: str
    pe_ratio: Optional[float] = None  # >35 = valuation overreach
    pb_ratio: Optional[float] = None  # >5 = valuation overreach
    debt_to_equity: Optional[float] = None  # >2 = distressed
    current_ratio: Optional[float] = None  # <1 = distressed
    drawdown_52w: Optional[float] = None  # < -0.40 = distressed
    flags: list[str] = field(default_factory=list)


@dataclass
class GateResult:
    verdict: str  # "PASS" | "FAIL" | "SKIP"
    triggered_tickers: list[str]
    bear_findings: list[BearFindings]
    reason: str
    fatal_tickers: list[str] = field(default_factory=list)


def _safe_float(x: object) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch_bear_fundamentals(ticker: str) -> BearFindings:
    """Pull key fields from yfinance Ticker.info. Missing fields → None. Never raises."""
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        pe = _safe_float(info.get("trailingPE"))
        pb = _safe_float(info.get("priceToBook"))
        de = _safe_float(info.get("debtToEquity"))
        cr = _safe_float(info.get("currentRatio"))
        cur_px = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        hi52 = _safe_float(info.get("fiftyTwoWeekHigh"))
        dd: Optional[float] = None
        if cur_px is not None and hi52 is not None and hi52 > 0:
            dd = (cur_px / hi52) - 1.0
        return BearFindings(
            ticker=ticker,
            pe_ratio=pe,
            pb_ratio=pb,
            debt_to_equity=de,
            current_ratio=cr,
            drawdown_52w=dd,
            flags=[],
        )
    except Exception:
        return BearFindings(ticker=ticker, flags=[])


def _audit_bear(findings: BearFindings) -> BearFindings:
    """Populate findings.flags per threshold. Returns mutated object."""
    flags = findings.flags
    if findings.pe_ratio is not None and findings.pe_ratio > 35:
        flags.append("VALUATION_PE")
    if findings.pb_ratio is not None and findings.pb_ratio > 5:
        flags.append("VALUATION_PB")
    if findings.debt_to_equity is not None and findings.debt_to_equity > 2:
        flags.append("DISTRESSED_DEBT")
    if findings.current_ratio is not None and findings.current_ratio < 1:
        flags.append("DISTRESSED_LIQUIDITY")
    if findings.drawdown_52w is not None and findings.drawdown_52w < -0.40:
        flags.append("DISTRESSED_DRAWDOWN")
    findings.flags = flags
    return findings


def run_gate(weights: dict[str, float], ticker_list: list[str]) -> GateResult:
    """
    Screen positions with weight > WEIGHT_TRIGGER. FAIL if any such ticker has ≥2 bear flags.
    Never raises.
    """
    try:
        triggered: list[str] = []
        for t, w in (weights or {}).items():
            try:
                if Decimal(str(w)) > WEIGHT_TRIGGER:
                    triggered.append(str(t))
            except Exception:
                continue
        triggered = sorted(set(triggered))

        if not triggered:
            return GateResult(
                verdict="SKIP",
                triggered_tickers=[],
                bear_findings=[],
                reason="no position above 15% threshold",
                fatal_tickers=[],
            )

        bear_findings: list[BearFindings] = []
        fatal_tickers: list[str] = []
        for t in triggered:
            fnd = fetch_bear_fundamentals(t)
            _audit_bear(fnd)
            bear_findings.append(fnd)
            has_distress = any(f in _DISTRESS_FLAGS for f in fnd.flags)
            if len(fnd.flags) >= 2 and has_distress:
                fatal_tickers.append(t)

        if fatal_tickers:
            return GateResult(
                verdict="FAIL",
                triggered_tickers=triggered,
                bear_findings=bear_findings,
                reason=f">=2 bear flags on concentrated tickers: {', '.join(fatal_tickers)}",
                fatal_tickers=sorted(set(fatal_tickers)),
            )
        return GateResult(
            verdict="PASS",
            triggered_tickers=triggered,
            bear_findings=bear_findings,
            reason="no fatal bear flags on concentrated positions",
            fatal_tickers=[],
        )
    except Exception as exc:
        return GateResult(
            verdict="SKIP",
            triggered_tickers=[],
            bear_findings=[],
            reason=f"gate internal skip: {exc}",
            fatal_tickers=[],
        )
