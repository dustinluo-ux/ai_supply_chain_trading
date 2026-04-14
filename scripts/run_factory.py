"""
Factory CLI: load data, run get_best_model, print winner and exit.
Loading logic from scripts/train_ml_model.py lines 44–66.
"""
from __future__ import annotations

import sys
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CONFIG_PATH = ROOT / "config" / "model_config.yaml"


def _patch_model_config_training_window(config_path: Path, train_years: int) -> None:
    """Rolling window: train [today-N years, today-365d], test [today-365d, today]. Writes YAML."""
    from datetime import date, timedelta

    _today = date.today()
    try:
        _train_start = _today.replace(year=_today.year - train_years)
    except ValueError:
        _train_start = _today.replace(month=2, day=28, year=_today.year - train_years)
    _train_end = _today - timedelta(days=365)
    _test_start = _train_end
    _test_end = _today

    with open(config_path, "r", encoding="utf-8") as _f:
        _cfg = yaml.safe_load(_f) or {}
    _cfg.setdefault("training", {})
    _cfg["training"]["train_start"] = str(_train_start)
    _cfg["training"]["train_end"] = str(_train_end)
    _cfg["training"]["test_start"] = str(_test_start)
    _cfg["training"]["test_end"] = str(_test_end)
    with open(config_path, "w", encoding="utf-8") as _f:
        yaml.dump(_cfg, _f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def main() -> int:
    import argparse
    import os
    from src.data.csv_provider import load_prices
    from src.core.config import NEWS_DIR
    from src.data.unified_news_loader import UnifiedNewsLoader
    from src.utils.config_manager import get_config
    from src.models.factory import get_best_model

    parser = argparse.ArgumentParser(description="Run factory tournament.")
    parser.add_argument("--no-news", action="store_true", help="Pass news_signals=None.")
    parser.add_argument(
        "--train-years",
        type=int,
        default=4,
        help="Years of history for train_start (default: 4, i.e. train_start ≈ today - N years).",
    )
    args = parser.parse_args()

    cfg = get_config()
    tickers = cfg.get_watchlist()
    data_dir = Path(cfg.get_param("data_config.data_sources.data_dir"))
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        print("ERROR: No price data loaded.", flush=True)
        return 1
    _patch_model_config_training_window(CONFIG_PATH, int(args.train_years))
    with open(CONFIG_PATH, "r", encoding="utf-8") as _f_cfg:
        _cfg_after_patch = yaml.safe_load(_f_cfg) or {}
    _train_cfg = _cfg_after_patch.get("training", {})
    _train_start = str(_train_cfg.get("train_start", "2022-01-01"))
    _train_end = str(_train_cfg.get("train_end", "2023-12-31"))
    if args.no_news:
        news_signals = None
    else:
        news_signals = {}
        _loader_data_dir = os.environ.get("DATA_DIR", NEWS_DIR)
        _loader = UnifiedNewsLoader(str(_loader_data_dir))
        _loaded = _loader.load(tickers, _train_start, _train_end)
        for _ticker, _by_date in _loaded.items():
            for _d, _payload in _by_date.items():
                news_signals.setdefault(_ticker, {})[_d] = {
                    "sentiment": float(_payload.get("sentiment_score", 0.5)),
                    "supply_chain": float(_payload.get("supply_chain_score", 0.5)),
                }

    model, model_type, ic = get_best_model(prices_dict, news_signals or {}, str(CONFIG_PATH))
    model_path = "tech_only"
    if model is not None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            a = (yaml.safe_load(f).get("tracks") or {}).get("A") or {}
        model_path = a.get("model_path", "tech_only") if isinstance(a, dict) else "tech_only"
    print(f"[FACTORY] Winner: {model_type}", flush=True)
    print(f"[FACTORY] IC: {ic:.4f}", flush=True)
    print(f"[FACTORY] Model path: {model_path or 'tech_only'}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
