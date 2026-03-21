"""
Aggregate pod weights with sector cap and gross cap.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def aggregate_pod_weights(
    pod_weights: dict[str, pd.Series],
    meta_weights: dict[str, float],
    universe_pillars: dict[str, list],
    sector_cap: float = 0.40,
    gross_cap: float = 1.60,
    veto_threshold: float = 0.25,
    shrinkage_floor: float = 0.50,
    audit_path: Path | str | None = None,
    fsm_audit: dict | None = None,
) -> pd.Series:
    """Weighted sum of pod weights with conflict veto, Bayesian shrinkage, sector/gross caps, and optional audit."""
    # Step 1 — Weighted sum
    all_tickers = set()
    for s in pod_weights.values():
        if isinstance(s, pd.Series):
            all_tickers.update(s.index.tolist())
    raw = {}
    for t in all_tickers:
        v = 0.0
        for pod, s in pod_weights.items():
            if isinstance(s, pd.Series):
                v += meta_weights.get(pod, 0.0) * s.get(t, 0.0)
        raw[t] = v
    raw_series = pd.Series(raw)

    # Step 2 — Conflict detection and directional veto
    raw_series = raw_series.copy()
    conflict_details: list[dict[str, Any]] = []
    for t in raw_series.index:
        if raw_series[t] == 0 or (hasattr(raw_series[t], "__float__") and float(raw_series[t]) == 0.0):
            continue
        pod_contribs = {}
        for pod, s in pod_weights.items():
            if isinstance(s, pd.Series):
                contrib = meta_weights.get(pod, 0.0) * s.get(t, 0.0)
                pod_contribs[pod] = contrib
        has_pos = any(v > 0 for v in pod_contribs.values())
        has_neg = any(v < 0 for v in pod_contribs.values())
        conflict = has_pos and has_neg
        raw_val = float(raw_series[t])
        action = "none"
        confidence = None
        if not conflict:
            conflict_details.append({"ticker": t, "action": action, "confidence": confidence, "pod_contributions": pod_contribs})
            continue
        gross_contribution = sum(abs(v) for v in pod_contribs.values())
        confidence = abs(raw_val) / gross_contribution if gross_contribution > 0 else 1.0
        if confidence < veto_threshold:
            raw_series.loc[t] = 0.0
            action = "vetoed"
        else:
            action = "kept"
        conflict_details.append({"ticker": t, "action": action, "confidence": confidence, "pod_contributions": pod_contribs})

    n_conflicts = sum(1 for d in conflict_details if d["action"] in ("vetoed", "kept"))
    n_vetoed = sum(1 for d in conflict_details if d["action"] == "vetoed")
    vetoed_tickers = [d["ticker"] for d in conflict_details if d["action"] == "vetoed"]
    logger.info("[AGGREGATOR] conflicts=%d vetoed=%d", n_conflicts, n_vetoed)

    # Step 3 — Bayesian shrinkage
    meta_vals = [w for w in meta_weights.values() if w > 0]
    nonzero_pods = len(meta_vals)
    H = 0.0
    for w in meta_vals:
        if w > 0:
            H -= w * math.log(w)
    H_max = math.log(nonzero_pods) if nonzero_pods > 0 else 0.0
    if H_max <= 0 or nonzero_pods <= 1:
        lambda_raw = 1.0
    else:
        lambda_raw = max(0.0, min(1.0, 1.0 - H / H_max))
    shrinkage_lambda = shrinkage_floor + (1.0 - shrinkage_floor) * lambda_raw
    raw_series = raw_series * shrinkage_lambda
    logger.info("[AGGREGATOR] shrinkage lambda=%.3f entropy=%.4f", shrinkage_lambda, H)

    # Steps 4–6 — sector cap, gross cap, net sanity (unchanged)
    for pillar, tickers in universe_pillars.items():
        in_pillar = [t for t in tickers if t in raw_series.index]
        if not in_pillar:
            continue
        pillar_gross = raw_series.reindex(in_pillar).fillna(0).abs().sum()
        if pillar_gross > sector_cap and pillar_gross > 0:
            scale = sector_cap / pillar_gross
            for t in in_pillar:
                raw_series.loc[t] = raw_series.loc[t] * scale

    gross = raw_series.abs().sum()
    if gross > gross_cap and gross > 0:
        raw_series = raw_series * (gross_cap / gross)

    net = raw_series.sum()
    if net < 0.85 or net > 1.15:
        logger.warning("[AGGREGATOR] net_exposure=%.3f outside [0.85, 1.15]", net)

    # Step 7 — Write audit record
    if audit_path is not None:
        try:
            audit_path = Path(audit_path)
            conflict_details_audit = [d for d in conflict_details if d["action"] != "none"]
            audit_dict = {
                "as_of": datetime.now(timezone.utc).isoformat(),
                "n_conflicts": n_conflicts,
                "n_vetoed": n_vetoed,
                "vetoed_tickers": vetoed_tickers,
                "shrinkage_lambda": shrinkage_lambda,
                "meta_entropy": H,
                "conflict_details": conflict_details_audit,
            }
            if fsm_audit:
                audit_dict["fsm_track_d"] = fsm_audit
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(json.dumps(audit_dict, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("[AGGREGATOR] audit write failed: %s", e)

    return raw_series
