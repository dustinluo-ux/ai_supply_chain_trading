"""
Scan price CSV date ranges for key universe tickers.
Output: earliest, latest, trading days, file path for docs/PRICE_DATA_COVERAGE_REPORT.md
"""
import pandas as pd
from pathlib import Path

# Prefer nasdaq/csv when multiple; else first found
TICKER_PATHS = {
    "NVDA": "data/stock_market_data/nasdaq/csv/NVDA.csv",
    "AMD": "data/stock_market_data/nasdaq/csv/AMD.csv",
    "TSM": "data/stock_market_data/nyse/csv/TSM.csv",
    "AAPL": "data/stock_market_data/nasdaq/csv/AAPL.csv",
    "MSFT": "data/stock_market_data/nasdaq/csv/MSFT.csv",
    "INTC": "data/stock_market_data/nasdaq/csv/INTC.csv",
    "QCOM": "data/stock_market_data/nasdaq/csv/QCOM.csv",
    "MU": "data/stock_market_data/nasdaq/csv/MU.csv",
    "AMAT": "data/stock_market_data/nasdaq/csv/AMAT.csv",
}

project_root = Path(__file__).resolve().parent.parent

def main():
    results = []
    for ticker, rel_path in TICKER_PATHS.items():
        path = project_root / rel_path
        if not path.exists():
            results.append({
                "ticker": ticker,
                "file": str(rel_path),
                "earliest": None,
                "latest": None,
                "days": 0,
                "coverage": "MISSING",
            })
            continue
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True, dayfirst=True)
            if df.empty or not isinstance(df.index, pd.DatetimeIndex):
                results.append({"ticker": ticker, "file": str(rel_path), "earliest": None, "latest": None, "days": 0, "coverage": "NO_DATES"})
                continue
            idx = df.index.sort_values()
            earliest = idx.min()
            latest = idx.max()
            days = len(idx)
            # Simple gap check: expect ~252 trading days/year
            span_days = (latest - earliest).days
            expected = max(1, span_days * 252 // 365)
            gap_note = "OK" if days >= expected * 0.7 else "gaps?"
            results.append({
                "ticker": ticker,
                "file": str(rel_path),
                "earliest": earliest,
                "latest": latest,
                "days": days,
                "coverage": gap_note,
            })
        except Exception as e:
            results.append({
                "ticker": ticker,
                "file": str(rel_path),
                "earliest": None,
                "latest": None,
                "days": 0,
                "coverage": str(e)[:20],
            })

    # Print table
    print("| Ticker | Earliest | Latest | Days | Coverage | File |")
    print("|--------|----------|--------|------|----------|------|")
    for r in results:
        e = r["earliest"].strftime("%Y-%m-%d") if r["earliest"] else "?"
        l = r["latest"].strftime("%Y-%m-%d") if r["latest"] else "?"
        print(f"| {r['ticker']:6} | {e} | {l} | {r['days']:5} | {r['coverage']:8} | {r['file']} |")
    return results

if __name__ == "__main__":
    main()
