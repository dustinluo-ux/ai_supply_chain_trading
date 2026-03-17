"""
Pod Extension: thin wrapper around rebalance_alpha_sleeve (Dynamic Alpha-Sleeve).
"""
from __future__ import annotations

import pandas as pd


class PodExtension:
    """Wraps rebalance_alpha_sleeve from long_short_optimizer. Max gross 1.6."""

    def generate_weights(
        self,
        scores: pd.Series,
        prices_dict: dict,
        regime_status: dict,
        config: dict,
        scores_df: pd.DataFrame | None = None,
    ) -> pd.Series:
        if scores_df is None:
            scores_df = scores.to_frame().T if isinstance(scores, pd.Series) else pd.DataFrame(scores).T
        try:
            from src.portfolio.long_short_optimizer import rebalance_alpha_sleeve

            return rebalance_alpha_sleeve(scores, scores_df, prices_dict, regime_status, config)
        except Exception as e:
            print(f"[POD_EXTENSION] Error: {e}", flush=True)
            return pd.Series(dtype=float)
