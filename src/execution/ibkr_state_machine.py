"""
IBKR connection state machine. Standalone; connection injected optionally.
Spec: docs/RESILIENCE_SPEC.md Section 3.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
EXECUTION_STATUS_PATH = ROOT / "outputs" / "execution_status.json"

# (from_state, event) -> to_state. force_disconnect handled separately (ANY -> DISCONNECTED).
_TRANSITIONS: dict[tuple[str, str], str] = {
    ("UNKNOWN", "connect_attempt"): "CONNECTING",
    ("DISCONNECTED", "connect_attempt"): "CONNECTING",
    ("CONNECTING", "heartbeat_ok"): "CONNECTED",
    ("CONNECTING", "heartbeat_fail"): "DISCONNECTED",
    ("CONNECTED", "latency_high"): "DEGRADED",
    ("CONNECTED", "heartbeat_fail"): "FROZEN",
    ("CONNECTED", "disconnect"): "DISCONNECTED",
    ("DEGRADED", "heartbeat_ok"): "CONNECTED",
    ("DEGRADED", "heartbeat_fail"): "FROZEN",
    ("FROZEN", "timeout"): "DISCONNECTED",
    ("FROZEN", "heartbeat_ok"): "CONNECTED",
}


def _load_risk_config() -> dict[str, Any]:
    """Read risk_management from config/model_config.yaml."""
    path = ROOT / "config" / "model_config.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("risk_management", {}) or {}
    except Exception:
        return {}


class IBKRStateMachine:
    """
    IBKR connection state machine. No dependency on live IBKR;
    connection is injected optionally for ping/heartbeat.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.current_state = "UNKNOWN"
        self.latency_ms: float | None = None
        self.last_heartbeat: datetime | None = None
        self.consecutive_failures = 0
        self._config = config if config is not None else _load_risk_config()
        self._latency_threshold_ms = float(self._config.get("ibkr_latency_threshold_ms", 500))
        self._freeze_latency_ms = float(self._config.get("ibkr_freeze_latency_ms", 2000))
        self._freeze_timeout_seconds = int(self._config.get("ibkr_freeze_timeout_seconds", 60))

    @property
    def can_submit_orders(self) -> bool:
        return self.current_state == "CONNECTED"

    def transition(self, event: str) -> None:
        """Validate event from current state, update current_state, log at INFO. Invalid: log WARNING, no change."""
        from_state = self.current_state
        key = (from_state, event)
        to_state = _TRANSITIONS.get(key)
        if to_state is None and event == "force_disconnect":
            to_state = "DISCONNECTED"
        if to_state is None:
            logger.warning("[IBKRStateMachine] Invalid transition: state=%s event=%s (ignored)", from_state, event)
            return
        self.current_state = to_state
        logger.info("[IBKRStateMachine] %s --[%s]--> %s", from_state, event, to_state)

        if to_state == "FROZEN":
            self._on_enter_frozen()

    def _on_enter_frozen(self) -> None:
        """Write execution_status.json (merge) and fire connection_freeze Telegram alert."""
        data: dict[str, Any] = {}
        if EXECUTION_STATUS_PATH.exists():
            try:
                with open(EXECUTION_STATUS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data["manual_intervention_required"] = True
        data["ibkr_state"] = "FROZEN"
        data["as_of"] = datetime.now(timezone.utc).isoformat()
        try:
            EXECUTION_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(EXECUTION_STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("[IBKRStateMachine] Could not write execution_status.json: %s", e)
        try:
            from src.monitoring.telegram_alerts import send_alert
            send_alert(
                "connection_freeze",
                {
                    "state": self.current_state,
                    "latency_ms": self.latency_ms,
                    "reason": "Connection entered FROZEN state",
                },
            )
        except Exception as e:
            logger.warning("[IBKRStateMachine] Could not send connection_freeze alert: %s", e)

    def ping(self, ib_connection: Any = None) -> float | None:
        """
        Measure round-trip latency. If ib_connection is None or unavailable, return None.
        Stores result in self.latency_ms. Returns elapsed milliseconds or None.
        """
        if ib_connection is None:
            self.latency_ms = None
            return None
        try:
            t0 = datetime.now(timezone.utc)
            # Stub: replace with actual reqCurrentTime or equivalent call when wiring to live TWS.
            # e.g. ib_connection.reqCurrentTime() and wait for response, or use a no-op API call.
            _ = ib_connection
            t1 = datetime.now(timezone.utc)
            elapsed_ms = (t1 - t0).total_seconds() * 1000.0
            self.latency_ms = elapsed_ms
            return elapsed_ms
        except Exception as e:
            logger.debug("[IBKRStateMachine] ping failed: %s", e)
            self.latency_ms = None
            return None

    def check_heartbeat(self, ib_connection: Any = None) -> str:
        """
        Call ping(), then apply thresholds to determine event; transition; update last_heartbeat
        or consecutive_failures. On FROZEN: write execution_status.json and fire connection_freeze alert.
        Returns the new current_state.
        """
        latency = self.ping(ib_connection)
        if latency is None:
            event = "heartbeat_fail"
        elif latency > self._freeze_latency_ms:
            event = "heartbeat_fail"
        elif latency > self._latency_threshold_ms:
            event = "latency_high"
        else:
            event = "heartbeat_ok"

        self.transition(event)
        if event == "heartbeat_ok":
            self.last_heartbeat = datetime.now(timezone.utc)
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

        return self.current_state

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable snapshot for execution_status.json."""
        return {
            "current_state": self.current_state,
            "latency_ms": self.latency_ms,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "can_submit_orders": self.can_submit_orders,
            "consecutive_failures": self.consecutive_failures,
        }
