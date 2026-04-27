import pandas as pd
from pathlib import Path

p = Path(
    r"C:\ai_supply_chain_trading\trading_data\fundamentals\quarterly_signals.parquet"
)
if not p.exists():
    print(f"NOT FOUND: {p.resolve()}")
else:
    df = pd.read_parquet(p)
    cols = ["fcf_yield", "roic", "fcf_conversion", "net_capex_sales", "net_debt_ebitda"]
    print(f"Tickers covered: {df.ticker.nunique()}")
    print(f"Total rows: {len(df)}")
    print("\nNon-null coverage per metric:")
    print(df[cols].notna().mean().round(3).to_string())
