"""
Feature engineering for news-derived stress and SCSI.
Expects DataFrames with columns [Date, Ticker, Title, Body, Source].
"""
from __future__ import annotations

import math

import pandas as pd


def score_articles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add sentiment column by applying sentiment_finbert(title + " " + body) to each row.
    Input: DataFrame with columns [Date, Ticker, Title, Body, Source].
    Returns: same DataFrame with 'sentiment' column added.
    """
    from src.signals.news_engine import sentiment_finbert

    out = df.copy()
    sentiments = []
    for _, row in out.iterrows():
        text = (str(row.get("Title", "") or "") + " " + str(row.get("Body", "") or "")).strip()
        sentiments.append(sentiment_finbert(text))
    out["sentiment"] = sentiments
    return out


def compute_daily_stress(df: pd.DataFrame) -> pd.DataFrame:
    """
    Group by [Date, Ticker]; compute mean_sentiment, article_count,
    stress_raw = (mean_sentiment - 0.5) * log(1 + article_count).
    Returns DataFrame with columns [Date, Ticker, stress_raw].
    """
    if df.empty or "sentiment" not in df.columns:
        return pd.DataFrame(columns=["Date", "Ticker", "stress_raw"])

    g = df.groupby(["Date", "Ticker"], as_index=False)
    agg = g.agg(mean_sentiment=("sentiment", "mean"), article_count=("sentiment", "count"))
    agg["stress_raw"] = (agg["mean_sentiment"] - 0.5) * agg["article_count"].apply(
        lambda c: math.log(1 + c)
    )
    return agg[["Date", "Ticker", "stress_raw"]].copy()


def compute_scsi(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort by [Ticker, Date]; per ticker compute stress_7d (7d rolling mean of stress_raw),
    stress_30d (30d rolling mean), scsi = stress_7d - stress_30d.
    Returns DataFrame with columns [Date, Ticker, stress_raw, stress_7d, stress_30d, scsi].
    Uses min_periods=1 on rolling windows.
    """
    if daily_df.empty or "stress_raw" not in daily_df.columns:
        return pd.DataFrame(
            columns=["Date", "Ticker", "stress_raw", "stress_7d", "stress_30d", "scsi"]
        )

    df = daily_df.sort_values(["Ticker", "Date"]).copy()
    out = []
    for ticker, grp in df.groupby("Ticker", sort=False):
        g = grp.sort_values("Date")
        g = g.copy()
        g["stress_7d"] = g["stress_raw"].rolling(7, min_periods=1).mean()
        g["stress_30d"] = g["stress_raw"].rolling(30, min_periods=1).mean()
        g["scsi"] = g["stress_7d"] - g["stress_30d"]
        out.append(g)
    if not out:
        return pd.DataFrame(
            columns=["Date", "Ticker", "stress_raw", "stress_7d", "stress_30d", "scsi"]
        )
    result = pd.concat(out, ignore_index=True)
    return result[["Date", "Ticker", "stress_raw", "stress_7d", "stress_30d", "scsi"]]
