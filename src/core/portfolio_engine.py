"""
PortfolioEngine: build(as_of_date, gated_scores, context) -> Intent.
Uses HRP + Alpha Tilt when prices_dict and as_of are in context; else inverse-ATR fallback.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.core.intent import Intent
from src.core.types import Context


# EWMA vol span — reads from optimizer_config.yaml fixed_params.ewma_span; falls back to 38.
def _load_ewma_span() -> int:
    try:
        _p = Path(__file__).resolve().parents[2] / "config" / "optimizer_config.yaml"
        if _p.exists():
            with open(_p, encoding="utf-8") as _f:
                _d = yaml.safe_load(_f) or {}
            return int((_d.get("fixed_params") or {}).get("ewma_span", 38))
    except Exception:
        pass
    return 38


EWMA_SPAN = _load_ewma_span()
BASE_CAP, CAP_FLOOR, CAP_CEIL = 0.20, 0.10, 0.40
LOOKBACK_DAYS = 60
MIN_OBS = 30

logger = logging.getLogger(__name__)


def _load_strategy_params_tes_enabled() -> bool:
    """Master switch from config/strategy_params.yaml tes.tes_enabled (default True if absent)."""
    path = Path(__file__).resolve().parents[2] / "config" / "strategy_params.yaml"
    if not path.exists():
        return True
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        tes = raw.get("tes") or {}
        if "tes_enabled" in tes:
            return bool(tes["tes_enabled"])
    except Exception:
        pass
    return True


def _load_tes_multipliers(config: dict[str, Any] | None = None) -> dict[str, float]:
    """
    Load precomputed TES multipliers from DATA_DIR/tes_scores.json (D023).
    Returns {ticker: multiplier}. Empty dict = neutral (1.0) everywhere.
    Backward compat: if ``config`` passes tes_enabled=False, skip load.
    """
    try:
        if config is not None and config.get("tes_enabled") is False:
            return {}
        if not _load_strategy_params_tes_enabled():
            return {}
        data_dir = Path(
            os.environ.get("DATA_DIR", "C:/ai_supply_chain_trading/trading_data")
        )
        path = data_dir / "tes_scores.json"
        if not path.exists():
            logger.warning(
                "TES scores file not found at %s — all multipliers neutral", path
            )
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        out: dict[str, float] = {}
        now = datetime.now(timezone.utc)
        for ticker, entry in data.items():
            if not isinstance(entry, dict):
                continue
            mult = entry.get("multiplier")
            if mult is None:
                continue
            tkey = str(ticker).upper()
            out[tkey] = float(mult)
            audited_at = entry.get("audited_at")
            if audited_at:
                try:
                    age_days = (
                        now
                        - datetime.fromisoformat(str(audited_at).replace("Z", "+00:00"))
                    ).days
                    if age_days > 14:
                        logger.warning(
                            "TES score for %s is %d days old — consider refreshing",
                            tkey,
                            age_days,
                        )
                except (ValueError, TypeError):
                    pass
        return out
    except Exception as exc:
        logger.warning("Failed to load TES scores: %s — all multipliers neutral", exc)
        return {}


def _load_futures_multipliers() -> dict[str, float]:
    """Return {symbol: multiplier} from config/instruments.yaml futures block."""
    path = Path(__file__).resolve().parents[2] / "config" / "instruments.yaml"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return {
            sym: float(spec.get("multiplier", 1.0))
            for sym, spec in (cfg.get("futures") or {}).items()
            if isinstance(spec, dict)
        }
    except Exception:
        return {}


def _slice_to_as_of(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Return df with index <= as_of (no look-ahead)."""
    if df is None or df.empty:
        return df
    return df[df.index <= as_of]


