"""
Walk-forward model retraining: patch config dates, train, evaluate IC, update config and ic_monitor.json if IC >= 0.01.

Usage:
  python scripts/retrain_model.py
  python scripts/retrain_model.py --skip-tournament --track A
  python scripts/retrain_model.py --train-end 2025-06-01 --test-months 6
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

CONFIG_PATH = ROOT / "config" / "model_config.yaml"
IC_GATE = 0.01
IC_MONITOR_PATH = ROOT / "outputs" / "ic_monitor.json"


def _load_news_signals():
    """Load EODHD news parquet for training; return {} if not found."""
    from src.core.config import NEWS_DIR

    eodhd_path = Path(NEWS_DIR) / "eodhd_global_backfill.parquet"
    if not eodhd_path.exists():
        return {}
    import pandas as pd

    df = pd.read_parquet(eodhd_path, engine="fastparquet")
    news_signals = {}
    if (
        not df.empty
        and "Ticker" in df.columns
        and "Date" in df.columns
        and "Sentiment" in df.columns
    ):
        for ticker, grp in df.groupby("Ticker"):
            by_date = grp.groupby("Date")["Sentiment"].mean()
            news_signals[ticker] = {
                str(d): {"sentiment": float(s), "supply_chain": 0.5}
                for d, s in by_date.items()
            }
    return news_signals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Walk-forward retrain: patch dates, train, gate by IC, update config and ic_monitor."
    )
    parser.add_argument(
        "--train-start", type=str, default="2022-01-01", help="Training start date"
    )
    parser.add_argument(
        "--train-end",
        type=str,
        default=None,
        help="Training end date (default: today minus 90 days)",
    )
    parser.add_argument(
        "--test-months",
        type=int,
        default=6,
        help="Test window length in months after train_end",
    )
    parser.add_argument(
        "--skip-tournament",
        action="store_true",
        help="Use feature_names from config, skip tournament",
    )
    parser.add_argument(
        "--track",
        type=str,
        choices=["A", "B"],
        default="A",
        help="Track to update (A=absolute, B=residual)",
    )
    parser.add_argument(
        "--no-residual",
        action="store_true",
        help="Override residual_target to False (absolute target); track B is residual unless this is set",
    )
    parser.add_argument(
        "--residual",
        action="store_true",
        help="Override residual_target to True for track A; track B is always residual",
    )
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    if args.train_end is None:
        train_end_date = today - timedelta(days=90)
        args.train_end = train_end_date.isoformat()
    train_end_dt = datetime.fromisoformat(args.train_end.replace("Z", "+00:00"))
    test_start_dt = train_end_dt + timedelta(days=1)
    test_end_dt = test_start_dt + timedelta(days=args.test_months * 30)
    test_start = test_start_dt.strftime("%Y-%m-%d")
    test_end = test_end_dt.strftime("%Y-%m-%d")
    if test_end_dt.date() > today:
        test_end = today.isoformat()

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    orig_training = cfg.get("training", {}).copy()
    residual_target = (
        False if args.no_residual else (args.residual or args.track == "B")
    )
    cfg["training"] = {
        **orig_training,
        "train_start": args.train_start,
        "train_end": args.train_end,
        "test_start": test_start,
        "test_end": test_end,
        "residual_target": residual_target,
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(ROOT)
    ) as tmp:
        yaml.dump(
            cfg, tmp, default_flow_style=False, sort_keys=False, allow_unicode=True
        )
        temp_config_path = tmp.name
    try:
        from src.utils.config_manager import get_config
        from src.data.csv_provider import load_prices
        from src.signals.feature_factory import FeatureSelector
        from src.models.train_pipeline import ModelTrainingPipeline

        get_config()
        tickers = get_config().get_watchlist()
        data_dir = Path(get_config().get_param("data_config.data_sources.data_dir"))
        prices_dict = load_prices(data_dir, tickers)
        if not prices_dict:
            print("ERROR: No price data loaded.", flush=True)
            return 1

        news_signals = _load_news_signals()
        if news_signals:
            print(
                f"[INFO] Loaded EODHD news: {sum(len(v) for v in news_signals.values())} ticker-days.",
                flush=True,
            )
        else:
            print(
                "[INFO] No EODHD news parquet; training with neutral news defaults.",
                flush=True,
            )

        config_path_str = str(Path(temp_config_path))
        with open(config_path_str) as f:
            _model_cfg = yaml.safe_load(f)  # noqa: F841
        if not args.skip_tournament:
            selector = FeatureSelector(
                ic_threshold=0.005, corr_threshold=0.70, n_keep=5
            )
            selected = selector.tournament(
                prices_dict,
                news_signals,
                train_start=args.train_start,
                train_end=args.train_end,
                config_path=Path(config_path_str),
            )
            print(f"[Factory] Selected features: {selected}", flush=True)
        else:
            print(
                f"[retrain] --skip-tournament: using feature_names from config",
                flush=True,
            )

        pipeline = ModelTrainingPipeline(config_path_str)
        pipeline.config["training"]["save_models"] = False
        model = pipeline.train(
            prices_dict, technical_signals=None, news_signals=news_signals
        )

        ic, _ = pipeline.evaluate_ic(
            model,
            prices_dict,
            test_start=test_start,
            test_end=test_end,
            news_signals=news_signals,
        )

        passed = ic >= IC_GATE
        save_path = None
        if passed:
            save_dir = Path(pipeline.config["training"]["model_save_dir"])
            save_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = save_dir / f"{pipeline.active_model_type}_{timestamp}.pkl"
            model.save_model(str(save_path))
            print(f"[PASS] New model saved: {save_path}  IC={ic:.4f}", flush=True)
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                main_cfg = yaml.safe_load(f)
            if "tracks" not in main_cfg:
                main_cfg["tracks"] = {}
            if args.track not in main_cfg["tracks"]:
                main_cfg["tracks"][args.track] = {}
            main_cfg["tracks"][args.track]["model_path"] = str(save_path.resolve())
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(
                    main_cfg,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
            print(
                f"[Config] Updated tracks.{args.track}.model_path to {save_path}",
                flush=True,
            )
        else:
            print(f"[FAIL] IC={ic:.4f} below gate - keeping existing model", flush=True)

        entry = {
            "date": today.isoformat(),
            "train_end": args.train_end,
            "ic": round(ic, 6),
            "passed": passed,
            "model_path": str(save_path.resolve()) if save_path else None,
        }
        IC_MONITOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        if IC_MONITOR_PATH.exists():
            with open(IC_MONITOR_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
        if not isinstance(history, list):
            history = [history] if history else []
        history.append(entry)
        with open(IC_MONITOR_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        print(f"[IC] Appended to {IC_MONITOR_PATH}", flush=True)
        return 0 if passed else 1
    finally:
        Path(temp_config_path).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
