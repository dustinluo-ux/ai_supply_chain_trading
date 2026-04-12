"""
tests/test_tdo_validator.py

Unit tests for tdo_validator.py.

Covers every Red Team Constraint from AI_RULES.md §3:
  - EXECUTION GATE     : audit_hash missing → rejected
  - 50B-CAP RULE       : market_cap_usd >= 50B → rejected
  - CIRCUIT BREAKER    : < 3 supporting_findings → rejected
  - 24H GATE           : Pulse executing < 24h after created_at → rejected
  - 90-DAY EXPIRY      : thesis_expiry_date passed → rejected
  - TAMPER DETECTION   : execution_log hash mismatch → rejected
  - PHASE MISMATCH     : wrong expected_phase → rejected
  - MISSING AUDITOR    : AUDITED phase with null auditor → rejected

All tests are deterministic: now_utc is always injected explicitly.

Run with:
    C:\\Users\\dusro\\anaconda3\\envs\\alpha\\python.exe -m pytest tests/test_tdo_validator.py -v
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from tdo_validator import (
    AuditConstraintError,
    ValidationResult,
    compute_audit_hash,
    validate_tdo,
    validate_tdo_or_raise,
    verify_audit_hash,
    MARKET_CAP_CEILING_USD,
    SAME_DAY_EXECUTION_GATE_HOURS,
)

# ---------------------------------------------------------------------------
# Frozen timestamps (determinism — no datetime.now() in tests)
# ---------------------------------------------------------------------------
_T0 = datetime(2026, 3, 10, 9, 0, 0, tzinfo=timezone.utc)   # Scout emission
_T26 = _T0 + timedelta(hours=26)                              # 26h later: safe for Pulse
_T12 = _T0 + timedelta(hours=12)                              # 12h later: still inside gate
_T100 = _T0 + timedelta(days=100)                             # 100 days: past 90-day expiry


# ---------------------------------------------------------------------------
# Fixtures — minimal valid TDO building blocks
# ---------------------------------------------------------------------------
def _three_findings() -> list[dict]:
    """Minimal passing finding set — 3 findings each above 0.30 threshold."""
    return [
        {
            "url": f"https://arxiv.org/abs/test{i}",
            "title": f"Finding {i}",
            "source_domain": "arxiv.org",
            "composite_score": 0.75,
        }
        for i in range(3)
    ]


def _scouted_tdo() -> dict:
    """Minimal structurally valid TDO in SCOUTED phase."""
    return {
        "thesis_id": "tdo_7f3a9b12-4e1c-4d2f-a83b-9c0e1f2d3a4b",
        "schema_version": "1.0.0",
        "phase": "SCOUTED",
        "created_at": _T0.isoformat().replace("+00:00", "Z"),
        "scout": {
            "title": "GaN Power Semiconductor Supply Constraint",
            "thesis_claim": (
                "Gallium nitride power semiconductor demand will outpace supply "
                "through 2027 creating a structural margin expansion opportunity."
            ),
            "summary": "Three independent supply chain analyses confirm GaN constraint.",
            "confidence": 0.74,
            "horizon": "H3_DISCOVERY",
            "supporting_findings": _three_findings(),
        },
    }


def _sealed_auditor(market_cap: int = 4_200_000_000) -> dict:
    """
    Build a valid auditor section and seal it with a correct audit_hash.
    market_cap defaults to well below the 50B ceiling.
    """
    cap_passed = market_cap < MARKET_CAP_CEILING_USD
    auditor: dict = {
        "audit_hash": None,           # filled by compute_audit_hash below
        "audited_at": "2026-03-10T11:00:00Z",
        "auditor_version": "1.0.0",
        "tes_score": 0.68,
        "tes_components": {
            "primary_ticker": "WOLF",
            "company_name": "Wolfspeed Inc.",
            "niche_revenue_usd": 890_000_000,
            "total_revenue_usd": 1_020_000_000,
            "niche_revenue_ratio": 0.873,
            "divisional_cagr": 0.31,
            "patent_density": 0.59,
            "data_vintage": "2025-09-30",
            "data_confidence": "HIGH",
        },
        "market_cap_usd": market_cap,
        "cap_rule_passed": cap_passed,
        "bom_components": ["MOCVD reactor", "GaN epitaxial wafer"],
        "supply_chain": {
            "primary_company": "Wolfspeed Inc.",
            "suppliers": [],
            "customers": [],
            "competitors": [],
            "sec_filings_used": [],
        },
        "audit_failures": [],
    }
    auditor["audit_hash"] = compute_audit_hash(auditor)
    return auditor


def _audited_tdo(market_cap: int = 4_200_000_000) -> dict:
    """Full TDO in AUDITED phase with a correctly sealed auditor section."""
    tdo = _scouted_tdo()
    tdo["phase"] = "AUDITED"
    tdo["last_updated_at"] = "2026-03-10T11:30:00Z"
    tdo["auditor"] = _sealed_auditor(market_cap)
    return tdo


def _pulse_eligible_tdo(created_at: datetime = _T0) -> dict:
    """
    Full TDO in PULSE_ELIGIBLE phase.
    created_at is injected so tests can control the 24h gate.
    """
    tdo = _audited_tdo()
    tdo["phase"] = "PULSE_ELIGIBLE"
    tdo["created_at"] = created_at.isoformat().replace("+00:00", "Z")
    audit_hash = tdo["auditor"]["audit_hash"]
    tdo["pulse"] = {
        "execution_permitted": True,
        "execution_blocked_reason": None,
        "tes_threshold_used": 0.20,
        "macro_gate": {
            "regime": "BULL",
            "spy_vs_200sma": 1.08,
            "kill_switch_active": False,
            "evaluated_at": "2026-03-10T16:00:00Z",
        },
        "target_tickers": ["WOLF"],
        "suggested_position_bias": "OVERWEIGHT",
        "thesis_expiry_date": "2026-06-08",
        "execution_log": [
            {
                "event_type": "WEIGHT_APPLIED",
                "timestamp": "2026-03-11T10:00:00Z",
                "audit_hash_at_execution": audit_hash,
                "ticker": "WOLF",
                "weight": 0.15,
                "notes": None,
            }
        ],
    }
    return tdo


# ===========================================================================
# 1. HAPPY PATH
# ===========================================================================
class TestHappyPath:
    def test_scouted_tdo_passes(self):
        tdo = _scouted_tdo()
        result = validate_tdo(tdo, now_utc=_T26)
        assert result.passed, result.errors

    def test_audited_tdo_passes(self):
        tdo = _audited_tdo()
        result = validate_tdo(tdo, expected_phase="AUDITED", now_utc=_T26)
        assert result.passed, result.errors

    def test_pulse_eligible_tdo_passes(self):
        # created 26h before now → clears the 24h gate
        tdo = _pulse_eligible_tdo(created_at=_T0)
        result = validate_tdo(tdo, expected_phase="PULSE_ELIGIBLE", now_utc=_T26)
        assert result.passed, result.errors

    def test_validate_or_raise_does_not_raise_on_valid(self):
        tdo = _audited_tdo()
        validate_tdo_or_raise(tdo, expected_phase="AUDITED", now_utc=_T26)


# ===========================================================================
# 2. EXECUTION GATE — audit_hash required
# ===========================================================================
class TestExecutionGate:
    """
    AI_RULES.md §3 EXECUTION GATE:
    Pulse is unconditionally prohibited from executing without audit_hash.
    """

    def test_audited_phase_without_audit_hash_is_rejected(self):
        """Primary acceptance criterion: a TDO lacking audit_hash must be rejected."""
        tdo = _audited_tdo()
        tdo["auditor"]["audit_hash"] = None

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        codes = [e.code for e in result.errors]
        assert "MISSING_AUDIT_HASH" in codes

    def test_audited_phase_with_empty_string_audit_hash_is_rejected(self):
        tdo = _audited_tdo()
        tdo["auditor"]["audit_hash"] = ""

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "MISSING_AUDIT_HASH" for e in result.errors)

    def test_malformed_audit_hash_is_rejected(self):
        """Hash must be 'audit_' + 64-char hex; wrong length is rejected."""
        tdo = _audited_tdo()
        tdo["auditor"]["audit_hash"] = "audit_tooshort"

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "MALFORMED_AUDIT_HASH" for e in result.errors)

    def test_validate_or_raise_raises_on_missing_audit_hash(self):
        tdo = _audited_tdo()
        tdo["auditor"]["audit_hash"] = None

        with pytest.raises(AuditConstraintError) as exc_info:
            validate_tdo_or_raise(tdo, now_utc=_T26)

        assert any(e.code == "MISSING_AUDIT_HASH" for e in exc_info.value.errors)

    def test_null_auditor_section_in_audited_phase_is_rejected(self):
        """AUDITED phase requires a sealed auditor section — null is not enough."""
        tdo = _scouted_tdo()
        tdo["phase"] = "AUDITED"
        tdo["auditor"] = None

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "MISSING_AUDITOR" for e in result.errors)

    def test_scouted_phase_without_auditor_is_accepted(self):
        """SCOUTED phase does not yet require an auditor section."""
        tdo = _scouted_tdo()
        # auditor key not present at all
        result = validate_tdo(tdo, now_utc=_T26)
        assert result.passed, result.errors


# ===========================================================================
# 3. 50B-CAP RULE
# ===========================================================================
class TestCapRule:
    """AI_RULES.md §3 50B-CAP RULE"""

    def test_market_cap_above_ceiling_is_rejected(self):
        tdo = _audited_tdo(market_cap=60_000_000_000)  # $60B — over ceiling

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        codes = [e.code for e in result.errors]
        assert "CAP_RULE_VIOLATION" in codes

    def test_cap_rule_passed_false_is_rejected(self):
        """cap_rule_passed=False is independently enforced even if market_cap not set."""
        tdo = _audited_tdo()
        tdo["auditor"]["cap_rule_passed"] = False

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "CAP_RULE_FAILED" for e in result.errors)

    def test_market_cap_exactly_at_ceiling_is_rejected(self):
        """Boundary: >= ceiling means FAIL (ceiling is exclusive)."""
        tdo = _audited_tdo(market_cap=MARKET_CAP_CEILING_USD)

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "CAP_RULE_VIOLATION" for e in result.errors)

    def test_market_cap_below_ceiling_passes(self):
        tdo = _audited_tdo(market_cap=49_999_999_999)

        result = validate_tdo(tdo, expected_phase="AUDITED", now_utc=_T26)

        assert result.passed, result.errors


# ===========================================================================
# 4. CIRCUIT BREAKER — minimum findings
# ===========================================================================
class TestCircuitBreaker:
    """AI_RULES.md §3 CIRCUIT BREAKER: ≥ 3 findings required"""

    def test_two_findings_is_rejected(self):
        tdo = _scouted_tdo()
        tdo["scout"]["supporting_findings"] = _three_findings()[:2]

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "CIRCUIT_BREAKER" for e in result.errors)

    def test_zero_findings_is_rejected(self):
        tdo = _scouted_tdo()
        tdo["scout"]["supporting_findings"] = []

        result = validate_tdo(tdo, now_utc=_T26)

        # Both schema (minItems=3) and circuit breaker fire
        codes = [e.code for e in result.errors]
        assert "CIRCUIT_BREAKER" in codes or "SCHEMA_VIOLATION" in codes

    def test_exactly_three_findings_passes(self):
        tdo = _scouted_tdo()
        assert len(tdo["scout"]["supporting_findings"]) == 3
        result = validate_tdo(tdo, now_utc=_T26)
        assert result.passed, result.errors

    def test_low_composite_score_adds_warning_not_error(self):
        """Findings below threshold emit a warning only; the TDO still passes structure."""
        tdo = _scouted_tdo()
        tdo["scout"]["supporting_findings"][0]["composite_score"] = 0.25  # below 0.30

        result = validate_tdo(tdo, now_utc=_T26)

        # Should still have 3 findings → passes circuit breaker
        assert result.passed
        assert any("0.250" in w or "0.25" in w for w in result.warnings)


# ===========================================================================
# 5. 24H CONTAMINATION GATE
# ===========================================================================
class TestContaminationGate:
    """AI_RULES.md §3 24H CONTAMINATION GATE"""

    def test_pulse_within_24h_of_emission_is_rejected(self):
        """TDO created at T0, Pulse checks at T0+12h — must be blocked."""
        tdo = _pulse_eligible_tdo(created_at=_T0)

        result = validate_tdo(tdo, now_utc=_T12)

        assert not result.passed
        assert any(e.code == "CONTAMINATION_GATE" for e in result.errors)

    def test_pulse_after_24h_passes_gate(self):
        """TDO created at T0, Pulse checks at T0+26h — gate clears."""
        tdo = _pulse_eligible_tdo(created_at=_T0)

        result = validate_tdo(tdo, now_utc=_T26)

        # The only errors should not include CONTAMINATION_GATE
        gate_errors = [e for e in result.errors if e.code == "CONTAMINATION_GATE"]
        assert not gate_errors

    def test_scouted_phase_skips_contamination_gate(self):
        """Gate only applies to execution phases; SCOUTED TDO is unaffected."""
        tdo = _scouted_tdo()
        # Even if checked 1 second after emission, SCOUTED phase should pass
        result = validate_tdo(tdo, now_utc=_T0 + timedelta(seconds=1))
        assert result.passed, result.errors


# ===========================================================================
# 6. 90-DAY EXPIRY
# ===========================================================================
class TestExpiryGate:
    """AI_RULES.md §3 90-DAY EXPIRY"""

    def test_expired_thesis_is_rejected(self):
        """thesis_expiry_date in the past → re-audit required."""
        tdo = _pulse_eligible_tdo(created_at=_T0)
        tdo["phase"] = "EXECUTED"
        tdo["pulse"]["thesis_expiry_date"] = "2026-03-15"  # before _T100

        result = validate_tdo(tdo, now_utc=_T100)

        assert not result.passed
        assert any(e.code == "TDO_EXPIRED" for e in result.errors)

    def test_valid_expiry_does_not_block(self):
        tdo = _pulse_eligible_tdo(created_at=_T0)
        tdo["phase"] = "EXECUTED"
        tdo["pulse"]["thesis_expiry_date"] = "2027-01-01"  # far future

        result = validate_tdo(tdo, now_utc=_T26)

        expiry_errors = [e for e in result.errors if e.code == "TDO_EXPIRED"]
        assert not expiry_errors


# ===========================================================================
# 7. TAMPER DETECTION
# ===========================================================================
class TestTamperDetection:
    """execution_log[*].audit_hash_at_execution must match auditor.audit_hash"""

    def test_mismatched_log_hash_is_rejected(self):
        tdo = _pulse_eligible_tdo(created_at=_T0)
        # Corrupt the recorded hash in the execution log
        tdo["pulse"]["execution_log"][0]["audit_hash_at_execution"] = (
            "audit_" + "0" * 64
        )

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "TAMPERED_TDO" for e in result.errors)

    def test_correct_log_hash_passes(self):
        tdo = _pulse_eligible_tdo(created_at=_T0)
        # execution_log already has the correct hash from _pulse_eligible_tdo
        result = validate_tdo(tdo, now_utc=_T26)
        tamper_errors = [e for e in result.errors if e.code == "TAMPERED_TDO"]
        assert not tamper_errors


# ===========================================================================
# 8. PHASE MISMATCH
# ===========================================================================
class TestPhaseMismatch:
    def test_wrong_expected_phase_is_rejected(self):
        tdo = _scouted_tdo()
        result = validate_tdo(tdo, expected_phase="AUDITED", now_utc=_T26)

        assert not result.passed
        assert any(e.code == "PHASE_MISMATCH" for e in result.errors)

    def test_correct_expected_phase_passes(self):
        tdo = _audited_tdo()
        result = validate_tdo(tdo, expected_phase="AUDITED", now_utc=_T26)
        assert result.passed, result.errors


# ===========================================================================
# 9. SCHEMA VIOLATIONS
# ===========================================================================
class TestSchemaViolations:
    def test_missing_required_thesis_id_is_rejected(self):
        tdo = _scouted_tdo()
        del tdo["thesis_id"]

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_invalid_phase_enum_is_rejected(self):
        tdo = _scouted_tdo()
        tdo["phase"] = "NONEXISTENT_PHASE"

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_invalid_thesis_id_pattern_is_rejected(self):
        tdo = _scouted_tdo()
        tdo["thesis_id"] = "not-a-valid-tdo-id"

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_additional_root_property_is_rejected(self):
        """Schema has additionalProperties: false at root."""
        tdo = _scouted_tdo()
        tdo["rogue_field"] = "unexpected"

        result = validate_tdo(tdo, now_utc=_T26)

        assert not result.passed
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)


# ===========================================================================
# 10. audit_hash utilities
# ===========================================================================
class TestAuditHashUtilities:
    def test_compute_audit_hash_returns_correct_prefix(self):
        auditor = _sealed_auditor()
        h = compute_audit_hash(auditor)
        assert h.startswith("audit_")
        assert len(h) == 70  # "audit_" + 64-char hex

    def test_compute_audit_hash_is_deterministic(self):
        """Same auditor payload must always produce the same hash."""
        auditor = _sealed_auditor()
        h1 = compute_audit_hash(auditor)
        h2 = compute_audit_hash(auditor)
        assert h1 == h2

    def test_compute_audit_hash_changes_on_payload_mutation(self):
        auditor = _sealed_auditor()
        original = compute_audit_hash(auditor)

        auditor["tes_score"] = 0.99  # mutate a hash-input field
        mutated = compute_audit_hash(auditor)

        assert original != mutated

    def test_verify_audit_hash_passes_for_intact_section(self):
        auditor = _sealed_auditor()
        assert verify_audit_hash(auditor) is True

    def test_verify_audit_hash_fails_after_tampering(self):
        auditor = _sealed_auditor()
        auditor["market_cap_usd"] = 1  # tamper post-seal
        assert verify_audit_hash(auditor) is False

    def test_timestamp_excluded_from_hash_payload(self):
        """audited_at must NOT affect the hash (timestamps change, hash must be stable)."""
        auditor_a = _sealed_auditor()
        auditor_b = copy.deepcopy(auditor_a)
        auditor_b["audited_at"] = "2099-12-31T23:59:59Z"  # different timestamp

        hash_a = compute_audit_hash(auditor_a)
        hash_b = compute_audit_hash(auditor_b)

        assert hash_a == hash_b, "Timestamps must not affect the audit_hash."
