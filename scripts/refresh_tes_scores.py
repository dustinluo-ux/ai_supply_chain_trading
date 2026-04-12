"""
Batch TES scoring for watchlist tickers → data/tes_scores.json (D023).

Run: python scripts/refresh_tes_scores.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auditor.financial_fetcher import _load_auditor_config, fetch_tes_components_from_sec
from lib.shared_core.tes_scorer import build_tes_components

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("refresh_tes_scores")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_watchlist() -> list[str]:
    path = ROOT / "config" / "data_config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    wl = (cfg.get("universe_selection") or {}).get("watchlist") or []
    return [str(t).strip() for t in wl if str(t).strip()]


def _compute_multiplier(
    tes_score: float | None,
    tes_min_mult: float,
    tes_score_cap: float,
) -> float:
    if tes_score is None or tes_score == 0.0:
        return 1.0
    s = float(tes_score_cap)
    if s <= 0:
        return 1.0
    raw = tes_min_mult + (1.0 - tes_min_mult) * (float(tes_score) / s)
    return max(tes_min_mult, min(1.0, raw))


def _score_one_us_ticker(
    ticker: str,
    auditor_cfg: dict[str, Any],
) -> dict[str, Any]:
    audited_at = _now_iso()
    try:
        from src.data.sec_filing_parser import SECFilingParser

        parser = SECFilingParser()
        cik = parser._ticker_to_cik(ticker)  # noqa: SLF001
    except Exception as exc:
        return {
            "tes_score": None,
            "multiplier": 1.0,
            "data_confidence": "ERROR",
            "reason": f"CIK resolution failed: {exc}",
            "audited_at": audited_at,
        }
    if not cik:
        return {
            "tes_score": None,
            "multiplier": 1.0,
            "data_confidence": "ERROR",
            "reason": "CIK not resolved for ticker",
            "audited_at": audited_at,
        }
    try:
        raw = fetch_tes_components_from_sec(cik, auditor_config=auditor_cfg)
        built = build_tes_components(raw, auditor_config_path=None)
        ts = built.get("tes_score")
        conf = str(built.get("data_confidence", "STUB"))
        tes_min = float(auditor_cfg.get("tes_min_mult", 0.5))
        cap_s = float(auditor_cfg.get("tes_score_cap", 0.10))
        try:
            ts_f = float(ts) if ts is not None else None
        except (TypeError, ValueError):
            ts_f = None
        mult = _compute_multiplier(ts_f, tes_min, cap_s)
        return {
            "tes_score": ts_f,
            "multiplier": mult,
            "data_confidence": conf,
            "audited_at": audited_at,
        }
    except Exception as exc:
        return {
            "tes_score": None,
            "multiplier": 1.0,
            "data_confidence": "ERROR",
            "reason": str(exc),
            "audited_at": audited_at,
        }


def main() -> int:
    auditor_cfg = _load_auditor_config()
    rel_path = str(auditor_cfg.get("tes_scores_path", "data/tes_scores.json"))
    out_path = Path(rel_path)
    if not out_path.is_absolute():
        out_path = ROOT / out_path

    watchlist = _load_watchlist()
    out: dict[str, Any] = {}
    skipped = 0
    errors = 0

    for raw_t in watchlist:
        t = raw_t.upper()
        audited_at = _now_iso()
        if "." in raw_t:
            out[t] = {
                "tes_score": None,
                "multiplier": 1.0,
                "data_confidence": "SKIPPED",
                "reason": "non-US ticker",
                "audited_at": audited_at,
            }
            skipped += 1
            logger.info(
                "%s tes_score=%s multiplier=%s confidence=%s",
                t,
                out[t]["tes_score"],
                out[t]["multiplier"],
                out[t]["data_confidence"],
            )
            continue

        entry = _score_one_us_ticker(t, auditor_cfg)
        out[t] = entry
        if entry.get("data_confidence") == "ERROR":
            errors += 1
        logger.info(
            "%s tes_score=%s multiplier=%s confidence=%s",
            t,
            entry.get("tes_score"),
            entry.get("multiplier"),
            entry.get("data_confidence"),
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    text = json.dumps(out, indent=2, sort_keys=False)
    if not text or not text.strip():
        raise RuntimeError("refusing to write empty TES scores payload")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(out_path)

    n = len(watchlist)
    print(
        f"Summary: {n} tickers processed, {skipped} skipped (non-US), {errors} errors"
    )
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
