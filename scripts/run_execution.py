# Canonical execution entrypoint: mock (default) or paper (IB paper account).
"""
Canonical execution: spine -> Intent -> delta trades.
--mode mock: print only (no broker).
--mode paper: connect to IB paper; print orders; submit only with --confirm-paper.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.monitoring.incident_logger import log_incident
from src.core.portfolio_engine import _load_futures_multipliers
from src.utils.atomic_io import atomic_write_json
from src.data.csv_provider import (
    load_data_config,
    find_csv_path,
    load_prices,
    ensure_ohlcv,
)
from src.data.data_quality import DataQualityReport

# Cache for --rebalance: last valid weights from last non-rebalance run
LAST_VALID_WEIGHTS_PATH = ROOT / "outputs" / "last_valid_weights.json"

BENCHMARK_TICKER = "SPY"
SMA_KILL_SWITCH_DAYS = 200
KILL_SWITCH_MODE = "cash"
REQUIRED_REGIME_KEYS = (
    "regime_state",
    "spy_below_sma200",
    "kill_switch_active",
    "sideways_risk_scale",
    "kill_switch_mode",
)


def _instrument_type(symbol: str) -> str:
    """Read config/instruments.yaml; return 'future', 'option', or 'equity'."""
    _cfg_path = ROOT / "config" / "instruments.yaml"
    if not _cfg_path.exists():
        return "equity"
    try:
        with open(_cfg_path, encoding="utf-8") as _f:
            _icfg = yaml.safe_load(_f) or {}
        if symbol in (_icfg.get("futures") or {}):
            return "future"
        if symbol in (_icfg.get("options") or {}):
            return "option"
    except Exception:
        pass
    return "equity"


def _spy_benchmark_series(data_dir: Path) -> tuple[pd.Series, pd.Series] | None:
    path = find_csv_path(data_dir, BENCHMARK_TICKER)
    if not path:
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=False)
        df.index = pd.to_datetime(df.index, format="mixed", dayfirst=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df.columns = [c.lower() for c in df.columns]
        if "close" not in df.columns or len(df) < SMA_KILL_SWITCH_DAYS:
            return None
        close = df["close"]
        sma = close.rolling(
            SMA_KILL_SWITCH_DAYS, min_periods=SMA_KILL_SWITCH_DAYS
        ).mean()
        return (close, sma)
    except Exception:
        return None


def compute_target_weights(
    as_of: pd.Timestamp,
    tickers: list[str],
    prices_dict: dict[str, pd.DataFrame],
    data_dir: Path,
    *,
    top_n: int = 3,
    sideways_risk_scale: float = 0.5,
    llm_enabled: bool | None = None,
    score_floor: float | None = None,
) -> pd.Series:
    """
    Target weights from canonical spine (SignalEngine -> PolicyEngine -> PortfolioEngine).
    Delegates to src.core.target_weight_pipeline.compute_target_weights (path="weekly").
    score_floor: optional; when provided, passed to pipeline for regime-aware filtering (continuous from meta_weights).
    """
    from src.core.target_weight_pipeline import (
        compute_target_weights as _compute_target_weights,
    )
    from src.utils.config_manager import get_config as _get_config

    _llm = (
        bool(llm_enabled)
        if llm_enabled is not None
        else bool(_get_config().get_param("llm_analysis.enabled", True))
    )
    kwargs = {
        "top_n": top_n,
        "sideways_risk_scale": sideways_risk_scale,
        "weight_mode": "fixed",
        "path": "weekly",
        "llm_enabled": _llm,
    }
    if score_floor is not None:
        kwargs["score_floor"] = score_floor
    return _compute_target_weights(
        as_of,
        tickers,
        prices_dict,
        data_dir,
        **kwargs,
    )


def _create_paper_executor():
    """Create IB executor in paper mode using config/trading_config.yaml (host, port, paper_account)."""
    trading_config_path = ROOT / "config" / "trading_config.yaml"
    if not trading_config_path.exists():
        raise FileNotFoundError("config/trading_config.yaml required for --mode paper")
    with open(trading_config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    trading = config.get("trading", {})
    ib_config = trading.get("ib", {})
    execution_config = trading.get("execution", {})
    import os as _os

    paper_account = _os.getenv("IBKR_PAPER_ACCOUNT") or execution_config.get(
        "paper_account"
    )
    if not paper_account:
        raise ValueError(
            "Set IBKR_PAPER_ACCOUNT in .env or trading.execution.paper_account in trading_config.yaml"
        )
    from src.data.provider_factory import DataProviderFactory
    from src.execution.ib_executor import IBExecutor

    data_provider = DataProviderFactory.create("ib", **ib_config)
    return IBExecutor(ib_provider=data_provider, account=paper_account)


def _run_pods(
    as_of: pd.Timestamp,
    tickers: list[str],
    prices_dict: dict[str, pd.DataFrame],
    data_dir: Path,
    args: argparse.Namespace,
) -> pd.Series:
    """
    Three-pod aggregation path: Core, Extension, Ballast → aggregate_pod_weights.
    """
    from pods import PodCore, PodExtension, PodBallast, aggregate_pod_weights
    from src.signals.technical_library import (
        calculate_all_indicators,
        compute_signal_strength,
    )

    # 1. Master Score per ticker using technical_library (no look-ahead; slice to as_of)
    scores: dict[str, float] = {}
    prices_sliced: dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = prices_dict.get(t)
        if df is None or df.empty:
            continue
        df_slice = df[df.index <= as_of]
        if df_slice.empty or len(df_slice) < 60:
            continue
        prices_sliced[t] = df_slice
        try:
            indi = calculate_all_indicators(df_slice)
            if indi.empty:
                continue
            row = indi.iloc[-1]
            score, _meta = compute_signal_strength(row)
            scores[t] = float(score)
        except Exception as e:
            print(f"[PODS] Master score failed for {t}: {e}", flush=True)
            continue

    if not scores:
        print("[PODS] No valid master scores; returning empty weights.", flush=True)
        return pd.Series(dtype=float)

    scores_series = pd.Series(scores)

    # 2. Load regime_status (silent fail → empty dict)
    regime_status: dict = {}
    regime_path = ROOT / "outputs" / "regime_status.json"
    try:
        if regime_path.exists():
            with open(regime_path, "r", encoding="utf-8") as f:
                regime_status = json.load(f)
    except Exception as e:
        print(f"[PODS] Could not load regime_status.json: {e}", flush=True)
        regime_status = {}

    # 3. Load pod config and Track D config for Extension pod
    import yaml as _yaml

    mcfg_path = ROOT / "config" / "model_config.yaml"
    pods_cfg: dict = {}
    track_d_cfg: dict = {}
    if mcfg_path.exists():
        try:
            with open(mcfg_path, "r", encoding="utf-8") as f:
                mcfg = _yaml.safe_load(f) or {}
            pods_cfg = mcfg.get("pods", {}) or {}
            track_d_cfg = (mcfg.get("tracks", {}) or {}).get("D", {}) or {}
        except Exception as e:
            print(f"[PODS] Could not load model_config.yaml: {e}", flush=True)
            pods_cfg = {}
            track_d_cfg = {}

    core_cfg = pods_cfg.get("core", {}) or {}
    extension_cfg = track_d_cfg
    ballast_cfg = dict(pods_cfg.get("ballast", {}) or {})

    # 4. Load meta weights early so we can inject ballast_weight into ballast_cfg (Change 4)
    default_meta = {"core": 0.50, "extension": 0.30, "ballast": 0.20}
    meta_weights_path = ROOT / (
        pods_cfg.get("meta_weights_path") or "outputs/meta_weights.json"
    )
    meta_weights = default_meta.copy()
    try:
        if meta_weights_path.exists():
            with open(meta_weights_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            w = data.get("weights") or data
            for k in default_meta:
                if k in w:
                    meta_weights[k] = float(w[k])
    except Exception as e:
        print(f"[PODS] Could not load meta_weights.json: {e}", flush=True)
        meta_weights = default_meta.copy()
    meta_weights_override = regime_status.get("meta_weights_override")
    if isinstance(meta_weights_override, dict):
        meta_weights = default_meta.copy()
        for k in default_meta:
            if k in meta_weights_override:
                meta_weights[k] = float(meta_weights_override[k])
    ballast_cap = (
        0.60 if str(regime_status.get("regime_state", "")) == "Contraction" else 0.50
    )
    ballast_weight = max(0.20, min(ballast_cap, meta_weights.get("ballast", 0.20)))
    ballast_cfg["ballast_weight"] = ballast_weight

    # --- Step A — Load and reconcile frozen state ---
    try:
        import logging as _logging

        _logger = _logging.getLogger(__name__)
        _manual_resumed: set[str] = set()
        _frozen_pods_path = ROOT / "outputs" / "frozen_pods.json"
        frozen_pods_data = {"as_of": None, "frozen_pods": {}}
        if _frozen_pods_path.exists():
            try:
                with open(_frozen_pods_path, "r", encoding="utf-8") as _f:
                    frozen_pods_data = json.load(_f) or frozen_pods_data
            except Exception:
                frozen_pods_data = {"as_of": None, "frozen_pods": {}}
        current_frozen = frozen_pods_data.get("frozen_pods", {}) or {}

        _strategy_params_path = ROOT / "config" / "strategy_params.yaml"
        strategy_params = {}
        if _strategy_params_path.exists():
            try:
                with open(_strategy_params_path, "r", encoding="utf-8") as _f:
                    strategy_params = _yaml.safe_load(_f) or {}
            except Exception:
                strategy_params = {}
        resume_list = (strategy_params.get("pod_overrides", {}) or {}).get(
            "frozen_pods_resume", []
        ) or []
        for _pod_name in resume_list:
            if _pod_name in current_frozen:
                current_frozen.pop(_pod_name, None)
                _manual_resumed.add(_pod_name)
                log_incident(
                    "pod_unfrozen", {"pod": _pod_name, "manual_override": True}
                )
                _logger.info(
                    "[POD_FREEZE] %s manually unfrozen via strategy_params.yaml",
                    _pod_name,
                )
        try:
            _frozen_pods_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                _frozen_pods_path,
                {
                    "as_of": datetime.now(timezone.utc).isoformat(),
                    "frozen_pods": current_frozen,
                },
            )
        except Exception:
            pass
    except Exception as _e:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "[POD_FREEZE] Step A failed (fail-open): %s", _e
        )
        current_frozen = {}
        _manual_resumed = set()

    # --- Step B — Assess breakdown and apply new freezes ---
    try:
        breakdown = None
        _breakdown_path = ROOT / "outputs" / "structural_breakdown.json"
        if _breakdown_path.exists():
            try:
                with open(_breakdown_path, "r", encoding="utf-8") as _f:
                    breakdown = json.load(_f)
            except Exception:
                breakdown = None
        if isinstance(breakdown, dict) and breakdown:
            MANDATES = {
                "core": [0.8, 1.2],
                "extension": [-0.2, 0.6],
                "ballast": [0.0, 0.5],
            }
            _now_iso = datetime.now(timezone.utc).isoformat()

            if (
                breakdown.get("ic_decay", {}).get("severity") == "critical"
                and "extension" not in current_frozen
                and "extension" not in _manual_resumed
            ):
                current_frozen["extension"] = {
                    "reason": "IC decay CRITICAL",
                    "frozen_at": _now_iso,
                }
                log_incident(
                    "pod_frozen", {"pod": "extension", "reason": "IC decay CRITICAL"}
                )

            if (
                breakdown.get("residual_risk", {}).get("severity") == "critical"
                and "extension" not in current_frozen
                and "extension" not in _manual_resumed
            ):
                current_frozen["extension"] = {
                    "reason": "Residual risk CRITICAL",
                    "frozen_at": _now_iso,
                }
                log_incident(
                    "pod_frozen",
                    {"pod": "extension", "reason": "Residual risk CRITICAL"},
                )

            if breakdown.get("regime_misalignment", {}).get("severity") == "critical":
                pod_betas = (breakdown.get("regime_misalignment", {}) or {}).get(
                    "pod_betas", {}
                ) or {}
                worst_pod = None
                worst_excess = 0.0
                worst_beta = None
                for _p in ("core", "extension", "ballast"):
                    mandate = MANDATES.get(_p)
                    if not mandate:
                        continue
                    beta = float(pod_betas.get(_p, 0) or 0)
                    excess = max(
                        0.0, float(mandate[0]) - beta, beta - float(mandate[1])
                    )
                    if excess > worst_excess:
                        worst_excess = excess
                        worst_pod = _p
                        worst_beta = beta
                if (
                    worst_pod is not None
                    and worst_excess > 0
                    and worst_pod not in current_frozen
                ):
                    if worst_pod in _manual_resumed:
                        worst_pod = None
                if (
                    worst_pod is not None
                    and worst_excess > 0
                    and worst_pod not in current_frozen
                ):
                    current_frozen[worst_pod] = {
                        "reason": "Beta mandate breach CRITICAL",
                        "frozen_at": _now_iso,
                    }
                    log_incident(
                        "pod_frozen",
                        {
                            "pod": worst_pod,
                            "reason": "Beta mandate breach CRITICAL",
                            "beta": worst_beta,
                        },
                    )

            try:
                _frozen_pods_path = ROOT / "outputs" / "frozen_pods.json"
                _frozen_pods_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(
                    _frozen_pods_path,
                    {
                        "as_of": datetime.now(timezone.utc).isoformat(),
                        "frozen_pods": current_frozen,
                    },
                )
            except Exception:
                pass
    except Exception as _e:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "[POD_FREEZE] Step B failed (no new freezes applied): %s", _e
        )

    # 5. Instantiate and call pods with per-pod error isolation
    core = PodCore()
    ext = PodExtension()
    ballast = PodBallast()

    pod_weights: dict[str, pd.Series] = {}

    try:
        if "core" in current_frozen:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "[POD_FREEZE] %s is frozen — weights zeroed. reason=%s",
                "core",
                (current_frozen.get("core") or {}).get("reason"),
            )
            pod_weights["core"] = pd.Series(dtype=float)
        else:
            w_core = core.generate_weights(
                scores_series, prices_sliced, regime_status, core_cfg
            )
            pod_weights["core"] = (
                w_core if isinstance(w_core, pd.Series) else pd.Series(dtype=float)
            )
    except Exception as e:
        print(f"[POD_CORE] Error: {e}", flush=True)
        pod_weights["core"] = pd.Series(dtype=float)

    _fsm_audit: dict | None = None
    try:
        if "extension" in current_frozen:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "[POD_FREEZE] %s is frozen — weights zeroed. reason=%s",
                "extension",
                (current_frozen.get("extension") or {}).get("reason"),
            )
            pod_weights["extension"] = pd.Series(dtype=float)
        else:
            w_ext = ext.generate_weights(
                scores_series, prices_sliced, regime_status, extension_cfg
            )
            pod_weights["extension"] = (
                w_ext if isinstance(w_ext, pd.Series) else pd.Series(dtype=float)
            )
            # Capture FSM audit fields written as side-channel by rebalance_alpha_sleeve
            _fsm_audit = {
                "state": extension_cfg.pop("_last_fsm_state", "unknown"),
                "trigger": extension_cfg.pop("_last_fsm_trigger", "none"),
                "reason": extension_cfg.pop("_last_fsm_reason", ""),
            }
    except Exception as e:
        print(f"[POD_EXTENSION] Error: {e}", flush=True)
        pod_weights["extension"] = pd.Series(dtype=float)

    try:
        if "ballast" in current_frozen:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "[POD_FREEZE] %s is frozen — weights zeroed. reason=%s",
                "ballast",
                (current_frozen.get("ballast") or {}).get("reason"),
            )
            pod_weights["ballast"] = pd.Series(dtype=float)
        else:
            w_ballast = ballast.generate_weights(
                scores_series, prices_sliced, regime_status, ballast_cfg
            )
            pod_weights["ballast"] = (
                w_ballast
                if isinstance(w_ballast, pd.Series)
                else pd.Series(dtype=float)
            )
    except Exception as e:
        print(f"[POD_BALLAST] Error: {e}", flush=True)
        pod_weights["ballast"] = pd.Series(dtype=float)

    # 6. Load universe pillars from config/universe.yaml
    universe_pillars: dict[str, list] = {}
    universe_path = ROOT / "config" / "universe.yaml"
    if universe_path.exists():
        try:
            with open(universe_path, "r", encoding="utf-8") as f:
                ucfg = _yaml.safe_load(f) or {}
            universe_pillars = ucfg.get("pillars", {}) or {}
        except Exception as e:
            print(f"[PODS] Could not load universe.yaml: {e}", flush=True)
            universe_pillars = {}

    # 7. Aggregate with sector and gross caps from pods config
    sector_cap = float(pods_cfg.get("sector_cap", 0.40))
    gross_cap = float(pods_cfg.get("gross_cap", 1.60))
    cr_cfg = pods_cfg.get("conflict_resolution", {})
    veto_threshold = float(cr_cfg.get("veto_threshold", 0.25))
    shrinkage_floor = float(cr_cfg.get("shrinkage_floor", 0.50))

    active_pods = [
        p
        for p in meta_weights
        if p not in current_frozen
        and not pod_weights.get(p, pd.Series(dtype=float)).empty
    ]
    active_total = float(sum(meta_weights.get(p, 0.0) for p in active_pods))
    if active_total > 0 and active_pods:
        effective_meta = {p: float(meta_weights[p]) / active_total for p in active_pods}
    elif active_pods:
        effective_meta = {p: 1.0 / len(active_pods) for p in active_pods}
    else:
        effective_meta = {}

    agg_weights = aggregate_pod_weights(
        pod_weights=pod_weights,
        meta_weights=effective_meta,
        universe_pillars=universe_pillars,
        sector_cap=sector_cap,
        gross_cap=gross_cap,
        veto_threshold=veto_threshold,
        shrinkage_floor=shrinkage_floor,
        audit_path=ROOT / "outputs" / "aggregator_audit.json",
        fsm_audit=_fsm_audit,
    )

    # 8. Print per-pod and final summary
    for name in ("core", "extension", "ballast"):
        s = pod_weights.get(name, pd.Series(dtype=float))
        active = int((s != 0).sum()) if not s.empty else 0
        gross = float(s.abs().sum()) if not s.empty else 0.0
        print(f"[POD_{name.upper()}] positions={active} gross={gross:.3f}", flush=True)

    active_total = int((agg_weights != 0).sum()) if not agg_weights.empty else 0
    gross_total = float(agg_weights.abs().sum()) if not agg_weights.empty else 0.0
    net_total = float(agg_weights.sum()) if not agg_weights.empty else 0.0
    print(
        f"[PODS] Aggregated -- positions={active_total} gross={gross_total:.3f} net={net_total:.3f}",
        flush=True,
    )

    # Log per-pod weights before returning (for pod_pnl_tracker)
    try:
        from src.portfolio.pod_pnl_tracker import log_pod_weights

        pod_weights_dict = {
            name: (s.to_dict() if hasattr(s, "to_dict") else dict(s))
            for name, s in pod_weights.items()
        }
        log_pod_weights(
            pod_weights=pod_weights_dict,
            aggregate_weights=agg_weights,
            as_of=datetime.now(timezone.utc).isoformat(),
            history_path=ROOT / "outputs" / "pod_weights_history.jsonl",
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("log_pod_weights failed: %s", e)

    return agg_weights


def _write_execution_status(
    report: "DataQualityReport | None",
    ibkr_state: str = "UNKNOWN",
    manual_intervention_required: bool = False,
) -> None:
    """Merge report and ibkr fields with existing outputs/execution_status.json and write. Silent fail on error."""
    from datetime import datetime as _dt

    path = ROOT / "outputs" / "execution_status.json"
    data = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data["as_of"] = _dt.now(timezone.utc).isoformat()
    data["ibkr_state"] = ibkr_state
    data["manual_intervention_required"] = manual_intervention_required
    if report is not None:
        data["can_rebalance"] = report.can_rebalance
        data["critical_missing"] = list(report.critical_missing)
        data["degraded_missing"] = list(report.degraded_missing)
        data["warnings"] = list(report.warnings)
    else:
        data["can_rebalance"] = True
        data["critical_missing"] = []
        data["degraded_missing"] = []
        data["warnings"] = []
    try:
        atomic_write_json(path, data)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(
            "Could not write execution_status.json: %s", e
        )


def _update_drawdown_tracker(account_value: float, tracker_path: Path) -> dict:
    """
    Read outputs/drawdown_tracker.json if it exists; update peak_nav, current_nav,
    drawdown, last_updated; write back. If file missing, initialise with peak_nav=account_value,
    drawdown=0.0, flatten_active=False. Returns the updated tracker dict.
    """
    from datetime import datetime, timezone

    default = {
        "peak_nav": account_value,
        "current_nav": account_value,
        "drawdown": 0.0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "flatten_active": False,
    }
    if not tracker_path.exists():
        atomic_write_json(tracker_path, default)
        return default
    try:
        with open(tracker_path, "r", encoding="utf-8") as f:
            tracker = json.load(f)
    except Exception:
        tracker = dict(default)
    peak = float(tracker.get("peak_nav", account_value))
    peak = max(peak, account_value)
    tracker["peak_nav"] = peak
    tracker["current_nav"] = account_value
    tracker["drawdown"] = (account_value - peak) / peak if peak > 0 else 0.0
    tracker["last_updated"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(tracker_path, tracker)
    return tracker


def _get_score_floor() -> float:
    """
    Continuous score_floor from meta_weights.json: 0.50 + 0.30 * ballast_weight,
    with ballast_weight clipped to [0.20, 0.50]. Fallback: regime_status.json spy_below_sma -> 0.65 else 0.50.
    """
    meta_path = ROOT / "outputs" / "meta_weights.json"
    try:
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            weights = data.get("weights") or data
            ballast_weight = float(weights.get("ballast", 0.20))
            ballast_weight = max(0.20, min(0.50, ballast_weight))
            return 0.50 + 0.30 * ballast_weight
    except Exception:
        pass
    regime_path = ROOT / "outputs" / "regime_status.json"
    try:
        if regime_path.exists():
            with open(regime_path, "r", encoding="utf-8") as f:
                regime = json.load(f)
            score_floor_val = regime.get("score_floor")
            if score_floor_val is not None:
                return float(score_floor_val)
            if regime.get("spy_below_sma", regime.get("spy_below_sma200", False)):
                return 0.65
    except Exception:
        pass
    return 0.50


def main() -> tuple[int, list]:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
    parser = argparse.ArgumentParser(
        description="Canonical execution: spine -> Intent -> delta trades (mock or IB paper)."
    )
    parser.add_argument(
        "--tickers",
        type=str,
        required=True,
        help="Comma-separated tickers (e.g. AAPL,NVDA,SPY)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Signal date YYYY-MM-DD; default: latest Monday in data",
    )
    parser.add_argument("--top-n", type=int, default=3, help="Top N for portfolio")
    parser.add_argument(
        "--sideways-risk-scale", type=float, default=0.5, help="Sideways regime scale"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="mock",
        choices=["mock", "paper"],
        help="mock (print only) or paper (IB paper account)",
    )
    parser.add_argument(
        "--confirm-paper",
        action="store_true",
        help="With --mode paper: actually submit orders; without: dry-run print only",
    )
    parser.add_argument(
        "--rebalance",
        action="store_true",
        help="Rebalance mode: use last valid weights from cache; only propose trades for tickers that drifted past threshold (see strategy_params.rebalancing)",
    )
    parser.add_argument(
        "--check-fills",
        action="store_true",
        help="Skip execution; read fill ledger, print partial/unknown summary, and (in paper mode) query IB for current order status",
    )
    parser.add_argument(
        "--no-llm", action="store_true", help="Skip LLM and FinBERT news scoring"
    )
    parser.add_argument(
        "--no-hedge",
        action="store_true",
        help="Disable SMH hedge for this run (ignore trading_config hedge_enabled).",
    )
    parser.add_argument(
        "--pods", action="store_true", help="Enable three-pod allocation path"
    )
    parser.add_argument(
        "--reset-stop-loss",
        action="store_true",
        help="Clear flatten_active in drawdown_tracker and continue normal execution",
    )
    parser.add_argument(
        "--regime-multiplier",
        type=float,
        default=1.0,
        help="Deprecated: no longer applied to NAV (RiskPolicy.position_scale in weekly Two-Lane).",
    )
    parser.add_argument("--ibkr-host", type=str, default="127.0.0.1")
    parser.add_argument("--ibkr-port", type=int, default=7497)
    args = parser.parse_args()

    run_start_ts = datetime.now(timezone.utc).isoformat()
    current_run_fills: list = []

    if args.check_fills:
        from src.execution.fill_ledger import read_fill_ledger

        path = ROOT / "outputs" / "fills" / "fills.jsonl"
        records = read_fill_ledger(path)
        outstanding = [r for r in records if r.get("status") in ("partial", "unknown")]
        if not outstanding:
            print("No partial or unknown fills in ledger.", flush=True)
            return (0, [])
        print(
            f"--- Outstanding fills (partial/unknown): {len(outstanding)} ---",
            flush=True,
        )
        for r in outstanding:
            print(
                f"  {r.get('timestamp', '')} | {r.get('ticker', '')} | {r.get('side', '')} | "
                f"qty_req={r.get('qty_requested')} filled={r.get('qty_filled')} | "
                f"order_id={r.get('order_id')} | {r.get('status')} | {r.get('fill_check_reason', '')}",
                flush=True,
            )
        if args.mode == "paper":
            from src.execution.executor_factory import ExecutorFactory

            try:
                executor = _create_paper_executor()
                if hasattr(executor, "ib"):
                    _req = getattr(executor.ib, "reqOpenOrders", None) or getattr(
                        executor.ib, "requestOpenOrders", None
                    )
                    if callable(_req):
                        _req()
                    open_trades = list(executor.ib.openTrades())
                    print("--- IB open orders / trades ---", flush=True)
                    order_ids_ledger = {
                        str(r.get("order_id")) for r in outstanding if r.get("order_id")
                    }
                    for t in open_trades:
                        oid = str(t.order.orderId) if t.order else None
                        if oid in order_ids_ledger or not order_ids_ledger:
                            status = t.orderStatus.status if t.orderStatus else "?"
                            filled = getattr(t.orderStatus, "filled", 0) or 0
                            avg = getattr(t.orderStatus, "avgFillPrice", None) or None
                            print(
                                f"  order_id={oid} status={status} filled={filled} avgFillPrice={avg}",
                                flush=True,
                            )
            except Exception as e:
                print(f"  [WARN] Could not query IB: {e}", flush=True)
        return (0, [])

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        print("ERROR: No tickers provided.", flush=True)
        return (1, [])

    config = load_data_config()
    data_dir = config["data_dir"]
    prices_dict = load_prices(data_dir, tickers)

    _live_px: dict = {}
    _acct: dict = {}
    _contract_map: dict = {}
    if args.mode == "paper":
        try:
            from src.data import ibkr_live_provider as _ibkr
            from src.data.contract_resolver import resolve as _resolve_contract

            _live_client_id = 10 + (
                int(time.time()) % 89
            )  # 10–98; avoids reuse across rapid restarts
            _ib = _ibkr.connect(
                args.ibkr_host, args.ibkr_port, client_id=_live_client_id
            )
            try:
                _contracts = []
                _contract_map = {}
                for _t in tickers:
                    try:
                        _itype = _instrument_type(_t)
                        _c = _resolve_contract(_t, _itype, _ib)
                        _contracts.append(_c)
                        _contract_map[_t] = _c
                    except Exception as _ce:
                        print(
                            f"[IBKR][WARN] contract_resolver failed for {_t}: {_ce}; skipping.",
                            flush=True,
                        )
                _live_px = _ibkr.get_live_prices(_ib, _contracts) if _contracts else {}
                _acct = _ibkr.get_account_summary(_ib)
            finally:
                _ib.disconnect()
        except Exception as _e:
            print(
                f"[IBKR][WARN] Live price/account fetch failed: {_e}; "
                f"falling back to CSV prices and config NAV.",
                flush=True,
            )
            _live_px = {}
            _acct = {}
            _contract_map = {}

    # Overlay live prices as the last bar in prices_dict (paper mode only).
    # Keeps full CSV history intact for signal computation.
    # Only updates close (and open/high/low to same value) for the as_of bar.
    if args.mode == "paper" and _live_px:
        for ticker, px in _live_px.items():
            if ticker in prices_dict and px and px > 0:
                df = prices_dict[ticker]
                last_idx = df.index[-1]
                for col in ["close", "open", "high", "low"]:
                    if col in df.columns:
                        df[col] = df[col].astype(float)
                        df.loc[last_idx, col] = float(px)
                prices_dict[ticker] = df

    # Data quality check (RESILIENCE_SPEC Section 2)
    critical_missing = []
    degraded_missing = []
    warnings_list = []
    if not prices_dict:
        critical_missing.append("prices")
    smh_path = data_dir.parent / "benchmarks" / "SMH.csv"
    if not smh_path.exists() or smh_path.stat().st_size == 0:
        critical_missing.append("smh_benchmark")
    regime_path = ROOT / "outputs" / "regime_status.json"
    if not regime_path.exists():
        critical_missing.append("regime_status")
    dq_report = DataQualityReport(
        critical_missing=critical_missing,
        degraded_missing=degraded_missing,
        warnings=warnings_list,
    )
    if not dq_report.can_rebalance:
        _write_execution_status(
            dq_report, ibkr_state="UNKNOWN", manual_intervention_required=True
        )
        for src in dq_report.critical_missing:
            import logging

            logging.getLogger(__name__).error(
                "[DATA QUALITY] Critical source missing: %s", src
            )
        print(
            f"[DATA QUALITY] Cannot rebalance - critical sources missing: {dq_report.critical_missing}",
            flush=True,
        )
        return (1, [])
    if dq_report.degraded_missing or dq_report.warnings:
        import logging

        logging.getLogger(__name__).warning(
            "[DATA QUALITY] Degraded or warnings (continuing): degraded_missing=%s warnings=%s",
            dq_report.degraded_missing,
            dq_report.warnings,
        )

    all_dates = sorted(set().union(*[df.index for df in prices_dict.values()]))
    if not all_dates:
        print("ERROR: No dates in price data.", flush=True)
        return (1, [])

    if args.date:
        as_of = pd.to_datetime(args.date).normalize()
        if as_of not in all_dates and as_of not in pd.DatetimeIndex(all_dates):
            mondays = pd.date_range(min(all_dates), max(all_dates), freq="W-MON")
            mondays = mondays[mondays <= as_of]
            as_of = mondays[-1] if len(mondays) else pd.Timestamp(all_dates[-1])
    else:
        _today = pd.Timestamp.today().normalize()
        mondays = pd.date_range(min(all_dates), max(all_dates), freq="W-MON")
        mondays = mondays[
            mondays <= _today
        ]  # cap at today — prevents future-dated CSV rows driving as_of
        as_of = mondays[-1] if len(mondays) else pd.Timestamp(all_dates[-1])

    # Resolve executor, position_manager, and account_value before weight computation (stop-loss gate needs NAV).
    from src.execution.mock_executor import MockExecutor
    from src.portfolio.position_manager import PositionManager

    trading_config_path = ROOT / "config" / "trading_config.yaml"
    if args.mode == "mock":
        executor = ExecutorFactory.from_config_file()
        if not isinstance(executor, MockExecutor):
            raise RuntimeError(
                "With --mode mock, config must specify executor: mock. "
                "Use --mode paper for IB paper."
            )
    else:
        try:
            executor = _create_paper_executor()
        except (ConnectionError, Exception) as _pe:
            print(
                f"[IBKR][WARN] Paper executor connection failed: {_pe}\n"
                f"  Continuing in read-only paper mode (live prices/account from ibkr_live_provider; "
                f"no order submission until --confirm-paper with live TWS connection).",
                flush=True,
            )
            executor = ExecutorFactory.from_config_file()
    position_manager = PositionManager(executor)
    current_positions = position_manager.get_current_positions()
    current_weights = position_manager.positions_to_weights(current_positions)
    account_value = position_manager.get_account_value()
    if args.mode == "paper" and _acct:
        live_nav = _acct.get("net_liquidation", 0.0)
        if live_nav > 0:
            account_value = live_nav
        print(
            f"[IBKR] Account — NAV={live_nav:,.0f}  "
            f"AvailFunds={_acct.get('available_funds', 0):,.0f}  "
            f"MaintMargin={_acct.get('maint_margin_req', 0):,.0f}  "
            f"InitMargin={_acct.get('init_margin_req', 0):,.0f}",
            flush=True,
        )
    elif args.mode == "paper" and hasattr(executor, "ib_provider"):
        try:
            from src.execution.ibkr_bridge import AccountMonitor

            monitor_for_nav = AccountMonitor(executor.ib_provider)
            monitor_for_nav.refresh()
            live_nav = monitor_for_nav.get_net_liquidation()
            if live_nav > 0:
                account_value = live_nav
        except Exception:
            pass
    if account_value <= 0 and trading_config_path.exists():
        with open(trading_config_path, "r", encoding="utf-8") as f:
            tc = yaml.safe_load(f)
        account_value = float(tc.get("trading", {}).get("initial_capital", 100_000))
    # Regime de-gross removed from run_execution; weekly Two-Lane uses RiskPolicy.position_scale.

    _futures_mults = _load_futures_multipliers()

    if args.rebalance:
        # Rebalance mode: pull last valid weights from cache (no fresh signal generation)
        if not LAST_VALID_WEIGHTS_PATH.exists():
            print(
                "ERROR: --rebalance requires last valid weights. Run without --rebalance once to populate outputs/last_valid_weights.json",
                flush=True,
            )
            return (1, [])
        with open(LAST_VALID_WEIGHTS_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        target_weights_dict = cache.get("weights") or {}
        if not target_weights_dict:
            print("No weights in cache. Run without --rebalance first.", flush=True)
            return (1, [])
        optimal_weights_series = (
            pd.Series(target_weights_dict).reindex(tickers, fill_value=0.0).fillna(0.0)
        )
        intent_tickers = [
            t
            for t, w in target_weights_dict.items()
            if float(w) != 0 and t in set(tickers)
        ]
        intent = SimpleNamespace(
            tickers=intent_tickers,
            weights=dict(optimal_weights_series),
            futures_multipliers=_futures_mults,
        )
    else:
        # --reset-stop-loss: fully reset tracker to current NAV before any other logic
        if args.reset_stop_loss:
            _dd_path = ROOT / "outputs" / "drawdown_tracker.json"
            try:
                _fresh = {
                    "peak_nav": account_value,
                    "current_nav": account_value,
                    "drawdown": 0.0,
                    "flatten_active": False,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }
                atomic_write_json(_dd_path, _fresh)
                print(
                    "[STOP-LOSS] Reset: peak_nav and flatten_active cleared. Normal execution continues.",
                    flush=True,
                )
            except Exception as _e:
                print(f"[STOP-LOSS] Reset failed: {_e}", flush=True)

        _tracker_path = ROOT / "outputs" / "drawdown_tracker.json"
        tracker = _update_drawdown_tracker(account_value, _tracker_path)
        stop_threshold = -0.10
        _mcfg_path = ROOT / "config" / "model_config.yaml"
        if _mcfg_path.exists():
            try:
                with open(_mcfg_path, "r", encoding="utf-8") as _f:
                    _mcfg = yaml.safe_load(_f) or {}
                stop_threshold = float(
                    _mcfg.get("risk_management", {}).get("stop_loss_threshold", -0.10)
                )
            except Exception:
                pass
        if tracker["drawdown"] <= stop_threshold or tracker.get("flatten_active"):
            print(
                f"[STOP-LOSS] Drawdown {tracker['drawdown']:.1%} hit threshold {stop_threshold:.0%} - FLATTEN ALL. Skipping weight generation.",
                flush=True,
            )
            optimal_weights_series = pd.Series(0.0, index=tickers)
            intent_tickers = []
            intent = SimpleNamespace(
                tickers=[], weights={}, futures_multipliers=_futures_mults
            )
            try:
                from src.monitoring.telegram_alerts import send_alert

                send_alert(
                    "stop_loss",
                    {
                        "drawdown": tracker["drawdown"],
                        "peak_nav": tracker.get("peak_nav", 0),
                        "current_nav": tracker.get("current_nav", 0),
                    },
                )
            except Exception:
                pass
            tracker["flatten_active"] = True
            atomic_write_json(_tracker_path, tracker)
            _is_live_executor = (
                getattr(executor, "ib", None) is not None
                and getattr(executor.ib, "isConnected", lambda: False)()
            )
            if _is_live_executor:
                try:
                    _cancelled_ids = executor.cancel_all_orders()
                    _safe_result = executor.verify_safe_state()
                    log_incident(
                        "circuit_breaker_triggered",
                        {
                            "trigger": "global_stop_loss",
                            "drawdown": tracker.get("drawdown"),
                            "peak_nav": tracker.get("peak_nav"),
                            "cancelled_order_ids": _cancelled_ids,
                            "safe_state": _safe_result.get("safe_state"),
                            "open_orders_remaining": _safe_result.get(
                                "open_orders_remaining"
                            ),
                        },
                    )
                    log_incident("safe_state_verified", _safe_result)
                    _status_path = ROOT / "outputs" / "execution_status.json"
                    _status = {}
                    if _status_path.exists():
                        try:
                            with open(_status_path, "r", encoding="utf-8") as _f:
                                _status = json.load(_f)
                        except Exception:
                            pass
                    _status.update(_safe_result)
                    _status["cancelled_order_ids"] = _cancelled_ids
                    try:
                        atomic_write_json(_status_path, _status)
                    except Exception:
                        pass
                except Exception as _cancel_err:
                    import logging

                    logging.getLogger(__name__).error(
                        "[STOP_LOSS] Order cancellation failed: %s", _cancel_err
                    )
                    log_incident(
                        "circuit_breaker_triggered",
                        {
                            "trigger": "global_stop_loss",
                            "cancellation_error": str(_cancel_err),
                            "drawdown": tracker.get("drawdown"),
                        },
                    )
            else:
                log_incident(
                    "circuit_breaker_triggered",
                    {
                        "trigger": "global_stop_loss",
                        "drawdown": tracker.get("drawdown"),
                        "mode": "mock — no orders to cancel",
                    },
                )
            return (0, [])

        score_floor = _get_score_floor()
        if args.pods:
            optimal_weights_series = _run_pods(
                as_of, tickers, prices_dict, data_dir, args
            )
        else:
            optimal_weights_series = compute_target_weights(
                as_of,
                tickers,
                prices_dict,
                data_dir,
                top_n=args.top_n,
                sideways_risk_scale=args.sideways_risk_scale,
                llm_enabled=not args.no_llm,
                score_floor=score_floor,
            )
        if optimal_weights_series.sum() == 0:
            print("No target tickers from portfolio engine.", flush=True)
            return (0, [])
        intent_tickers = [t for t, w in optimal_weights_series.items() if float(w) != 0]
        intent = SimpleNamespace(
            tickers=intent_tickers,
            weights=optimal_weights_series.to_dict(),
            futures_multipliers=_futures_mults,
        )
        # Persist for next --rebalance
        atomic_write_json(
            LAST_VALID_WEIGHTS_PATH,
            {
                "as_of": str(as_of.date()),
                "weights": optimal_weights_series.to_dict(),
            },
        )

    # Successful completion: write execution_status for dashboard (RESILIENCE_SPEC Section 2)
    _ibkr_state = "CONNECTED" if args.mode == "paper" else "UNKNOWN"
    _write_execution_status(
        DataQualityReport(), ibkr_state=_ibkr_state, manual_intervention_required=False
    )

    smh_short_shares = 0
    smh_hedge_row = None
    if optimal_weights_series.sum() != 0 and intent_tickers:
        if trading_config_path.exists():
            with open(trading_config_path, "r", encoding="utf-8") as f:
                tc_hedge = yaml.safe_load(f) or {}
            hedge_cfg = tc_hedge.get("trading", {}).get("hedge", {})
            _hedge_on = bool(hedge_cfg.get("hedge_enabled", False)) and not bool(
                getattr(args, "no_hedge", False)
            )
            if _hedge_on:
                hedge_ratio = float(hedge_cfg.get("hedge_ratio", 1.0))
                annual_borrow_rate = float(hedge_cfg.get("annual_borrow_rate", 0.05))
                beta_lookback_days = int(hedge_cfg.get("beta_lookback_days", 60))
                smh_prices = load_prices(data_dir, ["SMH"])
                smh_df = smh_prices.get("SMH") if smh_prices else None
                if (
                    smh_df is not None
                    and not smh_df.empty
                    and "close" in smh_df.columns
                ):
                    smh_sliced = smh_df.loc[smh_df.index <= as_of]
                    if not smh_sliced.empty:
                        rets_smh = smh_sliced["close"].pct_change().dropna()
                        smh_last_price = float(smh_sliced["close"].iloc[-1])
                        if smh_last_price > 0:
                            betas = {}
                            for t in intent_tickers:
                                if (
                                    t not in prices_dict
                                    or prices_dict[t] is None
                                    or prices_dict[t].empty
                                ):
                                    betas[t] = 1.0
                                    continue
                                df_t = prices_dict[t].loc[prices_dict[t].index <= as_of]
                                if df_t.empty or "close" not in df_t.columns:
                                    betas[t] = 1.0
                                    continue
                                rets_t = df_t["close"].pct_change().dropna()
                                aligned = (
                                    pd.concat([rets_t, rets_smh], axis=1, join="inner")
                                    .dropna()
                                    .tail(beta_lookback_days)
                                )
                                if len(aligned) >= 20:
                                    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
                                    betas[t] = (
                                        cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 1.0
                                    )
                                else:
                                    betas[t] = 1.0
                            effective_beta = sum(
                                float(optimal_weights_series.get(t, 0)) * betas[t]
                                for t in intent_tickers
                            )
                            smh_short_notional = (
                                account_value * hedge_ratio * effective_beta
                            )
                            smh_short_shares = int(smh_short_notional / smh_last_price)
                            weekly_borrow_cost = (
                                annual_borrow_rate / 52
                            ) * smh_short_notional
                            print(
                                f"  [HEDGE] SMH short: {smh_short_shares} shares | beta={effective_beta:.3f} | weekly_borrow_cost=${weekly_borrow_cost:.2f}",
                                flush=True,
                            )
                            if smh_short_shares > 0:
                                smh_hedge_row = {
                                    "symbol": "SMH",
                                    "side": "SELL",
                                    "quantity": smh_short_shares,
                                    "delta_weight": -effective_beta * hedge_ratio,
                                    "drift": 0.0,
                                    "delta_dollars": -smh_short_notional,
                                }

    if args.rebalance:
        # Portfolio-level rebalance: only orders for tickers that drifted past threshold
        from src.execution.ibkr_bridge import RebalanceLogic

        positions_df = position_manager.get_current_positions()
        current_positions_list = []
        for _, row in positions_df.iterrows():
            current_positions_list.append(
                {
                    "symbol": row.get("symbol", ""),
                    "position": float(row.get("quantity", 0)),
                    "avgCost": float(row.get("avg_cost", 0)),
                    "market_value": float(row.get("market_value", 0)),
                }
            )
        prices_last = {}
        for sym, df in prices_dict.items():
            if df.empty or "close" not in df.columns:
                continue
            try:
                mask = df.index <= as_of
                up_to = df.loc[mask] if hasattr(mask, "any") and mask.any() else df
            except Exception:
                up_to = df
            if up_to.empty:
                continue
            close = up_to["close"].iloc[-1]
            if pd.notna(close):
                prices_last[sym] = float(close)
        # Overlay live prices for instruments without CSV data (e.g. futures like MNQ)
        for sym, px in _live_px.items():
            if sym not in prices_last and px and float(px) > 0:
                prices_last[sym] = float(px)
        rebalance_logic = RebalanceLogic()
        rebalance_orders = rebalance_logic.calculate_rebalance_orders(
            target_weights=intent.weights,
            current_positions=current_positions_list,
            nav=account_value,
            prices=prices_last,
        )
        executable = pd.DataFrame(
            [
                {
                    "symbol": o.ticker,
                    "side": o.side,
                    "quantity": o.quantity,
                    "delta_weight": o.target_weight - o.current_weight,
                    "drift": o.drift,
                    "delta_dollars": o.delta_dollars,
                }
                for o in rebalance_orders
            ]
        )
        if executable.empty:
            executable = pd.DataFrame(
                columns=[
                    "symbol",
                    "side",
                    "quantity",
                    "delta_weight",
                    "drift",
                    "delta_dollars",
                ]
            )
        if smh_short_shares > 0 and smh_hedge_row is not None:
            executable = pd.concat(
                [executable, pd.DataFrame([smh_hedge_row])], ignore_index=True
            )
    else:
        # Build last-close prices as of as_of so PositionManager can compute share quantities.
        # Without prices, quantity = int(delta_dollars / 0) = 0 and executable is always empty.
        prices_last = {}
        for sym, df in prices_dict.items():
            if df.empty or "close" not in df.columns:
                continue
            try:
                mask = df.index <= as_of
                up_to = df.loc[mask] if hasattr(mask, "any") and mask.any() else df
            except Exception:
                up_to = df
            if up_to.empty:
                continue
            close_val = up_to["close"].iloc[-1]
            if isinstance(close_val, pd.Series):
                close_val = close_val.iloc[0]
            if pd.notna(close_val) and float(close_val) > 0:
                prices_last[sym] = float(close_val)
        # Overlay live prices for instruments without CSV data (e.g. futures like MNQ)
        for sym, px in _live_px.items():
            if sym not in prices_last and px and float(px) > 0:
                prices_last[sym] = float(px)
        prices_series = pd.Series(prices_last) if prices_last else None

        delta_trades = position_manager.calculate_delta_trades(
            current_weights=current_weights,
            optimal_weights=optimal_weights_series,
            account_value=account_value,
            prices=prices_series,
            min_trade_size=0.005,
            significance_threshold=0.02,
            futures_multipliers=getattr(intent, "futures_multipliers", {}),
        )
        executable = delta_trades[
            delta_trades["should_trade"] & (delta_trades["quantity"] > 0)
        ]
        if smh_short_shares > 0 and smh_hedge_row is not None:
            executable = pd.concat(
                [executable, pd.DataFrame([smh_hedge_row])], ignore_index=True
            )

    mode_label = "mock" if args.mode == "mock" else "paper"
    title = "rebalance (drift threshold)" if args.rebalance else "delta trades"
    print(f"--- Canonical execution ({mode_label}): {title} ---", flush=True)
    print(f"  As-of:       {as_of.date()}", flush=True)
    print(f"  Account:     {account_value:,.2f}", flush=True)
    print(f"  Intent:      {intent.tickers}", flush=True)
    print(f"  Executable:  {len(executable)}", flush=True)
    for _, row in executable.iterrows():
        drift_str = f" drift={row.get('drift', 0):+.1%}" if "drift" in row else ""
        print(
            f"  {row['side']} {row['quantity']} {row['symbol']} (delta_w={row['delta_weight']:+.2%}{drift_str})",
            flush=True,
        )

    if args.mode == "mock":
        from src.execution.fill_ledger import append_fill_record

        for _, row in executable.iterrows():
            if row["quantity"] <= 0:
                continue
            _rec = append_fill_record(
                run_id=run_start_ts,
                ticker=row["symbol"],
                side=row["side"],
                qty_requested=int(row["quantity"]),
                qty_filled=int(row["quantity"]),
                avg_fill_price=None,
                order_id=None,
                stop_order_id=None,
                status="mock",
                fill_check_passed=True,
                fill_check_reason="mock",
                order_comment=None,
            )
            current_run_fills.append(_rec)
        print("  (Mock: no orders submitted.)", flush=True)
    elif args.mode == "paper":
        if args.confirm_paper:
            # Live Execution Bridge: circuit breaker + AccountMonitor + OrderDispatcher
            from src.execution.ibkr_bridge import (
                AccountMonitor,
                CircuitBreaker,
                OrderDispatcher,
                RiskManager,
                check_fill,
            )

            if hasattr(executor, "ib_provider"):
                monitor = AccountMonitor(executor.ib_provider)
                monitor.refresh()
                nav = monitor.get_net_liquidation()
                if nav <= 0:
                    nav = account_value
                monitor.log_nav_snapshot("Pre-Rebalance NAV", nav)
            else:
                nav = account_value
                monitor = None
            cb = CircuitBreaker()
            cb.record_nav(time.time(), nav)
            if cb.is_trading_paused():
                print(
                    "  [CIRCUIT BREAKER] Trading paused; no orders submitted.",
                    flush=True,
                )
            elif cb.check_and_pause_if_breach(nav):
                print(
                    "  [CIRCUIT BREAKER] 1d drawdown breach; trading paused.",
                    flush=True,
                )
            else:
                # Build ATR and entry price from prices for Smart Stop and sizing
                atr_per_share = {}
                entry_price_map = {}
                if prices_dict:
                    from src.portfolio.position_sizer import compute_atr_series

                    for sym, df in prices_dict.items():
                        df_ohlcv = ensure_ohlcv(df)
                        if len(df_ohlcv) < 2:
                            continue
                        up_to = df_ohlcv[df_ohlcv.index <= as_of]
                        if up_to.empty:
                            continue
                        last = up_to.iloc[-1]
                        _cv = last.get("close", 0)
                        if isinstance(_cv, pd.Series):
                            _cv = _cv.iloc[0]
                        entry_price_map[sym] = float(_cv or 0)
                        atr_series = compute_atr_series(
                            up_to["high"], up_to["low"], up_to["close"], period=14
                        )
                        if not atr_series.empty:
                            _atr_last = atr_series.iloc[-1]
                            if isinstance(_atr_last, pd.Series):
                                _atr_last = _atr_last.iloc[0]
                            atr_per_share[sym] = float(_atr_last)
                        else:
                            atr_per_share[sym] = 0.0
                exec_config = {}
                tc = None
                if trading_config_path.exists():
                    with open(trading_config_path, "r", encoding="utf-8") as f:
                        tc = yaml.safe_load(f)
                    exec_config = tc.get("trading", {}).get("execution", {})
                _min_sz = int(exec_config.get("min_order_size", 1))  # noqa: F841
                _max_sz = int(exec_config.get("max_position_size", 10000))  # noqa: F841
                if monitor is not None:
                    risk_mgr = RiskManager()
                    _tcfg = tc.get("trading", {}) if tc else {}
                    dispatcher = OrderDispatcher(
                        executor, risk_mgr, monitor, trading_cfg=_tcfg
                    )
                    _fill_positions_before = {}
                    _submitted_orders = []
                    if args.confirm_paper:
                        try:
                            for _rec in monitor.get_existing_positions() or []:
                                _sym = str(_rec.get("symbol", "")).upper()
                                _fill_positions_before[_sym] = int(
                                    _rec.get("position", 0)
                                )
                        except Exception:
                            _fill_positions_before = {}
                    for _, row in executable.iterrows():
                        if row["quantity"] <= 0:
                            continue
                        sym = row["symbol"]
                        result = dispatcher.dispatch_from_delta(
                            ticker=sym,
                            quantity=int(row["quantity"]),
                            side=row["side"],
                            entry_price=entry_price_map.get(sym, 0.0) or 1.0,
                            atr_per_share=atr_per_share.get(sym, 0.0),
                            is_propagated=False,
                            order_type="MARKET",
                        )
                        if args.confirm_paper and result.get("status") != "error":
                            _submitted_orders.append(
                                {
                                    "ticker": sym,
                                    "side": result.get("side", row["side"]),
                                    "quantity": result.get(
                                        "quantity", int(row["quantity"])
                                    ),
                                    "order_id": result.get("order_id"),
                                    "stop_order_id": result.get("stop_order_id"),
                                    "filled_quantity": result.get("filled_quantity", 0),
                                    "filled_price": result.get("filled_price"),
                                    "order_comment": result.get("comment"),
                                }
                            )
                        if result.get("status") == "error":
                            print(
                                f"  [ORDER ERROR] {sym}: {result.get('error', 'unknown')}",
                                flush=True,
                            )
                    if monitor is not None:
                        monitor.refresh()
                        monitor.log_nav_snapshot(
                            "Post-Rebalance NAV", monitor.get_net_liquidation()
                        )
                    if args.confirm_paper and _submitted_orders:
                        _FILL_CHECK_DELAY_SECS = 3  # allow broker time to process fills
                        time.sleep(_FILL_CHECK_DELAY_SECS)
                        monitor.refresh()
                        _fill_positions_after = {}
                        try:
                            for _rec in monitor.get_existing_positions() or []:
                                _sym = str(_rec.get("symbol", "")).upper()
                                _fill_positions_after[_sym] = int(
                                    _rec.get("position", 0)
                                )
                        except Exception:
                            _fill_positions_after = {}

                        print("\n--- Fill Check ---")
                        from src.execution.fill_ledger import append_fill_record

                        for _order in _submitted_orders:
                            _t = _order["ticker"].upper()
                            _before = _fill_positions_before.get(_t, 0)
                            _after = _fill_positions_after.get(_t, 0)
                            _chk = check_fill(
                                ticker=_t,
                                side=_order["side"],
                                quantity_submitted=_order["quantity"],
                                position_before=_before,
                                position_after=_after,
                            )
                            _level = "OK   " if _chk["passed"] else "WARN "
                            print(
                                f"[{_level}] {_t}: {_chk['reason']} "
                                f"(before={_before}, after={_after})"
                            )
                            if _chk["passed"] and "full fill" in (
                                _chk.get("reason") or ""
                            ):
                                _status = "full"
                            elif _chk["passed"] and "partial" in (
                                _chk.get("reason") or ""
                            ):
                                _status = "partial"
                            elif not _chk["passed"]:
                                _status = "failed"
                            else:
                                _status = "unknown"
                            _qty_filled = abs(_chk.get("delta_actual", 0))
                            _rec = append_fill_record(
                                run_id=run_start_ts,
                                ticker=_t,
                                side=_order["side"],
                                qty_requested=_order["quantity"],
                                qty_filled=_qty_filled,
                                avg_fill_price=_order.get("filled_price"),
                                order_id=_order.get("order_id"),
                                stop_order_id=_order.get("stop_order_id"),
                                status=_status,
                                fill_check_passed=_chk["passed"],
                                fill_check_reason=_chk.get("reason", ""),
                                order_comment=_order.get("order_comment"),
                            )
                            current_run_fills.append(_rec)
                            if _qty_filled < _order["quantity"]:
                                try:
                                    from src.monitoring.telegram_alerts import (
                                        send_alert as _sa,
                                    )

                                    _sa(
                                        "fill_miss",
                                        {
                                            "ticker": _t,
                                            "side": _order["side"],
                                            "qty_requested": _order["quantity"],
                                            "qty_filled": _qty_filled,
                                            "fill_check_reason": _chk.get("reason", ""),
                                        },
                                    )
                                except Exception:
                                    pass
                        cb.record_nav(
                            time.time(),
                            monitor.get_net_liquidation() if monitor else nav,
                        )
                else:
                    from src.utils.config_manager import get_config as _get_config

                    _min_sz = int(
                        _get_config().get_param(
                            "trading_config.trading.execution.min_order_size", 1
                        )
                    )
                    for _, row in executable.iterrows():
                        if row["quantity"] <= 0:
                            continue
                        if int(row["quantity"]) < _min_sz:
                            print(
                                f"  [SKIP] {row['symbol']}: quantity {int(row['quantity'])} below min_order_size {_min_sz}",
                                flush=True,
                            )
                            continue
                        executor.submit_order(
                            ticker=row["symbol"],
                            quantity=int(row["quantity"]),
                            side=row["side"],
                            order_type="MARKET",
                        )
                print("  (Paper: orders submitted to IB paper account.)", flush=True)
        else:
            print(
                "  (Paper: DRY-RUN. Use --confirm-paper to submit orders.)", flush=True
            )

    # Update pod fitness after execution when --pods (Task 2 of 3)
    if args.pods:
        try:
            from src.portfolio.pod_pnl_tracker import update_pod_fitness

            update_pod_fitness(
                fitness_path=ROOT / "outputs" / "pod_fitness.json",
                weights_history_path=ROOT / "outputs" / "pod_weights_history.jsonl",
                fills_path=ROOT / "outputs" / "fills" / "fills.jsonl",
            )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("update_pod_fitness failed: %s", e)

    return (0, current_run_fills)


def _main_entry() -> int:
    """Entry point: returns exit code for sys.exit. main() returns (exit_code, fill_records)."""
    res = main()
    return res[0] if isinstance(res, tuple) else res


if __name__ == "__main__":
    sys.exit(_main_entry())
