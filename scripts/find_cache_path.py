"""
Find the cached FNSPID file path
Useful when the file is too large to copy
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from huggingface_hub import scan_cache_dir
except ImportError:
    print("ERROR: huggingface_hub not installed")
    print("  pip install huggingface_hub")
    sys.exit(1)

print("=" * 60)
print("Finding Cached FNSPID File")
print("=" * 60)

try:
    cache_info = scan_cache_dir()
    
    found = False
    for repo in cache_info.repos:
        if "FNSPID" in repo.repo_id:
            print(f"\n[OK] Found FNSPID repository: {repo.repo_id}")
            for revision in repo.revisions:
                for file in revision.files:
                    if "nasdaq_exteral_data.csv" in file.file_name:
                        file_size_gb = file.size_on_disk / (1024**3)
                        print(f"\n[SUCCESS] Found cached file!")
                        print(f"  Path: {file.file_path}")
                        print(f"  Size: {file_size_gb:.2f} GB")
                        print(f"\n  You can use this path directly in process_fnspid.py")
                        print(f"  Or the script will auto-detect it from cache_info file")
                        found = True
                        break
                if found:
                    break
            if found:
                break
    
    if not found:
        print("\n[WARNING] Cached file not found")
        print("  Run download_fnspid.py first to download the file")
        
except Exception as e:
    print(f"\n[ERROR] Failed to scan cache: {e}")
    import traceback
    traceback.print_exc()
