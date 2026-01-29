"""
Backup cache files to data/cache_backup/ before clearing for Gemini re-run.
"""
import shutil
from pathlib import Path
from datetime import datetime

def backup_cache_files():
    """Move cache files to backup directory."""
    data_dir = Path('data')
    backup_dir = data_dir / 'cache_backup'
    
    # Create backup directory
    backup_dir.mkdir(exist_ok=True)
    print(f"[OK] Created backup directory: {backup_dir}")
    
    moved_files = []
    
    # Move supply_chain_mentions.csv
    csv_file = data_dir / 'supply_chain_mentions.csv'
    if csv_file.exists():
        try:
            backup_path = backup_dir / csv_file.name
            shutil.move(str(csv_file), str(backup_path))
            moved_files.append(csv_file.name)
            print(f"[OK] Moved: {csv_file.name}")
        except Exception as e:
            print(f"[ERROR] Error moving {csv_file.name}: {e}")
    else:
        print(f"[WARNING] File not found: {csv_file.name}")
    
    # Move all *_extractions.json files
    extraction_files = list(data_dir.glob('*_extractions.json'))
    if extraction_files:
        print(f"\nMoving {len(extraction_files)} extraction files...")
        for json_file in extraction_files:
            try:
                backup_path = backup_dir / json_file.name
                shutil.move(str(json_file), str(backup_path))
                moved_files.append(json_file.name)
            except Exception as e:
                print(f"[ERROR] Error moving {json_file.name}: {e}")
        print(f"[OK] Moved {len(extraction_files)} extraction files")
    else:
        print("[WARNING] No extraction files found")
    
    # Verify backup
    print(f"\n{'='*60}")
    print("BACKUP VERIFICATION")
    print(f"{'='*60}")
    
    backup_files = list(backup_dir.glob('*'))
    print(f"Files in backup directory: {len(backup_files)}")
    
    if backup_files:
        print("\nFirst 10 files:")
        for f in sorted(backup_files)[:10]:
            size_kb = f.stat().st_size / 1024
            print(f"  - {f.name} ({size_kb:.1f} KB)")
        
        if len(backup_files) > 10:
            print(f"  ... and {len(backup_files) - 10} more files")
    
    # Verify cache directory is empty
    print(f"\n{'='*60}")
    print("CACHE DIRECTORY CHECK")
    print(f"{'='*60}")
    
    csv_exists = (data_dir / 'supply_chain_mentions.csv').exists()
    extraction_count = len(list(data_dir.glob('*_extractions.json')))
    
    print(f"supply_chain_mentions.csv exists: {csv_exists}")
    print(f"*_extractions.json files: {extraction_count}")
    
    if not csv_exists and extraction_count == 0:
        print("[OK] Cache directory is empty - ready for Gemini re-run!")
    else:
        print("[WARNING] Some cache files still exist")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total files backed up: {len(backup_files)}")
    print(f"Backup location: {backup_dir.absolute()}")
    print(f"Backup date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return len(backup_files), moved_files

if __name__ == '__main__':
    backup_cache_files()
