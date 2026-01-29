"""
Check CSV Slicing Progress
Quick script to check if the slicing operation is running and show progress.
"""
from pathlib import Path
import datetime
import sys

def check_progress():
    """Check the progress of CSV slicing operation"""
    output_file = Path("data/raw/fnspid_nasdaq_news_2023_2024.csv")
    input_file = Path("data/raw/fnspid_nasdaq_news.csv")
    
    print("=" * 70)
    print("CSV SLICING PROGRESS CHECK")
    print("=" * 70)
    print()
    
    # Check input file
    if input_file.exists():
        input_size_gb = input_file.stat().st_size / (1024**3)
        print(f"Input file: {input_file.name}")
        print(f"  Size: {input_size_gb:.2f} GB")
        print()
    else:
        print(f"[ERROR] Input file not found: {input_file}")
        return
    
    # Check output file
    if output_file.exists():
        output_size = output_file.stat().st_size
        output_size_mb = output_size / (1024**2)
        output_size_gb = output_size / (1024**3)
        last_modified = datetime.datetime.fromtimestamp(output_file.stat().st_mtime)
        time_since_mod = datetime.datetime.now() - last_modified
        
        print(f"Output file: {output_file.name}")
        print(f"  Status: EXISTS - Process is running or completed")
        print(f"  Current size: {output_size_mb:.1f} MB ({output_size_gb:.3f} GB)")
        print(f"  Last modified: {last_modified.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Time since last write: {time_since_mod}")
        
        # Estimate progress
        if output_size_gb > 0:
            estimated_total_mb = 500  # Rough estimate for 2023-2024 data
            progress_pct = min(100, (output_size_mb / estimated_total_mb) * 100)
            print(f"  Estimated progress: ~{progress_pct:.1f}% (assuming ~500MB final size)")
        
        # Check if file is still being written (modified recently)
        if time_since_mod.total_seconds() < 60:
            print(f"  [ACTIVE] File was modified recently - process is likely still running")
        elif time_since_mod.total_seconds() < 300:
            print(f"  [PAUSED?] File not modified in last 5 minutes - may be processing a large chunk")
        else:
            print(f"  [COMPLETE?] File not modified recently - process may have finished or stopped")
        
        print()
        print("=" * 70)
        print("TIP: Run this script again in a few minutes to see updated progress")
        print("=" * 70)
    else:
        print(f"Output file: {output_file.name}")
        print(f"  Status: NOT CREATED YET")
        print()
        print("Possible reasons:")
        print("  1. Process is still reading initial chunks (may take several minutes)")
        print("  2. Process hasn't found any 2023-2024 data yet")
        print("  3. Process encountered an error")
        print()
        print("=" * 70)
        print("TIP: Check if Python process is running:")
        print("     Task Manager -> Details -> Look for python.exe")
        print("=" * 70)

if __name__ == "__main__":
    check_progress()
