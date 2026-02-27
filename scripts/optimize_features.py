"""
Standalone monthly research tool: search for a feature set superior to the
3-feature baseline. Implements search limits, multi-criteria gate, and automated reversion.

Usage: python scripts/optimize_features.py

Two-stage evaluation (Stage 1: fast IC/corr pre-filter; Stage 2: full walk-forward IC).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
MAX_FEATURES = 5
MIN_FEATURES = 3
MAX_EXTRA_CANDIDATES = 2
MAX_ITERATIONS = 50
STAGE1_IC_THRESHOLD = 0.005
STAGE1_CORR_THRESHOLD = 0.70
GATE_CORR_THRESHOLD = 0.70
GATE_MIN_POSITIVE_FOLDS = 3
LOG_PATH = "logs/optimization_history.json"
CONFIG_PATH = "config/model_config.yaml"
TEST_START = "2024-01-01"
TEST_END = "2024-12-31"


def _load_prices_and_news():
    """Same as train_ml_model.py: watchlist, load_prices, EODHD news."""
    import pandas as pd
    from src.data.csv_provider import load_prices
    from src.core.config import NEWS_DIR
    from src.utils.config_manager import get_config

    cfg = get_config()
    tickers = cfg.get_watchlist()
    data_dir = Path(cfg.get_param("data_config.data_sources.data_dir"))
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        return None, None
    eodhd_path = Path(NEWS_DIR) / "eodhd_global_backfill.parquet"
    news_signals = {}
    if eodhd_path.exists():
        df = pd.read_parquet(eodhd_path, engine="fastparquet")
        if not df.empty and "Ticker" in df.columns and "Date" in df.columns and "Sentiment" in df.columns:
            for ticker, grp in df.groupby("Ticker"):
                by_date = grp.groupby("Date")["Sentiment"].mean()
                news_signals[ticker] = {
                    str(d): {"sentiment": float(s), "supply_chain": 0.5}
                    for d, s in by_date.items()
                }
    return prices_dict, news_signals


def _write_feature_names(config_path: Path, feature_names: list) -> None:
    """Set model_config.yaml feature_names; preserve other keys."""
    try:
        from ruamel.yaml import YAML
        yaml_loader = YAML()
        yaml_loader.preserve_quotes = True
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml_loader.load(f)
        if cfg is None:
            cfg = {}
        if "features" not in cfg:
            cfg["features"] = {}
        cfg["features"]["feature_names"] = list(feature_names)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml_loader.dump(cfg, f)
    except ImportError:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if "features" not in cfg:
            cfg["features"] = {}
        cfg["features"]["feature_names"] = list(feature_names)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _update_model_path(config_path: Path, save_path: str) -> None:
    """Update training.model_path in model_config.yaml."""
    try:
        from ruamel.yaml import YAML
        yaml_loader = YAML()
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml_loader.load(f)
        if cfg and "training" in cfg:
            cfg["training"]["model_path"] = save_path
        with open(config_path, "w", encoding="utf-8") as f:
            yaml_loader.dump(cfg, f)
    except Exception:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if cfg and "training" in cfg:
            cfg["training"]["model_path"] = save_path
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _fast_evaluate_combo(
    full_matrix,
    feature_names: list,
    train_anchor,
    test_start,
    test_end,
    model_cfg,
    fold_weeks: int = 13,
):
    """Anchored walk-forward IC using only matrix slicing and sklearn Ridge. No price loading or indicator computation."""
    import numpy as np
    import pandas as pd
    from scipy.stats import spearmanr
    from sklearn.linear_model import Ridge

    if "date" not in full_matrix.columns:
        raise ValueError("full_matrix must have a 'date' column")
    cols = [c for c in feature_names if c in full_matrix.columns]
    if "forward_ret" not in full_matrix.columns or len(cols) != len(feature_names):
        return 0.0, []
    week_days = fold_weeks * 7
    ic_list = []
    fold_start = pd.to_datetime(test_start)
    test_end_dt = pd.to_datetime(test_end)
    train_anchor_dt = pd.to_datetime(train_anchor)

    while fold_start + pd.Timedelta(days=week_days) <= test_end_dt:
        fold_end = fold_start + pd.Timedelta(days=week_days)
        train_slice = full_matrix[
            (full_matrix["date"] >= train_anchor_dt) & (full_matrix["date"] < fold_start)
        ].copy()
        test_slice = full_matrix[
            (full_matrix["date"] >= fold_start) & (full_matrix["date"] < fold_end)
        ].copy()
        if train_slice.empty or test_slice.empty:
            fold_start = fold_end
            continue
        # Z-score forward_ret by date (cross-sectional)
        for _df in (train_slice, test_slice):
            g = _df.groupby("date")["forward_ret"]
            _df["forward_ret"] = g.transform(lambda x: (x - x.mean()) / x.std() if x.std() > 0 else x - x.mean())
        X_train = train_slice[cols].values
        y_train = train_slice["forward_ret"].values
        valid = np.isfinite(X_train).all(axis=1) & np.isfinite(y_train)
        X_train = X_train[valid]
        y_train = y_train[valid]
        if len(X_train) < 10:
            fold_start = fold_end
            continue
        X_test = test_slice[cols].values
        y_test = test_slice["forward_ret"].values
        valid_t = np.isfinite(X_test).all(axis=1) & np.isfinite(y_test)
        X_test = X_test[valid_t]
        y_test = y_test[valid_t]
        if len(X_test) == 0:
            fold_start = fold_end
            continue
        alpha = float(model_cfg.get("models", {}).get("ridge", {}).get("alpha", 0.001))
        ridge = Ridge(alpha=alpha)
        ridge.fit(X_train, y_train)
        pred = ridge.predict(X_test)
        r, _ = spearmanr(pred, y_test)
        ic_f = float(r) if r is not None and not np.isnan(r) else 0.0
        ic_list.append(ic_f)
        fold_start = fold_end

    if not ic_list:
        return 0.0, []
    return float(np.mean(ic_list)), ic_list


def _max_pairwise_corr(matrix, feature_names: list) -> float:
    """Max absolute Pearson correlation between any two features in the list."""
    import numpy as np
    cols = [c for c in feature_names if c in matrix.columns]
    if len(cols) < 2:
        return 0.0
    sub = matrix[cols].replace([np.inf, -np.inf], np.nan).fillna(matrix[cols].median())
    corr = sub.corr(method="pearson")
    m = 0.0
    for i, a in enumerate(cols):
        for j, b in enumerate(cols):
            if i >= j:
                continue
            c = corr.loc[a, b] if a in corr.columns and b in corr.index else 0.0
            m = max(m, abs(c))
    return float(m)


def main() -> int:
    import numpy as np
    import pandas as pd
    from scipy.stats import spearmanr, pearsonr
    from src.signals.feature_factory import FEATURE_REGISTRY, FeatureSelector
    from src.models.train_pipeline import ModelTrainingPipeline
    from src.models.model_factory import create_model

    config_path = ROOT / CONFIG_PATH
    with open(config_path, "r", encoding="utf-8") as f:
        import yaml
        model_cfg = yaml.safe_load(f)
    train_cfg = model_cfg.get("training", {})
    train_start = train_cfg.get("train_start", "2022-01-01")
    train_end = train_cfg.get("train_end", "2023-12-31")

    prices_dict, news_signals = _load_prices_and_news()
    if not prices_dict:
        print("ERROR: No price data loaded.", flush=True)
        return 1
    news_signals = news_signals or {}

    # Stage 1 — build full matrix ONCE over full date range (train + test); ensure 'date' column for Stage 2
    all_candidate_names = list(FEATURE_REGISTRY)
    selector = FeatureSelector(ic_threshold=STAGE1_IC_THRESHOLD, corr_threshold=STAGE1_CORR_THRESHOLD, n_keep=MAX_FEATURES)
    full_matrix = selector.build_feature_matrix(
        prices_dict, news_signals,
        start="2022-01-01",
        end=TEST_END,
        feature_columns=all_candidate_names,
    )
    if full_matrix.empty or "forward_ret" not in full_matrix.columns:
        print("ERROR: Feature matrix empty or missing forward_ret.", flush=True)
        return 1
    full_matrix = full_matrix.reset_index()
    if "date" not in full_matrix.columns and "index" in full_matrix.columns:
        full_matrix = full_matrix.rename(columns={"index": "date"})

    # Stage 1 uses only training rows
    train_end_dt = pd.to_datetime(train_end)
    stage1_matrix = full_matrix[full_matrix["date"] <= train_end_dt] if "date" in full_matrix.columns else full_matrix
    protected = [f for f in FEATURE_REGISTRY if FEATURE_REGISTRY[f].get("protected")]
    non_protected = [f for f in FEATURE_REGISTRY if f not in protected and f in stage1_matrix.columns]
    y = stage1_matrix["forward_ret"].values

    dropped_low_ic = []
    dropped_corr_protected = []
    survivors = []
    for col in non_protected:
        # Slice from stage1_matrix (training rows only)
        x = stage1_matrix[col].values
        valid = np.isfinite(x) & np.isfinite(y)
        if np.sum(valid) < 20:
            continue
        r, _ = spearmanr(x[valid], y[valid], nan_policy="omit")
        r = float(r) if r is not None and (not hasattr(r, "__len__") or len(r) > 0) else float("nan")
        if math.isnan(r) or abs(r) < STAGE1_IC_THRESHOLD:
            dropped_low_ic.append(col)
            continue
        high_corr = False
        for p in protected:
            if p not in stage1_matrix.columns:
                continue
            pv = stage1_matrix[p].values
            v2 = np.isfinite(pv) & np.isfinite(x)
            if np.sum(v2) < 20:
                continue
            c, _ = pearsonr(pv[v2], x[v2])
            c = float(c) if c is not None and not math.isnan(c) else 0.0
            if abs(c) >= STAGE1_CORR_THRESHOLD:
                high_corr = True
                break
        if high_corr:
            dropped_corr_protected.append(col)
            continue
        survivors.append(col)

    print(f"[Governor] Stage 1: {len(non_protected)} candidates evaluated -> {len(survivors)} survivors", flush=True)
    if dropped_low_ic:
        print(f"[Governor] Dropped (low IC): {dropped_low_ic}", flush=True)
    if dropped_corr_protected:
        print(f"[Governor] Dropped (corr with protected): {dropped_corr_protected}", flush=True)

    if len(survivors) == 0:
        print("[Governor] No candidates survived pre-filtering.", flush=True)
        # Jump to REVERSION (step 8)
        log_entries = []
        if Path(ROOT / LOG_PATH).exists():
            try:
                log_entries = json.loads((ROOT / LOG_PATH).read_text(encoding="utf-8"))
            except Exception:
                pass
        if not isinstance(log_entries, list):
            log_entries = []
        baseline_ic = 0.0  # not computed
        log_entries.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "REVERSION",
            "reason": "No candidates survived Stage 1 pre-filtering",
            "baseline_features": list(protected),
            "baseline_ic": baseline_ic,
            "combinations_evaluated": 0,
        })
        (ROOT / LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / LOG_PATH).write_text(json.dumps(log_entries, indent=2), encoding="utf-8")
        print("[Governor] No superior model found. Reverting to Baseline (3-feature)", flush=True)
        _write_feature_names(config_path, protected)
        pipeline = ModelTrainingPipeline(str(config_path))
        X, y, _ = pipeline.prepare_training_data(prices_dict, technical_signals=None, news_signals=news_signals)
        split = int(len(X) * 0.8)
        model = create_model(
            {**{"type": pipeline.active_model_type}, **pipeline.model_config},
            pipeline.feature_names,
        )
        model.fit(X[:split], y[:split], X[split:], y[split:])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = ROOT / "models" / "saved" / f"ridge_baseline_{timestamp}.pkl"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(save_path))
        _update_model_path(config_path, str(save_path))
        print(f"[Governor] Baseline model saved: {save_path}", flush=True)
        return 0

    # Build combination list
    from itertools import combinations as icombs
    combinations_to_test = []
    combinations_to_test.append(tuple(protected))
    for c in survivors:
        combinations_to_test.append(tuple(protected + [c]))
    for c1, c2 in icombs(survivors, 2):
        if c1 in stage1_matrix.columns and c2 in stage1_matrix.columns:
            r, _ = pearsonr(stage1_matrix[c1].values, stage1_matrix[c2].values)
            corr_c1_c2 = abs(float(r)) if r is not None and not math.isnan(r) else 0.0
            if corr_c1_c2 >= GATE_CORR_THRESHOLD:
                continue
        combinations_to_test.append(tuple(protected + [c1, c2]))
    if len(combinations_to_test) > MAX_ITERATIONS:
        combinations_to_test = combinations_to_test[:MAX_ITERATIONS]
        print(f"[Governor] Capped at {MAX_ITERATIONS} combinations (MAX_ITERATIONS limit)", flush=True)
    print(f"[Governor] Stage 2: {len(combinations_to_test)} combinations to evaluate", flush=True)

    # Stage 2 — full walk-forward evaluation
    log_entries = []
    if (ROOT / LOG_PATH).exists():
        try:
            log_entries = json.loads((ROOT / LOG_PATH).read_text(encoding="utf-8"))
        except Exception:
            pass
    if not isinstance(log_entries, list):
        log_entries = []

    baseline_ic = None
    run_entries = []
    total = len(combinations_to_test)

    for i, combo in enumerate(combinations_to_test):
        mean_ic, fold_ics = _fast_evaluate_combo(
            full_matrix,
            list(combo),
            train_anchor=pd.to_datetime(train_start),
            test_start=pd.to_datetime(TEST_START),
            test_end=pd.to_datetime(TEST_END),
            model_cfg=model_cfg,
        )
        if baseline_ic is None:
            baseline_ic = mean_ic
        n_pos = sum(1 for ic in fold_ics if ic > 0)
        # Slice from full_matrix (no re-build)
        max_corr = _max_pairwise_corr(full_matrix, list(combo))

        gate_1 = mean_ic > baseline_ic
        gate_2 = n_pos >= GATE_MIN_POSITIVE_FOLDS
        gate_3 = max_corr < GATE_CORR_THRESHOLD
        n_folds = len(fold_ics)

        if gate_1 and gate_2 and gate_3:
            decision = "ACCEPT"
            reason = f"IC {mean_ic:.4f} > baseline {baseline_ic:.4f}, {n_pos}/{n_folds} positive folds, max_corr={max_corr:.3f}"
        elif not gate_1:
            decision = "REJECT"
            reason = f"IC {mean_ic:.4f} <= baseline {baseline_ic:.4f}"
        elif not gate_2:
            decision = "REJECT"
            reason = f"Only {n_pos}/{n_folds} positive folds (need {GATE_MIN_POSITIVE_FOLDS})"
        else:
            decision = "REJECT"
            reason = f"max pairwise corr {max_corr:.3f} >= {GATE_CORR_THRESHOLD}"

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "features_tested": list(combo),
            "n_features": len(combo),
            "ic_per_fold": fold_ics,
            "mean_ic": mean_ic,
            "n_positive_folds": n_pos,
            "max_pairwise_corr": max_corr,
            "baseline_ic": baseline_ic,
            "gate_1_ic_improvement": gate_1,
            "gate_2_consistency": gate_2,
            "gate_3_orthogonality": gate_3,
            "decision": decision,
            "reason": reason,
        }
        run_entries.append(entry)
        log_entries.append(entry)
        (ROOT / LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / LOG_PATH).write_text(json.dumps(log_entries, indent=2), encoding="utf-8")

        print(f"[Governor] Combo {i + 1}/{total}: {combo}", flush=True)
        print(f"          IC={mean_ic:.4f} | folds={fold_ics} | pos={n_pos}/4 | max_corr={max_corr:.3f} -> {decision}", flush=True)

    # Winner selection and reversion
    winners = [e for e in run_entries if e.get("decision") == "ACCEPT"]

    if winners:
        best = max(winners, key=lambda e: e["mean_ic"])
        print(f"[Governor] Winner: {best['features_tested']} IC={best['mean_ic']:.4f}", flush=True)
        _write_feature_names(config_path, best["features_tested"])
        pipeline = ModelTrainingPipeline(str(config_path))
        X, y, _ = pipeline.prepare_training_data(prices_dict, technical_signals=None, news_signals=news_signals)
        split = int(len(X) * 0.8)
        model = create_model(
            {**{"type": pipeline.active_model_type}, **pipeline.model_config},
            pipeline.feature_names,
        )
        model.fit(X[:split], y[:split], X[split:], y[split:])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = ROOT / "models" / "saved" / f"ridge_optimized_{timestamp}.pkl"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(save_path))
        _update_model_path(config_path, str(save_path))
        print(f"[Governor] Model saved: {save_path}", flush=True)
        print("[Governor] model_config.yaml updated.", flush=True)
        return 0
    else:
        print("[Governor] No superior model found. Reverting to Baseline (3-feature)", flush=True)
        log_entries.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "REVERSION",
            "reason": "No combination passed all three gates",
            "baseline_features": list(protected),
            "baseline_ic": baseline_ic,
            "combinations_evaluated": len(combinations_to_test),
        })
        (ROOT / LOG_PATH).write_text(json.dumps(log_entries, indent=2), encoding="utf-8")
        _write_feature_names(config_path, list(protected))
        pipeline = ModelTrainingPipeline(str(config_path))
        X, y, _ = pipeline.prepare_training_data(prices_dict, technical_signals=None, news_signals=news_signals)
        split = int(len(X) * 0.8)
        model = create_model(
            {**{"type": pipeline.active_model_type}, **pipeline.model_config},
            pipeline.feature_names,
        )
        model.fit(X[:split], y[:split], X[split:], y[split:])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = ROOT / "models" / "saved" / f"ridge_baseline_{timestamp}.pkl"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(save_path))
        _update_model_path(config_path, str(save_path))
        print(f"[Governor] Baseline model saved: {save_path}", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