def _hrp_leaves_average_linkage(dist_matrix: list) -> list[int]:
    """Pure Python average linkage → leaf ordering. Accepts list-of-lists or 2-D array."""
    n = len(dist_matrix)
    if n == 1:
        return [0]
    if n == 2:
        return [0, 1]
    sizes: dict[int, int] = {i: 1 for i in range(n)}
    children: dict[int, tuple[int, int]] = {}
    dists: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            dists[(i, j)] = float(dist_matrix[i][j])
    active = list(range(n))
    next_id = n
    for _ in range(n - 1):
        best = float("inf")
        bi, bj = -1, -1
        for ai in range(len(active)):
            for aj in range(ai + 1, len(active)):
                ca, cb = active[ai], active[aj]
                d = dists.get((min(ca, cb), max(ca, cb)), float("inf"))
                if d < best:
                    best, bi, bj = d, ca, cb
        mid = next_id
        next_id += 1
        si, sj = sizes[bi], sizes[bj]
        sizes[mid] = si + sj
        children[mid] = (bi, bj)
        active.remove(bi)
        active.remove(bj)
        for ck in active:
            d_i = dists.get((min(bi, ck), max(bi, ck)), float("inf"))
            d_j = dists.get((min(bj, ck), max(bj, ck)), float("inf"))
            dists[(min(mid, ck), max(mid, ck))] = (si * d_i + sj * d_j) / (si + sj)
        active.append(mid)

    def _leaves(node: int) -> list[int]:
        if node < n:
            return [node]
        l, r = children[node]
        return _leaves(l) + _leaves(r)

    return _leaves(next_id - 1)


def _hrp_weights_scipy(returns_df: pd.DataFrame) -> dict[str, float]:
    """HRP — fully pure Python, zero numpy/BLAS operations. Safe on Windows MKL."""
    tickers = list(returns_df.columns)
    n = len(tickers)
    if n < 2:
        return {tickers[0]: 1.0} if n == 1 else {}
    # Extract to Python list-of-lists to avoid all numpy/BLAS
    X_raw = returns_df.values.tolist()
    obs = len(X_raw)
    # Mean-center
    col_mean = [sum(X_raw[k][j] for k in range(obs)) / obs for j in range(n)]
    X_c = [[X_raw[k][j] - col_mean[j] for j in range(n)] for k in range(obs)]
    # Covariance matrix (pure Python)
    d = max(obs - 1, 1)
    cov = [
        [sum(X_c[k][i] * X_c[k][j] for k in range(obs)) / d for j in range(n)]
        for i in range(n)
    ]
    # Std and correlation
    std = [max(cov[i][i] ** 0.5, 1e-8) for i in range(n)]
    corr = [
        [max(-1.0, min(1.0, cov[i][j] / (std[i] * std[j]))) for j in range(n)]
        for i in range(n)
    ]
    for i in range(n):
        corr[i][i] = 1.0
    # Distance matrix
    dist = [
        [max((1.0 - corr[i][j]) / 2.0, 0.0) ** 0.5 for j in range(n)] for i in range(n)
    ]
    for i in range(n):
        dist[i][i] = 0.0
    # Leaf ordering (pure Python average linkage)
    sort_ix = _hrp_leaves_average_linkage(dist)
    # HRP bisection (pure Python lists)
    w = [1.0] * n
    clusters = [sort_ix]
    while clusters:
        next_clusters = []
        for cluster in clusters:
            if len(cluster) > 1:
                mid = len(cluster) // 2
                next_clusters += [cluster[:mid], cluster[mid:]]
        for ci in range(0, len(next_clusters) - 1, 2):
            c0, c1 = next_clusters[ci], next_clusters[ci + 1]

            def _ivp_var_py(idx: list) -> float:
                sz = len(idx)
                sub = [[cov[idx[a]][idx[b]] for b in range(sz)] for a in range(sz)]
                dv = [max(sub[a][a], 1e-8) for a in range(sz)]
                iv = [1.0 / dv[a] for a in range(sz)]
                iv_s = sum(iv) or 1.0
                iv = [x / iv_s for x in iv]
                return sum(
                    iv[a] * sub[a][b] * iv[b] for a in range(sz) for b in range(sz)
                )

            v0, v1 = _ivp_var_py(c0), _ivp_var_py(c1)
            alpha = 1.0 - v0 / (v0 + v1) if (v0 + v1) > 0 else 0.5
            for idx in c0:
                w[idx] *= alpha
            for idx in c1:
                w[idx] *= 1.0 - alpha
        clusters = next_clusters
    total = sum(w)
    if total > 0:
        w = [x / total for x in w]
    return {tickers[i]: w[i] for i in range(n)}


