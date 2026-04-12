"""
tests/test_tdo_bridge.py — Integration tests for tdo_bridge.promote_to_tdo()

Loads a real ThesisCandidate fixture from tests/fixtures/thesis_candidate_sample.json,
promotes it to a TDO, and verifies full THESIS_SCHEMA.json compliance.

All timestamps are injected via now_utc= for determinism.
No alpha_scout internals are imported.
"""

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tdo_bridge import MappingError, promote_to_tdo
from tdo_validator import AuditConstraintError, validate_tdo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "thesis_candidate_sample.json"
_NOW = datetime(2026, 3, 10, 9, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def tc() -> dict:
    """Return a fresh copy of the sample ThesisCandidate dict for each test."""
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# TestHappyPath — core promotion and schema compliance
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_returns_dict(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert isinstance(tdo, dict)

    def test_schema_compliant(self, tc):
        """Primary acceptance criterion: output must be 100% THESIS_SCHEMA compliant."""
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        result = validate_tdo(tdo, expected_phase="SCOUTED", now_utc=_NOW)
        assert result.passed, [f"[{e.code}] {e.message}" for e in result.errors]

    def test_phase_is_scouted(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert tdo["phase"] == "SCOUTED"

    def test_schema_version(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert tdo["schema_version"] == "1.0.0"

    def test_thesis_id_format(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert re.match(
            r"^tdo_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            tdo["thesis_id"],
        ), f"thesis_id format mismatch: {tdo['thesis_id']}"

    def test_thesis_id_deterministic(self, tc):
        """Same thesis_claim must always produce the same thesis_id."""
        tdo1 = promote_to_tdo(tc, now_utc=_NOW)
        tdo2 = promote_to_tdo(copy.deepcopy(tc), now_utc=_NOW)
        assert tdo1["thesis_id"] == tdo2["thesis_id"]

    def test_thesis_id_changes_with_claim(self, tc):
        """Different thesis_claim must produce a different thesis_id."""
        tc2 = copy.deepcopy(tc)
        tc2["thesis_claim"] = (
            "A completely different falsifiable claim about an unrelated supply chain "
            "bottleneck that is entirely distinct from the original thesis claim text."
        )
        tdo1 = promote_to_tdo(tc, now_utc=_NOW)
        tdo2 = promote_to_tdo(tc2, now_utc=_NOW)
        assert tdo1["thesis_id"] != tdo2["thesis_id"]

    def test_created_at_from_generated_at(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        # TC fixture has generated_at "2026-03-08T14:08:08.000000+00:00"
        assert tdo["created_at"].startswith("2026-03-08T14:08:08")

    def test_created_at_falls_back_to_now_when_absent(self, tc):
        tc_copy = copy.deepcopy(tc)
        del tc_copy["generated_at"]
        tdo = promote_to_tdo(tc_copy, now_utc=_NOW)
        assert tdo["created_at"].startswith("2026-03-10T09:00:00")

    def test_auditor_section_absent(self, tc):
        """SCOUTED TDO must not contain an auditor section."""
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert "auditor" not in tdo


# ---------------------------------------------------------------------------
# TestScoutFieldMapping — individual scout field checks
# ---------------------------------------------------------------------------

class TestScoutFieldMapping:
    def test_title_mapped(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert tdo["scout"]["title"] == tc["title"]

    def test_thesis_claim_mapped(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert tdo["scout"]["thesis_claim"] == tc["thesis_claim"]

    def test_summary_mapped(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert tdo["scout"]["summary"] == tc["summary"]

    def test_confidence_mapped(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert tdo["scout"]["confidence"] == tc["confidence"]

    def test_default_horizon_h3(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert tdo["scout"]["horizon"] == "H3_DISCOVERY"

    def test_custom_horizon_h2(self, tc):
        tdo = promote_to_tdo(tc, horizon="H2_STRUCTURAL", now_utc=_NOW)
        assert tdo["scout"]["horizon"] == "H2_STRUCTURAL"

    def test_custom_horizon_h1(self, tc):
        tdo = promote_to_tdo(tc, horizon="H1_TACTICAL", now_utc=_NOW)
        assert tdo["scout"]["horizon"] == "H1_TACTICAL"

    def test_critical_disagreement_string_preserved(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        cd = tdo["scout"]["critical_disagreement"]
        assert isinstance(cd, str)
        assert len(cd) > 0

    def test_critical_disagreement_none_string_becomes_null(self, tc):
        tc_copy = copy.deepcopy(tc)
        tc_copy["critical_disagreement"] = "None"
        tdo = promote_to_tdo(tc_copy, now_utc=_NOW)
        assert tdo["scout"]["critical_disagreement"] is None

    def test_critical_disagreement_absent_becomes_null(self, tc):
        tc_copy = copy.deepcopy(tc)
        tc_copy.pop("critical_disagreement", None)
        tdo = promote_to_tdo(tc_copy, now_utc=_NOW)
        assert tdo["scout"]["critical_disagreement"] is None

    def test_research_risks_parsed_to_list(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        risks = tdo["scout"]["research_risks"]
        assert isinstance(risks, list)
        assert len(risks) == 3  # fixture has 3 bullet points

    def test_research_risks_no_bullet_chars(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        for risk in tdo["scout"]["research_risks"]:
            assert not risk.startswith("•")
            assert not risk.startswith("-")
            assert not risk.startswith("*")

    def test_research_risks_none_string_becomes_empty_list(self, tc):
        tc_copy = copy.deepcopy(tc)
        tc_copy["research_risks"] = "None"
        tdo = promote_to_tdo(tc_copy, now_utc=_NOW)
        assert tdo["scout"]["research_risks"] == []

    def test_bottleneck_description_null_by_default(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert tdo["scout"]["bottleneck_description"] is None

    def test_bottleneck_description_passed_through(self, tc):
        desc = "GaN HEMT substrate fabrication requiring MOCVD reactors"
        tdo = promote_to_tdo(tc, bottleneck_description=desc, now_utc=_NOW)
        assert tdo["scout"]["bottleneck_description"] == desc

    def test_query_origin_absent_by_default(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert "query_origin" not in tdo["scout"]

    def test_query_origin_included_when_provided(self, tc):
        tdo = promote_to_tdo(tc, query_origin="GaN power semiconductor supply", now_utc=_NOW)
        assert tdo["scout"]["query_origin"] == "GaN power semiconductor supply"

    def test_trigger_source_absent_by_default(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert "trigger_source" not in tdo["scout"]

    def test_trigger_source_included_when_provided(self, tc):
        tdo = promote_to_tdo(tc, trigger_source="SENTINEL_ACCELERATION", now_utc=_NOW)
        assert tdo["scout"]["trigger_source"] == "SENTINEL_ACCELERATION"


# ---------------------------------------------------------------------------
# TestFindingMapping — ResearchFinding → TDO finding item
# ---------------------------------------------------------------------------

class TestFindingMapping:
    def test_finding_count_preserved(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        assert len(tdo["scout"]["supporting_findings"]) == 3

    def test_key_quote_stripped(self, tc):
        """key_quote is a TC field not in THESIS_SCHEMA (additionalProperties: false)."""
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        for finding in tdo["scout"]["supporting_findings"]:
            assert "key_quote" not in finding, (
                f"key_quote must be stripped from findings; found it in {finding}"
            )

    def test_published_date_normalized_to_yyyy_mm_dd(self, tc):
        """Schema requires format:date (YYYY-MM-DD); TC stores full ISO datetime."""
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        for finding in tdo["scout"]["supporting_findings"]:
            pd = finding.get("published_date")
            if pd is not None:
                assert re.match(r"^\d{4}-\d{2}-\d{2}$", pd), (
                    f"published_date must be YYYY-MM-DD; got '{pd}'"
                )

    def test_finding_required_fields_present(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        for finding in tdo["scout"]["supporting_findings"]:
            assert "url" in finding
            assert "title" in finding
            assert "source_domain" in finding
            assert "composite_score" in finding

    def test_finding_no_extra_keys(self, tc):
        """No keys outside the 9 schema-defined properties (additionalProperties: false)."""
        allowed = {
            "url", "title", "snippet", "source_domain", "published_date",
            "relevance_score", "novelty_score", "evidence_quality", "composite_score",
        }
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        for i, finding in enumerate(tdo["scout"]["supporting_findings"]):
            extra = set(finding.keys()) - allowed
            assert not extra, f"findings[{i}] has unexpected keys: {extra}"

    def test_scores_preserved(self, tc):
        tdo = promote_to_tdo(tc, now_utc=_NOW)
        src = tc["supporting_findings"][0]
        out = tdo["scout"]["supporting_findings"][0]
        assert out["composite_score"] == src["composite_score"]
        assert out["relevance_score"] == src["relevance_score"]


# ---------------------------------------------------------------------------
# TestMappingErrors — structural gaps raise MappingError
# ---------------------------------------------------------------------------

class TestMappingErrors:
    def test_non_dict_raises(self):
        with pytest.raises(MappingError, match="dict"):
            promote_to_tdo("not a dict", now_utc=_NOW)

    def test_missing_title_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        del tc_copy["title"]
        with pytest.raises(MappingError, match="title"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_missing_thesis_claim_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        del tc_copy["thesis_claim"]
        with pytest.raises(MappingError, match="thesis_claim"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_missing_summary_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        del tc_copy["summary"]
        with pytest.raises(MappingError, match="summary"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_missing_confidence_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        del tc_copy["confidence"]
        with pytest.raises(MappingError, match="confidence"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_missing_supporting_findings_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        del tc_copy["supporting_findings"]
        with pytest.raises(MappingError, match="supporting_findings"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_too_few_findings_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        tc_copy["supporting_findings"] = tc["supporting_findings"][:2]
        with pytest.raises(MappingError, match="3"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_findings_not_a_list_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        tc_copy["supporting_findings"] = "not a list"
        with pytest.raises(MappingError, match="list"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_finding_missing_composite_score_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        bad_finding = copy.deepcopy(tc["supporting_findings"][0])
        del bad_finding["composite_score"]
        tc_copy["supporting_findings"] = [bad_finding] + tc["supporting_findings"][1:]
        with pytest.raises(MappingError, match="composite_score"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_finding_missing_url_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        bad_finding = copy.deepcopy(tc["supporting_findings"][0])
        del bad_finding["url"]
        tc_copy["supporting_findings"] = [bad_finding] + tc["supporting_findings"][1:]
        with pytest.raises(MappingError, match="url"):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_invalid_horizon_raises(self, tc):
        with pytest.raises(MappingError, match="horizon"):
            promote_to_tdo(tc, horizon="INVALID_HORIZON", now_utc=_NOW)

    def test_invalid_trigger_source_raises(self, tc):
        with pytest.raises(MappingError, match="trigger_source"):
            promote_to_tdo(tc, trigger_source="BAD_SOURCE", now_utc=_NOW)

    def test_empty_thesis_claim_raises(self, tc):
        tc_copy = copy.deepcopy(tc)
        tc_copy["thesis_claim"] = "   "
        with pytest.raises(MappingError, match="thesis_claim"):
            promote_to_tdo(tc_copy, now_utc=_NOW)


# ---------------------------------------------------------------------------
# TestRedTeamConstraints — AuditConstraintError when TDO violates gate rules
# ---------------------------------------------------------------------------

class TestRedTeamConstraints:
    def test_title_exceeding_max_length_raises(self, tc):
        """
        title exceeding schema maxLength:120 must be caught by the JSON Schema
        validator inside promote_to_tdo and raised as AuditConstraintError.
        Evidence: THESIS_SCHEMA.json scout.title maxLength:120.
        """
        tc_copy = copy.deepcopy(tc)
        tc_copy["title"] = "X" * 121
        with pytest.raises(AuditConstraintError):
            promote_to_tdo(tc_copy, now_utc=_NOW)

    def test_all_trigger_sources_accepted(self, tc):
        """All valid trigger_source values must produce a schema-compliant TDO."""
        for source in ("MANUAL_QUERY", "SENTINEL_ACCELERATION", "SEED_PAPER", "CRON_SCHEDULED"):
            tdo = promote_to_tdo(tc, trigger_source=source, now_utc=_NOW)
            result = validate_tdo(tdo, expected_phase="SCOUTED", now_utc=_NOW)
            assert result.passed, f"trigger_source={source} produced invalid TDO: {result.errors}"

    def test_all_horizons_accepted(self, tc):
        """All valid horizon values must produce a schema-compliant TDO."""
        for h in ("H1_TACTICAL", "H2_STRUCTURAL", "H3_DISCOVERY"):
            tdo = promote_to_tdo(tc, horizon=h, now_utc=_NOW)
            result = validate_tdo(tdo, expected_phase="SCOUTED", now_utc=_NOW)
            assert result.passed, f"horizon={h} produced invalid TDO: {result.errors}"
