"""
Move cached FNSPID file to project folder
Makes the project self-contained by moving the file from cache to project folder
"""
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from huggingface_hub import scan_cache_dir
except ImportError:
    print("ERROR: huggingface_hub not installed")
    print("  pip install huggingface_hub")
    sys.exit(1)

print("=" * 60)
print("Move Cached File to Project Folder")
print("=" * 60)

# Target location in project folder
output_path = Path("data/raw/fnspid_nasdaq_news.csv")
output_path.parent.mkdir(parents=True, exist_ok=True)

print(f"\n[1/3] Finding cached file...")

try:
    cache_info = scan_cache_dir()
    
    cached_file_path = None
    for repo in cache_info.repos:
        if "FNSPID" in repo.repo_id:
            for revision in repo.revisions:
                for file in revision.files:
                    if "nasdaq_exteral_data.csv" in file.file_name:
                        cached_file_path = Path(file.file_path)
                        file_size_gb = file.size_on_disk / (1024**3)
                        print(f"  [OK] Found cached file: {cached_file_path}")
                        print(f"  [OK] File size: {file_size_gb:.2f} GB")
                        break
                if cached_file_path:
                    break
            if cached_file_path:
                break
    
    if not cached_file_path or not cached_file_path.exists():
        print(f"  [ERROR] Cached file not found")
        print(f"  Run 'python scripts/download_fnspid.py' first")
        sys.exit(1)
    
    print(f"\n[2/3] Checking disk space...")
    # Check available space (rough estimate)
    import os
    stat = os.statvfs(output_path.parent) if hasattr(os, 'statvfs') else None
    if stat:
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
        print(f"  Available space: {free_gb:.1f} GB")
        if free_gb < 25:
            print(f"  [WARNING] Low disk space! File requires ~23.2 GB")
    
    print(f"\n[3/3] Moving file to project folder...")
    print(f"  From: {cached_file_path}")
    print(f"  To:   {output_path}")
    print(f"  [INFO] This may take a few minutes (23GB file)...")
    
    if output_path.exists():
        response = input(f"  File already exists at {output_path}. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print(f"  [CANCELLED] Not overwriting existing file")
            sys.exit(0)
        output_path.unlink()
    
    # Move file (faster than copy, but removes from cache)
    shutil.move(str(cached_file_path), str(output_path))
    
    file_size_gb = output_path.stat().st_size / (1024**3)
    print(f"  [OK] File moved successfully!")
    print(f"  [OK] File size: {file_size_gb:.2f} GB")
    print(f"  [OK] Location: {output_path.absolute()}")
    print(f"  [OK] Project is now self-contained!")
    
    print(f"\n" + "=" * 60)
    print(f"[SUCCESS] File is now in project folder")
    print(f"  You can now run: python scripts/process_fnspid.py")
    print(f"=" * 60)
    
except Exception as e:
    print(f"  [ERROR] Failed to move file: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
