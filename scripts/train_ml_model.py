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
TEST_START = "2024-01-01"
TEST_END = "2024-12-31"
IC_GATE = 0.01


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tournament", action="store_true", default=False, help="Use feature_names from config, skip tournament")
    args = parser.parse_args()

    cfg = get_config()
    tickers = cfg.get_watchlist()
    data_dir = Path(cfg.get_param("data_config.data_sources.data_dir"))
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        print("ERROR: No price data loaded. Check data_dir and tickers.", flush=True)
        return 1

    eodhd_path = Path(NEWS_DIR) / "eodhd_global_backfill.parquet"
    if not eodhd_path.exists():
        print("[INFO] No EODHD news parquet found; training with neutral news defaults.", flush=True)
        news_signals = {}
    else:
        df = pd.read_parquet(eodhd_path, engine="fastparquet")
        news_signals = {}
        if not df.empty and "Ticker" in df.columns and "Date" in df.columns and "Sentiment" in df.columns:
            for ticker, grp in df.groupby("Ticker"):
                by_date = grp.groupby("Date")["Sentiment"].mean()
                news_signals[ticker] = {
                    str(d): {"sentiment": float(s), "supply_chain": 0.5}
                    for d, s in by_date.items()
                }
        n_ticker_days = sum(len(v) for v in news_signals.values())
        print(f"[INFO] Loaded EODHD news: {n_ticker_days} ticker-days of sentiment data.", flush=True)

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

    pipeline = ModelTrainingPipeline(CONFIG_PATH)
    pipeline.config["training"]["save_models"] = False
    model = pipeline.train(prices_dict, technical_signals=None, news_signals=news_signals)

    ic, _ = pipeline.evaluate_ic(
        model, prices_dict,
        test_start=TEST_START, test_end=TEST_END,
        news_signals=news_signals,
    )

    passed = ic >= IC_GATE
    msg = "PASS: proceed to Phase 3 wiring" if passed else "FAIL: do not wire ML model"
    print(f"[GATE] IC={ic:.4f} — {msg}", flush=True)

    if passed:
        save_dir = Path(pipeline.config["training"]["model_save_dir"])
        save_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = save_dir / f"{pipeline.active_model_type}_{timestamp}.pkl"
        model.save_model(str(save_path))
        print(f"[Pipeline] Model saved to {save_path}", flush=True)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
