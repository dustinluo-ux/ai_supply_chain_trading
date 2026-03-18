"""
Smoke test for IBKRStateMachine and connection_freeze alert.
Run from project root. Spec: docs/RESILIENCE_SPEC.md.
"""
from __future__ import annotations

import sys

# 1. Import IBKRStateMachine — no import error
from src.execution.ibkr_state_machine import IBKRStateMachine

# 2. Instantiate — current_state is "UNKNOWN", can_submit_orders is False
sm = IBKRStateMachine()
assert sm.current_state == "UNKNOWN", f"expected UNKNOWN, got {sm.current_state}"
assert sm.can_submit_orders is False, f"expected can_submit_orders False, got {sm.can_submit_orders}"
print("2. OK: current_state=UNKNOWN, can_submit_orders=False")

# 3. transition("connect_attempt") — state becomes "CONNECTING"
sm.transition("connect_attempt")
assert sm.current_state == "CONNECTING", f"expected CONNECTING, got {sm.current_state}"
print("3. OK: state=CONNECTING")

# 4. transition("heartbeat_ok") — state becomes "CONNECTED", can_submit_orders is True
sm.transition("heartbeat_ok")
assert sm.current_state == "CONNECTED", f"expected CONNECTED, got {sm.current_state}"
assert sm.can_submit_orders is True, f"expected can_submit_orders True, got {sm.can_submit_orders}"
print("4. OK: state=CONNECTED, can_submit_orders=True")

# 5. transition("latency_high") — state becomes "DEGRADED", can_submit_orders is False
sm.transition("latency_high")
assert sm.current_state == "DEGRADED", f"expected DEGRADED, got {sm.current_state}"
assert sm.can_submit_orders is False, f"expected can_submit_orders False, got {sm.can_submit_orders}"
print("5. OK: state=DEGRADED, can_submit_orders=False")

# 6. transition("heartbeat_fail") — state becomes "FROZEN", can_submit_orders is False
sm.transition("heartbeat_fail")
assert sm.current_state == "FROZEN", f"expected FROZEN, got {sm.current_state}"
assert sm.can_submit_orders is False, f"expected can_submit_orders False, got {sm.can_submit_orders}"
print("6. OK: state=FROZEN, can_submit_orders=False")

# 7. Confirm connection_freeze is accepted by send_alert without raising KeyError
from src.monitoring.telegram_alerts import send_alert

send_alert("connection_freeze", {"state": "FROZEN", "latency_ms": None, "reason": "smoke test"})
print("7. OK: send_alert('connection_freeze', ...) accepted, no KeyError")

print("\nSmoke test passed.")
