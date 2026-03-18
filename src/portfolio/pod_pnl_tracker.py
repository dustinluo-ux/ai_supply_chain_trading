"""
Attribute realized P&L from fills to pods, compute rolling Sharpe/MDD per pod,
and update pod_fitness.json. Helper to append per-pod weight snapshots to history.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Bootstrap from 2024 OOS baselines when pod_fitness.json is missing (match meta_allocator)
DEFAULT_FITNESS = {
    "core": {"sharpe": 0.526, "mdd": -0.094},
    "extension": {"sharpe": 0.206, "mdd": -0.233},
    "ballast": {"sharpe": 0.10, "mdd": -0.050},
}


def log_pod_weights(
    pod_weights: dict[str, dict[str, float]],
    aggregate_weights: pd.Series | dict[str, float],
    as_of: str,
    history_path: Path | str,
) -> None:
    """
    Append one JSON object (as_of, pod_weights, aggregate_weights) to history_path.
    Creates file if it does not exist. Converts pandas Series to dict. Never raises.
    """
    history_path = Path(history_path)
    try:
        agg = aggregate_weights
        if isinstance(agg, pd.Series):
            agg = agg.dropna().to_dict()
        elif not isinstance(agg, dict):
            agg = dict(agg) if agg else {}
        payload = {
            "as_of": as_of,
            "pod_weights": pod_weights,
            "aggregate_weights": agg,
        }
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.exception("log_pod_weights failed: %s", e)


def _compute_pod_daily_returns(
    weights_history: list[dict],
    fills_history: list[dict],
) -> dict[str, pd.Series]:
    """
    Attribute realized P&L from each fill to pods by weight fraction; group by pod and date.
    Returns dict pod_name -> Series of daily returns (index = date).
    """
    out: dict[str, dict[str, float]] = {}
    if not weights_history or not fills_history:
        return {}

    try:
        # Sort snapshots by as_of for binary search / linear scan
        snapshots = sorted(weights_history, key=lambda x: x.get("as_of", "") or "")

        for fill in fills_history:
            ts = fill.get("timestamp") or fill.get("date")
            if not ts:
                continue
            ticker = fill.get("ticker") or fill.get("symbol")
            if not ticker:
                continue
            qty = fill.get("quantity")
            if qty is None:
                qty = fill.get("qty_filled", 0)
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                continue
            price = fill.get("fill_price")
            if price is None:
                price = fill.get("avg_fill_price")
            if price is None:
                continue
            try:
                price = float(price)
            except (TypeError, ValueError):
                continue
            side = (fill.get("side") or "").upper()

            # Realized P&L for this fill (dollars): optional field or derive from side/qty/price
            pnl = fill.get("pnl") or fill.get("realized_pnl")
            if pnl is not None:
                try:
                    pnl = float(pnl)
                except (TypeError, ValueError):
                    pnl = None
            if pnl is None:
                sign = 1.0 if side == "SELL" else -1.0
                pnl = sign * qty * price

            # Most recent snapshot with as_of <= fill timestamp
            fill_ts = ts[:10] if isinstance(ts, str) and len(ts) >= 10 else str(ts)
            snapshot = None
            for s in reversed(snapshots):
                as_of = (s.get("as_of") or "")[:10] if s.get("as_of") else ""
                if as_of and fill_ts and as_of <= fill_ts:
                    snapshot = s
                    break
            if not snapshot:
                continue

            agg_weights = snapshot.get("aggregate_weights") or {}
            if isinstance(agg_weights, pd.Series):
                agg_weights = agg_weights.to_dict()
            agg_w = agg_weights.get(ticker) or agg_weights.get(ticker.upper())
            if agg_w is None or abs(float(agg_w)) < 1e-12:
                continue

            pod_weights = snapshot.get("pod_weights") or {}
            nav = float(snapshot.get("nav", 1.0)) or 1.0

            for pod_name, pw in pod_weights.items():
                if not isinstance(pw, dict):
                    continue
                w = pw.get(ticker) or pw.get(ticker.upper())
                if w is None:
                    continue
                try:
                    frac = float(w) / float(agg_w)
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
                attributed = pnl * frac
                if pod_name not in out:
                    out[pod_name] = {}
                day = fill_ts if len(fill_ts) >= 10 else ts
                out[pod_name][day] = out[pod_name].get(day, 0.0) + attributed / nav
    except Exception as e:
        logger.exception("_compute_pod_daily_returns failed: %s", e)
        return {}

    result = {}
    for pod_name, day_pnl in out.items():
        if not day_pnl:
            result[pod_name] = pd.Series(dtype=float)
        else:
            result[pod_name] = pd.Series(day_pnl).sort_index()
    return result


def _compute_fitness(
    daily_returns_series: pd.Series,
    min_obs: int = 20,
    fallback_sharpe: float | None = None,
    fallback_mdd: float | None = None,
) -> dict[str, Any]:
    """
    Compute rolling Sharpe and MDD from the most recent 60 observations.
    If fewer than min_obs, return fallbacks with live=False.
    """
    try:
        series = daily_returns_series.dropna()
        n_obs = len(series)
        if n_obs < min_obs:
            return {
                "sharpe": fallback_sharpe,
                "mdd": fallback_mdd,
                "live": False,
                "n_obs": n_obs,
            }
        tail = series.tail(60)
        n_obs = len(tail)
        mean_ret = float(tail.mean())
        std_ret = float(tail.std())
        if std_ret and std_ret > 0:
            sharpe = mean_ret / std_ret * (252 ** 0.5)
        else:
            sharpe = 0.0
        equity = (1 + tail).cumprod()
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max.replace(0, float("nan"))
        mdd = float(drawdown.min()) if len(drawdown) else (fallback_mdd or 0.0)
        return {
            "sharpe": sharpe,
            "mdd": mdd,
            "live": True,
            "n_obs": n_obs,
        }
    except Exception as e:
        logger.exception("_compute_fitness failed: %s", e)
        return {
            "sharpe": fallback_sharpe,
            "mdd": fallback_mdd,
            "live": False,
            "n_obs": len(daily_returns_series) if daily_returns_series is not None else 0,
        }


def update_pod_fitness(
    fitness_path: Path | str,
    weights_history_path: Path | str,
    fills_path: Path | str,
) -> dict[str, Any]:
    """
    Load fitness/weights/fills, compute per-pod daily returns, update Sharpe/MDD per pod,
    write pod_fitness.json and return the updated fitness dict. Never raises.
    """
    fitness_path = Path(fitness_path)
    weights_history_path = Path(weights_history_path)
    fills_path = Path(fills_path)

    try:
        # a. Load existing pod_fitness or use defaults
        fitness: dict[str, dict[str, Any]] = {}
        if fitness_path.exists():
            try:
                raw = json.loads(fitness_path.read_text(encoding="utf-8"))
                for k, v in (raw or {}).items():
                    if isinstance(v, dict):
                        fitness[k] = dict(v)
            except Exception as e:
                logger.warning("Could not load pod_fitness.json: %s", e)
        for pod in ("core", "extension", "ballast"):
            if pod not in fitness:
                fitness[pod] = dict(DEFAULT_FITNESS.get(pod, {"sharpe": 0.0, "mdd": 0.0}))

        # b. Load pod_weights_history.jsonl
        weights_history: list[dict] = []
        if weights_history_path.exists():
            with open(weights_history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict) and "as_of" in obj and "pod_weights" in obj:
                            weights_history.append(obj)
                    except json.JSONDecodeError:
                        continue

        # c. Load fills.jsonl
        fills_history: list[dict] = []
        if fills_path.exists():
            with open(fills_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        fills_history.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # d. Per-pod daily returns
        pod_returns = _compute_pod_daily_returns(weights_history, fills_history)

        # e. For each pod: _compute_fitness with fallback from current entry; if live, overwrite sharpe/mdd
        for pod in ("core", "extension", "ballast"):
            series = pod_returns.get(pod)
            if series is None or series.empty:
                series = pd.Series(dtype=float)
            current = fitness.get(pod) or {}
            fallback_sharpe = current.get("sharpe")
            fallback_mdd = current.get("mdd")
            if fallback_sharpe is None:
                fallback_sharpe = DEFAULT_FITNESS.get(pod, {}).get("sharpe")
            if fallback_mdd is None:
                fallback_mdd = DEFAULT_FITNESS.get(pod, {}).get("mdd")
            comp = _compute_fitness(series, min_obs=20, fallback_sharpe=fallback_sharpe, fallback_mdd=fallback_mdd)
            fitness[pod]["sharpe"] = comp["sharpe"]
            fitness[pod]["mdd"] = comp["mdd"]
            fitness[pod]["live"] = comp["live"]
            fitness[pod]["n_obs"] = comp["n_obs"]

        # f. Write back
        fitness_path.parent.mkdir(parents=True, exist_ok=True)
        fitness_path.write_text(json.dumps(fitness, indent=2), encoding="utf-8")

        # g. Log summary per pod
        for pod in ("core", "extension", "ballast"):
            c = fitness.get(pod) or {}
            logger.info(
                "[POD_FITNESS] %s: sharpe=%.4f mdd=%.4f live=%s n_obs=%s",
                pod,
                c.get("sharpe", 0),
                c.get("mdd", 0),
                c.get("live", False),
                c.get("n_obs", 0),
            )

        return fitness
    except Exception as e:
        logger.exception("update_pod_fitness failed: %s", e)
        out = {}
        for pod in ("core", "extension", "ballast"):
            out[pod] = dict(DEFAULT_FITNESS.get(pod, {"sharpe": 0.0, "mdd": 0.0}))
        return out
