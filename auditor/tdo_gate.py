"""
auditor/tdo_gate.py — TDO Execution Eligibility Gate

Single public function: verify_execution_eligibility(tdo, *, now_utc) -> bool

Checks all Red Team Constraints that must hold before Pulse is permitted to
submit any order against a thesis. Returns False (never raises) on any failure.

Checks (in order)
-----------------
1. Phase is execution-eligible (AUDITED or PULSE_ELIGIBLE)
2. audit_hash is present and re-derives correctly (verify_audit_hash)
3. cap_rule_passed is True in auditor section
3a. TDO age >= 24h from created_at (contamination gate)
4. market_cap_usd < 50_000_000_000 (belt-and-suspenders, independent of cap_rule_passed)
5. Thesis age <= 90 days from auditor.audited_at (or created_at as fallback)
6. pulse.macro_gate.kill_switch_active is not True

Evidence
--------
THESIS_SCHEMA.json §red_team_constraints (lines 348-390): market_cap_ceiling_usd,
max_thesis_age_days, audit_hash_required_for_execution.
INDEX.md §Module3-Pulse: all 5 TDO gate checks before position build.
tdo_validator.py: MARKET_CAP_CEILING_USD, MAX_THESIS_AGE_DAYS constants.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -- workspace root on sys.path so tdo_validator is importable ----------------
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from tdo_validator import (  # noqa: E402
    MARKET_CAP_CEILING_USD,
    MAX_THESIS_AGE_DAYS,
    verify_audit_hash,
)

logger = logging.getLogger(__name__)

# Phases that make a TDO eligible for execution consideration
_EXECUTION_ELIGIBLE_PHASES: frozenset[str] = frozenset(
    {"AUDITED", "PULSE_ELIGIBLE"}
)

# Minimum available funds required to proceed (USD). Prevents execution when
# account is depleted or IBKR session returns zero/negative.
# AI_RULES.md §3 — Liquidity_Rule added 2026-03-10.
_LIQUIDITY_RULE_MIN_USD: float = 1_000.0


def verify_execution_eligibility(
    tdo: dict[str, Any],
    *,
    now_utc: datetime | None = None,
    available_funds: float | None = None,
) -> bool:
    """
    Return True only if the TDO passes every execution safety check.

    Parameters
    ----------
    tdo : dict
        Thesis Data Object dict. Must be AUDITED or PULSE_ELIGIBLE phase.
    now_utc : datetime | None
        Override current UTC time (for deterministic tests).
    available_funds : float | None
        Live available funds from IBKR AccountMonitor. When provided,
        enforces Check 7 (Liquidity_Rule): blocks if funds <= 0 or below
        _LIQUIDITY_RULE_MIN_USD. When None, the check is skipped
        (backward-compatible: mock mode, dry-run, no live session).

    Returns
    -------
    bool
        True = all checks passed, execution is permitted.
        False = at least one check failed; reason logged at WARNING level.

    Never raises.
    """
    _now = now_utc or datetime.now(timezone.utc)

    try:
        return _run_checks(tdo, _now, available_funds)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "tdo_gate: unexpected exception during eligibility check — %s: %s; "
            "returning False to block execution.",
            type(exc).__name__,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _run_checks(tdo: dict[str, Any], now: datetime, available_funds: float | None) -> bool:
    if not isinstance(tdo, dict):
        logger.warning("tdo_gate: tdo is not a dict (%s) — blocked", type(tdo).__name__)
        return False

    thesis_id = tdo.get("thesis_id", "<unknown>")

    # ── Check 1: Phase ───────────────────────────────────────────────────────
    phase = tdo.get("phase", "")
    if phase not in _EXECUTION_ELIGIBLE_PHASES:
        logger.warning(
            "tdo_gate [%s]: phase='%s' is not in %s — blocked",
            thesis_id, phase, sorted(_EXECUTION_ELIGIBLE_PHASES),
        )
        return False

    # ── Check 2: audit_hash validity ─────────────────────────────────────────
    auditor = tdo.get("auditor")
    if not isinstance(auditor, dict):
        logger.warning(
            "tdo_gate [%s]: auditor section is absent or not a dict — blocked",
            thesis_id,
        )
        return False

    if not verify_audit_hash(auditor):
        logger.warning(
            "tdo_gate [%s]: audit_hash verification failed (missing, malformed, or tampered) — blocked",
            thesis_id,
        )
        return False

    # ── Check 3: cap_rule_passed ─────────────────────────────────────────────
    if not auditor.get("cap_rule_passed", False):
        logger.warning(
            "tdo_gate [%s]: cap_rule_passed is False — blocked",
            thesis_id,
        )
        return False

    # ── Check 3a: 24h contamination gate ────────────────────────────────────
    created_at_str = tdo.get("created_at")
    if created_at_str:
        try:
            created_dt = datetime.fromisoformat(
                str(created_at_str).replace("Z", "+00:00")
            )
            age_hours = (now - created_dt).total_seconds() / 3600
            if age_hours < 24.0:
                logger.warning(
                    "tdo_gate [%s]: CONTAMINATION_GATE — TDO is %.1fh old "
                    "(min 24h required) — blocked",
                    thesis_id, age_hours,
                )
                return False
        except (ValueError, TypeError) as exc:
            logger.warning(
                "tdo_gate [%s]: could not parse created_at '%s': %s — blocked",
                thesis_id, created_at_str, exc,
            )
            return False

    # ── Check 4: market_cap_usd < ceiling (belt-and-suspenders) ─────────────
    market_cap = auditor.get("market_cap_usd")
    if market_cap is not None and market_cap >= MARKET_CAP_CEILING_USD:
        logger.warning(
            "tdo_gate [%s]: market_cap_usd=%s >= ceiling %s — blocked",
            thesis_id, market_cap, MARKET_CAP_CEILING_USD,
        )
        return False

    # ── Check 5: thesis age ≤ MAX_THESIS_AGE_DAYS ───────────────────────────
    # Use audited_at if present; fall back to created_at (audit may be very fresh).
    age_ref = auditor.get("audited_at") or tdo.get("created_at")
    if age_ref:
        try:
            ref_dt = datetime.fromisoformat(str(age_ref).replace("Z", "+00:00"))
            age_days = (now - ref_dt).days
            if age_days > MAX_THESIS_AGE_DAYS:
                logger.warning(
                    "tdo_gate [%s]: thesis is %d days old (max %d) — blocked",
                    thesis_id, age_days, MAX_THESIS_AGE_DAYS,
                )
                return False
        except (ValueError, TypeError) as exc:
            logger.warning(
                "tdo_gate [%s]: could not parse age reference '%s': %s — blocked",
                thesis_id, age_ref, exc,
            )
            return False

    # ── Check 6: kill_switch_active ──────────────────────────────────────────
    pulse = tdo.get("pulse")
    if isinstance(pulse, dict):
        macro_gate = pulse.get("macro_gate")
        if isinstance(macro_gate, dict) and macro_gate.get("kill_switch_active", False):
            logger.warning(
                "tdo_gate [%s]: pulse.macro_gate.kill_switch_active is True — blocked",
                thesis_id,
            )
            return False

    # ── Check 7: Liquidity_Rule (only when available_funds is provided) ──────
    # Skipped in mock/dry-run mode (available_funds=None). Enforced in live mode.
    # Does not read TDO-native sizing (THESIS_SCHEMA has no target_position_size_usd;
    # additionalProperties:false blocks additions without a schema version bump).
    # The 5% execution buffer lives in OrderDispatcher._quantity_from_weight().
    if available_funds is not None:
        if available_funds <= 0.0:
            logger.warning(
                "tdo_gate [%s]: Liquidity_Rule BLOCKED — available_funds=%.2f <= 0 "
                "(account depleted or IBKR session returned zero).",
                thesis_id, available_funds,
            )
            return False
        if available_funds < _LIQUIDITY_RULE_MIN_USD:
            logger.warning(
                "tdo_gate [%s]: Liquidity_Rule BLOCKED — available_funds=%.2f < "
                "floor %.2f USD. Insufficient liquidity for minimum viable position.",
                thesis_id, available_funds, _LIQUIDITY_RULE_MIN_USD,
            )
            return False
        logger.info(
            "tdo_gate [%s]: Liquidity_Rule PASSED — available_funds=%.2f",
            thesis_id, available_funds,
        )
    # ── End Check 7 ──────────────────────────────────────────────────────────

    logger.info(
        "tdo_gate [%s]: all checks passed — execution eligible (phase=%s)",
        thesis_id, phase,
    )
    return True
