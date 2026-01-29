"""
Macro Regime Classifier - Classify macroeconomic regimes
Ported from wealth_signal_mvp_v1/core/regimes/macro_regime_classifier.py
"""
import pandas as pd
from src.utils.logger import setup_logger

logger = setup_logger()


def classify_macro_regime(df_macro: pd.DataFrame) -> pd.Series:
    """
    Classify macroeconomic regime for each row in a macro feature DataFrame.

    Parameters:
        df_macro: Contains macroeconomic features like yield curve, CPI, ISM, etc.
                  Expected columns:
                  - 'T10Y3M': 10y - 3m yield spread
                  - 'FEDFUNDS_REAL': Real Fed Funds Rate
                  - 'BAMLH0A0HYM2': High Yield Credit Spread (ICE BofA)
                  - 'ISM': ISM Manufacturing Index
                  - 'CPI_YOY': YoY CPI Inflation

    Returns:
        Series: A regime label for each date (e.g., "risk_on", "recession", "volatile", etc.)
    """
    labels = []

    for i, row in df_macro.iterrows():
        try:
            # Default label
            label = "neutral"

            # Recession: Inverted yield curve + weak ISM
            if row.get("T10Y3M", 1) < 0 and row.get("ISM", 50) < 48:
                label = "recession"
            # Volatile: High credit spreads
            elif row.get("BAMLH0A0HYM2", 0) > 5:
                label = "volatile"
            # Stagflation: High rates + high inflation
            elif row.get("FEDFUNDS_REAL", 0) > 1.5 and row.get("CPI_YOY", 0) > 4:
                label = "stagflation"
            # Risk-on: Strong ISM + low inflation
            elif row.get("ISM", 0) > 52 and row.get("CPI_YOY", 0) < 3:
                label = "risk_on"

            labels.append(label)
        except Exception as e:
            logger.warning(f"Error classifying regime for row {i}: {e}")
            labels.append("unknown")

    return pd.Series(labels, index=df_macro.index, name="regime")


def export_regimes(df_macro: pd.DataFrame, out_path: str = "outputs/macro_regimes.csv") -> None:
    """
    Classify and export regime labels to a CSV file.

    Parameters:
        df_macro: Macro features DataFrame
        out_path: CSV output path
    """
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    df = df_macro.copy()
    df["regime"] = classify_macro_regime(df)
    df.to_csv(out_path, index=True)
    logger.info(f"Exported regimes to: {out_path}")
