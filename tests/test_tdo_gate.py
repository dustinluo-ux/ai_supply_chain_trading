"""
tests/test_tdo_gate.py — Unit tests for auditor/tdo_gate.verify_execution_eligibility()

Covers every execution gate check:
  1. Valid AUDITED TDO                    → True
  2. Valid PULSE_ELIGIBLE TDO             → True
  3. Ineligible phase variants            → False
  4. Missing auditor section              → False
  5. Tampered / missing audit_hash        → False
  6. cap_rule_passed = False              → False
  7. market_cap_usd >= 50B               → False
  8. Thesis age > 90 days                → False
  9. kill_switch_active = True           → False
 10. Edge cases: null market_cap, no pulse section, non-dict input

All timestamps injected via now_utc= for full determinism.
"""

from __future__ import annotations

import copy
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# -- ensure workspace root is importable ------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "ai_supply_chain_trading") not in sys.path:
    sys.path.insert(0, str(_ROOT / "ai_supply_chain_trading"))

from tdo_validator import MARKET_CAP_CEILING_USD, compute_audit_hash
from auditor.tdo_gate import verify_execution_eligibility

# ---------------------------------------------------------------------------
# Frozen timestamps — no datetime.now() in tests
# ---------------------------------------------------------------------------
_AUDIT_TS = "2026-03-10T11:00:00Z"                         # when TDO was audited
_AUDIT_DT = datetime(2026, 3, 10, 11, 0, 0, tzinfo=timezone.utc)
_NOW_SAFE = _AUDIT_DT + timedelta(days=1)                   # 1 day later: well within 90d
_NOW_EXPIRED = _AUDIT_DT + timedelta(days=91)               # 91 days later: past 90d limit
_CAP_BELOW = 4_200_000_000                                  # $4.2B — well below 50B ceiling
_CAP_AT_CEILING = MARKET_CAP_CEILING_USD                    # exactly $50B — must fail
_CAP_ABOVE = MARKET_CAP_CEILING_USD + 1                     # $50B+1 — must fail


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _sealed_auditor(
    market_cap: int | None = _CAP_BELOW,
    cap_rule_passed: bool | None = None,
    audited_at: str = _AUDIT_TS,
) -> dict:
    """Build a valid auditor section sealed with the correct audit_hash."""
    if cap_rule_passed is None:
        cap_rule_passed = (market_cap is not None and market_cap < MARKET_CAP_CEILING_USD)
    auditor: dict = {
        "audit_hash": None,
        "audited_at": audited_at,
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
        "cap_rule_passed": cap_rule_passed,
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


def _audited_tdo(
    market_cap: int | None = _CAP_BELOW,
    cap_rule_passed: bool | None = None,
    audited_at: str = _AUDIT_TS,
    phase: str = "AUDITED",
) -> dict:
    """Full TDO in AUDITED (or given) phase with correctly sealed auditor section."""
    return {
        "thesis_id": "tdo_7f3a9b12-4e1c-4d2f-a83b-9c0e1f2d3a4b",
        "schema_version": "1.0.0",
        "phase": phase,
        "created_at": "2026-03-10T09:00:00Z",
        "last_updated_at": "2026-03-10T11:30:00Z",
        "scout": {
            "title": "GaN Power Semiconductor Supply Constraint",
            "thesis_claim": (
                "Gallium nitride power semiconductor demand will outpace supply "
                "through 2027 creating a structural margin expansion opportunity."
            ),
            "summary": "Three independent analyses confirm GaN constraint.",
            "confidence": 0.74,
            "horizon": "H3_DISCOVERY",
            "supporting_findings": [
                {
                    "url": f"https://arxiv.org/abs/test{i}",
                    "title": f"Finding {i}",
                    "source_domain": "arxiv.org",
                    "composite_score": 0.75,
                }
                for i in range(3)
            ],
        },
        "auditor": _sealed_auditor(
            market_cap=market_cap,
            cap_rule_passed=cap_rule_passed,
            audited_at=audited_at,
        ),
    }


def _with_pulse(tdo: dict, kill_switch_active: bool = False) -> dict:
    """Add a pulse section to a TDO (copies to avoid mutation)."""
    tdo = copy.deepcopy(tdo)
    tdo["phase"] = "PULSE_ELIGIBLE"
    tdo["pulse"] = {
        "execution_permitted": True,
        "execution_blocked_reason": None,
        "tes_threshold_used": 0.20,
        "macro_gate": {
            "regime": "BULL",
            "spy_vs_200sma": 1.08,
            "kill_switch_active": kill_switch_active,
            "evaluated_at": "2026-03-10T16:00:00Z",
        },
        "target_tickers": ["WOLF"],
        "suggested_position_bias": "OVERWEIGHT",
        "thesis_expiry_date": "2026-06-08",
        "execution_log": [],
    }
    return tdo


# ---------------------------------------------------------------------------
# TestHappyPath — TDOs that should pass
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_valid_audited_tdo_passes(self):
        tdo = _audited_tdo()
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True

    def test_valid_pulse_eligible_tdo_passes(self):
        tdo = _with_pulse(_audited_tdo())
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True

    def test_kill_switch_false_passes(self):
        tdo = _with_pulse(_audited_tdo(), kill_switch_active=False)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True

    def test_no_pulse_section_passes(self):
        """AUDITED TDO with no pulse section: no kill switch to check → should pass."""
        tdo = _audited_tdo()
        assert "pulse" not in tdo
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True

    def test_null_market_cap_with_cap_rule_true_passes(self):
        """market_cap_usd=None skips belt check; cap_rule_passed=True is accepted."""
        tdo = _audited_tdo(market_cap=None, cap_rule_passed=True)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True


# ---------------------------------------------------------------------------
# TestPhaseGate — ineligible phases
# ---------------------------------------------------------------------------

class TestPhaseGate:
    @pytest.mark.parametrize("phase", [
        "SCOUTED",
        "AUDIT_PENDING",
        "AUDIT_FAILED",
        "PULSE_BLOCKED",
        "EXECUTED",
        "EXPIRED",
        "",
    ])
    def test_ineligible_phase_blocked(self, phase):
        tdo = _audited_tdo(phase=phase)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False


# ---------------------------------------------------------------------------
# TestAuditHashGate — check 2
# ---------------------------------------------------------------------------

class TestAuditHashGate:
    def test_missing_auditor_section_blocked(self):
        tdo = _audited_tdo()
        del tdo["auditor"]
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False

    def test_null_auditor_blocked(self):
        tdo = _audited_tdo()
        tdo["auditor"] = None
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False

    def test_missing_audit_hash_blocked(self):
        tdo = _audited_tdo()
        del tdo["auditor"]["audit_hash"]
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False

    def test_tampered_audit_hash_blocked(self):
        tdo = _audited_tdo()
        original = tdo["auditor"]["audit_hash"]
        # Flip a single character in the hash payload
        tdo["auditor"]["audit_hash"] = original[:-1] + ("0" if original[-1] != "0" else "1")
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False

    def test_hash_still_passes_after_deep_copy(self):
        """audit_hash must be deterministic: verify_audit_hash on a deepcopy must pass."""
        tdo = _audited_tdo()
        tdo2 = copy.deepcopy(tdo)
        assert verify_execution_eligibility(tdo2, now_utc=_NOW_SAFE) is True

    def test_rehashed_after_mutation_passes(self):
        """If we re-seal the hash after a legitimate change, the gate passes again."""
        tdo = _audited_tdo()
        # Mutate and re-seal
        tdo["auditor"]["tes_score"] = 0.99
        tdo["auditor"]["audit_hash"] = compute_audit_hash(tdo["auditor"])
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True


# ---------------------------------------------------------------------------
# TestCapRuleGate — checks 3 and 4
# ---------------------------------------------------------------------------

class TestCapRuleGate:
    def test_cap_rule_passed_false_blocked(self):
        """cap_rule_passed=False blocks regardless of market_cap value."""
        tdo = _audited_tdo(market_cap=_CAP_BELOW, cap_rule_passed=False)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False

    def test_market_cap_exactly_at_ceiling_blocked(self):
        """market_cap == 50_000_000_000 must be blocked (>= ceiling)."""
        tdo = _audited_tdo(market_cap=_CAP_AT_CEILING, cap_rule_passed=True)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False

    def test_market_cap_above_ceiling_blocked(self):
        """market_cap > 50B must be blocked."""
        tdo = _audited_tdo(market_cap=_CAP_ABOVE, cap_rule_passed=True)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False

    def test_market_cap_one_below_ceiling_passes(self):
        """market_cap = 50B - 1 must pass (strictly less than ceiling)."""
        tdo = _audited_tdo(market_cap=MARKET_CAP_CEILING_USD - 1, cap_rule_passed=True)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True

    def test_large_cap_blocked_even_if_cap_rule_set_true(self):
        """Belt-and-suspenders: even with cap_rule_passed=True, large cap is blocked."""
        tdo = _audited_tdo(market_cap=100_000_000_000, cap_rule_passed=True)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False


# ---------------------------------------------------------------------------
# TestThesisAgeGate — check 5
# ---------------------------------------------------------------------------

class TestThesisAgeGate:
    def test_thesis_at_90_days_exactly_passes(self):
        """Exactly 90 days old: <= MAX_THESIS_AGE_DAYS, must pass."""
        tdo = _audited_tdo()
        now = _AUDIT_DT + timedelta(days=90)
        assert verify_execution_eligibility(tdo, now_utc=now) is True

    def test_thesis_at_91_days_blocked(self):
        """91 days old: > MAX_THESIS_AGE_DAYS (90), must be blocked."""
        tdo = _audited_tdo()
        assert verify_execution_eligibility(tdo, now_utc=_NOW_EXPIRED) is False

    def test_thesis_100_days_old_blocked(self):
        tdo = _audited_tdo()
        now = _AUDIT_DT + timedelta(days=100)
        assert verify_execution_eligibility(tdo, now_utc=now) is False

    def test_thesis_clears_contamination_gate(self):
        """created_at >= 24h before now clears Check 3a; still within 90d window."""
        tdo = _audited_tdo()
        now = _AUDIT_DT + timedelta(hours=6)
        created = now - timedelta(hours=25)
        tdo["created_at"] = created.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert verify_execution_eligibility(tdo, now_utc=now) is True

    def test_fresh_thesis_blocked_by_contamination_gate(self, caplog):
        """TDO younger than 24h from created_at is blocked (CONTAMINATION_GATE)."""
        caplog.set_level(logging.WARNING)
        tdo = _audited_tdo()
        now = _AUDIT_DT + timedelta(hours=6)
        assert verify_execution_eligibility(tdo, now_utc=now) is False
        assert any("CONTAMINATION_GATE" in r.message for r in caplog.records), caplog.text

    def test_missing_audited_at_uses_created_at(self):
        """Falls back to created_at when audited_at is absent."""
        tdo = _audited_tdo()
        del tdo["auditor"]["audited_at"]
        # created_at is "2026-03-10T09:00:00Z" — within 90 days of _NOW_SAFE
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True

    def test_unparseable_age_reference_blocked(self):
        """Unparseable audited_at timestamp cannot be verified — must block."""
        tdo = _audited_tdo()
        tdo["auditor"]["audited_at"] = "not-a-date"
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False


# ---------------------------------------------------------------------------
# TestKillSwitchGate — check 6
# ---------------------------------------------------------------------------

class TestKillSwitchGate:
    def test_kill_switch_active_blocks(self):
        tdo = _with_pulse(_audited_tdo(), kill_switch_active=True)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is False

    def test_kill_switch_inactive_passes(self):
        tdo = _with_pulse(_audited_tdo(), kill_switch_active=False)
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True

    def test_pulse_present_no_macro_gate_passes(self):
        """pulse section exists but macro_gate is absent: no kill switch to trigger."""
        tdo = _with_pulse(_audited_tdo())
        del tdo["pulse"]["macro_gate"]
        assert verify_execution_eligibility(tdo, now_utc=_NOW_SAFE) is True


# ---------------------------------------------------------------------------
# TestRobustness — edge cases, never raises
# ---------------------------------------------------------------------------

class TestRobustness:
    def test_non_dict_input_returns_false(self):
        assert verify_execution_eligibility("not a dict", now_utc=_NOW_SAFE) is False

    def test_none_input_returns_false(self):
        assert verify_execution_eligibility(None, now_utc=_NOW_SAFE) is False

    def test_empty_dict_returns_false(self):
        assert verify_execution_eligibility({}, now_utc=_NOW_SAFE) is False

    def test_function_never_raises_on_garbage(self):
        """verify_execution_eligibility must absorb all exceptions, never raise."""
        for bad in [42, [], b"bytes", object()]:
            result = verify_execution_eligibility(bad, now_utc=_NOW_SAFE)
            assert result is False, f"Expected False for input {bad!r}, got {result}"
