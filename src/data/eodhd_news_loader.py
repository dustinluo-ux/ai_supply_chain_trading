"""
EODHD historical news loader for backtest news signal pipeline.
Loads eodhd_global_backfill.parquet, filters by tickers and date range,
applies cross-sectional z-score normalization per date, rescales to [0, 1].
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_DEFAULT_DATA_DIR = r"C:\ai_supply_chain_trading\trading_data"


def load_eodhd_news_signals(
    tickers: list[str],
    start_date: str,
    end_date: str,
    parquet_path: Path | str | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """
    Load EODHD news from parquet, filter by tickers and [start_date, end_date],
    z-score normalize Sentiment per date, rescale to [0, 1]. Returns
    {ticker: {date_str: {"sentiment_score": float}}}.
    Silent fail on missing file or error → return {}.
    """
    if not tickers:
        return {}
    try:
        data_dir = os.environ.get("DATA_DIR", _DEFAULT_DATA_DIR)
        if parquet_path is None:
            parquet_path = Path(data_dir) / "news" / "eodhd_global_backfill.parquet"
        path = Path(parquet_path)
        if not path.exists():
            print(f"[EODHD] Parquet not found at: {path}")
            return {}
        df = pd.read_parquet(path, engine="fastparquet")
        if df.empty or "Date" not in df.columns or "Ticker" not in df.columns or "Sentiment" not in df.columns:
            return {}
        df = df[df["Ticker"].isin(tickers) & (df["Date"] >= start_date) & (df["Date"] <= end_date)].copy()
        if df.empty:
            print(f"[EODHD] No rows in range {start_date}–{end_date} for {len(tickers)} tickers")
            return {}
        row_count = len(df)
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for date_str, grp in df.groupby("Date", sort=False):
            sents = grp.groupby("Ticker")["Sentiment"].mean()
            if len(sents) == 1:
                for t in sents.index:
                    out.setdefault(t, {})[str(date_str)] = {"sentiment_score": 0.5}
                continue
            mean_s = float(sents.mean())
            std_s = float(sents.std())
            if std_s <= 0 or np.isnan(std_s):
                for t in sents.index:
                    out.setdefault(t, {})[str(date_str)] = {"sentiment_score": 0.5}
                continue
            z = (sents - mean_s) / std_s
            rescaled = np.clip((z + 3.0) / 6.0, 0.0, 1.0)
            for t in rescaled.index:
                out.setdefault(t, {})[str(date_str)] = {"sentiment_score": float(rescaled[t])}
        tickers_covered = len(out)
        date_min = min(d for d in df["Date"].astype(str))
        date_max = max(d for d in df["Date"].astype(str))
        print(f"[EODHD] Loaded: {tickers_covered} tickers, {date_min}–{date_max}, {row_count} rows")
        return out
    except Exception as e:
        print(f"[EODHD] Failed to load news signals: {type(e).__name__}: {e}")
        return {}