def hrp_alpha_tilt(
    scores: dict[str, float],
    prices_dict: dict[str, pd.DataFrame],
    as_of: pd.Timestamp,
    top_n: int,
    score_floor: float = 0.0,
    tes_multipliers: dict[str, float] | None = None,
    max_single_weight: float = 0.40,
) -> dict[str, float]:
    """
    HRP + Alpha Tilt allocation: filter by score > score_floor and sufficient history,
    EWMA vol, liquidity-scaled caps, HRP base weights, alpha tilt, cap at liquidity.
    All data sliced to <= as_of (no look-ahead).
    Returns dict ticker -> weight for full score universe (0.0 for non-selected).
    """
    universe = list(scores.keys())
    if not universe:
        return {}
    out = {t: 0.0 for t in universe}

    # Slice all price data to as_of
    sliced = {}
    for t, df in prices_dict.items():
        if df is None or df.empty:
            continue
        s = _slice_to_as_of(df, as_of)
        if s is not None and not s.empty:
            sliced[t] = s

    # EWMA vol per ticker (data <= as_of)
    vol_30d: dict[str, float] = {}
    for ticker, df in sliced.items():
        if "close" not in df.columns:
            continue
        try:
            close = df["close"]
            if hasattr(close, "iloc") and getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            returns = close.pct_change(fill_method=None).dropna()
            if len(returns) < 2:
                continue
            ewma_std = returns.ewm(span=EWMA_SPAN, adjust=False).std()
            vol = float(ewma_std.iloc[-1]) if len(ewma_std) else None
            if vol is None or (vol != vol) or vol <= 0:
                vol = float(returns.std())
            if vol is None or (vol != vol) or vol <= 0:
                vol = 0.01
            vol_30d[ticker] = vol
        except Exception:
            continue

    # Liquidity caps: ADV = 20d mean(close*volume), cap = clip(0.20*sqrt(adv/adv_median), 0.10, 0.40)
    adv: dict[str, float | None] = {}
    for ticker, df in sliced.items():
        if "close" not in df.columns or "volume" not in df.columns:
            adv[ticker] = None
            continue
        try:
            close = df["close"]
            if hasattr(close, "iloc") and getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            vol = df["volume"]
            if hasattr(vol, "iloc") and getattr(vol, "ndim", 1) > 1:
                vol = vol.iloc[:, 0]
            dollar_vol = (close * vol).dropna()
            if len(dollar_vol) < 20:
                adv[ticker] = None
                continue
            adv[ticker] = float(dollar_vol.iloc[-20:].mean())
        except Exception:
            adv[ticker] = None
    adv_values = [v for v in adv.values() if v is not None and v > 0]
    # Pure Python median — avoids numpy/MKL
    if adv_values:
        _s = sorted(adv_values)
        _n = len(_s)
        adv_median = (
            (_s[_n // 2 - 1] + _s[_n // 2]) / 2.0 if _n % 2 == 0 else float(_s[_n // 2])
        )
    else:
        adv_median = 1.0
    liquidity_cap: dict[str, float] = {}
    for t in vol_30d:
        if adv.get(t) is None or adv_median <= 0:
            liquidity_cap[t] = BASE_CAP
        else:
            raw = BASE_CAP * math.sqrt(adv[t] / adv_median)
            liquidity_cap[t] = max(CAP_FLOOR, min(CAP_CEIL, raw))

    # Eligible: score > score_floor, has vol; take top_n by score
    eligible = [t for t in scores if t in vol_30d and scores[t] > score_floor]
    eligible = sorted(eligible, key=lambda t: -scores[t])[:top_n]
    if not eligible:
        return out

    # HRP base weights (returns sliced to <= as_of, last LOOKBACK_DAYS)
    use_hrp = False
    hrp_base_weight: dict[str, float] = {}
    try:
        returns_dict: dict[str, pd.Series] = {}
        for t in eligible:
            if (
                t not in sliced
                or sliced[t] is None
                or sliced[t].empty
                or "close" not in sliced[t].columns
            ):
                continue
            close = sliced[t]["close"]
            if hasattr(close, "iloc") and getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            ret = close.pct_change(fill_method=None).dropna()
            if len(ret) < MIN_OBS:
                continue
            ret = ret.iloc[-LOOKBACK_DAYS:]
            returns_dict[t] = ret
        if len(returns_dict) < 2:
            raise ValueError("fewer than 2 tickers with sufficient return history")
        returns_df = pd.concat(returns_dict, axis=1, join="inner")
        if returns_df.shape[1] < 2 or len(returns_df) < MIN_OBS:
            raise ValueError("insufficient overlapping returns for HRP")
        hrp_weights = _hrp_weights_scipy(returns_df)
        dropped = [t for t in eligible if t not in hrp_weights]
        hrp_sum = sum(hrp_weights.values())
        equal_share = (1.0 - hrp_sum) / len(dropped) if dropped else 0.0
        for t in dropped:
            hrp_weights[t] = equal_share
        use_hrp = True
        hrp_base_weight = {t: hrp_weights[t] for t in eligible if t in hrp_weights}
    except Exception:
        use_hrp = False

    if use_hrp and hrp_base_weight:
        mean_score = (
            sum(scores[t] for t in eligible) / len(eligible) if eligible else 1e-9
        )
        if mean_score <= 0:
            mean_score = 1e-9
        tilted_w = {
            t: hrp_base_weight[t] * (scores[t] / mean_score)
            for t in eligible
            if t in hrp_base_weight
        }
        total_tilted = sum(tilted_w.values())
        if total_tilted <= 0:
            w = {t: 1.0 / len(eligible) for t in eligible}
        else:
            w = {t: tilted_w[t] / total_tilted for t in tilted_w}
    else:
        # Fallback: score/vol
        raw_w = {t: scores[t] / vol_30d[t] for t in eligible}
        total_raw = sum(raw_w.values())
        if total_raw <= 0:
            w = {t: 1.0 / len(eligible) for t in eligible}
        else:
            w = {t: raw_w[t] / total_raw for t in eligible}

    # Iterative cap at liquidity — bounded to prevent infinite oscillation when
    # sum(caps) < 1.0 (infeasible: excess can never be fully absorbed).
    # D023: TES cap tilt — fail-open (neutral multipliers on any failure).
    try:
        if tes_multipliers is None:
            tes = _load_tes_multipliers()
        else:
            tes = dict(tes_multipliers)
    except Exception as exc:
        logger.warning(
            "TES load failed in hrp_alpha_tilt: %s — neutral multipliers", exc
        )
        tes = {}
    cap_t = {}
    for t in w:
        base = float(liquidity_cap.get(t, BASE_CAP))
        m = float(tes.get(str(t).upper(), 1.0))
        cap_t[t] = min(base, base * m)
    if w:
        keys = set(tes.keys())
        n_with_file = sum(1 for t in w if str(t).upper() in keys)
        applied = [float(tes.get(str(t).upper(), 1.0)) for t in w]
        logger.info(
            "TES tilt (hrp_alpha_tilt): %d/%d basket tickers with TES file entry; mult min=%.4f max=%.4f",
            n_with_file,
            len(w),
            min(applied),
            max(applied),
        )
    for _cap_iter in range(50):
        capped = {t for t in w if w[t] > cap_t[t] + 1e-9}
        uncapped = {t for t in w if t not in capped}
        if not capped:
            break
        excess = sum(w[t] - cap_t[t] for t in capped)
        for t in capped:
            w[t] = cap_t[t]
        if uncapped:
            total_uncapped = sum(w[t] for t in uncapped)
            if total_uncapped <= 0:
                break
            for t in uncapped:
                w[t] += excess * (w[t] / total_uncapped)
        else:
            break
    total_after = sum(w.values())
    if total_after > 0:
        w = {t: w[t] / total_after for t in w}
    # Hard single-position ceiling (config-driven, post-TES post-liquidity guardrail)
    # When only one ticker selected: cap weight and leave remainder as cash (no renorm).
    # When multiple tickers: iterative clamp with renormalization.
    if max_single_weight < 1.0:
        if len(w) == 1:
            # Single ticker: hard cap, no renormalization (remainder stays in cash)
            w = {t: min(v, max_single_weight) for t, v in w.items()}
        else:
            # Multiple tickers: iterative clamping with renormalization
            for _clamp_iter in range(20):
                # Check if any weight exceeds cap
                exceeds = [t for t, v in w.items() if v > max_single_weight + 1e-9]
                if not exceeds:
                    break
                # Clamp and renormalize
                w = {t: min(v, max_single_weight) for t, v in w.items()}
                _total_hard = sum(w.values())
                if _total_hard > 0:
                    w = {t: v / _total_hard for t, v in w.items()}
    for t in w:
        out[t] = w[t]
    return out


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
        Uses HRP + Alpha Tilt when context has prices_dict and as_of; else inverse-ATR.
        """
        prices_dict = context.get("prices_dict")
        if isinstance(as_of_date, pd.Timestamp):
            as_of_ts = as_of_date
        else:
            as_of_ts = pd.to_datetime(as_of_date)
        max_single_w = 0.40
        _tc_path = (
            Path(__file__).resolve().parents[2] / "config" / "trading_config.yaml"
        )
        if _tc_path.exists():
            try:
                with open(_tc_path, encoding="utf-8") as _f_tc:
                    _tc = yaml.safe_load(_f_tc) or {}
                max_single_w = float(
                    (_tc.get("risk") or {}).get(
                        "max_single_position_weight", max_single_w
                    )
                )
            except Exception:
                pass
        tes_m = _load_tes_multipliers()
        fut_m = _load_futures_multipliers()
        intent: Intent
        try:
            if prices_dict and len(prices_dict) > 0:
                weights = hrp_alpha_tilt(
                    gated_scores,
                    prices_dict,
                    as_of_ts,
                    top_n=context.get("top_n", 3),
                    score_floor=float(context.get("score_floor", 0.0)),
                    tes_multipliers=tes_m,
                    max_single_weight=max_single_w,
                )
                tickers_universe = context.get("tickers") or list(gated_scores.keys())
                for t in tickers_universe:
                    if t not in weights:
                        weights[t] = 0.0
                tickers_ordered = [t for t in weights if weights.get(t, 0.0) > 0]
                tickers_ordered = sorted(tickers_ordered, key=lambda t: -weights[t])
                intent = Intent(
                    tickers=tickers_ordered,
                    weights=weights,
                    mode="backtest",
                    futures_multipliers=fut_m,
                )
            else:
                intent = self._build_inverse_atr(
                    gated_scores,
                    context,
                    tes_multipliers=tes_m,
                    max_single_weight=max_single_w,
                    futures_multipliers=fut_m,
                )
        except Exception:
            intent = self._build_inverse_atr(
                gated_scores,
                context,
                tes_multipliers=tes_m,
                max_single_weight=max_single_w,
                futures_multipliers=fut_m,
            )
        if context.get("path") == "weekly":
            intent = Intent(
                tickers=intent.tickers,
                weights=intent.weights,
                mode="execution",
                metadata=getattr(intent, "metadata", None),
                futures_multipliers=intent.futures_multipliers,
            )
        return intent

    def _build_inverse_atr(
        self,
        gated_scores: dict[str, float],
        context: Context,
        tes_multipliers: dict[str, float] | None = None,
        max_single_weight: float = 0.40,
        futures_multipliers: dict[str, float] | None = None,
    ) -> Intent:
        """Rank by gated_scores, take top_n, inverse-vol weights using atr_norms (fallback)."""
        fut_m = futures_multipliers or {}
        top_n = context.get("top_n", 3)
        atr_norms = context.get("atr_norms") or {}
        tickers_universe = context.get("tickers") or list(gated_scores.keys())

        if all(v == 0.0 for v in gated_scores.values()):
            return Intent(
                tickers=[],
                weights={t: 0.0 for t in tickers_universe},
                mode="backtest",
                futures_multipliers=fut_m,
            )
        ranked = sorted(gated_scores.items(), key=lambda x: -x[1])[:top_n]
        if not ranked:
            weights_dict = {t: 0.0 for t in tickers_universe}
            return Intent(
                tickers=[],
                weights=weights_dict,
                mode="backtest",
                futures_multipliers=fut_m,
            )

        inv_vol = [1.0 / (max(atr_norms.get(t, 0.5), 1e-6)) for t, _ in ranked]
        total_inv = sum(inv_vol)
        weights_list = [x / total_inv for x in inv_vol]
        intent_tickers = [t for t, _ in ranked]
        intent_weights = {t: w for (t, _), w in zip(ranked, weights_list)}

        try:
            if tes_multipliers is None:
                tes = _load_tes_multipliers()
            else:
                tes = dict(tes_multipliers)
        except Exception as exc:
            logger.warning(
                "TES load failed in _build_inverse_atr: %s — neutral multipliers", exc
            )
            tes = {}
        for t in list(intent_weights.keys()):
            intent_weights[t] *= float(tes.get(str(t).upper(), 1.0))
        total = sum(intent_weights.values())
        if total > 0:
            intent_weights = {t: w / total for t, w in intent_weights.items()}
        if intent_weights:
            keys = set(tes.keys())
            n_with_file = sum(1 for t in intent_weights if str(t).upper() in keys)
            applied = [float(tes.get(str(t).upper(), 1.0)) for t in intent_weights]
            logger.info(
                "TES tilt (_build_inverse_atr): %d/%d tickers with TES file entry; mult min=%.4f max=%.4f",
                n_with_file,
                len(intent_weights),
                min(applied),
                max(applied),
            )

        # Hard single-position ceiling (config-driven, post-TES guardrail)
        # When only one ticker selected: cap weight and leave remainder as cash (no renorm).
        # When multiple tickers: iterative clamp with renormalization.
        if max_single_weight < 1.0:
            if len(intent_weights) == 1:
                # Single ticker: hard cap, no renormalization (remainder stays in cash)
                intent_weights = {
                    t: min(v, max_single_weight) for t, v in intent_weights.items()
                }
            else:
                # Multiple tickers: iterative clamping with renormalization
                for _clamp_iter in range(20):
                    # Check if any weight exceeds cap
                    exceeds = [
                        t
                        for t, v in intent_weights.items()
                        if v > max_single_weight + 1e-9
                    ]
                    if not exceeds:
                        break
                    # Clamp and renormalize
                    intent_weights = {
                        t: min(v, max_single_weight) for t, v in intent_weights.items()
                    }
                    _total_hard = sum(intent_weights.values())
                    if _total_hard > 0:
                        intent_weights = {
                            t: v / _total_hard for t, v in intent_weights.items()
                        }

        for t in tickers_universe:
            if t not in intent_weights:
                intent_weights[t] = 0.0

        return Intent(
            tickers=intent_tickers,
            weights=intent_weights,
            mode="backtest",
            futures_multipliers=fut_m,
        )

    def _build_backtest(
        self,
        gated_scores: dict[str, float],
        context: Context,
    ) -> Intent:
        """Alias for _build_inverse_atr (backward compatibility)."""
        return self._build_inverse_atr(gated_scores, context)

    def _build_weekly(
        self,
        gated_scores: dict[str, float],
        context: Context,
    ) -> Intent:
        """Deprecated: no longer used for sizing. Equal weight 1/N."""
        top_n = context.get("top_n", 10)
        tickers = list(gated_scores.keys())[:top_n]
        if not tickers:
            return Intent(
                tickers=[], weights={}, mode="execution", futures_multipliers={}
            )
        w = 1.0 / len(tickers)
        weights = {t: w for t in tickers}
        return Intent(
            tickers=tickers,
            weights=weights,
            mode="execution",
            futures_multipliers=_load_futures_multipliers(),
        )
