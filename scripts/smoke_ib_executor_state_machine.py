"""
Smoke test for IBExecutor + IBKRStateMachine: submit_order guarded by can_submit_orders.
Run from project root. Spec: docs/RESILIENCE_SPEC.md (state machine gates order submission).
"""
from __future__ import annotations

# 1. Import IBExecutor from src.execution.ib_executor — no import error
from src.execution.ib_executor import IBExecutor

# 2. Import IBKRStateMachine from src.execution.ibkr_state_machine
from src.execution.ibkr_state_machine import IBKRStateMachine


class _MockIBProvider:
    """Minimal provider so IBExecutor.__init__ runs; .ib is unused when guard triggers."""
    ib = None


def main() -> None:
    # 3. Instantiate state machine — state UNKNOWN, can_submit_orders False
    sm = IBKRStateMachine()
    assert sm.current_state == "UNKNOWN", f"expected UNKNOWN, got {sm.current_state}"
    assert sm.can_submit_orders is False, f"expected can_submit_orders False, got {sm.can_submit_orders}"
    print("3. OK: state=UNKNOWN, can_submit_orders=False")

    # IBExecutor needs ib_provider and account; mock provider has .ib (we never call IB when guarded)
    provider = _MockIBProvider()
    executor = IBExecutor(ib_provider=provider, account="TEST")

    # 4. submit_order with state_machine injected — returns False, logs, no raise (can_submit_orders False)
    result = executor.submit_order(
        "AAPL", 10, "BUY",
        state_machine=sm,
    )
    assert result is False, f"expected False when can_submit_orders False, got {result}"
    print("4. OK: submit_order returned False, no exception (guard active)")

    # 5. Transition state machine to CONNECTED; confirm can_submit_orders is True
    sm.transition("connect_attempt")
    sm.transition("heartbeat_ok")
    assert sm.current_state == "CONNECTED", f"expected CONNECTED, got {sm.current_state}"
    assert sm.can_submit_orders is True, f"expected can_submit_orders True, got {sm.can_submit_orders}"
    print("5. OK: state=CONNECTED, can_submit_orders=True")

    print("\nSmoke test passed.")


if __name__ == "__main__":
    main()
