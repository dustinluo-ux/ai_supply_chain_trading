"""
TES (Thesis Execution Score) — shared scorer.
Formula shape fixed by THESIS_SCHEMA / ADR D-TES-STUBS; patent density prior until USPTO.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_AUDITOR_CONFIG = _ROOT / "config" / "auditor_config.yaml"


def merge_data_confidence(a: str, b: str) -> str:
    """Weakest link: STUB < ESTIMATED < COMPUTED."""
    if a == "STUB" or b == "STUB":
        return "STUB"
    if a == "ESTIMATED" or b == "ESTIMATED":
        return "ESTIMATED"
    return "COMPUTED"


def _load_auditor_config_dict(path: Path | None = None) -> dict[str, Any]:
    p = path or _DEFAULT_AUDITOR_CONFIG
    if not p.exists():
        return {"default_patent_density": 0.10, "niche_revenue_fraction": 0.15}
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def estimate_patent_density(
    components: dict[str, Any],
    *,
    config_default: float = 0.10,
    log: logging.Logger | None = None,
) -> float:
    """
    Prior for patent density until USPTO integration.
    Always merged as ESTIMATED downstream (never COMPUTED).
    """
    lg = log or logger
    lg.warning(
        "estimate_patent_density: using config default %.2f - "
        "integrate USPTO API (see auditor_config.yaml: default_patent_density) to replace",
        float(config_default),
    )
    return float(config_default)


def calculate_tes_score(
    niche_revenue: Any,
    total_revenue: Any,
    divisional_cagr: Any,
    patent_density: Any,
) -> float:
    if total_revenue is None:
        return 0.0
    try:
        tr = Decimal(str(total_revenue))
    except Exception:
        return 0.0
    if tr <= 0:
        return 0.0
    try:
        nr = Decimal(str(niche_revenue)) if niche_revenue is not None else Decimal("0")
        dc = Decimal(str(divisional_cagr)) if divisional_cagr is not None else Decimal("0")
        pd_ = Decimal(str(patent_density)) if patent_density is not None else Decimal("0")
    except Exception:
        return 0.0
    revenue_ratio = nr / tr
    tes = revenue_ratio * (Decimal("1.0") + dc) * pd_
    clamped = max(Decimal("0.0"), min(tes, Decimal("1000000.0")))
    return float(clamped)


def build_tes_components(
    components: dict[str, Any],
    *,
    auditor_config_path: Path | None = None,
    log: logging.Logger | None = None,
) -> dict[str, Any]:
    """
    Fill patent_density from config default; merge data_confidence with ESTIMATED (patent path).
    """
    lg = log or logger
    cfg = _load_auditor_config_dict(auditor_config_path)
    default_pd = float(cfg.get("default_patent_density", 0.10))

    out = dict(components)
    pd = estimate_patent_density(out, config_default=default_pd, log=lg)
    out["patent_density"] = pd

    fetch_conf = str(out.get("data_confidence", "STUB"))
    out["data_confidence"] = merge_data_confidence(fetch_conf, "ESTIMATED")

    out["tes_score"] = calculate_tes_score(
        out.get("niche_revenue_usd"),
        out.get("total_revenue_usd"),
        out.get("divisional_cagr"),
        pd,
    )
    return out
