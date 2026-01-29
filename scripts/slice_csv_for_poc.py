"""
Slice CSV for PoC
Extracts 2023-2024 data from a large CSV file to create a smaller PoC dataset.
This reduces a 23GB file down to ~200-500MB for easier handling.
"""
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

# Default paths
DEFAULT_INPUT_FILE = r"C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\data\raw\fnspid_nasdaq_news.csv"
DEFAULT_OUTPUT_FILE = r"C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\data\raw\fnspid_nasdaq_news_2023_2024.csv"

def find_date_column(df_sample: pd.DataFrame) -> str:
    """
    Try to find the date column in the DataFrame
    
    Args:
        df_sample: Sample DataFrame (first few rows)
        
    Returns:
        Name of date column, or None if not found
    """
    # Common date column names
    date_keywords = ['date', 'time', 'published', 'created', 'timestamp']
    
    for col in df_sample.columns:
        col_lower = col.lower()
        if any(keyword in col_lower for keyword in date_keywords):
            return col
    
    return None

def slice_csv(
    input_file: str = None,
    output_file: str = None,
    date_start: str = "2023-01-01",
    date_end: str = "2024-12-31",
    date_column: str = None,
    chunksize: int = 100000
):
    """
    Slice a large CSV file to extract data for a specific date range
    
    Args:
        input_file: Path to input CSV file
        output_file: Path to output CSV file
        date_start: Start date (YYYY-MM-DD)
        date_end: End date (YYYY-MM-DD)
        date_column: Name of date column (auto-detect if None)
        chunksize: Number of rows to process at a time
    """
    if input_file is None:
        input_file = DEFAULT_INPUT_FILE
    if output_file is None:
        output_file = DEFAULT_OUTPUT_FILE
    
    input_path = Path(input_file)
    output_path = Path(output_file)
    
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}")
        return
    
    # Check file size
    file_size_gb = input_path.stat().st_size / (1024**3)
    print(f"Input file: {input_path}")
    print(f"   Size: {file_size_gb:.2f} GB")
    print(f"Output file: {output_path}")
    print(f"   Date range: {date_start} to {date_end}")
    print(f"   Chunk size: {chunksize:,} rows\n")
    
    # First, peek at the structure to find date column
    print("[1/4] Peeking at CSV structure to find date column...")
    try:
        df_peek = pd.read_csv(input_path, nrows=5, low_memory=False)
        print(f"   [OK] Found columns: {df_peek.columns.tolist()}")
        
        # Auto-detect date column if not provided
        if date_column is None:
            date_column = find_date_column(df_peek)
            if date_column:
                print(f"   [OK] Auto-detected date column: '{date_column}'")
            else:
                print(f"   [WARNING] Could not auto-detect date column.")
                print(f"   Available columns: {df_peek.columns.tolist()}")
                print(f"   Please specify date column name manually.")
                return
        else:
            if date_column not in df_peek.columns:
                print(f"   [ERROR] Date column '{date_column}' not found in CSV")
                print(f"   Available columns: {df_peek.columns.tolist()}")
                return
            print(f"   [OK] Using date column: '{date_column}'")
    except Exception as e:
        print(f"   [ERROR] Error peeking at CSV: {e}")
        return
    
    # Parse date range (make timezone-aware to match CSV data)
    try:
        date_start_dt = pd.to_datetime(date_start)
        date_end_dt = pd.to_datetime(date_end)
        # Make timezone-aware (UTC) to match the CSV data format
        date_start_dt = date_start_dt.tz_localize('UTC') if date_start_dt.tz is None else date_start_dt
        date_end_dt = date_end_dt.tz_localize('UTC') if date_end_dt.tz is None else date_end_dt
        print(f"\n[2/4] Date range: {date_start_dt.date()} to {date_end_dt.date()} (UTC)")
    except Exception as e:
        print(f"   [ERROR] Error parsing date range: {e}")
        return
    
    # Process in chunks
    print(f"\n[3/4] Processing CSV in chunks of {chunksize:,} rows...")
    print("   This may take a while for large files. Please be patient...\n")
    
    first_chunk = True
    total_rows_processed = 0
    total_rows_saved = 0
    
    try:
        chunks = pd.read_csv(input_path, chunksize=chunksize, low_memory=False)
        
        for i, chunk in enumerate(chunks):
            total_rows_processed += len(chunk)
            
            # Convert date column
            try:
                chunk[date_column] = pd.to_datetime(chunk[date_column], errors='coerce')
            except Exception as e:
                print(f"   [WARNING] Error parsing dates in chunk {i}: {e}")
                continue
            
            # Filter for date range
            filtered = chunk[
                (chunk[date_column] >= date_start_dt) & 
                (chunk[date_column] <= date_end_dt)
            ]
            
            # Save filtered rows
            if not filtered.empty:
                filtered.to_csv(
                    output_path,
                    mode='a',
                    index=False,
                    header=first_chunk
                )
                total_rows_saved += len(filtered)
                first_chunk = False
            
            # Progress update every 10 chunks
            if i % 10 == 0:
                print(f"   Processed {total_rows_processed:,} rows... "
                      f"({total_rows_saved:,} rows saved so far)")
        
        print(f"\n[4/4] [SUCCESS] Extraction complete!")
        print(f"   Total rows processed: {total_rows_processed:,}")
        print(f"   Rows saved: {total_rows_saved:,}")
        
        if output_path.exists():
            output_size_gb = output_path.stat().st_size / (1024**3)
            reduction = (1 - output_size_gb / file_size_gb) * 100
            print(f"   Output file size: {output_size_gb:.2f} GB")
            print(f"   Size reduction: {reduction:.1f}%")
            print(f"\n[SUCCESS] PoC dataset saved to: {output_path}")
            print(f"   You can now use this smaller file for your project!")
        else:
            print(f"   [WARNING] No matching rows found in date range {date_start} to {date_end}")
            
    except Exception as e:
        print(f"\n[ERROR] Error processing CSV: {e}")
        import traceback
        traceback.print_exc()
        if output_path.exists():
            print(f"\n[WARNING] Partial output may have been saved to: {output_path}")


if __name__ == "__main__":
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Slice large CSV file for PoC")
    parser.add_argument("--input", "-i", type=str, help="Input CSV file path")
    parser.add_argument("--output", "-o", type=str, help="Output CSV file path")
    parser.add_argument("--date-start", type=str, default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--date-end", type=str, default="2024-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--date-column", type=str, help="Name of date column (auto-detect if not provided)")
    parser.add_argument("--chunksize", type=int, default=100000, help="Chunk size for processing")
    
    args = parser.parse_args()
    
    slice_csv(
        input_file=args.input,
        output_file=args.output,
        date_start=args.date_start,
        date_end=args.date_end,
        date_column=args.date_column,
        chunksize=args.chunksize
    )
