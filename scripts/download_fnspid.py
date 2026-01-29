"""
Download FNSPID Dataset from Hugging Face
Downloads NASDAQ news data for financial news analysis

Requires Hugging Face token for authentication:
1. Get token from: https://huggingface.co/settings/tokens
2. Create a "Read" token
3. Set environment variable: export HF_TOKEN=your_token_here
   Or pass as argument: --token your_token_here
"""
import os
import sys
from pathlib import Path
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, continue without it
    pass

try:
    from huggingface_hub import hf_hub_download, login
except ImportError:
    print("ERROR: huggingface_hub not installed. Install with:")
    print("  pip install huggingface_hub pandas pyarrow")
    sys.exit(1)


def download_fnspid_dataset(
    output_path: str = "data/raw/fnspid_nasdaq_news.csv",
    hf_token: str = None,
    use_cache: bool = False
):
    """
    Download NASDAQ news data from FNSPID dataset on Hugging Face
    
    Args:
        output_path: Path to save the downloaded CSV file (in project folder)
        hf_token: Hugging Face token (if None, reads from HF_TOKEN env var or prompts)
        use_cache: If True, use Hugging Face cache location (saves space but not self-contained)
                   If False, download directly to project folder (self-contained, default)
    """
    print("=" * 60)
    print("FNSPID Dataset Download")
    print("=" * 60)
    
    # Create output directory
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Hugging Face repository and file
    repo_id = "Zihan1004/FNSPID"
    filename = "Stock_news/nasdaq_exteral_data.csv"
    
    print(f"\n[1/4] Authenticating with Hugging Face...")
    
    # Get token from environment or parameter
    if not hf_token:
        hf_token = os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_HUB_TOKEN')
    
    # Authenticate if token provided
    if hf_token:
        try:
            login(token=hf_token)
            print(f"  [OK] Authenticated with Hugging Face token")
        except Exception as e:
            print(f"  [WARNING] Authentication failed: {e}")
            print(f"  [INFO] Continuing without authentication (may fail if repo is private)")
    else:
        print(f"  [INFO] No Hugging Face token found")
        print(f"  [INFO] Set HF_TOKEN environment variable or provide --token argument")
        print(f"  [INFO] Get token from: https://huggingface.co/settings/tokens")
        print(f"  [INFO] Continuing without authentication (may fail if repo is private)")
    
    print(f"\n[2/4] Downloading from Hugging Face...")
    print(f"  Repository: {repo_id}")
    print(f"  File: {filename}")
    print(f"  Output: {output_path}")
    
    if use_cache:
        print(f"  [INFO] Using Hugging Face cache (saves disk space, not self-contained)")
    else:
        print(f"  [INFO] Downloading directly to project folder (self-contained)")
        print(f"  [INFO] This makes the project portable - all data in one place")
        print(f"  [INFO] Project folder: {output_path.parent.absolute()}")
    
    try:
        if use_cache:
            # Download to cache (saves space but not self-contained)
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                repo_type="dataset",
                force_download=False
            )
            print(f"  [OK] Downloaded to cache: {downloaded_path}")
            
            # Create marker file for processing script
            cache_info_file = output_path.parent / f"{output_path.stem}_cache_path.txt"
            with open(cache_info_file, 'w') as f:
                f.write(str(downloaded_path))
            print(f"  [OK] Cache path saved to: {cache_info_file}")
            print(f"  [INFO] Processing script will read from cache")
        else:
            # Download directly to project folder (self-contained)
            print(f"  [INFO] Downloading to: {output_path.parent}")
            
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                repo_type="dataset",
                local_dir=str(output_path.parent),  # Download directly to project folder
                local_dir_use_symlinks=False,  # Use actual files, not symlinks
                force_download=False
            )
        
            print(f"  [OK] Downloaded to: {downloaded_path}")
            
            # The file is downloaded to a subdirectory matching the filename path
            # Check if it's in the expected location or a subdirectory
            expected_path = output_path.parent / "Stock_news" / "nasdaq_exteral_data.csv"
            
            if Path(downloaded_path) == output_path or Path(downloaded_path) == expected_path:
                # File is in the right place
                if Path(downloaded_path) != output_path:
                    # Move from subdirectory to exact output path
                    print(f"\n[3/4] Moving to final location...")
                    import shutil
                    if output_path.exists():
                        output_path.unlink()
                    shutil.move(str(downloaded_path), str(output_path))
                    # Clean up empty subdirectory if created
                    try:
                        (output_path.parent / "Stock_news").rmdir()
                    except:
                        pass
                else:
                    print(f"\n[3/4] File already in correct location")
            else:
                # File downloaded to unexpected location, move it
                print(f"\n[3/4] Moving file to project folder...")
                import shutil
                if output_path.exists():
                    output_path.unlink()
                shutil.move(str(downloaded_path), str(output_path))
                print(f"  [OK] Moved to: {output_path}")
            
            file_size_gb = output_path.stat().st_size / (1024**3)
            print(f"  [OK] File size: {file_size_gb:.1f} GB")
            print(f"  [OK] File is now in project folder (self-contained)")
        
    except OSError as e:
        if "not enough space" in str(e).lower():
            file_size_gb = 23.2  # Approximate size
            print(f"  [ERROR] Not enough disk space to download to project folder")
            print(f"  [INFO] File requires ~{file_size_gb:.1f} GB free space")
            print(f"  [INFO] Options:")
            print(f"    1. Free up disk space")
            print(f"    2. Use --use-cache flag to use Hugging Face cache instead")
            print(f"       python scripts/download_fnspid.py --use-cache")
            sys.exit(1)
        else:
            raise
        
    except Exception as e:
        print(f"  [ERROR] Download failed: {e}")
        print(f"\nTroubleshooting:")
        print(f"  1. **AUTHENTICATION REQUIRED:** Get a Hugging Face token:")
        print(f"     - Visit: https://huggingface.co/settings/tokens")
        print(f"     - Create a 'Read' token (free)")
        print(f"     - Set environment variable: export HF_TOKEN=your_token_here")
        print(f"     - Or pass as argument: --token your_token_here")
        print(f"  2. Check internet connection")
        print(f"  3. Verify Hugging Face repository exists: https://huggingface.co/datasets/{repo_id}")
        print(f"  4. Try manual download from Hugging Face website")
        sys.exit(1)
    
    # Verify the download
    print(f"\n[4/4] Verifying download...")
    try:
        # Check file exists and has size
        if not output_path.exists():
            print(f"  [ERROR] File not found at: {output_path}")
            sys.exit(1)
        
        file_size_gb = output_path.stat().st_size / (1024**3)
        print(f"  [OK] File exists: {output_path}")
        print(f"  [OK] File size: {file_size_gb:.2f} GB")
        
        # Read first few rows to check format
        print(f"  [INFO] Reading sample rows to verify format...")
        df_sample = pd.read_csv(output_path, nrows=10)
        
        print(f"  [OK] File is valid CSV")
        print(f"\n  Columns ({len(df_sample.columns)}):")
        for col in df_sample.columns:
            dtype = df_sample[col].dtype
            print(f"    - {col}: {dtype}")
        
        print(f"\n  Sample rows (first 5):")
        print(df_sample.head().to_string())
        
        # Check file size
        file_size = output_path.stat().st_size / (1024 * 1024)  # MB
        print(f"\n  File size: {file_size:.2f} MB")
        
        # Count total rows (this may take a while for large files)
        print(f"\n  Counting total rows (this may take a moment)...")
        total_rows = sum(1 for _ in open(output_path)) - 1  # Subtract header
        print(f"  Total articles: {total_rows:,}")
        
        # Check date range if 'date' column exists
        if 'date' in df_sample.columns:
            print(f"\n  Checking date range...")
            df_dates = pd.read_csv(
                output_path,
                usecols=['date'],
                parse_dates=['date'],
                nrows=10000  # Sample for speed
            )
            if not df_dates.empty:
                print(f"    Sample date range: {df_dates['date'].min()} to {df_dates['date'].max()}")
        
        print(f"\n" + "=" * 60)
        print(f"[SUCCESS] Download complete!")
        print(f"  File: {output_path}")
        print(f"  Total articles: {total_rows:,}")
        print(f"=" * 60)
        
    except Exception as e:
        print(f"  [ERROR] Verification failed: {e}")
        print(f"  File may be corrupted. Try downloading again.")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Download FNSPID dataset from Hugging Face')
    parser.add_argument(
        '--output',
        type=str,
        default='data/raw/fnspid_nasdaq_news.csv',
        help='Output path for downloaded CSV file (default: data/raw/fnspid_nasdaq_news.csv)'
    )
    parser.add_argument(
        '--token',
        type=str,
        default=None,
        help='Hugging Face token (or set HF_TOKEN environment variable)'
    )
    parser.add_argument(
        '--use-cache',
        action='store_true',
        help='Use Hugging Face cache location (saves disk space but not self-contained)'
    )
    
    args = parser.parse_args()
    
    download_fnspid_dataset(args.output, args.token, args.use_cache)
