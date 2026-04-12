"""
AuditOrchestrator — full auditor pipeline (BOM → supply chain → financials → TES → cap → hash).

Canonical documentation hub: docs/INDEX.md (canonical specs live under docs/).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from auditor.bom_decomposer import BOMDecompositionError, decompose_bottleneck
from auditor.financial_fetcher import fetch_tes_components_from_sec
from auditor.market_cap_lookup import get_market_cap_usd
from auditor.supply_chain_scraper import scrape_supply_chain
from lib.shared_core.tes_scorer import build_tes_components, calculate_tes_score
from tdo_validator import compute_audit_hash

CORE_STAGES: Final[tuple[str, ...]] = (
    "BOM_DECOMPOSE",
    "SUPPLY_CHAIN",
    "FINANCIAL_FETCH",
    "TES_SCORE",
)


def _financial_fallback() -> dict[str, Any]:
    """Same shape as auditor.financial_fetcher._default_tes_components_dict (no SEC data)."""
    return {
        "total_revenue_usd": 0.0,
        "niche_revenue_usd": 0.0,
        "niche_revenue_source": "NONE",
        "divisional_cagr": 0.0,
        "patent_density": 0.0,
        "data_confidence": "STUB",
    }


def _guess_ticker(company_name: str) -> str | None:
    """Best-effort ticker from company title (no full name→ticker DB)."""
    n = (company_name or "").strip().lower()
    if "on semiconductor" in n:
        return "ON"
    if "apple" in n and "inc" in n:
        return "AAPL"
    return None


def _resolve_cik_sync(company_name: str) -> str | None:
    """Resolve 10-digit CIK for SEC company facts API."""
    ticker = _guess_ticker(company_name)
    if not ticker:
        return None
    try:
        from src.data.sec_filing_parser import SECFilingParser

        parser = SECFilingParser()
        cik = parser._ticker_to_cik(ticker)  # noqa: SLF001 — reuse SEC CIK cache
        return cik
    except Exception as exc:
        logger.warning("_resolve_cik_sync: %s — %s", type(exc).__name__, exc)
        return None


class SECFinancialFetcher:
    """
    Stage 3: company name → CIK → Phase 1 `fetch_tes_components_from_sec` dict
    (niche_revenue_usd, total_revenue_usd, divisional_cagr, data_confidence: COMPUTED|ESTIMATED|STUB).
    """

    async def fetch_financials(self, company_name: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        cik = await loop.run_in_executor(None, partial(_resolve_cik_sync, company_name))
        if not cik:
            return _financial_fallback()
        return await loop.run_in_executor(
            None,
            partial(fetch_tes_components_from_sec, cik),
        )


def _supply_chain_stage_failed(sc: dict[str, Any]) -> bool:
    """Heuristic: no filings and no primary company and no competitors."""
    if not sc:
        return True
    no_primary = not sc.get("primary_company")
    no_filings = not sc.get("sec_filings_used")
    no_competitors = not sc.get("competitors")
    return bool(no_primary and no_filings and no_competitors)


def _financial_stage_failed(fin: dict[str, Any]) -> bool:
    tr = fin.get("total_revenue_usd")
    try:
        return tr is None or float(tr) <= 0.0
    except (TypeError, ValueError):
        return True


def _tes_stage_failed(built: dict[str, Any]) -> bool:
    """Stage failure = exception path only; tes_score == 0 is allowed (warning elsewhere)."""
    return built.get("tes_score") is None


def _build_tes_components_schema_dict(built: dict[str, Any], company_name: str, ticker: str | None) -> dict[str, Any]:
    """Shape `auditor.tes_components` per THESIS_SCHEMA (niche_revenue_ratio + data_confidence)."""
    nr = built.get("niche_revenue_usd")
    tr = built.get("total_revenue_usd")
    try:
        ratio = (float(nr) / float(tr)) if tr not in (None, 0, 0.0) else None
    except (TypeError, ValueError, ZeroDivisionError):
        ratio = None
    return {
        "primary_ticker": ticker,
        "company_name": company_name or None,
        "niche_revenue_usd": nr,
        "total_revenue_usd": tr,
        "niche_revenue_ratio": ratio,
        "divisional_cagr": built.get("divisional_cagr"),
        "patent_density": built.get("patent_density"),
        "data_confidence": built.get("data_confidence"),
        "data_vintage": None,
    }


class AuditOrchestrator:
    """Runs core audit stages; sets phase AUDITED vs AUDIT_FAILED; seals audit_hash last."""

    def __init__(self, *, auditor_version: str = "1.0.0") -> None:
        self._auditor_version = auditor_version

    async def audit(self, tdo: dict[str, Any]) -> dict[str, Any]:
        scout = tdo.get("scout") or {}
        title = str(scout.get("title") or "")
        bottleneck = str(scout.get("bottleneck_description") or "")
        company_name = title or bottleneck or "Unknown"

        stage_failed: dict[str, bool] = {k: True for k in CORE_STAGES}
        bom_components: list[str] = []
        supply_chain: dict[str, Any] = {}
        financial: dict[str, Any] = {}
        built: dict[str, Any] = {}
        ticker = _guess_ticker(company_name)

        # Stage 1 — BOM
        try:
            if bottleneck.strip():
                bom_components = await decompose_bottleneck(bottleneck)
                stage_failed["BOM_DECOMPOSE"] = not bool(bom_components)
            else:
                stage_failed["BOM_DECOMPOSE"] = True
        except BOMDecompositionError:
            logger.warning("BOM_DECOMPOSE failed; continuing with empty BOM", exc_info=False)
            bom_components = []
            stage_failed["BOM_DECOMPOSE"] = True

        # Stage 2 — Supply chain (sync; offload thread)
        loop = asyncio.get_running_loop()
        try:
            supply_chain = await loop.run_in_executor(
                None,
                partial(scrape_supply_chain, title or company_name, bom_components or []),
            )
            stage_failed["SUPPLY_CHAIN"] = _supply_chain_stage_failed(supply_chain)
        except Exception:
            logger.exception("SUPPLY_CHAIN stage raised")
            supply_chain = {
                "primary_company": None,
                "suppliers": [],
                "customers": [],
                "competitors": [],
                "sec_filings_used": [],
            }
            stage_failed["SUPPLY_CHAIN"] = True

        # Stage 3 — Financials
        try:
            financial = await SECFinancialFetcher().fetch_financials(company_name)
            stage_failed["FINANCIAL_FETCH"] = _financial_stage_failed(financial)
        except Exception:
            logger.exception("FINANCIAL_FETCH stage raised")
            financial = _financial_fallback()
            stage_failed["FINANCIAL_FETCH"] = True

        # Stage 4 — TES (build_tes_components sets tes_score; then scalar recompute per spec)
        try:
            built = build_tes_components(dict(financial))
            tes_scalar = calculate_tes_score(
                built.get("niche_revenue_usd"),
                built.get("total_revenue_usd"),
                built.get("divisional_cagr"),
                built.get("patent_density"),
            )
            built["tes_score"] = tes_scalar
            stage_failed["TES_SCORE"] = _tes_stage_failed(built)
        except Exception:
            logger.exception("TES_SCORE stage raised")
            built = {"tes_score": None}
            stage_failed["TES_SCORE"] = True

        # Stage 5 — Market cap + 50B rule
        cap_raw = None
        if ticker:
            cap_raw = await loop.run_in_executor(
                None, partial(get_market_cap_usd, ticker)
            )
        cap_rule_passed = (
            cap_raw is not None and float(cap_raw) < 50_000_000_000.0
        )

        core_all_failed = all(stage_failed[k] for k in CORE_STAGES)
        new_phase = "AUDIT_FAILED" if core_all_failed else "AUDITED"

        tes_score_final = float(built.get("tes_score") or 0.0)
        tes_components = _build_tes_components_schema_dict(built, company_name, ticker)

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        auditor: dict[str, Any] = {
            "audit_hash": "",
            "audited_at": now,
            "auditor_version": self._auditor_version,
            "tes_score": tes_score_final,
            "tes_components": tes_components,
            "market_cap_usd": cap_raw,
            "cap_rule_passed": bool(cap_rule_passed),
            "bom_components": bom_components,
            "supply_chain": supply_chain,
            "core_stage_failures": stage_failed,
        }
        auditor["audit_hash"] = compute_audit_hash(auditor)

        tdo["auditor"] = auditor
        tdo["phase"] = new_phase
        tdo["last_updated_at"] = now

        if tes_score_final == 0.0:
            logger.warning("tes_score is 0.0 after audit (recorded); phase=%s", new_phase)

        return tdo


def run_tes_build_from_sec(
    cik: str,
    *,
    auditor_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Module-level helper for tests: CIK → SEC components → merged TES dict (tes_score)."""
    raw = fetch_tes_components_from_sec(cik, auditor_config=auditor_config)
    return build_tes_components(raw, auditor_config_path=None)
