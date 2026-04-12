"""
Auditor — Supply Chain Scraper
Port of alpha_scout/src/excavation/supply_chain_scraper.py.
Queries SEC EDGAR for 10-K filings; extracts Competition and Supply Chain sections.
Returns a dict shaped to THESIS_SCHEMA.json §auditor.supply_chain.
Config from auditor_config.yaml. No Pydantic for inter-module output.
"""

import logging
import re
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "auditor_config.yaml"

_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_EDGAR_FILING_BASE = "https://www.sec.gov"

_SECTION_PATTERN = re.compile(
    r"\bcompetition\b|\bsupply\s+chain\b",
    re.IGNORECASE,
)


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_headers() -> dict:
    _cfg = _load_config()
    return {
        "User-Agent": _cfg.get("sec_edgar_user_agent", ""),
        "Accept-Encoding": "gzip, deflate",
    }


def _search_edgar(query: str) -> list[dict]:
    """
    Search EDGAR full-text search for 10-K filings matching query.
    Returns list of filing dicts with keys: entity_name, filing_date, document_url.
    Returns [] on any error. Uses config for timeout, start date, max_results.
    """
    _cfg = _load_config()
    timeout = _cfg.get("request_timeout_seconds", 15)
    startdt = _cfg.get("sec_search_start_date", "2022-01-01")
    max_results = _cfg.get("sec_max_results", 3)

    params = {
        "q": query,
        "forms": "10-K",
        "dateRange": "custom",
        "startdt": startdt,
    }
    try:
        resp = requests.get(
            _EDGAR_SEARCH_URL,
            params=params,
            headers=_get_headers(),
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(
                "_search_edgar: non-200 status %s for query='%s'",
                resp.status_code,
                query[:50],
            )
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("_search_edgar: %s — %s", type(exc).__name__, exc)
        return []

    hits = data.get("hits", {}).get("hits", [])
    results: list[dict] = []
    for hit in hits[:max_results]:
        src = hit.get("_source", {})
        entity_name = src.get("entity_name", "")
        filing_date = src.get("file_date", "")
        file_url = src.get("file_url", "")
        document_url = (
            (_EDGAR_FILING_BASE + file_url) if file_url else ""
        )
        results.append({
            "entity_name": entity_name,
            "filing_date": filing_date,
            "document_url": document_url,
        })
    return results


def _extract_sections(html_text: str, max_chars: int) -> dict[str, str]:
    """
    Parse 10-K HTML and extract text from sections whose headings match
    "Competition" or "Supply Chain" (case-insensitive).
    Returns {"competition": "...", "supply_chain": "..."}.
    """
    text = html_text[:max_chars]
    soup = BeautifulSoup(text, "html.parser")
    out: dict[str, str] = {"competition": "", "supply_chain": ""}
    tag_re = re.compile(r"^h[1-4]$", re.IGNORECASE)
    heading_like = soup.find_all(tag_re)
    for elem in heading_like:
        elem_text = elem.get_text(separator=" ", strip=True)
        if not _SECTION_PATTERN.search(elem_text):
            continue
        key = (
            "competition"
            if re.search(r"\bcompetition\b", elem_text, re.IGNORECASE)
            else "supply_chain"
        )
        if out[key]:
            continue
        parts: list[str] = []
        sibling = elem.find_next_sibling()
        for _ in range(5):
            if sibling is None:
                break
            parts.append(sibling.get_text(separator=" ", strip=True))
            sibling = sibling.find_next_sibling()
        out[key] = " ".join(parts)
    for elem in soup.find_all(["p", "b"]):
        elem_text = elem.get_text(separator=" ", strip=True)
        if not _SECTION_PATTERN.search(elem_text):
            continue
        key = (
            "competition"
            if re.search(r"\bcompetition\b", elem_text, re.IGNORECASE)
            else "supply_chain"
        )
        if out[key]:
            continue
        parts = []
        sibling = elem.find_next_sibling()
        for _ in range(5):
            if sibling is None:
                break
            parts.append(sibling.get_text(separator=" ", strip=True))
            sibling = sibling.find_next_sibling()
        out[key] = " ".join(parts)
    return out


def map_shipping_routes(components: list[str]) -> list[str]:
    """
    STUB — Map components to likely shipping routes.
    Internal only; not part of THESIS_SCHEMA §auditor.supply_chain return.
    """
    logger.warning(
        "map_shipping_routes: stub — integrate Flexport/Freightos API to populate"
    )
    return [
        "STUB: China (Shenzhen) → USA (Los Angeles) — sea freight",
        "STUB: South Korea (Busan) → Europe (Rotterdam) — sea freight",
        "STUB: Japan (Yokohama) → USA (Long Beach) — sea freight",
    ]


def _default_supply_chain_dict() -> dict:
    """Return empty supply_chain shape per THESIS_SCHEMA.json §auditor.supply_chain."""
    return {
        "primary_company": None,
        "suppliers": [],
        "customers": [],
        "competitors": [],
        "sec_filings_used": [],
    }


def scrape_supply_chain(query: str, components: list[str]) -> dict:
    """
    Full supply chain data assembly: SEC filing scrape + internal shipping stub.
    Returns dict conforming to THESIS_SCHEMA.json §auditor.supply_chain.
    Caller should check internal scrape_status (e.g. via exception or return
    convention); this function does not raise — on failure returns default dict
    with primary_company=None and empty lists. Orchestrator must append to
    audit_failures when scrape failed (e.g. empty sec_filings_used and no primary_company).
    """
    _cfg = _load_config()
    timeout = _cfg.get("request_timeout_seconds", 15)
    max_filing_chars = _cfg.get("sec_max_filing_chars", 500000)
    max_competitors = _cfg.get("max_competitors", 10)

    filings = _search_edgar(query)
    if not filings:
        return _default_supply_chain_dict()

    filing = filings[0]
    primary_company = filing.get("entity_name") or None
    document_url = filing.get("document_url", "")

    # sec_filings_used: accession numbers preferred; fallback to document_url (THESIS_SCHEMA)
    sec_filings_used: list[str] = []
    if document_url:
        # Try to extract accession from URL (e.g. .../0001234567-24-000001/...)
        acc_match = re.search(r"/(\d{10}-\d{2}-\d{6})/", document_url)
        if acc_match:
            sec_filings_used.append(acc_match.group(1))
        else:
            sec_filings_used.append(document_url)

    if not document_url:
        return {
            "primary_company": primary_company,
            "suppliers": [],
            "customers": [],
            "competitors": [],
            "sec_filings_used": sec_filings_used,
        }

    try:
        resp = requests.get(
            document_url,
            headers=_get_headers(),
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(
                "scrape_supply_chain: status %s for %s",
                resp.status_code,
                document_url[:80],
            )
            return {
                "primary_company": primary_company,
                "suppliers": [],
                "customers": [],
                "competitors": [],
                "sec_filings_used": sec_filings_used,
            }
        sections = _extract_sections(resp.text, max_filing_chars)
    except Exception as exc:
        logger.warning(
            "scrape_supply_chain: %s — %s",
            type(exc).__name__,
            exc,
        )
        return {
            "primary_company": primary_company,
            "suppliers": [],
            "customers": [],
            "competitors": [],
            "sec_filings_used": sec_filings_used,
        }

    competition_text = sections.get("competition", "")
    comp_matches = re.findall(
        r'"([^"]+)"|([A-Z][a-zA-Z]+ (?:Inc|Corp|Ltd|LLC|AG|SE|GmbH)[^,\n]*)',
        competition_text,
    )
    competitors: list[dict] = []
    seen: set[str] = set()
    for m in comp_matches:
        for g in m:
            if g:
                name = g.strip()
                if name and name not in seen:
                    seen.add(name)
                    competitors.append({"name": name, "ticker": None})
                    if len(competitors) >= max_competitors:
                        break
        if len(competitors) >= 10:
            break

    # Stub: shipping routes not in schema output; used internally only
    map_shipping_routes(components)

    logger.info(
        "scrape_supply_chain: found %d competitors, primary_company=%s",
        len(competitors),
        primary_company,
    )
    return {
        "primary_company": primary_company,
        "suppliers": [],
        "customers": [],
        "competitors": competitors,
        "sec_filings_used": sec_filings_used,
    }
