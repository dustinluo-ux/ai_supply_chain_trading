"""Tests for src.agents.skeptic_gate (no live yfinance)."""
from __future__ import annotations

from unittest.mock import patch

from src.agents import skeptic_gate
from src.agents.skeptic_gate import BearFindings, _audit_bear, fetch_bear_fundamentals, run_gate


def test_skip_when_all_weights_at_or_below_trigger() -> None:
    n = 10
    w = {f"T{i}": 1.0 / n for i in range(n)}
    r = run_gate(w, list(w.keys()))
    assert r.verdict == "SKIP"
    assert r.triggered_tickers == []
    assert "15%" in r.reason or "threshold" in r.reason.lower()


def test_pass_one_flag_on_concentrated_weight() -> None:
    def _fetch(t: str) -> BearFindings:
        return BearFindings(ticker=t, pe_ratio=36.0, flags=[])

    with patch.object(skeptic_gate, "fetch_bear_fundamentals", side_effect=_fetch):
        r = run_gate({"AAA": 0.20}, ["AAA"])
    assert r.verdict == "PASS"
    assert "AAA" in r.triggered_tickers
    assert r.fatal_tickers == []


def test_fail_two_flags_fatal_ticker() -> None:
    # FAIL requires >=2 flags AND at least one distress flag
    def _fetch(t: str) -> BearFindings:
        return BearFindings(
            ticker=t,
            pe_ratio=40.0,        # VALUATION_PE flag
            pb_ratio=6.0,         # VALUATION_PB flag
            debt_to_equity=3.0,   # DISTRESSED_DEBT flag (distress required for FAIL)
            flags=[],
        )

    with patch.object(skeptic_gate, "fetch_bear_fundamentals", side_effect=_fetch):
        r = run_gate({"ZZZ": 0.20}, ["ZZZ"])
    assert r.verdict == "FAIL"
    assert "ZZZ" in r.fatal_tickers
    assert len(r.bear_findings) == 1
    assert len(r.bear_findings[0].flags) >= 2


def test_audit_bear_two_flags_from_pe_pb() -> None:
    f = BearFindings(
        ticker="X",
        pe_ratio=40.0,
        pb_ratio=6.0,
        debt_to_equity=1.0,
        current_ratio=1.5,
        drawdown_52w=-0.10,
        flags=[],
    )
    _audit_bear(f)
    assert len(f.flags) == 2
    assert "VALUATION_PE" in f.flags
    assert "VALUATION_PB" in f.flags


def test_fetch_bear_fundamentals_yfinance_raises_returns_empty_findings() -> None:
    with patch("yfinance.Ticker", side_effect=RuntimeError("no network")):
        out = fetch_bear_fundamentals("IBM")
    assert out.ticker == "IBM"
    assert out.pe_ratio is None
    assert out.pb_ratio is None
    assert out.debt_to_equity is None
    assert out.current_ratio is None
    assert out.drawdown_52w is None
    assert out.flags == []
