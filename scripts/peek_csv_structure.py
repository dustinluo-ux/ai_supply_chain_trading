"""
Peek at CSV Structure
Reads first 5 rows of a large CSV file to inspect column names and structure
without loading the entire file into memory.
"""
import pandas as pd
import sys
from pathlib import Path

# Default path to the large CSV file
DEFAULT_FILE_PATH = r"C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\data\raw\fnspid_nasdaq_news.csv"

def peek_csv(file_path: str = None):
    """
    Peek at the first 5 rows of a CSV file
    
    Args:
        file_path: Path to CSV file (defaults to fnspid_nasdaq_news.csv)
    """
    if file_path is None:
        file_path = DEFAULT_FILE_PATH
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        print(f"   Please check the path and try again.")
        return
    
    print(f"Reading first 5 rows from: {file_path}")
    print(f"   File size: {file_path.stat().st_size / (1024**3):.2f} GB\n")
    
    try:
        # Read just the first 5 rows
        df_peek = pd.read_csv(file_path, nrows=5, low_memory=False)
        
        print("=" * 80)
        print("--- COLUMN NAMES FOUND ---")
        print("=" * 80)
        print(df_peek.columns.tolist())
        print()
        
        print("=" * 80)
        print("--- SAMPLE DATA (First 5 Rows) ---")
        print("=" * 80)
        print(df_peek.head())
        print()
        
        print("=" * 80)
        print("--- DATA TYPES ---")
        print("=" * 80)
        print(df_peek.dtypes)
        print()
        
        # Check for date columns
        date_columns = []
        for col in df_peek.columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in ['date', 'time', 'published', 'created']):
                date_columns.append(col)
        
        if date_columns:
            print("=" * 80)
            print("--- POTENTIAL DATE COLUMNS ---")
            print("=" * 80)
            for col in date_columns:
                print(f"  • {col}: {df_peek[col].iloc[0] if len(df_peek) > 0 else 'N/A'}")
            print()
        
        # Check for content columns
        content_columns = []
        for col in df_peek.columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in ['content', 'text', 'body', 'summary', 'description', 'headline', 'title']):
                content_columns.append(col)
        
        if content_columns:
            print("=" * 80)
            print("--- POTENTIAL CONTENT COLUMNS ---")
            print("=" * 80)
            for col in content_columns:
                sample = str(df_peek[col].iloc[0]) if len(df_peek) > 0 else 'N/A'
                preview = sample[:100] + "..." if len(sample) > 100 else sample
                print(f"  • {col}: {preview}")
            print()
        
        print("=" * 80)
        print("[SUCCESS] Successfully peeked at CSV structure!")
        print("=" * 80)
        print("\nNext steps:")
        print("1. Note the DATE column name (for filtering)")
        print("2. Note the CONTENT column name (for analysis)")
        print("3. Run slice_csv_for_poc.py to extract 2023-2024 data")
        
    except Exception as e:
        print(f"[ERROR] Error reading CSV: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Allow file path as command line argument
    file_path = sys.argv[1] if len(sys.argv) > 1 else None
    peek_csv(file_path)
