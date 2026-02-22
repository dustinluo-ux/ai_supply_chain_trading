"""
Generate feature matrix: Tiingo news -> SCSI -> merge with price returns; save parquet and print correlations.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate feature matrix from Tiingo news and prices.")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated; default: config watchlist")
    parser.add_argument("--start", type=str, default="2022-01-01")
    parser.add_argument("--end", type=str, default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output parquet path; default: feature_matrix.parquet in data_manager.get_path('prices')",
    )
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        from src.utils.config_manager import get_config
        tickers = get_config().get_watchlist()

    if not tickers:
        print("ERROR: No tickers. Set --tickers or config watchlist.", file=sys.stderr)
        return 1

    from src.utils.data_manager import get_path
    from src.utils.storage_handler import read_from_parquet, save_to_parquet
    from src.signals.feature_engineering import score_articles, compute_daily_stress, compute_scsi

    news_dir = get_path("news")
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")

    # 1. Load all tiingo_{YYYY}_{MM}.parquet from news dir; filter to tickers and date range
    import pandas as pd

    parts = []
    for p in sorted(news_dir.glob("tiingo_*.parquet")):
        name = p.stem
        if not name.startswith("tiingo_"):
            continue
        try:
            y, m = name.replace("tiingo_", "").split("_")
            month_start = datetime(int(y), int(m), 1)
            if month_start > end_dt:
                continue
            from calendar import monthrange
            _, last_d = monthrange(int(y), int(m))
            month_end = datetime(int(y), int(m), last_d)
            if month_end < start_dt:
                continue
        except Exception:
            continue
        try:
            df = read_from_parquet(p)
            if df.empty:
                continue
            if "Date" not in df.columns:
                continue
            df["Date"] = pd.to_datetime(df["Date"])
            df = df[(df["Date"] >= pd.Timestamp(args.start)) & (df["Date"] <= pd.Timestamp(args.end))]
            df = df[df["Ticker"].isin([t.upper() for t in tickers])]
            if not df.empty:
                parts.append(df)
        except Exception as e:
            print(f"  [WARN] Skip {p.name}: {e}", flush=True)

    if not parts:
        print("ERROR: No Tiingo parquet data found in date range.", file=sys.stderr)
        return 1

    news_df = pd.concat(parts, ignore_index=True).drop_duplicates()

    # 2. score_articles -> compute_daily_stress -> compute_scsi
    scored = score_articles(news_df)
    daily = compute_daily_stress(scored)
    scsi_df = compute_scsi(daily)

    # 3. Look-ahead: shift SCSI Date forward by 1 day
    scsi_df = scsi_df.copy()
    scsi_df["Date"] = scsi_df["Date"] + pd.Timedelta(days=1)

    # 4. Load price data (csv_provider); build [Date, Ticker, close, next_day_return]
    from src.data.csv_provider import load_data_config, load_prices

    config = load_data_config()
    data_dir = config["data_dir"]
    if not isinstance(data_dir, Path):
        data_dir = Path(data_dir)
    prices_dict = load_prices(data_dir, tickers)

    price_parts = []
    for ticker, df in prices_dict.items():
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df["close"] = df["close"]
        df["next_day_return"] = df["close"].pct_change(1).shift(-1)
        df = df[["close", "next_day_return"]].dropna(subset=["next_day_return"])
        df = df.reset_index()
        df = df.rename(columns={"index": "Date"})
        df["Ticker"] = ticker
        df = df[(df["Date"] >= pd.Timestamp(args.start)) & (df["Date"] <= pd.Timestamp(args.end))]
        if not df.empty:
            price_parts.append(df[["Date", "Ticker", "close", "next_day_return"]])

    if not price_parts:
        print("ERROR: No price data for tickers in date range.", file=sys.stderr)
        return 1

    price_df = pd.concat(price_parts, ignore_index=True)
    price_df["Date"] = pd.to_datetime(price_df["Date"]).dt.normalize()
    scsi_df["Date"] = pd.to_datetime(scsi_df["Date"]).dt.normalize()

    # 5. Left merge: price (left) with SCSI on [Date, Ticker]
    matrix = price_df.merge(
        scsi_df,
        on=["Date", "Ticker"],
        how="left",
    )

    # 6. Drop rows where scsi or next_day_return is NaN
    matrix = matrix.dropna(subset=["scsi", "next_day_return"])

    # 7. Correlation
    from scipy.stats import spearmanr, pearsonr

    sr, sp = spearmanr(matrix["scsi"], matrix["next_day_return"])
    pr, pp = pearsonr(matrix["scsi"], matrix["next_day_return"])
    n = len(matrix)
    print("Spearman r={:.4f}  p={:.4f}".format(sr, sp))
    print("Pearson  r={:.4f}  p={:.4f}".format(pr, pp))
    print("N={}".format(n))

    # 8. Save to --output
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = get_path("prices") / "feature_matrix.parquet"
    out_path = Path(out_path)
    save_to_parquet(matrix, out_path)

    # 9. Summary
    print("Summary: tickers={}, date range {} to {}, total rows={}, output={}".format(
        tickers, args.start, args.end, len(matrix), out_path
    ))

    return 0


if __name__ == "__main__":
    sys.exit(main())
