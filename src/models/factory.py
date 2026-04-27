"""
ML model tournament factory: walk-forward IC competition and cached winner selection.

Design (reference only — this module is a stub). Implements get_best_model() to run
a walk-forward IC tournament among Ridge, XGBoost, and CatBoost; cache the winner
per calendar week; and optionally save the winner to models/saved/ and update
config/model_config.yaml tracks.A.model_path (matching train_ml_model.py behavior).

Evidence and contracts:
- Tournament pattern: scripts/model_duel.py (get_xy via pipeline.extract_features_for_date
  and _calculate_forward_return, folds, Spearman IC, winner selection). Model duel uses
  only XGBoost and CatBoost and hardcoded 2025 quarterly folds (model_duel.py:60–73).
  This factory extends to Ridge and uses train/test window from config (see below).
- Walk-forward and label: src/models/train_pipeline.py ModelTrainingPipeline.prepare_training_data
  (cross-sectional z-score label), evaluate_ic() anchored walk-forward (train_pipeline.py:281–339).
  DECISIONS.md D021: IC gate = mean IC >= 0.02 on anchored walk-forward.
- Config dates: config/model_config.yaml training.train_start, train_end, test_start, test_end
  (model_config.yaml:24–27). No hardcoded dates; read from config_path.
- Save and config update: scripts/train_ml_model.py lines 106–125 — save to
  pipeline.config["training"]["model_save_dir"] with active_model_type + timestamp,
  then update config["tracks"]["A"]["model_path"] and write YAML. Same side effect
  required when winner passes IC gate.
- Caller blend: src/core/target_weight_pipeline.py loads model via
  MODEL_REGISTRY[active].load_model(path) (target_weight_pipeline.py:328, 133);
  path from config training.model_path or tracks. If get_best_model returns (None, "tech_only", 0.0),
  caller must set ml_blend_weight=0 (per task spec).
- Model creation: src/models/model_factory.py create_model(model_config, feature_names),
  MODEL_REGISTRY (model_factory.py:16–24). CatBoost is not in MODEL_REGISTRY; implementation
  must either register CatBoost or instantiate it in this module for the tournament.

Ambiguities / conflicts:
- model_duel.py uses 4 fixed 2025 quarterly folds; train_pipeline.evaluate_ic uses 13-week
  anchored walk-forward from config. This factory should use config test_start/test_end and
  anchored walk-forward (e.g. same logic as evaluate_ic) for IC gate consistency with D021.
- IC gate threshold: model_duel uses mean_ic > 0.01 and >= 3/4 folds positive (model_duel.py:71).
  train_ml_model uses IC_GATE = 0.01 (train_ml_model.py:34). Spec: no model > 0.01 → (None, "tech_only", 0.0).
  D021 states "IC >= 0.02" for integration; spec uses 0.01 for tournament pass. Implementation
  may use 0.01 for "winner" and optionally require 0.02 for side-effect (save + config update).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Tuple

# Optional: from .base_predictor import BaseReturnPredictor (for return type when implemented)


def _cache_path() -> Path:
    """Path to models/factory_winner.json (project root = parent of src)."""
    # project root = parent of src; __file__ is src/models/factory.py -> parent.parent.parent
    root = Path(__file__).resolve().parent.parent.parent
    return root / "models" / "factory_winner.json"


def get_best_model(
    prices_dict: dict[str, Any],
    news_signals: dict[str, Any],
    config_path: str | Path,
) -> Tuple[Optional[Any], str, float]:
    """
    Run walk-forward IC tournament among Ridge, XGBoost, and CatBoost; return winner or tech-only.

    Uses train_start, train_end, test_start, test_end from config at config_path (no hardcoded dates).
    Same walk-forward evaluation pattern as train_pipeline.evaluate_ic (anchored walk-forward).
    If a winner passes the IC gate, side effect: save model to models/saved/ and update
    config tracks.A.model_path (see scripts/train_ml_model.py:106–125).

    Caching:
        - After selecting a winner, write models/factory_winner.json with keys:
          model_type, ic, model_path, selected_at (ISO timestamp).
        - On subsequent calls within the same calendar week, load from cache and skip tournament.
        - Cache invalidation: if selected_at is older than 7 days, re-run tournament.

    Parameters
    ----------
    prices_dict : dict[str, Any]
        Per-ticker DataFrames (OHLCV, index = date). Same contract as
        ModelTrainingPipeline.prepare_training_data / model_duel get_xy.
    news_signals : dict[str, Any]
        Per-ticker news signals; passed to extract_features_for_date (e.g. train_pipeline).
    config_path : str | Path
        Path to config/model_config.yaml. Used to read training.train_start, train_end,
        test_start, test_end and (on side effect) to write tracks.A.model_path.

    Returns
    -------
    tuple (model, model_type_str, ic_score)
        - If a model passes IC > 0.01: (model_object, "ridge"|"xgboost"|"catboost", mean_ic).
        - If no model passes: (None, "tech_only", 0.0). Caller must set ml_blend_weight=0.

    Raises
    ------
    FileNotFoundError
        If config_path does not exist.
    ValueError
        If no training data can be built from prices_dict and config dates.

    References
    ----------
    - scripts/model_duel.py (tournament structure, get_xy, save, config update).
    - src/models/train_pipeline.py (prepare_training_data, evaluate_ic, extract_features_for_date).
    - config/model_config.yaml (training.*, tracks.A).
    - scripts/train_ml_model.py:106–125 (save path, tracks.A.model_path update).
    """
    import yaml
    from datetime import datetime, timezone, timedelta

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    training = config.get("training", {})
    _train_start = training.get("train_start", "2022-01-01")  # noqa: F841
    _train_end = training.get("train_end", "2023-12-31")  # noqa: F841
    test_start = training.get("test_start", "2024-01-01")
    test_end = training.get("test_end", "2024-12-31")
    config_path_abs = config_path.resolve()
    root = config_path_abs.parent.parent
    model_save_dir_str = training.get("model_save_dir", "models/saved/")
    model_save_dir = (
        root / model_save_dir_str
        if not Path(model_save_dir_str).is_absolute()
        else Path(model_save_dir_str)
    )
    ic_gate = float(training.get("factory_ic_gate", 0.01))

    cache_file = _cache_path()
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
        except Exception:
            cached = None
        if cached:
            selected_at = cached.get("selected_at")
            if selected_at:
                try:
                    sel_dt = datetime.fromisoformat(selected_at.replace("Z", "+00:00"))
                    if sel_dt.tzinfo is None:
                        sel_dt = sel_dt.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    if (now - sel_dt) <= timedelta(days=7):
                        model_type = cached.get("model_type")
                        model_path = cached.get("model_path")
                        ic = float(cached.get("ic", 0.0))
                        if model_type and model_path:
                            from .model_factory import MODEL_REGISTRY

                            model_class = MODEL_REGISTRY.get(model_type)
                            if model_class is not None:
                                model = model_class.load_model(model_path)
                                return (model, model_type, ic)
                except Exception:
                    pass

    from .train_pipeline import ModelTrainingPipeline
    from .model_factory import MODEL_REGISTRY

    news_signals = news_signals or {}
    results: list[Tuple[Any, str, float]] = []
    model_types = ["ridge", "xgboost", "catboost"]

    for model_type in model_types:
        if model_type not in MODEL_REGISTRY:
            continue
        pipeline = ModelTrainingPipeline(str(config_path))
        pipeline.config["training"]["residual_target"] = True
        pipeline.config["training"]["save_models"] = False
        pipeline.active_model_type = model_type
        pipeline.model_config = pipeline.config.get("models", {}).get(model_type) or {}
        if not isinstance(pipeline.model_config, dict):
            pipeline.model_config = {}

        try:
            model = pipeline.train(
                prices_dict,
                technical_signals=None,
                news_signals=news_signals,
            )
        except Exception as e:
            print(
                f"[FACTORY][WARN] {model_type} train() failed: {type(e).__name__}: {e}",
                flush=True,
            )
            continue
        try:
            mean_ic, _ = pipeline.evaluate_ic(
                model,
                prices_dict,
                test_start=test_start,
                test_end=test_end,
                news_signals=news_signals,
            )
        except Exception as e:
            print(
                f"[FACTORY][WARN] {model_type} evaluate_ic() failed: {type(e).__name__}: {e}",
                flush=True,
            )
            continue
        results.append((model, model_type, float(mean_ic)))

    passed = [(m, t, ic) for m, t, ic in results if ic > ic_gate]
    tie_order = ["catboost", "xgboost", "ridge"]
    passed.sort(
        key=lambda x: (x[2], -(tie_order.index(x[1]) if x[1] in tie_order else 999)),
        reverse=True,
    )
    if not passed:
        return (None, "tech_only", 0.0)

    best = passed[0]
    model, model_type, ic = best

    save_dir = model_save_dir
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"{model_type}_{timestamp}.pkl"
    model.save_model(str(save_path))

    # Same file-write pattern as scripts/train_ml_model.py lines 106–125
    if "tracks" not in config:
        config["tracks"] = {}
    if "A" not in config["tracks"]:
        config["tracks"]["A"] = {}
    config["tracks"]["A"]["model_path"] = str(save_path.resolve())
    with open(config_path_abs, "w", encoding="utf-8") as f:
        yaml.dump(
            config, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model_type": model_type,
                "ic": ic,
                "model_path": str(save_path.resolve()),
                "selected_at": datetime.now(timezone.utc).isoformat(),
            },
            f,
            indent=2,
        )

    return (model, model_type, ic)
