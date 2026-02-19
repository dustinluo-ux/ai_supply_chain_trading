"""
Standalone Phase 3 ML training runner.

Loads price data, trains model via ModelTrainingPipeline, evaluates IC on test period.
If IC >= 0.02: save model to models/saved/ and print PASS. Else: print FAIL, do not save.

Usage:
  python scripts/train_ml_model.py

No wiring into signal_engine — research/validation only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.csv_provider import load_data_config, load_prices
from src.models.train_pipeline import ModelTrainingPipeline

TICKERS = ["NVDA", "AMD", "TSM", "AAPL", "MSFT", "GOOGL"]
CONFIG_PATH = "config/model_config.yaml"
TEST_START = "2024-01-01"
TEST_END = "2024-12-31"
IC_GATE = 0.02


def main() -> int:
    config = load_data_config()
    data_dir = config["data_dir"]
    prices_dict = load_prices(data_dir, TICKERS)
    if not prices_dict:
        print("ERROR: No price data loaded. Check data_dir and tickers.", flush=True)
        return 1

    pipeline = ModelTrainingPipeline(CONFIG_PATH)
    pipeline.config["training"]["save_models"] = False
    model = pipeline.train(prices_dict, technical_signals=None, news_signals={})

    ic = pipeline.evaluate_ic(
        model, prices_dict,
        test_start=TEST_START, test_end=TEST_END,
        news_signals={},
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
