"""Quick diagnostic to check CSV file format and date ranges"""
import pandas as pd
from pathlib import Path

data_dir = Path("C:/Users/dusro/Downloads/stock/stock_market_data/nasdaq/csv")
csv_files = list(data_dir.glob("*.csv"))[:5]  # Check first 5 files

print("Checking CSV file formats...")
print("=" * 60)

for csv_file in csv_files:
    print(f"\nFile: {csv_file.name}")
    try:
        # Try with dayfirst=True
        df = pd.read_csv(csv_file, index_col=0, parse_dates=True, dayfirst=True)
        print(f"  Columns: {df.columns.tolist()}")
        print(f"  Date range: {df.index.min()} to {df.index.max()}")
        print(f"  Total rows: {len(df)}")
        
        # Check if we have 2023-2024 data
        df_2023 = df[(df.index >= '2023-01-01') & (df.index <= '2024-12-31')]
        print(f"  2023-2024 rows: {len(df_2023)}")
        
        # Check if we have 2020+ data
        df_recent = df[df.index >= '2020-01-01']
        print(f"  2020+ rows: {len(df_recent)}")
        
        # Sample dates
        print(f"  Sample dates: {df.index[:3].tolist()}")
        
    except Exception as e:
        print(f"  ERROR: {e}")
