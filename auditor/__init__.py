"""Auditor package: SEC-backed financial inputs for TES."""

from auditor.financial_fetcher import SecClient, fetch_tes_components_from_sec

__all__ = ["SecClient", "fetch_tes_components_from_sec"]
