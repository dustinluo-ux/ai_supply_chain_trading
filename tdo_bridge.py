"""
tdo_bridge.py — ThesisCandidate → TDO Promotion Bridge
Location: workspace root (same level as tdo_validator.py).

Converts a serialised alpha_scout ThesisCandidate dict to a
THESIS_SCHEMA.json v1.0.0 compliant TDO dict (phase = SCOUTED).

Design constraints
------------------
- Does NOT import or modify any alpha_scout internal module.
- Does NOT accept or produce Pydantic models; operates on plain dicts.
- Calls validate_tdo_or_raise() before returning; callers can rely on
  the output being schema-valid.
- Raises MappingError (not AuditConstraintError) for structural gaps
  in the source data that prevent a mapping from being formed at all.
  AuditConstraintError propagates if the assembled TDO fails Red Team
  constraints (e.g. confidence < 0.30, fewer than 3 findings).

Key field mappings (ThesisCandidate → TDO)
-------------------------------------------
  title               → scout.title
  thesis_claim        → scout.thesis_claim   (also seeds thesis_id via UUID v5)
  summary             → scout.summary
  confidence          → scout.confidence
  supporting_findings → scout.supporting_findings  (key_quote stripped; published_date
                          truncated to YYYY-MM-DD per schema format:date)
  critical_disagreement → scout.critical_disagreement  ("None" string → null)
  research_risks      → scout.research_risks  (bulleted string → list[str])
  generated_at        → created_at  (top-level, immutable)
  — (not in TC)       → scout.horizon             (kwarg, default "H3_DISCOVERY")
  — (not in TC)       → scout.bottleneck_description  (kwarg, default null)
  — (not in TC)       → scout.query_origin        (kwarg, optional)
  — (not in TC)       → scout.trigger_source      (kwarg, optional)

Evidence: THESIS_SCHEMA.json lines 52–147 (scout section),
          alpha_scout/src/core/models.py lines 11–115 (ThesisCandidate / ResearchFinding).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from tdo_validator import AuditConstraintError, validate_tdo_or_raise  # noqa: F401 (re-exported for callers)

# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class MappingError(ValueError):
    """
    Raised when a required ThesisCandidate field is absent or structurally
    incompatible with the TDO schema — i.e. before schema validation even runs.
    """


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_HORIZONS: frozenset[str] = frozenset(
    {"H1_TACTICAL", "H2_STRUCTURAL", "H3_DISCOVERY"}
)
_VALID_TRIGGER_SOURCES: frozenset[str] = frozenset(
    {"MANUAL_QUERY", "SENTINEL_ACCELERATION", "SEED_PAPER", "CRON_SCHEDULED"}
)

# Fields that must be present in a serialised ThesisCandidate
_TC_REQUIRED: tuple[str, ...] = (
    "title",
    "thesis_claim",
    "summary",
    "confidence",
    "supporting_findings",
)

# Fields that must be present in each ResearchFinding
_FINDING_REQUIRED: tuple[str, ...] = (
    "url",
    "title",
    "source_domain",
    "composite_score",
)

# All keys allowed in a TDO supporting_findings item (additionalProperties: false)
_FINDING_SCHEMA_KEYS: frozenset[str] = frozenset(
    {
        "url",
        "title",
        "snippet",
        "source_domain",
        "published_date",
        "relevance_score",
        "novelty_score",
        "evidence_quality",
        "composite_score",
    }
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _make_thesis_id(thesis_claim: str) -> str:
    """
    Deterministic UUID v5 derived from thesis_claim.
    Format: tdo_{uuid5_hex_with_dashes}.
    Evidence: THESIS_SCHEMA.json line 22 — "Deterministic UUID v5 derived from thesis_claim text."
    """
    uid = uuid.uuid5(uuid.NAMESPACE_URL, thesis_claim)
    return f"tdo_{uid}"


def _normalize_datetime_to_iso(raw: Any) -> str:
    """
    Accept a datetime object or ISO 8601 string and return a clean
    ISO 8601 UTC string (Z suffix, no +00:00).
    """
    if isinstance(raw, datetime):
        s = raw.astimezone(timezone.utc).isoformat()
    else:
        s = str(raw)
    return s.replace("+00:00", "Z")


def _normalize_date(raw: str | None) -> str | None:
    """
    Truncate an ISO 8601 datetime string to a date-only string (YYYY-MM-DD)
    as required by schema format:date for supporting_findings.published_date.
    Returns None if raw is falsy.
    """
    if not raw:
        return None
    # Take the first 10 chars: handles both "2025-11-14" and "2025-11-14T00:00:00Z"
    return str(raw)[:10]


def _parse_research_risks(raw: str) -> list[str]:
    """
    Convert a ThesisCandidate research_risks string to a list[str].

    TC stores risks as a bulleted string (• or - or *) or the sentinel "None".
    THESIS_SCHEMA stores them as array[str] (scout.research_risks).
    """
    if not raw or raw.strip().lower() == "none":
        return []
    result: list[str] = []
    for line in raw.split("\n"):
        # Strip leading bullet chars and whitespace
        stripped = re.sub(r"^[\s•\-\*·]+", "", line).strip()
        if stripped:
            result.append(stripped)
    return result


def _map_finding(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    """
    Map one ThesisCandidate ResearchFinding dict to a TDO supporting_findings item.

    Strips key_quote (not in THESIS_SCHEMA supporting_findings properties).
    Normalises published_date to YYYY-MM-DD (schema format:date).
    Evidence: THESIS_SCHEMA.json lines 108-128 (additionalProperties: false).
    """
    if not isinstance(raw, dict):
        raise MappingError(
            f"supporting_findings[{idx}] must be a dict; got {type(raw).__name__}."
        )
    for field in _FINDING_REQUIRED:
        if field not in raw:
            raise MappingError(
                f"supporting_findings[{idx}] is missing required field '{field}'. "
                f"Found keys: {sorted(raw.keys())}"
            )

    # Build output with only schema-allowed keys (key_quote is intentionally dropped)
    out: dict[str, Any] = {}
    for key in _FINDING_SCHEMA_KEYS:
        if key not in raw:
            continue
        if key == "published_date":
            out[key] = _normalize_date(raw[key])
        else:
            out[key] = raw[key]

    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def promote_to_tdo(
    legacy_json: dict[str, Any],
    *,
    horizon: str = "H3_DISCOVERY",
    query_origin: str | None = None,
    trigger_source: str | None = None,
    bottleneck_description: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """
    Promote a serialised ThesisCandidate dict to a THESIS_SCHEMA.json v1.0.0 TDO dict.

    Parameters
    ----------
    legacy_json : dict
        A ThesisCandidate serialised as a plain dict (e.g. from tc.model_dump()
        or json.loads of a saved file). Must contain the fields listed in
        _TC_REQUIRED. Does not need to be a Pydantic model.
    horizon : str
        Scout horizon classification. Must be one of H1_TACTICAL, H2_STRUCTURAL,
        H3_DISCOVERY. Defaults to H3_DISCOVERY (appropriate for alpha_scout output).
    query_origin : str | None
        Optional: original search query that triggered this thesis. Omitted from
        TDO if not provided.
    trigger_source : str | None
        Optional: one of MANUAL_QUERY | SENTINEL_ACCELERATION | SEED_PAPER |
        CRON_SCHEDULED. Omitted if not provided.
    bottleneck_description : str | None
        Optional: supply chain bottleneck description for the Auditor's BOM
        decomposer. Set to null in TDO if not provided; Auditor will skip BOM.
    now_utc : datetime | None
        Inject current UTC time for deterministic tests. Defaults to
        datetime.now(timezone.utc).

    Returns
    -------
    dict
        A schema-compliant TDO dict with phase = "SCOUTED". Guaranteed to pass
        validate_tdo(tdo, expected_phase="SCOUTED") before return.

    Raises
    ------
    MappingError
        When a required ThesisCandidate field is absent, the wrong type, or
        structurally incompatible with the TDO schema (e.g. fewer than 3
        supporting_findings, unrecognised horizon value).
    AuditConstraintError
        When the assembled TDO fails THESIS_SCHEMA.json validation or a Red Team
        Constraint (e.g. confidence < 0.30, composite_score < 0.30).
    """
    # ------------------------------------------------------------------
    # Guard: input type
    # ------------------------------------------------------------------
    if not isinstance(legacy_json, dict):
        raise MappingError(
            f"legacy_json must be a dict; got {type(legacy_json).__name__}. "
            "Pass the result of ThesisCandidate.model_dump() or json.loads(...)."
        )

    # ------------------------------------------------------------------
    # Guard: required ThesisCandidate fields
    # ------------------------------------------------------------------
    missing = [f for f in _TC_REQUIRED if f not in legacy_json]
    if missing:
        raise MappingError(
            f"ThesisCandidate dict is missing required field(s): {missing}. "
            f"Found keys: {sorted(legacy_json.keys())}"
        )

    thesis_claim: str = legacy_json["thesis_claim"]
    if not isinstance(thesis_claim, str) or not thesis_claim.strip():
        raise MappingError("thesis_claim must be a non-empty string.")

    # ------------------------------------------------------------------
    # Guard: horizon / trigger_source enum values
    # ------------------------------------------------------------------
    if horizon not in _VALID_HORIZONS:
        raise MappingError(
            f"horizon must be one of {sorted(_VALID_HORIZONS)}; got '{horizon}'."
        )
    if trigger_source is not None and trigger_source not in _VALID_TRIGGER_SOURCES:
        raise MappingError(
            f"trigger_source must be one of {sorted(_VALID_TRIGGER_SOURCES)}; "
            f"got '{trigger_source}'."
        )

    # ------------------------------------------------------------------
    # Guard: supporting_findings list length
    # ------------------------------------------------------------------
    findings_raw = legacy_json["supporting_findings"]
    if not isinstance(findings_raw, list):
        raise MappingError(
            f"supporting_findings must be a list; got {type(findings_raw).__name__}."
        )
    if len(findings_raw) < 3:
        raise MappingError(
            f"supporting_findings requires at least 3 items (circuit breaker threshold); "
            f"got {len(findings_raw)}."
        )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    _now = now_utc or datetime.now(timezone.utc)

    generated_at_raw = legacy_json.get("generated_at")
    if generated_at_raw:
        created_at = _normalize_datetime_to_iso(generated_at_raw)
    else:
        created_at = _normalize_datetime_to_iso(_now)

    # ------------------------------------------------------------------
    # Map supporting_findings (strips key_quote, normalises published_date)
    # ------------------------------------------------------------------
    findings = [_map_finding(f, i) for i, f in enumerate(findings_raw)]

    # ------------------------------------------------------------------
    # critical_disagreement: "None" sentinel → null
    # ------------------------------------------------------------------
    critical_disagreement_raw = legacy_json.get("critical_disagreement", "None")
    critical_disagreement: str | None = (
        None
        if not critical_disagreement_raw
        or str(critical_disagreement_raw).strip().lower() == "none"
        else critical_disagreement_raw
    )

    # ------------------------------------------------------------------
    # research_risks: bulleted string → list[str]
    # ------------------------------------------------------------------
    research_risks: list[str] = _parse_research_risks(
        legacy_json.get("research_risks", "None")
    )

    # ------------------------------------------------------------------
    # Assemble scout section
    # ------------------------------------------------------------------
    scout: dict[str, Any] = {
        "title": legacy_json["title"],
        "thesis_claim": thesis_claim,
        "summary": legacy_json["summary"],
        "confidence": legacy_json["confidence"],
        "horizon": horizon,
        "supporting_findings": findings,
        "critical_disagreement": critical_disagreement,
        "research_risks": research_risks,
        "bottleneck_description": bottleneck_description,
    }
    # Optional fields: only include if provided (schema allows absence)
    if query_origin is not None:
        scout["query_origin"] = query_origin
    if trigger_source is not None:
        scout["trigger_source"] = trigger_source

    # ------------------------------------------------------------------
    # Assemble TDO
    # ------------------------------------------------------------------
    tdo: dict[str, Any] = {
        "thesis_id": _make_thesis_id(thesis_claim),
        "schema_version": "1.0.0",
        "phase": "SCOUTED",
        "created_at": created_at,
        "scout": scout,
    }

    # ------------------------------------------------------------------
    # Final gate: validate before returning
    # Raises AuditConstraintError if schema or Red Team constraints fail.
    # ------------------------------------------------------------------
    validate_tdo_or_raise(tdo, expected_phase="SCOUTED", now_utc=_now)

    return tdo
