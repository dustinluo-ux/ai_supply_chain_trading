"""
PortfolioEngine: build(as_of_date, gated_scores, context) -> Intent.
P0: Single canonical sizing via _build_backtest() (rank by score, top-N, inverse-vol).
Weekly/execution path uses same weights; intent.mode set to "execution".
"""
from __future__ import annotations

import pandas as pd

from src.core.intent import Intent
from src.core.types import Context


class PortfolioEngine:
    """
    Builds target portfolio (Intent) from gated scores.
    """

    def build(
        self,
        as_of_date: pd.Timestamp,
        gated_scores: dict[str, float],
        context: Context,
    ) -> Intent:
        """
        Returns Intent: tickers (ordered), weights (ticker -> weight), mode.
        P0: Single canonical sizing via _build_backtest() (ranking, top-N, inverse-vol).
        """
        intent = self._build_backtest(gated_scores, context)
        if context.get("path") == "weekly":
            intent = Intent(tickers=intent.tickers, weights=intent.weights, mode="execution", metadata=getattr(intent, "metadata", None))
        return intent

    def _build_backtest(
        self,
        gated_scores: dict[str, float],
        context: Context,
    ) -> Intent:
        """Rank by gated_scores, take top_n, inverse-vol weights using atr_norms."""
        top_n = context.get("top_n", 3)
        atr_norms = context.get("atr_norms") or {}
        tickers_universe = context.get("tickers") or list(gated_scores.keys())

        if all(v == 0.0 for v in gated_scores.values()):
            return Intent(tickers=[], weights={t: 0.0 for t in tickers_universe}, mode="backtest")
        ranked = sorted(gated_scores.items(), key=lambda x: -x[1])[:top_n]
        if not ranked:
            weights_dict = {t: 0.0 for t in tickers_universe}
            return Intent(tickers=[], weights=weights_dict, mode="backtest")

        inv_vol = [1.0 / (max(atr_norms.get(t, 0.5), 1e-6)) for t, _ in ranked]
        total_inv = sum(inv_vol)
        weights_list = [x / total_inv for x in inv_vol]
        intent_tickers = [t for t, _ in ranked]
        intent_weights = {t: w for (t, _), w in zip(ranked, weights_list)}

        for t in tickers_universe:
            if t not in intent_weights:
                intent_weights[t] = 0.0

        return Intent(tickers=intent_tickers, weights=intent_weights, mode="backtest")

    def _build_weekly(
        self,
        gated_scores: dict[str, float],
        context: Context,
    ) -> Intent:
        """Deprecated: no longer used for sizing. P0 canonical sizing is _build_backtest(). Equal weight 1/N."""
        top_n = context.get("top_n", 10)
        tickers = list(gated_scores.keys())[:top_n]
        if not tickers:
            return Intent(tickers=[], weights={}, mode="execution")
        w = 1.0 / len(tickers)
        weights = {t: w for t in tickers}
        return Intent(tickers=tickers, weights=weights, mode="execution")
