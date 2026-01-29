"""
Move Stock Data to OneDrive
Moves stock market data from C drive to OneDrive for cloud storage.
"""
import shutil
import sys
from pathlib import Path
from datetime import datetime

# Paths
SOURCE_DIR = Path(r"C:\Users\dusro\Downloads\stock\stock_market_data")
DEST_DIR = Path(r"C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\data\stock_market_data")

def get_directory_size(path: Path) -> int:
    """Calculate total size of directory in bytes"""
    total = 0
    try:
        for entry in path.rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
    except Exception as e:
        print(f"   ⚠️  Warning: Could not calculate size for {path}: {e}")
    return total

def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def move_stock_data(source: Path = None, dest: Path = None, dry_run: bool = False, auto_confirm: bool = False):
    """
    Move stock data from source to destination
    
    Args:
        source: Source directory (defaults to C:/Users/dusro/Downloads/stock/stock_market_data)
        dest: Destination directory (defaults to OneDrive project folder)
        dry_run: If True, only show what would be moved without actually moving
    """
    if source is None:
        source = SOURCE_DIR
    if dest is None:
        dest = DEST_DIR
    
    source = Path(source)
    dest = Path(dest)
    
    print("=" * 80)
    print("Move Stock Data to OneDrive")
    print("=" * 80)
    print(f"Source: {source}")
    print(f"Destination: {dest}")
    print(f"Mode: {'DRY RUN (no files will be moved)' if dry_run else 'LIVE (files will be moved)'}")
    print()
    
    # Check if source exists
    if not source.exists():
        print(f"[ERROR] Source directory does not exist: {source}")
        return
    
    # Check if source has subdirectories
    subdirs = [d for d in source.iterdir() if d.is_dir()]
    if not subdirs:
        print(f"[WARNING] Source directory is empty or has no subdirectories: {source}")
        return
    
    print(f"Found {len(subdirs)} subdirectories:")
    for subdir in subdirs:
        size = get_directory_size(subdir)
        print(f"   • {subdir.name}: {format_size(size)}")
    
    # Calculate total size
    total_size = get_directory_size(source)
    print(f"\nTotal size: {format_size(total_size)}")
    
    if dry_run:
        print("\n[DRY RUN] No files will be moved")
        print("   Run without --dry-run to actually move files")
        return
    
    # Confirm before moving
    print("\n[WARNING] This will move all files from source to destination.")
    print("   The source files will be deleted after successful copy.")
    
    if not auto_confirm:
        response = input("   Continue? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("   Cancelled.")
            return
    else:
        print("   Auto-confirmed (--yes flag provided)")
    
    # Create destination directory
    print(f"\n[1/3] Creating destination directory...")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        print(f"   [OK] Created: {dest}")
    except Exception as e:
        print(f"   [ERROR] Error creating destination: {e}")
        return
    
    # Move each subdirectory
    print(f"\n[2/3] Moving subdirectories...")
    moved_count = 0
    failed_count = 0
    
    for subdir in subdirs:
        source_subdir = subdir
        dest_subdir = dest / subdir.name
        
        print(f"\n   Moving: {subdir.name}...")
        try:
            # Use shutil.move which handles the move operation
            shutil.move(str(source_subdir), str(dest_subdir))
            print(f"   [OK] Moved: {subdir.name}")
            moved_count += 1
        except Exception as e:
            print(f"   [ERROR] Error moving {subdir.name}: {e}")
            failed_count += 1
    
    print(f"\n[3/3] [SUCCESS] Move operation complete!")
    print(f"   Successfully moved: {moved_count} directories")
    if failed_count > 0:
        print(f"   Failed: {failed_count} directories")
    
    # Verify destination
    if dest.exists():
        dest_subdirs = [d for d in dest.iterdir() if d.is_dir()]
        print(f"\nDestination now contains {len(dest_subdirs)} subdirectories:")
        for subdir in dest_subdirs:
            size = get_directory_size(subdir)
            print(f"   • {subdir.name}: {format_size(size)}")
    
    print(f"\n[SUCCESS] Stock data has been moved to OneDrive!")
    print(f"   Update config/data_config.yaml to point to:")
    print(f"   data_dir: \"{dest.as_posix()}\"")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Move stock data to OneDrive")
    parser.add_argument("--source", "-s", type=str, help="Source directory")
    parser.add_argument("--dest", "-d", type=str, help="Destination directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be moved without actually moving")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm without prompting")
    
    args = parser.parse_args()
    
    # Pass yes flag to move function
    move_stock_data(
        source=args.source,
        dest=args.dest,
        dry_run=args.dry_run,
        auto_confirm=args.yes if hasattr(args, 'yes') else False
    )
