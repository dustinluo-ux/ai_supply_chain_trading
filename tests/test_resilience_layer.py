"""Tests for src.data.resilience_layer (mocked vendors)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from src.core.state import PipelineState, VendorEvent
from src.data import resilience_layer


def _five_row_ohlcv() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "open": [10.0, 10.5, 11.0, 11.2, 11.3],
            "high": [10.6, 11.0, 11.5, 11.6, 11.7],
            "low": [9.9, 10.2, 10.8, 11.0, 11.1],
            "close": [10.4, 10.9, 11.3, 11.4, 11.5],
            "volume": [1e6, 1.1e6, 1.2e6, 1.0e6, 9e5],
        },
        index=idx,
    )


def test_vendor_chain_falls_through_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def boom(*_a, **_k):
        called.append("csv")
        raise RuntimeError("disk full")

    def yf_ok(*_a, **_k):
        called.append("yfinance")
        return _five_row_ohlcv()

    monkeypatch.setattr(resilience_layer, "_try_csv", boom)
    monkeypatch.setattr(resilience_layer, "_try_yfinance", yf_ok)
    monkeypatch.setattr(resilience_layer, "_try_marketaux", lambda *a, **k: None)
    monkeypatch.setattr(resilience_layer, "_try_alphavantage", lambda *a, **k: None)

    out = resilience_layer.get_prices(
        ["ZZZ"],
        "2024-01-01",
        "2024-01-10",
        Path("/tmp"),
        marketaux_api_key=None,
        alphavantage_api_key=None,
    )
    assert "csv" in called and "yfinance" in called
    assert "ZZZ" in out
    assert isinstance(out["ZZZ"]["close"].iloc[0], Decimal)


def test_close_column_is_decimal_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resilience_layer, "_try_csv", lambda *a, **k: None)
    monkeypatch.setattr(resilience_layer, "_try_marketaux", lambda *a, **k: None)
    monkeypatch.setattr(resilience_layer, "_try_yfinance", lambda *a, **k: _five_row_ohlcv())
    monkeypatch.setattr(resilience_layer, "_try_alphavantage", lambda *a, **k: None)

    out = resilience_layer.get_prices(
        ["X"],
        "2024-01-01",
        "2024-01-07",
        Path("/tmp"),
    )
    assert isinstance(out["X"]["close"].iloc[0], Decimal)
    assert isinstance(out["X"]["volume"].iloc[0], (float, int))


def test_pipeline_state_to_dict_json_serializable() -> None:
    st = PipelineState(
        run_id="rid",
        started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        tickers_requested=["AAPL"],
        tickers_loaded=["AAPL"],
        signal_scores={"AAPL": Decimal("0.12345678901234567890")},
        regime="BULL",
        nav=Decimal("100000.50"),
        target_weights={"AAPL": Decimal("1.0")},
        warnings=["w"],
        errors=[],
    )
    st.vendor_events.append(
        VendorEvent("AAPL", "csv", True, None, 1.5),
    )
    d = st.to_dict()
    json.dumps(d)
    assert d["signal_scores"]["AAPL"] == "0.12345678901234567890"
    assert d["nav"] == "100000.50"


def test_save_atomic_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    st = PipelineState(
        run_id="r1",
        started_at=datetime.now(timezone.utc),
        tickers_requested=["NVDA"],
    )
    st.save(p)
    assert p.exists()
    assert p.read_text(encoding="utf-8").strip()
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["run_id"] == "r1"


def test_get_prices_records_vendor_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resilience_layer, "_try_csv", lambda *a, **k: None)
    monkeypatch.setattr(resilience_layer, "_try_marketaux", lambda *a, **k: None)
    monkeypatch.setattr(resilience_layer, "_try_yfinance", lambda *a, **k: _five_row_ohlcv())
    monkeypatch.setattr(resilience_layer, "_try_alphavantage", lambda *a, **k: None)

    st = PipelineState(
        run_id="x",
        started_at=datetime.now(timezone.utc),
        tickers_requested=["X"],
    )
    resilience_layer.get_prices(
        ["X"],
        "2024-01-01",
        "2024-01-07",
        Path("/tmp"),
        state=st,
    )
    assert len(st.vendor_events) >= 2
    assert st.fallback_count() >= 1
