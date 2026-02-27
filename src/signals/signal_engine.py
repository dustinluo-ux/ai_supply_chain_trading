"""
SignalEngine: generate(as_of_date, universe, data_context) -> (scores, aux).

Canonical signal generation orchestrator.
- Backtest path: technical_library + optional news_engine + optional SentimentPropagator.
- Weekly path: SignalCombiner.get_top_stocks (precomputed signals).

Blending formula (STRATEGY_LOGIC.md §2):
    Final_Score = (1 - news_weight) * Technical_Score + news_weight * News_Composite

SentimentPropagator (STRATEGY_LOGIC.md §2.1):
    When enable_propagation=True, sentiment propagates through supply chain
    relationships (Tier 1: 0.5-0.8, Tier 2: 0.2, max depth 2) to enrich
    the news_composite before it is blended with the technical score.
    If propagation data is missing, news_composite defaults to 0.5 (Neutral).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.types import DataContext
from src.utils.config_manager import get_config

logger = logging.getLogger(__name__)


_SMA_KILL_SWITCH_DAYS = 200  # SPY vs 200-SMA binary regime fallback


class SignalEngine:
    """
    Generates ticker-level scores for a given date.
    Returns (scores: dict[str, float], aux: dict) where aux carries atr_norms,
    regime_state, news_weight_used, buzz_by_ticker, etc.
    """

    def __init__(self) -> None:
        self._propagator: Any = None  # Lazy-init SentimentPropagator

    # ------------------------------------------------------------------
    # Lazy propagator
    # ------------------------------------------------------------------
    def _get_propagator(self) -> Any:
        """Lazy-initialize SentimentPropagator.  Returns None if DB not found."""
        if self._propagator is not None:
            return self._propagator
        try:
            from src.signals.sentiment_propagator import SentimentPropagator

            cfg = get_config()
            tier1 = float(cfg.get_param("strategy_params.propagation.tier_1_weight", 0.5))
            tier2 = float(cfg.get_param("strategy_params.propagation.tier_2_weight", 0.2))
            self._propagator = SentimentPropagator(tier1_weight=tier1, tier2_weight=tier2)
            return self._propagator
        except Exception as exc:
            logger.warning("SentimentPropagator init failed (supply chain DB missing?): %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def generate(
        self,
        as_of_date: pd.Timestamp,
        universe: list[str],
        data_context: DataContext,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """
        Returns (scores, aux).
        scores: ticker -> master score (or composite score).
        aux: atr_norms, regime_state, news_weight_used, optional buzz_by_ticker, etc.
        """
        if data_context.get("source") == "precomputed":
            return self._generate_weekly(as_of_date, universe, data_context)
        return self._generate_backtest(as_of_date, universe, data_context)

    # ------------------------------------------------------------------
    # Backtest path (three-phase when propagation is active)
    # ------------------------------------------------------------------
    def _generate_backtest(
        self,
        as_of_date: pd.Timestamp,
        universe: list[str],
        data_context: DataContext,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Backtest path: technical indicators + optional news + optional propagation."""
        
        # --- 2. LOCAL IMPORTS ---
        from src.signals.technical_library import (
            OHLCV_COLS,
            calculate_all_indicators,
            compute_signal_strength,
        )

        # --- 3. CONFIG AND LOGIC ---
        cfg = get_config()
        min_required_days: int = cfg.get_param(
            "strategy_params.warmup.min_required_days",
        )

        prices_dict = data_context.get("prices_dict") or {}
        weight_mode = data_context.get("weight_mode", "fixed")
        regime_state = data_context.get("regime_state")
        spy_above_sma200 = data_context.get("spy_above_sma200")
        category_weights_override = data_context.get("category_weights_override")
        news_dir = data_context.get("news_dir")
        sector_sentiments_this_week = data_context.get("sector_sentiments_this_week") or {}
        signal_horizon_days_this_week = data_context.get("signal_horizon_days_this_week", 5)
        news_weight_used = data_context.get("news_weight_used", 0.0)
        ensure_ohlcv_fn = data_context.get("ensure_ohlcv")
        enable_propagation = data_context.get("enable_propagation", False)
        logger.info(
            "Propagation enabled: %s | news_dir: %s | news_weight: %.2f",
            enable_propagation, news_dir is not None, news_weight_used,
        )

        # ==============================================================
        # Regime resolution (Stage 3 wiring)
        # ==============================================================
        # Pre-resolve category weights when weight_mode is "regime".
        # 1. Use regime_state from data_context if caller already detected it.
        # 2. Otherwise auto-detect from SPY in prices_dict (HMM → SMA-200).
        # 3. Load the matching weight set from technical_master_score.yaml
        #    via ConfigManager, and pass as category_weights_override so
        #    compute_signal_strength uses them directly.
        # 4. If SPY data is missing, fall back to fixed weights + warning.
        resolved_category_weights = category_weights_override  # rolling/ml already set

        if weight_mode == "regime" and resolved_category_weights is None:
            effective_regime = regime_state
            effective_spy_above = spy_above_sma200

            # Auto-detect if caller didn't provide regime data
            if effective_regime is None and effective_spy_above is None:
                regime_ticker = str(
                    data_context.get("regime_ticker", "SPY")
                )
                effective_regime, effective_spy_above = self._detect_regime(
                    prices_dict, as_of_date, regime_ticker=regime_ticker,
                )

            # Resolve weights from ConfigManager
            resolved_category_weights = self._resolve_regime_weights(
                cfg, effective_regime, effective_spy_above,
            )

            if resolved_category_weights is not None:
                regime_state = effective_regime  # update for aux output
            else:
                logger.warning(
                    "Regime weight resolution failed for %s — "
                    "falling back to fixed weights",
                    as_of_date,
                )

        week_scores: dict[str, float] = {}
        atr_norms: dict[str, float] = {}
        buzz_by_ticker: dict[str, bool] = {}
        enriched_composites: dict[str, float] = {}

        # ==============================================================
        # Phase 1: Compute indicators + base news composites
        # ==============================================================
        cached: dict[str, dict[str, Any]] = {}  # t -> {row, news_composite, sentiment_current}

        for t in universe:
            if t not in prices_dict:
                week_scores[t] = 0.5
                atr_norms[t] = 0.5
                continue
            df = prices_dict[t]
            slice_df = df[df.index <= as_of_date]
            if slice_df.empty or len(slice_df) < min_required_days:
                logger.info(
                    "%s skipped: %d days found, %d required (as_of=%s)",
                    t, len(slice_df), min_required_days,
                    as_of_date.strftime("%Y-%m-%d") if hasattr(as_of_date, "strftime") else as_of_date,
                )
                week_scores[t] = 0.5
                atr_norms[t] = 0.5
                continue
            if ensure_ohlcv_fn:
                slice_df = ensure_ohlcv_fn(slice_df)
            if not all(c in slice_df.columns for c in OHLCV_COLS):
                week_scores[t] = 0.5
                atr_norms[t] = 0.5
                continue
            try:
                ind = calculate_all_indicators(slice_df)
                row = ind.iloc[-1]
                row_sizing = ind.iloc[-2] if len(ind) >= 2 else row
                atr_val = (
                    float(row_sizing.get("atr_norm", 0.5))
                    if "atr_norm" in row_sizing.index
                    else 0.5
                )
                atr_norms[t] = atr_val

                # Base news composite
                news_composite_val = None
                sentiment_current = 0.5  # default neutral
                new_network_links: list = []
                if news_dir is not None:
                    try:
                        from src.signals.news_engine import (
                            DEFAULT_SECTOR_MAP,
                            compute_news_composite,
                        )

                        sector_map_use = DEFAULT_SECTOR_MAP if universe else {}
                        llm_enabled = data_context.get("llm_enabled", True)
                        r = compute_news_composite(
                            Path(news_dir),
                            t,
                            as_of_date,
                            sector_sentiments=sector_sentiments_this_week or None,
                            sector_map=sector_map_use,
                            signal_horizon_days=signal_horizon_days_this_week,
                            llm_enabled=llm_enabled,
                        )
                        news_composite_val = r.get("news_composite", 0.5)
                        sentiment_current = r.get("sentiment_current", 0.5)
                        buzz_by_ticker[t] = r.get("buzz_active", False)
                        new_network_links = r.get("new_network_links", []) or []
                    except Exception:
                        news_composite_val = 0.5
                        buzz_by_ticker[t] = False

                cached[t] = {
                    "row": row,
                    "news_composite": news_composite_val,
                    "sentiment_current": sentiment_current,
                    "new_network_links": new_network_links,
                }
            except Exception:
                week_scores[t] = 0.5
                atr_norms[t] = 0.5

        # Phase 1 summary
        n_buzz = sum(1 for v in buzz_by_ticker.values() if v)
        if news_dir is not None:
            logger.info(
                "News articles found > 0 for %d/%d tickers (as_of=%s)",
                n_buzz, len(universe), as_of_date,
            )

        # ==============================================================
        # Phase 2: Sentiment propagation (optional)
        # ==============================================================
        extended_universe: list[str] = list(universe)
        if enable_propagation and news_dir is not None:
            enriched_composites, propagated_targets = self._propagate_sentiments(
                universe, cached, valid_tickers=set(prices_dict.keys()),
            )
            # Add only price-verified discovered tickers to extended universe (no duplicates)
            try:
                from src.data.csv_provider import find_csv_path, load_data_config, load_prices
                data_dir = load_data_config().get("data_dir") or Path("data/stock_market_data")
                data_dir = Path(data_dir)
                min_rsi = float(get_config().get_param("strategy_params.propagation.min_rsi_norm_for_entry", 0.50))
                logger.info("[RSI gate] min_rsi_norm_for_entry=%.2f (config)", min_rsi)
                added_new: set[str] = set()
                for target in propagated_targets:
                    if target in universe:
                        continue
                    ticker_upper = target.upper()
                    if ticker_upper in added_new:
                        continue
                    if ticker_upper in cached:
                        extended_universe.append(ticker_upper)
                        added_new.add(ticker_upper)
                        continue
                    if find_csv_path(data_dir, ticker_upper) is None:
                        continue
                    loaded = load_prices(data_dir, [ticker_upper])
                    if ticker_upper not in loaded:
                        continue
                    df = loaded[ticker_upper]
                    slice_df = df[df.index <= as_of_date]
                    if slice_df.empty or len(slice_df) < min_required_days:
                        continue
                    if ensure_ohlcv_fn:
                        slice_df = ensure_ohlcv_fn(slice_df)
                    if not all(c in slice_df.columns for c in OHLCV_COLS):
                        continue
                    ind = calculate_all_indicators(slice_df)
                    row = ind.iloc[-1]
                    rsi_val = float(row.get("rsi_norm", 0.5))
                    if rsi_val < min_rsi:
                        logger.info(
                            "[PROPAGATION SKIP] %s: rsi_norm=%.3f below min_rsi_norm_for_entry=%.2f",
                            ticker_upper, rsi_val, min_rsi,
                        )
                        continue
                    extended_universe.append(ticker_upper)
                    added_new.add(ticker_upper)
                    atr_norms[ticker_upper] = float(
                        ind.iloc[-2].get("atr_norm", 0.5)
                        if len(ind) >= 2 else row.get("atr_norm", 0.5)
                    )
                    cached[ticker_upper] = {
                        "row": row,
                        "news_composite": enriched_composites.get(ticker_upper, 0.5),
                        "sentiment_current": 0.5,
                        "new_network_links": [],
                    }
                    prices_dict[ticker_upper] = df
                    logger.info("Added price-verified propagated ticker %s to scoring", ticker_upper)
            except Exception as exc:
                logger.debug("Extended-universe load skipped: %s", exc)

        # ==============================================================
        # Phase 3: Compute final scores (blending in compute_signal_strength)
        # ==============================================================

        for t in extended_universe:
            if t in week_scores:
                continue  # Already set to 0.5 fallback in Phase 1
            entry = cached.get(t)
            if entry is None:
                week_scores[t] = 0.5
                atr_norms.setdefault(t, 0.5)
                continue

            # Use enriched composite if propagation produced one, else base
            news_composite_val = enriched_composites.get(t, entry.get("news_composite"))

            try:
                score, _ = compute_signal_strength(
                    entry["row"],
                    category_weights_override=resolved_category_weights,
                    news_composite=news_composite_val,
                    news_weight_override=news_weight_used if news_dir else None,
                )
                week_scores[t] = score
            except Exception:
                week_scores[t] = 0.5

        aux = {
            "atr_norms": atr_norms,
            "regime_state": regime_state,
            "news_weight_used": news_weight_used,
            "buzz_by_ticker": buzz_by_ticker,
        }
        return week_scores, aux

    # ------------------------------------------------------------------
    # Regime detection (Stage 3 wiring)
    # ------------------------------------------------------------------
    def _detect_regime(
        self,
        prices_dict: dict[str, pd.DataFrame],
        as_of_date: pd.Timestamp,
        regime_ticker: str = "SPY",
    ) -> tuple[str | None, bool | None]:
        """
        Auto-detect market regime from the regime ticker's price data.

        Strategy (per SYSTEM_MAP.md § Stage 3):
          1. HMM 3-state (BULL/BEAR/SIDEWAYS) via get_regime_hmm
          2. SPY vs 200-SMA binary fallback
          3. (None, None) if regime ticker data is missing

        Returns (regime_state, spy_above_sma200).
        """
        spy_df = prices_dict.get(regime_ticker)
        if spy_df is None:
            logger.warning(
                "Regime ticker '%s' not in prices_dict; "
                "cannot auto-detect regime",
                regime_ticker,
            )
            return None, None

        # Normalise column names
        cols_lower = {c.lower(): c for c in spy_df.columns}
        close_col = cols_lower.get("close")
        if close_col is None:
            return None, None
        spy_close = spy_df[close_col].sort_index()

        # 1) Try HMM 3-state
        try:
            from src.signals.weight_model import get_regime_hmm

            regime_state, _ = get_regime_hmm(spy_close, as_of_date)
            if regime_state is not None:
                logger.info(
                    "Regime auto-detected: %s (HMM, as_of=%s)",
                    regime_state, as_of_date,
                )
                return regime_state, None
        except Exception as exc:
            logger.debug("HMM regime detection failed: %s", exc)

        # 2) Fallback: SPY vs 200-SMA binary
        slice_close = spy_close[spy_close.index <= as_of_date]
        if len(slice_close) >= _SMA_KILL_SWITCH_DAYS:
            sma200 = slice_close.rolling(_SMA_KILL_SWITCH_DAYS).mean().iloc[-1]
            current = slice_close.iloc[-1]
            if pd.notna(sma200) and pd.notna(current):
                above = bool(current >= sma200)
                regime_label = "BULL" if above else "BEAR"
                logger.info(
                    "Regime auto-detected: %s (SMA-200 fallback, as_of=%s)",
                    regime_label, as_of_date,
                )
                return regime_label, above

        return None, None

    @staticmethod
    def _resolve_regime_weights(
        cfg: Any,
        regime_state: str | None,
        spy_above_sma200: bool | None,
    ) -> dict[str, float] | None:
        """
        Load the weight set matching the detected regime from
        ``technical_master_score.yaml`` via ConfigManager.

        Returns ``None`` if no regime data is available (caller should
        use fixed weights).
        """
        if regime_state == "BULL":
            return cfg.get_param("technical_master_score.BULL_WEIGHTS")
        if regime_state == "BEAR":
            # DEFENSIVE_WEIGHTS is canonical; BEAR_WEIGHTS is backward-compat alias
            w = cfg.get_param("technical_master_score.DEFENSIVE_WEIGHTS", None)
            if w is None:
                w = cfg.get_param("technical_master_score.BEAR_WEIGHTS")
            return w
        if regime_state == "SIDEWAYS":
            return cfg.get_param("technical_master_score.SIDEWAYS_WEIGHTS")
        # No HMM label — binary fallback
        if spy_above_sma200 is not None:
            key = "BULL_WEIGHTS" if spy_above_sma200 else "DEFENSIVE_WEIGHTS"
            return cfg.get_param(f"technical_master_score.{key}")
        return None

    # ------------------------------------------------------------------
    # Sentiment propagation helper
    # ------------------------------------------------------------------
    def _propagate_sentiments(
        self,
        universe: list[str],
        cached: dict[str, dict[str, Any]],
        valid_tickers: set[str] | None = None,
    ) -> tuple[dict[str, float], set[str]]:
        """
        Run SentimentPropagator for each ticker with news, enrich news composites.

        For each ticker with non-neutral sentiment, propagates through supply chain
        relationships. Target tickers receive an enriched news_composite that blends
        their direct news with propagated sentiment.

        Returns (enriched_composites, propagated_targets).
        - enriched_composites: {ticker: enriched_news_composite} for tickers that
          received propagated signals.
        - propagated_targets: set of all tickers that received at least one signal
          (for extended-universe / price-verified expansion).
        """
        propagator = self._get_propagator()
        if propagator is None:
            return {}, set()

        from src.signals.sentiment_propagator import NewsItem

        # Collect propagated signals grouped by target ticker (include targets not in universe)
        propagated_by_target: dict[str, list] = {}
        universe_upper = {t.upper(): t for t in universe}

        for t, entry in cached.items():
            sentiment = entry.get("sentiment_current", 0.5)
            if abs(sentiment - 0.5) < 1e-6:
                continue

            bipolar_sentiment = (sentiment - 0.5) * 2.0

            try:
                news_item = NewsItem(
                    ticker=t.upper(),
                    sentiment_score=bipolar_sentiment,
                    supply_chain_score=0.0,
                    confidence=1.0,
                    relationship="Neutral",
                    reasoning=f"Propagated from news sentiment ({sentiment:.3f})",
                )
                discovered_links = entry.get("new_network_links") or None
                signals = propagator.propagate(
                    news_item,
                    discovered_links=discovered_links,
                    valid_tickers=valid_tickers,
                )
                for sig in signals:
                    # Keep original casing for universe tickers; use sig.ticker for others
                    target_key = universe_upper.get(sig.ticker.upper()) or sig.ticker.upper()
                    propagated_by_target.setdefault(target_key, []).append(sig)
            except Exception as exc:
                logger.debug("Propagation from %s failed: %s", t, exc)

        cfg = get_config()
        blend_factor: float = cfg.get_param(
            "strategy_params.propagation.blend_factor",
        )

        enriched: dict[str, float] = {}
        for target, prop_signals in propagated_by_target.items():
            base = cached.get(target, {}).get("news_composite", 0.5)
            if not prop_signals:
                continue

            avg_prop_sentiment = sum(s.sentiment_score for s in prop_signals) / len(
                prop_signals
            )
            prop_unipolar = max(0.0, min(1.0, (avg_prop_sentiment + 1.0) / 2.0))
            enriched_val = (1.0 - blend_factor) * base + blend_factor * prop_unipolar
            enriched[target] = max(0.0, min(1.0, enriched_val))

        if enriched:
            logger.info(
                "Propagation enriched %d ticker(s) news composites", len(enriched)
            )
        return enriched, set(propagated_by_target.keys())

    # ------------------------------------------------------------------
    # Weekly path (unchanged)
    # ------------------------------------------------------------------
    def _generate_weekly(
        self,
        as_of_date: pd.Timestamp,
        universe: list[str],
        data_context: DataContext,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Weekly path: SignalCombiner.get_top_stocks; scores from composite/technical signal."""
        combiner = data_context.get("combiner")
        date_str = data_context.get("date")
        top_n = data_context.get("top_n", 10)
        mode = data_context.get("mode", "technical_only")
        if combiner is None:
            return {}, {}

        top_stocks = combiner.get_top_stocks(date=date_str, top_n=top_n, mode=mode)
        if top_stocks is None or top_stocks.empty:
            return {}, {}

        score_col = (
            "technical_signal" if mode == "technical_only" else "composite_signal"
        )
        if score_col not in top_stocks.columns:
            score_col = (
                "composite_signal"
                if "composite_signal" in top_stocks.columns
                else "technical_signal"
            )
        if score_col not in top_stocks.columns:
            score_col = (
                top_stocks.columns[2]
                if len(top_stocks.columns) > 2
                else top_stocks.columns[0]
            )
        scores = dict(
            zip(
                top_stocks["ticker"].astype(str),
                top_stocks[score_col].fillna(0.5).tolist(),
            )
        )
        return scores, {}
