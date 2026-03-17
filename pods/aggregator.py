"""
Aggregate pod weights with sector cap and gross cap.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def aggregate_pod_weights(
    pod_weights: dict[str, pd.Series],
    meta_weights: dict[str, float],
    universe_pillars: dict[str, list],
    sector_cap: float = 0.40,
    gross_cap: float = 1.60,
) -> pd.Series:
    # 1. Weighted sum: raw[t] = Σ meta_weights[pod] × pod_weights[pod].get(t, 0.0)
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

    # 2. Sector cap: for each pillar, if pillar_gross > sector_cap, scale down
    for pillar, tickers in universe_pillars.items():
        in_pillar = [t for t in tickers if t in raw_series.index]
        if not in_pillar:
            continue
        pillar_gross = raw_series.reindex(in_pillar).fillna(0).abs().sum()
        if pillar_gross > sector_cap and pillar_gross > 0:
            scale = sector_cap / pillar_gross
            for t in in_pillar:
                raw_series.loc[t] = raw_series.loc[t] * scale

    # 3. Gross cap: if gross > gross_cap, scale all by gross_cap / gross
    gross = raw_series.abs().sum()
    if gross > gross_cap and gross > 0:
        raw_series = raw_series * (gross_cap / gross)

    # 4. Net sanity: if net outside [0.85, 1.15], log WARNING
    net = raw_series.sum()
    if net < 0.85 or net > 1.15:
        logger.warning("[AGGREGATOR] net_exposure=%.3f outside [0.85, 1.15]", net)

    # 5. Return pd.Series(raw)
    return raw_series
