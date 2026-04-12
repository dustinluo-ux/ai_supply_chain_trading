"""
SEC company facts → TES financial inputs (ADR D-TES-STUBS).
Company facts: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
Segment (dimensional) XBRL is not exposed here — niche revenue uses config ratio only.
"""
from __future__ import annotations

import logging
import os
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional

import requests
import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_AUDITOR_CONFIG_PATH = _ROOT / "config" / "auditor_config.yaml"


def _load_auditor_config(path: Path | None = None) -> dict[str, Any]:
    p = path or _AUDITOR_CONFIG_PATH
    defaults: dict[str, Any] = {
        "niche_revenue_fraction": 0.15,
        "default_patent_density": 0.10,
    }
    if not p.exists():
        return defaults
    with open(p, "r", encoding="utf-8") as f:
        merged = {**defaults, **(yaml.safe_load(f) or {})}
    return merged


def _default_tes_components_dict() -> dict[str, Any]:
    return {
        "total_revenue_usd": 0.0,
        "niche_revenue_usd": 0.0,
        "niche_revenue_source": "NONE",
        "divisional_cagr": 0.0,
        "patent_density": 0.0,
        "data_confidence": "STUB",
    }


def _classify_data_confidence(
    total_revenue: float,
    divisional_cagr: float,
    niche_revenue_source: str,
) -> str:
    if total_revenue <= 0:
        return "STUB"
    if total_revenue > 0 and divisional_cagr != 0.0 and niche_revenue_source != "CONFIG_RATIO":
        return "COMPUTED"
    if total_revenue > 0:
        return "ESTIMATED"
    return "STUB"


_REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]


def _sec_headers() -> dict[str, str]:
    ua = os.environ.get("SEC_EDGAR_USER_AGENT", "AI-SupplyChain research@example.com")
    return {
        "User-Agent": ua,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    }


def _parse_latest_revenue_usd(facts_payload: dict[str, Any], cik: str) -> float:
    """
    Latest annual 10-K FY USD revenue; priority-ordered GAAP tags (first match wins).
    """
    try:
        us_gaap = facts_payload.get("facts", {}).get("us-gaap", {})
        cik10 = str(cik).strip().lstrip("0").zfill(10)
        for tag in _REVENUE_TAGS:
            block = us_gaap.get(tag)
            if not block:
                continue
            units = block.get("units", {}).get("USD", [])
            rows = [
                r
                for r in units
                if str(r.get("form", "")).upper() == "10-K" and str(r.get("fp", "")).upper() == "FY"
            ]
            if not rows:
                continue
            sorted_rows = sorted(rows, key=lambda r: str(r.get("end", "") or ""))
            val = sorted_rows[-1].get("val")
            if val is None:
                continue
            logger.info("_parse_latest_revenue_usd: matched tag '%s' for CIK %s", tag, cik10)
            return float(val)  # boundary conversion — Decimal math applied downstream
    except (TypeError, KeyError, IndexError, ValueError):
        return 0.0
    return 0.0


class SecClient:
    """Minimal SEC data.sec.gov client (company facts only; no second API)."""

    def __init__(self, min_interval_s: float = 0.11) -> None:
        self._min_interval = min_interval_s
        self._last = 0.0
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(var, None)

    def _rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last = time.time()

    def get_company_facts(self, cik: str) -> Optional[dict[str, Any]]:
        """
        GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
        Returns full JSON or None on failure.
        """
        cik10 = str(cik).strip().lstrip("0").zfill(10)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
        self._rate_limit()
        try:
            r = requests.get(url, headers=_sec_headers(), timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning("get_company_facts failed for CIK %s: %s", cik10, e)
            return None


def fetch_tes_components_from_sec(
    cik: str,
    *,
    auditor_config: dict[str, Any] | None = None,
    client: SecClient | None = None,
) -> dict[str, Any]:
    """
    Build TES financial component dict from SEC company facts + config ratio for niche revenue.
    """
    cfg = auditor_config or _load_auditor_config()
    niche_frac = float(cfg.get("niche_revenue_fraction", 0.15))

    sec = client or SecClient()
    facts = sec.get_company_facts(cik)
    if not facts:
        return _default_tes_components_dict()

    cik10 = str(cik).strip().lstrip("0").zfill(10)
    total_revenue = _parse_latest_revenue_usd(facts, cik10)
    divisional_cagr = 0.0

    niche_revenue_source = "CONFIG_RATIO"
    if total_revenue <= 0:
        niche_revenue_usd_dec = Decimal("0.00")
    else:
        niche_revenue_usd_dec = (
            Decimal(str(total_revenue)) * Decimal(str(niche_frac))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    niche_revenue_usd = float(niche_revenue_usd_dec)  # boundary conversion — Decimal arithmetic complete; float for schema compat

    data_confidence = _classify_data_confidence(
        total_revenue,
        divisional_cagr,
        niche_revenue_source,
    )

    return {
        "total_revenue_usd": total_revenue,
        "niche_revenue_usd": niche_revenue_usd,
        "niche_revenue_source": niche_revenue_source,
        "divisional_cagr": divisional_cagr,
        "patent_density": 0.0,
        "data_confidence": data_confidence,
    }
