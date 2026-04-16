"""Duel XGBoost vs CatBoost on walk-forward IC (2025 quarterly folds). Rank label. Gate: IC>0.01 and >=3/4 folds positive."""
from __future__ import annotations
import sys
import yaml
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def _build_rank_label(meta_df):
    meta_df = meta_df.copy()
    meta_df["pct"] = meta_df.groupby("date")["forward_return"].rank(pct=True, method="average")
    pct = meta_df["pct"].values
    return (pct - np.mean(pct)) / (np.std(pct) or 1e-8)
def main():
    from src.utils.config_manager import get_config
    from src.data.csv_provider import load_prices
    from src.models.train_pipeline import ModelTrainingPipeline
    cfg_path = ROOT / "config" / "model_config.yaml"
    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f)
    tickers = get_config().get_watchlist()
    data_dir = Path(get_config().get_param("data_config.data_sources.data_dir"))
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        print("ERROR: No price data."); return 1
    news_signals = {}
    pipeline = ModelTrainingPipeline(str(cfg_path))
    pipeline.config["training"]["train_start"] = "2022-01-01"
    pipeline.config["training"]["train_end"] = "2024-12-31"
    pipeline.config["training"]["residual_target"] = False

    def get_xy(start, end):
        X_list, meta = [], []
        for t in prices_dict:
            for d in pd.date_range(start, end, freq="W-MON"):
                f = pipeline.extract_features_for_date(t, pd.Timestamp(d), prices_dict, news_signals)
                if f is None: continue
                r = pipeline._calculate_forward_return(t, pd.Timestamp(d), prices_dict)
                if r is None: continue
                X_list.append(f); meta.append({"date": d, "forward_return": r})
        if not X_list: return None, None, None
        X = np.array(X_list)
        df = pd.DataFrame(meta); y = _build_rank_label(df)
        return X, y, df

    X_train, y_train, _ = get_xy("2022-01-01", "2024-12-31")
    if X_train is None or len(X_train) < 50:
        print("ERROR: Insufficient train data."); return 1

    from xgboost import XGBRegressor
    from catboost import CatBoostRegressor
    xgb = XGBRegressor(max_depth=3, n_estimators=100, learning_rate=0.05, subsample=0.8, random_state=42)
    cat = CatBoostRegressor(depth=4, iterations=100, learning_rate=0.05, verbose=0, random_state=42, cat_features=[])
    xgb.fit(X_train, y_train); cat.fit(X_train, y_train)
    folds = [("2025-01-01", "2025-03-31"), ("2025-04-01", "2025-06-30"), ("2025-07-01", "2025-09-30"), ("2025-10-01", "2025-12-31")]
    results = {}
    for name, model in [("XGBoost", xgb), ("CatBoost", cat)]:
        ics = []
        for s, e in folds:
            X_t, y_t, _ = get_xy(s, e)
            if X_t is None or len(X_t) < 5: ics.append(0.0); continue
            pred = model.predict(X_t)
            ic, _ = spearmanr(pred, y_t); ics.append(float(ic) if not np.isnan(ic) else 0.0)
        mean_ic = np.mean(ics); n_pos = sum(1 for i in ics if i > 0)
        results[name] = {"mean_ic": mean_ic, "folds": ics, "n_positive": n_pos}
        passed = mean_ic > 0.01 and n_pos >= 3
        results[name]["passed"] = passed

    print("\n--- DUEL RESULTS ---")
    print(f"{'Model':<12} {'Q1':>8} {'Q2':>8} {'Q3':>8} {'Q4':>8} {'Mean IC':>8} {'Pass':>6}")
    for name in ["XGBoost", "CatBoost"]:
        r = results[name]; f = r["folds"]
        print(f"{name:<12} {f[0]:>8.4f} {f[1]:>8.4f} {f[2]:>8.4f} {f[3]:>8.4f} {r['mean_ic']:>8.4f} {'YES' if r['passed'] else 'NO':>6}")
    winner = None
    if results["XGBoost"]["passed"] and results["CatBoost"]["passed"]:
        winner = "XGBoost" if results["XGBoost"]["mean_ic"] >= results["CatBoost"]["mean_ic"] else "CatBoost"
    elif results["XGBoost"]["passed"]: winner = "XGBoost"
    elif results["CatBoost"]["passed"]: winner = "CatBoost"
    if winner:
        import joblib
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = ROOT / "models" / "saved" / f"{winner.lower()}_duel_{ts}.pkl"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(xgb if winner == "XGBoost" else cat, save_path)
        with open(cfg_path, "r") as f: c = yaml.safe_load(f)
        if "tracks" not in c: c["tracks"] = {}
        if "A" not in c["tracks"]: c["tracks"]["A"] = {}
        c["tracks"]["A"]["model_path"] = str(save_path.resolve()); c["use_ml"] = True
        with open(cfg_path, "w") as f: yaml.dump(c, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        print(f"\n[DUEL] Winner: {winner}. Saved {save_path}; use_ml=true, tracks.A updated.")
    else:
        print("\n[DUEL] No winner. ML remains neutralized.")
    return 0 if winner else 1
if __name__ == "__main__":
    sys.exit(main())
