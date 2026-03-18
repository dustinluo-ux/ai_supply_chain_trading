"""
Data criticality and quality reporting. Spec: docs/RESILIENCE_SPEC.md Sections 1, 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class IncompleteDataError(Exception):
    """Raised when a CRITICAL data source is missing or fails (if caller is configured to raise)."""

    def __init__(self, missing_sources: list[str], criticality: str) -> None:
        self.missing_sources = list(missing_sources)
        self.criticality = str(criticality)
        super().__init__(f"missing_sources={self.missing_sources!r} criticality={self.criticality!r}")

    def __str__(self) -> str:
        return f"IncompleteDataError(missing_sources={self.missing_sources!r}, criticality={self.criticality!r})"


@dataclass
class DataQualityReport:
    critical_missing: list[str] = field(default_factory=list)
    degraded_missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    can_rebalance: bool = field(init=False)

    def __post_init__(self) -> None:
        self.can_rebalance = len(self.critical_missing) == 0

    def to_dict(self) -> dict:
        """Plain dict suitable for JSON serialisation."""
        return {
            "critical_missing": list(self.critical_missing),
            "degraded_missing": list(self.degraded_missing),
            "warnings": list(self.warnings),
            "can_rebalance": self.can_rebalance,
        }


CRITICAL_SOURCES = ["prices", "smh_benchmark", "regime_status"]
DEGRADED_SOURCES = ["eodhd_news", "tiingo_news", "marketaux_news", "meta_weights"]
