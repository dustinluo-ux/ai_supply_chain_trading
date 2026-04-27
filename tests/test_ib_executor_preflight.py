from types import SimpleNamespace

import pytest

from src.execution.ib_executor import IBExecutor


class FakeProvider:
    def __init__(self, connected=True):
        self.ib = SimpleNamespace(isConnected=lambda: connected)


class FakeIB:
    def __init__(self):
        self.orders = []

    def isConnected(self):
        return True

    def placeOrder(self, contract, order):
        self.orders.append((contract, order))
        return SimpleNamespace(
            order=SimpleNamespace(orderId=123),
            orderStatus=SimpleNamespace(
                status="Submitted", filled=0, avgFillPrice=0.0
            ),
        )


class FakeProviderWithOrders:
    def __init__(self):
        self.ib = FakeIB()


def test_validate_order_request_paper_account_accepts_valid_market_order():
    executor = IBExecutor(FakeProvider(), "DUM123456")

    executor.validate_order_request("NVDA", 10, "BUY", "MARKET")


def test_validate_order_request_live_account_requires_explicit_env(monkeypatch):
    monkeypatch.delenv("ALLOW_LIVE_IBKR", raising=False)
    executor = IBExecutor(FakeProvider(), "U999999")

    with pytest.raises(RuntimeError, match="live account blocked"):
        executor.validate_order_request("NVDA", 10, "BUY", "MARKET")


def test_validate_order_request_rejects_quantity_above_configured_cap():
    class CappedExecutor(IBExecutor):
        def _load_execution_config(self):
            return {"max_order_quantity": 5}

    executor = CappedExecutor(FakeProvider(), "DUM123456")

    with pytest.raises(RuntimeError, match="exceeds max"):
        executor.validate_order_request("NVDA", 6, "BUY", "MARKET")


def test_validate_order_request_rejects_disconnected_broker():
    executor = IBExecutor(FakeProvider(connected=False), "DUM123456")

    with pytest.raises(RuntimeError, match="not connected"):
        executor.validate_order_request("NVDA", 10, "BUY", "MARKET")


def test_submit_contract_order_uses_common_preflight_and_sets_account_ref():
    provider = FakeProviderWithOrders()
    executor = IBExecutor(provider, "DUM123456")
    contract = SimpleNamespace(symbol="MNQ")

    result = executor.submit_contract_order(
        contract,
        "MNQ",
        2,
        "BUY",
        order_type="MARKET",
        order_comment="weekly_rebalance_overlay",
    )

    assert result["order_id"] == "123"
    assert result["ticker"] == "MNQ"
    assert len(provider.ib.orders) == 1
    placed_contract, placed_order = provider.ib.orders[0]
    assert placed_contract is contract
    assert placed_order.account == "DUM123456"
    assert placed_order.orderRef == "weekly_rebalance_overlay"
