"""Unit tests for ibkr_live_provider (mocked IB; no live TWS)."""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _ensure_ib_insync_stub() -> None:
    """Allow importing ibkr_live_provider when ib_insync is not installed (e.g. CI bare Python)."""
    if "ib_insync" in sys.modules:
        return
    mod = types.ModuleType("ib_insync")

    class _Util:
        @staticmethod
        def isNan(x):
            if x is None:
                return True
            try:
                return x != x
            except Exception:
                return True

    class IB:
        """Stub class; tests patch ``src.data.ibkr_live_provider.IB``."""

    mod.IB = IB
    mod.util = _Util()
    sys.modules["ib_insync"] = mod


try:
    import ib_insync  # noqa: F401
except ImportError:
    _ensure_ib_insync_stub()

from src.data.ibkr_live_provider import (
    connect,
    get_account_summary,
    get_live_prices,
    get_positions,
)


class TestConnect(unittest.TestCase):
    @patch("src.data.ibkr_live_provider.IB")
    def test_connect_raises_connection_error_on_failure(self, mock_ib_cls):
        mock_inst = MagicMock()
        mock_ib_cls.return_value = mock_inst
        mock_inst.connect.side_effect = OSError("Connection refused")
        with self.assertRaises(ConnectionError) as ctx:
            connect("127.0.0.1", 7497, 1)
        self.assertIn("Failed to connect to IBKR", str(ctx.exception))

    @patch("src.data.ibkr_live_provider.IB")
    def test_connect_raises_when_not_connected_after_connect(self, mock_ib_cls):
        mock_inst = MagicMock()
        mock_ib_cls.return_value = mock_inst
        mock_inst.connect.return_value = None
        mock_inst.isConnected.return_value = False
        with self.assertRaises(ConnectionError):
            connect("127.0.0.1", 7497, 1)


class TestGetAccountSummary(unittest.TestCase):
    def test_returns_float_fields(self):
        ib = MagicMock()

        class Row:
            def __init__(self, tag, value):
                self.tag = tag
                self.value = value
                self.currency = "USD"
                self.account = ""

        rows = [
            Row("NetLiquidation", "100001.5"),
            Row("AvailableFunds", "50000"),
            Row("MaintMarginReq", "1200.25"),
            Row("InitMarginReq", "2400"),
            Row("BuyingPower", "200000"),
            Row("GrossPositionValue", "75000"),
        ]

        def account_summary_side_effect():
            return list(rows)

        ib.accountSummary.side_effect = account_summary_side_effect
        ib.sleep = MagicMock()

        summary = get_account_summary(ib)

        ib.reqAccountSummary.assert_called_once()
        ib.cancelAccountSummary.assert_called_once()

        self.assertIsInstance(summary["net_liquidation"], float)
        self.assertEqual(summary["net_liquidation"], 100001.5)
        self.assertEqual(summary["available_funds"], 50000.0)
        self.assertEqual(summary["maint_margin_req"], 1200.25)
        self.assertEqual(summary["init_margin_req"], 2400.0)
        self.assertEqual(summary["buying_power"], 200000.0)
        self.assertEqual(summary["gross_position_value"], 75000.0)


class TestGetLivePrices(unittest.TestCase):
    @patch("src.data.ibkr_live_provider._historical_last_close")
    def test_fallback_to_historical_when_snapshot_empty(self, mock_hist):
        ib = MagicMock()
        contract = MagicMock()
        contract.symbol = "TEST"
        contract.localSymbol = ""

        ticker = MagicMock()
        ticker.last = float("nan")
        ticker.close = float("nan")
        ticker.marketPrice = MagicMock(return_value=float("nan"))
        ticker.updateEvent = MagicMock()
        ticker.updateEvent.wait = MagicMock(return_value=False)

        ib.reqMktData.return_value = ticker
        mock_hist.return_value = 42.5

        out = get_live_prices(ib, [contract])

        self.assertEqual(out, {"TEST": 42.5})
        mock_hist.assert_called_once()
        ib.cancelMktData.assert_called_once_with(contract)

    def test_excludes_failed_contract_without_raising(self):
        ib = MagicMock()
        good = MagicMock(symbol="OK", localSymbol="")
        bad = MagicMock(symbol="BAD", localSymbol="")

        good_t = MagicMock()
        good_t.last = 10.0
        good_t.close = float("nan")
        good_t.marketPrice = MagicMock(return_value=float("nan"))
        good_t.updateEvent = MagicMock()
        good_t.updateEvent.wait = MagicMock(return_value=True)

        def req_mkt_data(contract, *_args, **_kwargs):
            if contract.symbol == "BAD":
                raise ValueError("invalid contract")
            return good_t

        ib.reqMktData.side_effect = req_mkt_data

        out = get_live_prices(ib, [good, bad])

        self.assertEqual(out, {"OK": 10.0})


class TestGetPositions(unittest.TestCase):
    def test_returns_list_of_dicts_with_floats(self):
        ib = MagicMock()
        ib.waitOnUpdate = MagicMock(return_value=True)

        c = MagicMock()
        c.symbol = "XYZ"
        c.localSymbol = ""
        c.secType = "STK"

        pos = MagicMock()
        pos.contract = c
        pos.position = 10
        pos.avgCost = 50.5
        ib.positions.return_value = [pos]

        ticker = MagicMock()
        ticker.last = 55.0
        ticker.close = float("nan")
        ticker.marketPrice = MagicMock(return_value=float("nan"))
        ticker.updateEvent = MagicMock()
        ticker.updateEvent.wait = MagicMock(return_value=True)
        ib.reqMktData.return_value = ticker

        rows = get_positions(ib)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "XYZ")
        self.assertEqual(rows[0]["position"], 10.0)
        self.assertEqual(rows[0]["avg_cost"], 50.5)
        self.assertEqual(rows[0]["asset_class"], "STK")
        self.assertEqual(rows[0]["market_value"], 10.0 * 55.0)


if __name__ == "__main__":
    unittest.main()
