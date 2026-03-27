"""
Standalone Phase 3 ML training runner.

Loads price data, runs feature tournament (updates model_config feature_names),
trains model via ModelTrainingPipeline, evaluates IC on test period.
If IC >= gate: save model to models/saved/ and print PASS. Else: print FAIL, do not save.

Usage:
  python scripts/train_ml_model.py

No wiring into signal_engine — research/validation only.
"""
from __future__ import annotations

import sys
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.data.csv_provider import load_prices
from src.core.config import NEWS_DIR
from src.utils.config_manager import get_config
from src.signals.feature_factory import FeatureSelector
from src.models.train_pipeline import ModelTrainingPipeline

# Fix 1 (docs/ml_ic_result.md): TICKER MISMATCH — use canonical watchlist from config
# instead of hardcoded list so training/IC align with data_config.yaml.
# Note: models/saved/ridge_20260221_131840.pkl is stale (5 features); current config uses 7 features.
# Do not delete the old file; re-run training to produce a new saved model.
CONFIG_PATH = "config/model_config.yaml"
IC_GATE = 0.01


def _load_news_signals_from_parquet(parquet_path: Path) -> dict:
    if not parquet_path.exists():
        print(f"[INFO] No news parquet found at {parquet_path}; training with neutral news defaults.", flush=True)
        return {}
    df = pd.read_parquet(parquet_path, engine="fastparquet")
    news_signals: dict = {}
    if not df.empty and "Ticker" in df.columns and "Date" in df.columns and "Sentiment" in df.columns:
        for ticker, grp in df.groupby("Ticker"):
            by_date = grp.groupby("Date")["Sentiment"].mean()
            news_signals[ticker] = {
                str(d): {"sentiment": float(s), "supply_chain": 0.5}
                for d, s in by_date.items()
            }
    n_ticker_days = sum(len(v) for v in news_signals.values())
    print(f"[INFO] Loaded EODHD news: {n_ticker_days} ticker-days of sentiment data.", flush=True)
    return news_signals


def _train_eval_and_save(
    model_type: str,
    prices_dict: dict,
    news_signals: dict,
    no_residual: bool,
) -> tuple[float, bool, Path | None]:
    pipeline = ModelTrainingPipeline(CONFIG_PATH)
    pipeline.config["training"]["save_models"] = False
    if no_residual:
        pipeline.config["training"]["residual_target"] = False
    pipeline.active_model_type = model_type
    pipeline.model_config = pipeline.config["models"][model_type]

    model = pipeline.train(prices_dict, technical_signals=None, news_signals=news_signals)
    train_cfg = pipeline.config.get("training", {})
    test_start = train_cfg.get("test_start", "2024-01-01")
    test_end = train_cfg.get("test_end", "2024-12-31")
    ic, _ = pipeline.evaluate_ic(
        model, prices_dict,
        test_start=test_start, test_end=test_end,
        news_signals=news_signals,
    )
    passed = ic >= IC_GATE
    msg = "PASS: proceed to Phase 3 wiring" if passed else "FAIL: do not wire ML model"
    print(f"[GATE][{model_type}] IC={ic:.4f} — {msg}", flush=True)

    if passed:
        save_dir_cfg = str(pipeline.config["training"]["model_save_dir"])
        _save_dir_raw = Path(save_dir_cfg)
        save_dir = _save_dir_raw if _save_dir_raw.is_absolute() else (ROOT / _save_dir_raw)
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = save_dir / f"{model_type}_{timestamp}.pkl"
            model.save_model(str(save_path))
            if not save_path.exists():
                print(f"[ERROR] Save failed — file not found at {save_path}", flush=True)
                return ic, False, None
            print(f"[Pipeline][{model_type}] Model saved to {save_path}", flush=True)
            return ic, True, save_path
        except Exception as e:
            print(f"[ERROR][{model_type}] Could not save model: {e}", flush=True)
            return ic, False, None
    return ic, False, None


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tournament", action="store_true", default=False, help="Use feature_names from config, skip tournament")
    parser.add_argument("--no-residual", action="store_true", help="Override residual_target to False at runtime (absolute target); does not modify config file")
    parser.add_argument("--sentiment-engine", choices=["none", "finbert", "gemini"], default="finbert")
    parser.add_argument("--news-dir", type=str, default=None, help="Optional parquet path override for EODHD news data")
    parser.add_argument("--train-both", action="store_true", default=False, help="Train CatBoost and Ridge sequentially")
    args = parser.parse_args()

    cfg = get_config()
    tickers = cfg.get_watchlist()
    data_dir = Path(cfg.get_param("data_config.data_sources.data_dir"))
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        print("ERROR: No price data loaded. Check data_dir and tickers.", flush=True)
        return 1

    if args.sentiment_engine == "none":
        news_signals = {}
    else:
        if args.news_dir:
            eodhd_path = Path(args.news_dir)
            if eodhd_path.is_dir():
                eodhd_path = eodhd_path / "eodhd_global_backfill.parquet"
        else:
            eodhd_path = Path(NEWS_DIR) / "eodhd_global_backfill.parquet"
        news_signals = _load_news_signals_from_parquet(eodhd_path)

    # Feature Selection Tournament: update model_config.yaml feature_names before pipeline reads it (unless --skip-tournament)
    with open(ROOT / CONFIG_PATH, "r", encoding="utf-8") as f:
        model_cfg = yaml.safe_load(f)
    if not args.skip_tournament:
        train_cfg = model_cfg.get("training", {})
        selector = FeatureSelector(ic_threshold=0.005, corr_threshold=0.70, n_keep=5)
        selected = selector.tournament(
            prices_dict,
            news_signals,
            train_start=train_cfg.get("train_start", "2022-01-01"),
            train_end=train_cfg.get("train_end", "2023-12-31"),
            config_path=ROOT / CONFIG_PATH,
        )
        print(f"[Factory] Selected features: {selected}", flush=True)
    else:
        feature_names = model_cfg.get("features", {}).get("feature_names", [])
        print(f"[train] --skip-tournament: using feature_names from config: {feature_names}", flush=True)

    model_types = ["catboost", "ridge"] if args.train_both else [ModelTrainingPipeline(CONFIG_PATH).active_model_type]
    overall_pass = True
    first_saved_path: Path | None = None
    for model_type in model_types:
        ic, saved, save_path = _train_eval_and_save(
            model_type=model_type,
            prices_dict=prices_dict,
            news_signals=news_signals,
            no_residual=args.no_residual,
        )
        overall_pass = overall_pass and (ic >= IC_GATE)
        if saved and save_path is not None and first_saved_path is None:
            first_saved_path = save_path

    if first_saved_path is not None and not args.train_both:
        config_path = ROOT / CONFIG_PATH
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if "tracks" not in cfg:
            cfg["tracks"] = {}
        if "A" not in cfg["tracks"]:
            cfg["tracks"]["A"] = {}
        cfg["tracks"]["A"]["model_path"] = str(first_saved_path.resolve())
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        print(f"[Config] Updated tracks.A.model_path to {first_saved_path}", flush=True)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
