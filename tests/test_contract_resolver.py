"""Unit tests for src.data.contract_resolver (mocked IB; no TWS)."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from ib_insync import Future, Option, Stock

from src.data.contract_resolver import resolve

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo_temp_dir() -> Path:
    path = ROOT / "outputs" / f"_contract_resolver_test_{os.getpid()}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        for child in path.glob("*"):
            child.unlink(missing_ok=True)
        path.rmdir()

@pytest.fixture
def instruments_path(repo_temp_dir: Path) -> Path:
    cfg = {
        "equities": {"use_watchlist": False, "exchange": "SMART", "currency": "USD"},
        "futures": {
            "MNQ": {
                "description": "Micro E-mini NASDAQ-100 Futures",
                "exchange": "CME",
                "currency": "USD",
                "multiplier": 2,
                "front_month_offset": 1,
                "roll_warning_dte": 5,
            }
        },
        "options": {
            "SMH": {
                "description": "SMH options",
                "exchange": "SMART",
                "currency": "USD",
                "right": ["C", "P"],
                "expiry_dte_target": 30,
                "strike_atm_offset": 0,
            }
        },
        "allocation_limits": {"max_futures_pct": 0.2, "max_options_pct": 0.1},
    }
    p = repo_temp_dir / "instruments.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


@pytest.fixture
def instruments_with_watchlist(repo_temp_dir: Path) -> tuple[Path, Path]:
    inst = repo_temp_dir / "instruments.yaml"
    inst.write_text(
        yaml.dump(
            {
                "equities": {"use_watchlist": True, "exchange": "SMART", "currency": "USD"},
                "futures": {},
                "options": {},
            }
        ),
        encoding="utf-8",
    )
    dc = repo_temp_dir / "data_config.yaml"
    dc.write_text(
        yaml.dump({"universe_selection": {"watchlist": ["AMD", "NVDA"]}}),
        encoding="utf-8",
    )
    return inst, dc


def test_equity_returns_stock_with_exchange_currency(instruments_path: Path) -> None:
    ib = MagicMock()

    def _qual(c: Stock) -> list:
        assert c.symbol == "AAPL"
        assert c.exchange == "SMART"
        assert c.currency == "USD"
        return [c]

    ib.qualifyContracts.side_effect = _qual
    out = resolve("AAPL", "equity", ib, config_path=instruments_path)
    assert isinstance(out, Stock)
    assert out.symbol == "AAPL"
    assert out.exchange == "SMART"
    assert out.currency == "USD"
    ib.qualifyContracts.assert_called_once()


def test_future_picks_front_month_and_warns_low_dte(
    instruments_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ib = MagicMock()
    today = dt.date.today()

    def _mk_detail(exp_yyyymmdd: str) -> MagicMock:
        d = MagicMock()
        c = Future(
            symbol="MNQ",
            lastTradeDateOrContractMonth=exp_yyyymmdd,
            exchange="CME",
            currency="USD",
        )
        d.contract = c
        return d

    # Nearest expiry has low DTE -> roll warning after selection
    exp_near = (today + dt.timedelta(days=3)).strftime("%Y%m%d")
    exp_far = (today + dt.timedelta(days=90)).strftime("%Y%m%d")
    details = [_mk_detail(exp_near), _mk_detail(exp_far)]
    ib.reqContractDetails.return_value = details

    qualified = Future(
        symbol="MNQ",
        lastTradeDateOrContractMonth=exp_near,
        exchange="CME",
        currency="USD",
    )
    ib.qualifyContracts.return_value = [qualified]

    out = resolve("MNQ", "future", ib, config_path=instruments_path)
    assert isinstance(out, Future)
    assert out.lastTradeDateOrContractMonth == exp_near
    captured = capsys.readouterr().out
    assert "[CONTRACT][WARN]" in captured
    assert "MNQ" in captured
    assert "DTE" in captured


def test_option_picks_nearest_expiry_to_target(instruments_path: Path) -> None:
    ib = MagicMock()
    today = dt.date.today()
    target = today + dt.timedelta(days=30)
    exp_close = target.strftime("%Y%m%d")
    exp_far = (today + dt.timedelta(days=200)).strftime("%Y%m%d")

    def _qual(c: Stock | Option) -> list:
        if isinstance(c, Stock):
            return [c]
        return [Option("SMH", exp_close, 250.0, "C", "SMART", currency="USD")]

    ib.qualifyContracts.side_effect = _qual

    ticker = MagicMock()
    ticker.bid = 249.0
    ticker.ask = 251.0
    ticker.updateEvent = MagicMock()
    ticker.updateEvent.wait = MagicMock()
    ib.reqMktData.return_value = ticker

    def _detail(exp: str, strike: float) -> MagicMock:
        m = MagicMock()
        m.contract = Option("SMH", exp, strike, "C", "SMART", currency="USD")
        return m

    details = [
        _detail(exp_far, 240.0),
        _detail(exp_far, 260.0),
        _detail(exp_close, 248.0),
        _detail(exp_close, 250.0),
        _detail(exp_close, 252.0),
    ]
    ib.reqContractDetails.return_value = details

    out = resolve("SMH", "option", ib, config_path=instruments_path)
    assert isinstance(out, Option)
    assert out.lastTradeDateOrContractMonth == exp_close
    assert out.strike == 250.0
    assert out.right in ("C", "P")


def test_unknown_instrument_type_raises(instruments_path: Path) -> None:
    ib = MagicMock()
    with pytest.raises(ValueError, match="unrecognised instrument_type"):
        resolve("X", "swap", ib, config_path=instruments_path)


def test_future_symbol_not_in_config_raises(instruments_path: Path) -> None:
    ib = MagicMock()
    with pytest.raises(ValueError, match="not in instruments.yaml futures"):
        resolve("CL", "future", ib, config_path=instruments_path)


def test_option_symbol_not_in_config_raises(instruments_path: Path) -> None:
    ib = MagicMock()
    with pytest.raises(ValueError, match="not in instruments.yaml options"):
        resolve("QQQ", "option", ib, config_path=instruments_path)


def test_equity_symbol_not_in_watchlist_raises(
    instruments_with_watchlist: tuple[Path, Path],
) -> None:
    inst_path, _dc = instruments_with_watchlist
    ib = MagicMock()
    with pytest.raises(ValueError, match="not in data_config"):
        resolve("NOTINLIST", "equity", ib, config_path=inst_path)
