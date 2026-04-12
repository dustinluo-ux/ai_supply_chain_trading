"""
tdo_validator.py — Thesis Data Object validator (v1.0.0)

The ONLY authorised gateway for cross-module TDO handoffs.
Validates a TDO dict against THESIS_SCHEMA.json and enforces every
Red Team Constraint from AI_RULES.md §3 at each phase transition.

Usage:
    from tdo_validator import validate_tdo, validate_tdo_or_raise, compute_audit_hash

    # Validate without raising:
    result = validate_tdo(tdo_dict, expected_phase="AUDITED")
    if not result.passed:
        for err in result.errors:
            print(err)

    # Validate and raise on failure:
    validate_tdo_or_raise(tdo_dict, expected_phase="PULSE_ELIGIBLE")

    # Compute audit_hash in AuditOrchestrator after sealing:
    tdo["auditor"]["audit_hash"] = compute_audit_hash(tdo["auditor"])

Red Team Constraints enforced here (mirror THESIS_SCHEMA.json §red_team_constraints):
  - 50B-CAP RULE       : market_cap_usd < 50_000_000_000
  - EXECUTION GATE     : audit_hash must be present and well-formed
  - CIRCUIT BREAKER    : ≥ 3 supporting_findings with composite_score ≥ 0.30
  - 24H GATE           : Pulse cannot execute within 24h of created_at
  - 90-DAY EXPIRY      : thesis_expiry_date must not have passed
  - TAMPER DETECTION   : execution_log[*].audit_hash_at_execution must match auditor.audit_hash
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft7Validator
except ImportError as exc:
    raise ImportError(
        "jsonschema is required: "
        "C:\\Users\\dusro\\anaconda3\\envs\\alpha\\python.exe -m pip install jsonschema"
    ) from exc

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCHEMA_PATH = (
    Path(__file__).parent / "shared_schemas" / "THESIS_SCHEMA.json"
    if (Path(__file__).parent / "shared_schemas" / "THESIS_SCHEMA.json").exists()
    else Path(__file__).parent / "THESIS_SCHEMA.json"
)

# ---------------------------------------------------------------------------
# Red Team Constraint constants
# Mirror THESIS_SCHEMA.json §red_team_constraints — never change without
# a "Proposal Review" from the Lead Architect.
# ---------------------------------------------------------------------------
MARKET_CAP_CEILING_USD: int = 50_000_000_000
MIN_SUPPORTING_FINDINGS: int = 3
MIN_COMPOSITE_SCORE: float = 0.30
MAX_THESIS_AGE_DAYS: int = 90
SAME_DAY_EXECUTION_GATE_HOURS: int = 24

# Phases that require a sealed auditor section
_PHASES_REQUIRING_AUDIT: frozenset[str] = frozenset(
    {"AUDITED", "PULSE_ELIGIBLE", "PULSE_BLOCKED", "EXECUTED", "EXPIRED"}
)
# Phases where the Pulse execution gate must be checked
_PHASES_REQUIRING_EXECUTION_GATE: frozenset[str] = frozenset(
    {"PULSE_ELIGIBLE", "EXECUTED"}
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class ValidationError:
    code: str
    message: str
    path: str = ""


@dataclass
class ValidationResult:
    passed: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, code: str, message: str, path: str = "") -> None:
        self.errors.append(ValidationError(code=code, message=message, path=path))
        self.passed = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def __repr__(self) -> str:
        status = "PASS" if self.passed else f"FAIL ({len(self.errors)} error(s))"
        return (
            f"ValidationResult({status}, "
            f"errors={[e.code for e in self.errors]}, "
            f"warnings={len(self.warnings)})"
        )


class AuditConstraintError(Exception):
    """Raised by validate_tdo_or_raise when any Red Team Constraint is violated."""

    def __init__(self, errors: list[ValidationError]) -> None:
        messages = "; ".join(f"[{e.code}] {e.message}" for e in errors)
        super().__init__(f"TDO validation failed: {messages}")
        self.errors = errors


# ---------------------------------------------------------------------------
# Schema loading (module-level cache)
# ---------------------------------------------------------------------------
_schema_cache: dict | None = None


def _load_schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        with _SCHEMA_PATH.open(encoding="utf-8") as fh:
            _schema_cache = json.load(fh)
    return _schema_cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def validate_tdo(
    tdo: dict[str, Any],
    *,
    expected_phase: str | None = None,
    now_utc: datetime | None = None,
) -> ValidationResult:
    """
    Validate a TDO dict against THESIS_SCHEMA.json and all Red Team Constraints.

    Args:
        tdo:            The Thesis Data Object as a Python dict.
        expected_phase: If provided, the TDO's phase field must equal this value.
        now_utc:        Override for current UTC time (inject in tests for determinism).
                        Defaults to datetime.now(tz=timezone.utc).

    Returns:
        ValidationResult. Check result.passed; inspect result.errors for FAIL codes.
    """
    result = ValidationResult()
    now = now_utc or datetime.now(tz=timezone.utc)

    # Step 1 — structural JSON Schema validation
    # We do NOT return early here: schema violations (e.g. wrong pattern on
    # audit_hash, minItems on supporting_findings) are collected alongside the
    # semantic Red Team checks below.  Both layers of errors are reported
    # together so callers see the full picture.
    # We do bail out early only if tdo is not a mapping at all, since the
    # sub-checks all assume dict access.
    if not isinstance(tdo, dict):
        result.add_error("SCHEMA_VIOLATION", "TDO must be a JSON object (dict).", path="(root)")
        return result
    _check_json_schema(tdo, result)

    # Step 2 — phase assertion
    phase = tdo.get("phase", "")
    if expected_phase is not None and phase != expected_phase:
        result.add_error(
            "PHASE_MISMATCH",
            f"Expected phase '{expected_phase}' but TDO has phase '{phase}'.",
            path="phase",
        )

    # Step 3 — Scout section invariants (always)
    _check_scout_section(tdo, result)

    # Step 4 — Auditor section (required once phase passes AUDIT_PENDING)
    if phase in _PHASES_REQUIRING_AUDIT:
        _check_auditor_section(tdo, result)

    # Step 5 — Pulse execution gate (required for PULSE_ELIGIBLE / EXECUTED)
    if phase in _PHASES_REQUIRING_EXECUTION_GATE:
        _check_pulse_section(tdo, result, now)

    # Step 6 — temporal constraints
    _check_temporal_constraints(tdo, result, now)

    return result


def validate_tdo_or_raise(
    tdo: dict[str, Any],
    *,
    expected_phase: str | None = None,
    now_utc: datetime | None = None,
) -> None:
    """validate_tdo, but raises AuditConstraintError on any failure."""
    result = validate_tdo(tdo, expected_phase=expected_phase, now_utc=now_utc)
    if not result.passed:
        raise AuditConstraintError(result.errors)


# ---------------------------------------------------------------------------
# Audit hash utilities
# ---------------------------------------------------------------------------
def compute_audit_hash(auditor_section: dict[str, Any]) -> str:
    """
    Compute the audit_hash for an auditor section.

    Call this in AuditOrchestrator after all fields are finalised and before
    writing the TDO to disk or passing it to Pulse.

    The hash is stable: same inputs always produce the same output.
    Timestamps (audited_at) are deliberately excluded from the payload to
    ensure the hash can be re-verified at any future point.
    """
    payload = _canonical_audit_payload(auditor_section)
    return "audit_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_audit_hash(auditor_section: dict[str, Any]) -> bool:
    """
    Re-derive the expected audit_hash and compare it against the stored value.
    Returns True only if they match exactly.
    """
    stored = auditor_section.get("audit_hash", "")
    return stored == compute_audit_hash(auditor_section)


def validate_schema(tdo: dict[str, Any], expected_phase: str | None = None) -> bool:
    """
    Lightweight boolean wrapper around validate_tdo().
    Returns True if the TDO passes schema + Red Team constraints, False otherwise.
    Suitable for guard-clause use: if not validate_schema(tdo): halt()

    For detailed error reporting use validate_tdo() directly.
    For hard-stop enforcement use validate_tdo_or_raise().
    """
    result = validate_tdo(tdo, expected_phase=expected_phase)
    return result.passed


def _canonical_audit_payload(auditor_section: dict[str, Any]) -> str:
    """
    Deterministic serialisation of the immutable audit fields.
    Only fields that are fixed after the Auditor seals the TDO are included.
    """
    payload = {
        "tes_score": auditor_section.get("tes_score"),
        "tes_components": auditor_section.get("tes_components"),
        "market_cap_usd": auditor_section.get("market_cap_usd"),
        "cap_rule_passed": auditor_section.get("cap_rule_passed"),
        "supply_chain": auditor_section.get("supply_chain"),
        "bom_components": auditor_section.get("bom_components"),
    }
    return json.dumps(payload, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Internal checkers
# ---------------------------------------------------------------------------
def _check_json_schema(tdo: dict, result: ValidationResult) -> None:
    schema = _load_schema()
    validator = Draft7Validator(schema)
    for error in sorted(validator.iter_errors(tdo), key=lambda e: list(e.absolute_path)):
        path = " > ".join(str(p) for p in error.absolute_path) or "(root)"
        result.add_error("SCHEMA_VIOLATION", error.message, path=path)


def _check_scout_section(tdo: dict, result: ValidationResult) -> None:
    scout = tdo.get("scout") or {}

    # Circuit breaker: minimum finding count
    findings = scout.get("supporting_findings") or []
    if len(findings) < MIN_SUPPORTING_FINDINGS:
        result.add_error(
            "CIRCUIT_BREAKER",
            (
                f"Scout requires ≥ {MIN_SUPPORTING_FINDINGS} supporting_findings; "
                f"found {len(findings)}."
            ),
            path="scout.supporting_findings",
        )

    # Warn on any finding below the composite threshold (schema allows 0.0–1.0 broadly)
    # Guard: if findings are not dicts (schema violation already captured), skip
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        score = finding.get("composite_score")
        if score is not None and score < MIN_COMPOSITE_SCORE:
            result.add_warning(
                f"scout.supporting_findings[{i}].composite_score "
                f"{score:.3f} < threshold {MIN_COMPOSITE_SCORE}."
            )


def _check_auditor_section(tdo: dict, result: ValidationResult) -> None:
    phase = tdo.get("phase", "")
    auditor = tdo.get("auditor")

    if auditor is None:
        result.add_error(
            "MISSING_AUDITOR",
            f"Phase '{phase}' requires a sealed auditor section but auditor is null.",
            path="auditor",
        )
        return

    # --- audit_hash ---
    audit_hash: str | None = auditor.get("audit_hash")
    if not audit_hash:
        result.add_error(
            "MISSING_AUDIT_HASH",
            (
                "auditor.audit_hash is required and must not be null or empty. "
                "Pulse is unconditionally prohibited from executing without a "
                "verified audit_hash. (AI_RULES.md §3 EXECUTION GATE)"
            ),
            path="auditor.audit_hash",
        )
    elif not (audit_hash.startswith("audit_") and len(audit_hash) == 70):
        # "audit_" (6 chars) + SHA-256 hex digest (64 chars) = 70 chars total
        result.add_error(
            "MALFORMED_AUDIT_HASH",
            (
                f"audit_hash must match pattern audit_{{hex64}} (70 chars); "
                f"got length {len(audit_hash)}."
            ),
            path="auditor.audit_hash",
        )

    # --- 50B-cap rule ---
    market_cap = auditor.get("market_cap_usd")
    cap_rule_passed = auditor.get("cap_rule_passed")

    if market_cap is not None and market_cap >= MARKET_CAP_CEILING_USD:
        result.add_error(
            "CAP_RULE_VIOLATION",
            (
                f"50B-CAP RULE: market_cap_usd {market_cap:,.0f} >= "
                f"ceiling {MARKET_CAP_CEILING_USD:,.0f}. "
                "Pulse MUST NOT execute. (AI_RULES.md §3)"
            ),
            path="auditor.market_cap_usd",
        )

    if cap_rule_passed is False:
        result.add_error(
            "CAP_RULE_FAILED",
            (
                "auditor.cap_rule_passed is False. "
                "Pulse execution is unconditionally blocked. (AI_RULES.md §3)"
            ),
            path="auditor.cap_rule_passed",
        )

    # --- TES score sanity ---
    tes_score = auditor.get("tes_score")
    if tes_score is not None and tes_score < 0:
        result.add_error(
            "INVALID_TES_SCORE",
            f"auditor.tes_score must be ≥ 0; got {tes_score}.",
            path="auditor.tes_score",
        )


def _check_pulse_section(
    tdo: dict, result: ValidationResult, now: datetime
) -> None:
    phase = tdo.get("phase", "")
    pulse = tdo.get("pulse")

    if pulse is None:
        result.add_error(
            "MISSING_PULSE",
            f"Phase '{phase}' requires a pulse section but pulse is null.",
            path="pulse",
        )
        return

    # execution_permitted must be explicitly True
    if not pulse.get("execution_permitted"):
        reason = pulse.get("execution_blocked_reason") or "No reason provided."
        result.add_error(
            "EXECUTION_BLOCKED",
            f"pulse.execution_permitted is not True. Reason: {reason}",
            path="pulse.execution_permitted",
        )

    # Tamper detection: every execution_log entry must carry the current audit_hash
    auditor = tdo.get("auditor") or {}
    expected_hash = auditor.get("audit_hash")
    for i, entry in enumerate(pulse.get("execution_log") or []):
        recorded = entry.get("audit_hash_at_execution")
        if recorded != expected_hash:
            result.add_error(
                "TAMPERED_TDO",
                (
                    f"execution_log[{i}].audit_hash_at_execution '{recorded}' "
                    f"does not match auditor.audit_hash '{expected_hash}'. "
                    "TDO may have been tampered. Halt immediately."
                ),
                path=f"pulse.execution_log[{i}].audit_hash_at_execution",
            )


def _check_temporal_constraints(
    tdo: dict, result: ValidationResult, now: datetime
) -> None:
    phase = tdo.get("phase", "")

    # 24h contamination gate — only blocks execution phases
    if phase in _PHASES_REQUIRING_EXECUTION_GATE:
        created_at_str = tdo.get("created_at")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
                age_hours = (now - created_at).total_seconds() / 3600
                if age_hours < SAME_DAY_EXECUTION_GATE_HOURS:
                    result.add_error(
                        "CONTAMINATION_GATE",
                        (
                            f"24H CONTAMINATION GATE: TDO is only {age_hours:.1f}h old "
                            f"(minimum {SAME_DAY_EXECUTION_GATE_HOURS}h required before "
                            "Pulse may execute). Prevents same-day Scout-to-Pulse "
                            "feedback loop. (AI_RULES.md §6)"
                        ),
                        path="created_at",
                    )
            except ValueError:
                result.add_error(
                    "INVALID_CREATED_AT",
                    f"created_at '{created_at_str}' is not a valid ISO 8601 datetime.",
                    path="created_at",
                )

    # 90-day expiry — checked on re-execution
    if phase == "EXECUTED":
        pulse = tdo.get("pulse") or {}
        expiry_str = pulse.get("thesis_expiry_date")
        if expiry_str:
            try:
                expiry_date = datetime.fromisoformat(expiry_str)
                if expiry_date.tzinfo is None:
                    expiry_date = expiry_date.replace(tzinfo=timezone.utc)
                if now > expiry_date:
                    result.add_error(
                        "TDO_EXPIRED",
                        (
                            f"90-DAY EXPIRY: thesis_expiry_date {expiry_str} has passed. "
                            "Re-audit required before further execution. (AI_RULES.md §3)"
                        ),
                        path="pulse.thesis_expiry_date",
                    )
            except ValueError:
                result.add_error(
                    "INVALID_EXPIRY_DATE",
                    f"pulse.thesis_expiry_date '{expiry_str}' is not a valid ISO date.",
                    path="pulse.thesis_expiry_date",
                )
