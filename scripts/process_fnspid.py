"""
Process FNSPID Dataset
Filters news articles by keywords and converts to our JSON format
"""
import pandas as pd
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.universe_loader import UniverseLoader


def load_universe_tickers() -> set:
    """Load ticker symbols from our universe"""
    print("\n[1/6] Loading universe tickers...")
    try:
        loader = UniverseLoader()
        ticker_metadata = loader.load_universe(max_tickers=1000)  # Get all available
        tickers = {t['ticker'].upper() for t in ticker_metadata}
        print(f"  [OK] Loaded {len(tickers)} tickers from universe")
        return tickers
    except Exception as e:
        print(f"  [WARNING] Could not load universe: {e}")
        print(f"  [WARNING] Will process all tickers in news data")
        return set()


def filter_by_keywords(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter articles by supply chain keywords
    
    Args:
        df: DataFrame with news articles
        
    Returns:
        Filtered DataFrame
    """
    print("\n[2/6] Filtering by keywords...")
    
    # Supply chain keywords (case-insensitive)
    keywords = [
        'supply', 'supplier', 'contract', 'partnership', 'partner',
        'datacenter', 'data center', 'AI', 'artificial intelligence',
        'chip', 'semiconductor', 'GPU', 'CPU', 'processor',
        'manufacturing', 'order', 'hyperscaler', 'cloud',
        'AWS', 'Azure', 'GCP', 'Microsoft', 'Google', 'Amazon',
        'NVIDIA', 'AMD', 'Intel', 'TSMC', 'Taiwan Semiconductor',
        'OpenAI', 'Anthropic', 'datacenter', 'server', 'infrastructure',
        'supply chain', 'logistics', 'procurement', 'vendor'
    ]
    
    # Create regex pattern
    pattern = '|'.join(keywords)
    
    # Filter by headline (case-insensitive)
    if 'headline' in df.columns:
        mask = df['headline'].str.contains(pattern, case=False, na=False, regex=True)
        filtered = df[mask].copy()
        print(f"  Articles before filtering: {len(df):,}")
        print(f"  Articles after filtering: {len(filtered):,}")
        print(f"  Reduction: {(1 - len(filtered)/len(df))*100:.1f}%")
    else:
        print(f"  [WARNING] 'headline' column not found. Available columns: {df.columns.tolist()}")
        print(f"  [WARNING] Skipping keyword filtering")
        filtered = df.copy()
    
    return filtered


def extract_ticker_from_article(article: Dict, df: pd.DataFrame) -> str:
    """
    Extract ticker symbol from article
    
    Tries multiple methods:
    1. 'ticker' column
    2. 'symbol' column
    3. Extract from 'headline' or other text fields
    """
    # Try direct ticker columns (case-insensitive)
    article_lower = {k.lower(): v for k, v in article.items()}
    for col in ['ticker', 'symbol', 'stock', 'stock_symbol', 'ticker_symbol']:
        if col in article_lower and pd.notna(article_lower[col]):
            ticker = str(article_lower[col]).upper().strip()
            # Clean up ticker (remove extra spaces, special chars)
            ticker = ''.join(c for c in ticker if c.isalnum())
            if ticker and 1 <= len(ticker) <= 10:  # Reasonable ticker length
                return ticker
    
    # Try extracting from headline (look for patterns like "NVDA", "(NVDA)", etc.)
    headline_cols = ['headline', 'title', 'headline_text']
    for col in headline_cols:
        if col in article and pd.notna(article[col]):
            headline = str(article[col])
            # Look for ticker in parentheses: (NVDA), [NVDA], etc.
            import re
            patterns = [
                r'\(([A-Z]{1,5})\)',  # (NVDA)
                r'\[([A-Z]{1,5})\]',  # [NVDA]
                r'\b([A-Z]{2,5})\b',  # Standalone uppercase (2-5 chars)
            ]
            for pattern in patterns:
                matches = re.findall(pattern, headline)
                if matches:
                    ticker = matches[0].upper().strip()
                    if 2 <= len(ticker) <= 5:
                        return ticker
    
    return None


def convert_to_our_format(article: Dict) -> Dict:
    """
    Convert FNSPID article format to our format
    
    Our format:
    {
        "title": "...",
        "description": "...",
        "content": "...",
        "publishedAt": "2023-06-15T10:00:00Z"
    }
    
    FNSPID CSV columns:
    - Article_title -> title
    - Article -> content
    - Lsa_summary or Luhn_summary -> description
    - Date -> publishedAt
    """
    # Map column names (case-insensitive)
    article_lower = {k.lower(): v for k, v in article.items()}
    
    # Title mapping - FNSPID uses 'Article_title'
    title = (
        article.get('Article_title') or article.get('article_title') or
        article.get('headline') or article.get('title') or article.get('headline_text') or
        article_lower.get('article_title') or article_lower.get('headline') or 
        article_lower.get('title') or ''
    )
    
    # Description mapping - FNSPID has summary fields (Lsa_summary, Luhn_summary, etc.)
    description = (
        article.get('Lsa_summary') or article.get('Luhn_summary') or 
        article.get('Textrank_summary') or article.get('Lexrank_summary') or
        article.get('summary') or article.get('description') or article.get('abstract') or
        article_lower.get('lsa_summary') or article_lower.get('luhn_summary') or
        article_lower.get('textrank_summary') or article_lower.get('lexrank_summary') or
        article_lower.get('summary') or article_lower.get('description') or 
        article_lower.get('abstract') or ''
    )
    
    # Content mapping - FNSPID uses 'Article' for full content
    content = (
        article.get('Article') or article.get('article') or
        article.get('content') or article.get('text') or article.get('body') or
        article_lower.get('article') or article_lower.get('content') or 
        article_lower.get('text') or article_lower.get('body') or
        description  # Fallback to description if no content
    )
    
    # Date parsing - FNSPID uses 'Date'
    date_str = None
    date_cols = ['Date', 'date', 'publishedAt', 'published_at', 'publish_date', 'timestamp', 'time']
    for date_col in date_cols:
        if date_col in article and pd.notna(article[date_col]):
            date_str = str(article[date_col])
            break
        elif date_col in article_lower and pd.notna(article_lower[date_col]):
            date_str = str(article_lower[date_col])
            break
    
    # Parse and format date - FNSPID format: '2023-12-16 23:00:00 UTC'
    if date_str:
        try:
            # Remove 'UTC' suffix if present
            date_str = date_str.replace(' UTC', '').strip()
            # Try various date formats (including FNSPID format)
            for fmt in [
                '%Y-%m-%d %H:%M:%S',  # FNSPID format: '2023-12-16 23:00:00'
                '%Y-%m-%d', 
                '%Y-%m-%dT%H:%M:%S', 
                '%Y-%m-%dT%H:%M:%SZ'
            ]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    # Format as ISO with timezone (space-separated format for compatibility)
                    date_str = dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
                    break
                except ValueError:
                    continue
        except Exception:
            # If parsing fails, try pandas (handles many formats)
            try:
                dt = pd.to_datetime(date_str)
                # Format as space-separated ISO with timezone
                date_str = dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
            except Exception:
                date_str = None
    
    # Convert to strings, handling NaN/None
    title_str = str(title).strip() if title and pd.notna(title) else ''
    description_str = str(description).strip() if description and pd.notna(description) else ''
    content_str = str(content).strip() if content and pd.notna(content) else ''
    
    return {
        'title': title_str,
        'description': description_str,
        'content': content_str,
        'publishedAt': date_str or ''
    }


def process_fnspid(
    input_path: str,
    output_dir: str = "data/news",
    date_start: str = "2020-01-01",
    date_end: str = "2022-12-31",
    filter_universe: bool = True
):
    """
    Process FNSPID dataset and convert to our JSON format
    
    Args:
        input_path: Path to FNSPID CSV file
        output_dir: Directory to save JSON files
        date_start: Start date filter (YYYY-MM-DD)
        date_end: End date filter (YYYY-MM-DD)
        filter_universe: Only process tickers in our universe
    """
    print("=" * 60)
    print("FNSPID Dataset Processing")
    print("=" * 60)
    
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Checkpoint file for progress tracking
    checkpoint_file = output_dir / ".process_checkpoint.json"
    
    # Check if input file exists
    # Also check for cache path file (backward compatibility for old downloads)
    cache_info_file = input_path.parent / f"{input_path.stem}_cache_path.txt"
    actual_input_path = input_path
    
    # First check if file exists in project folder (preferred - self-contained)
    if input_path.exists():
        file_size_gb = input_path.stat().st_size / (1024**3)
        print(f"  [OK] Found file in project folder: {input_path}")
        print(f"  [OK] File size: {file_size_gb:.1f} GB (self-contained)")
        actual_input_path = input_path
    elif cache_info_file.exists():
        # Fallback: check for cache path file (for old downloads that used cache)
        print(f"  [INFO] File not in project folder, checking cache info file...")
        with open(cache_info_file, 'r') as f:
            cached_path = f.read().strip()
        if Path(cached_path).exists():
            actual_input_path = Path(cached_path)
            file_size_gb = actual_input_path.stat().st_size / (1024**3)
            print(f"  [OK] Using cached file: {actual_input_path}")
            print(f"  [OK] File size: {file_size_gb:.1f} GB")
        else:
            print(f"  [WARNING] Cache path file exists but cached file not found")
            print(f"  [WARNING] Expected: {cached_path}")
    else:
        # Try to find in Hugging Face cache (last resort)
        print(f"  [INFO] File not found in project folder, searching Hugging Face cache...")
        try:
            from huggingface_hub import scan_cache_dir
            cache_info = scan_cache_dir()
            for repo in cache_info.repos:
                if "FNSPID" in repo.repo_id:
                    for revision in repo.revisions:
                        for file in revision.files:
                            if "nasdaq_exteral_data.csv" in file.file_name:
                                actual_input_path = Path(file.file_path)
                                print(f"  [OK] Found in cache: {actual_input_path}")
                                break
        except:
            pass
    
    # Final check
    if not actual_input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        print(f"  Options:")
        print(f"    1. Run 'python scripts/download_fnspid.py' to download to project folder")
        print(f"    2. Run 'python scripts/find_cache_path.py' to locate cached file")
        sys.exit(1)
    
    # Load universe tickers
    universe_tickers = load_universe_tickers() if filter_universe else None
    
    # Load FNSPID data
    print(f"\n[3/6] Loading FNSPID data from {actual_input_path}...")
    print(f"  [INFO] Using chunked reading to avoid RAM issues (23GB file)")
    print(f"  [INFO] Processing in streaming mode - filtering as we read")
    print(f"  [INFO] This will take 10-15 minutes but won't crash your RAM...")
    
    try:
        # Stream processing: filter by date while reading chunks (don't load all into memory!)
        chunk_size = 50000  # Process 50k rows at a time
        filtered_chunks = []
        total_rows = 0
        filtered_rows = 0
        
        # Find date column name (try common variations)
        date_col = None
        sample_chunk = pd.read_csv(actual_input_path, nrows=100, low_memory=False)
        for col in ['date', 'Date', 'publishedAt', 'published_at', 'publish_date', 'timestamp']:
            if col in sample_chunk.columns:
                date_col = col
                break
        
        # Initialize comparison dates (will be adjusted based on actual data timezone)
        date_start_dt = pd.to_datetime(date_start)
        date_end_dt = pd.to_datetime(date_end)
        
        if not date_col:
            print(f"  [WARNING] No date column found. Available: {sample_chunk.columns.tolist()}")
            print(f"  [WARNING] Will process all rows (no date filtering)")
        else:
            # Check if date column has timezone info by parsing a sample
            sample_parsed = pd.to_datetime(sample_chunk[date_col], errors='coerce')
            if len(sample_parsed) > 0 and sample_parsed.dtype.tz is not None:
                # Dates are timezone-aware (likely UTC), make comparison dates UTC-aware too
                if date_start_dt.tz is None:
                    date_start_dt = date_start_dt.tz_localize('UTC')
                if date_end_dt.tz is None:
                    date_end_dt = date_end_dt.tz_localize('UTC')
                print(f"  [INFO] Detected timezone-aware dates (UTC), adjusted comparison dates")
        
        # Stream through file, filtering by date as we go
        print(f"  [INFO] Streaming through file (date column: {date_col or 'N/A'})...")
        print(f"  [INFO] Progress updates every 10 chunks (~500k rows)...")
        print(f"  [INFO] NOTE: When running in your terminal, there is NO timeout - it will complete!")
        
        import time
        start_time = time.time()
        
        for chunk_num, chunk in enumerate(pd.read_csv(actual_input_path, chunksize=chunk_size, low_memory=False), 1):
            total_rows += len(chunk)
            
            # Filter by date if date column exists
            if date_col and date_col in chunk.columns:
                chunk[date_col] = pd.to_datetime(chunk[date_col], errors='coerce')
                chunk_filtered = chunk[(chunk[date_col] >= date_start_dt) & (chunk[date_col] <= date_end_dt)]
                if not chunk_filtered.empty:
                    filtered_chunks.append(chunk_filtered)
                    filtered_rows += len(chunk_filtered)
            else:
                # No date filtering - keep all
                filtered_chunks.append(chunk)
                filtered_rows += len(chunk)
            
            # More frequent progress updates
            if chunk_num % 10 == 0:
                elapsed = time.time() - start_time
                rate = total_rows / elapsed if elapsed > 0 else 0
                print(f"    Chunk {chunk_num}: {total_rows:,} rows processed, {filtered_rows:,} in date range "
                      f"({rate:,.0f} rows/sec, {elapsed/60:.1f} min elapsed)")
        
        print(f"  [OK] Streamed {total_rows:,} total rows")
        print(f"  [OK] Filtered to {filtered_rows:,} rows in date range")
        print(f"  [INFO] Combining filtered chunks...")
        
        # Combine filtered chunks (much smaller now)
        if filtered_chunks:
            df = pd.concat(filtered_chunks, ignore_index=True)
            print(f"  [OK] Combined into DataFrame: {len(df):,} rows")
            
            # Save checkpoint after date filtering
            checkpoint_data = {
                'phase': 'date_filtered',
                'total_rows': total_rows,
                'filtered_rows': len(df),
                'timestamp': datetime.now().isoformat()
            }
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
        else:
            print(f"  [WARNING] No rows found in date range!")
            df = pd.DataFrame()
        
    except MemoryError as e:
        print(f"  [ERROR] Out of memory! {e}")
        print(f"  [INFO] Try reducing chunk_size or processing date range in smaller batches")
        sys.exit(1)
    except Exception as e:
        print(f"  [ERROR] Failed to load CSV: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Date filtering already done during streaming load
    # Just verify we have data
    if df.empty:
        print(f"\n[ERROR] No data found after filtering!")
        print(f"  Check date range: {date_start} to {date_end}")
        print(f"  Check if date column exists in CSV")
        sys.exit(1)
    
    print(f"\n[4/6] Date filtering complete (done during streaming load)")
    print(f"  [OK] {len(df):,} articles in date range {date_start} to {date_end}")
    
    # Filter by keywords
    df_filtered = filter_by_keywords(df)
    
    # Group by ticker
    print(f"\n[5/6] Grouping articles by ticker...")
    ticker_articles: Dict[str, List[Dict]] = {}
    
    for idx, row in df_filtered.iterrows():
        if idx % 10000 == 0 and idx > 0:
            print(f"  Processed {idx:,} articles...")
        
        article = row.to_dict()
        ticker = extract_ticker_from_article(article, df_filtered)
        
        if not ticker:
            continue
        
        # Filter by universe if enabled
        if filter_universe and universe_tickers and ticker not in universe_tickers:
            continue
        
        # Debug: Show raw article keys for first few articles
        if idx < 3:
            print(f"\n[DEBUG] Raw article #{idx} keys: {list(article.keys())}")
            print(f"[DEBUG] Raw article sample fields:")
            print(f"  Article_title: {str(article.get('Article_title', 'N/A'))[:100]}")
            print(f"  Article: {str(article.get('Article', 'N/A'))[:100]}")
            print(f"  Date: {article.get('Date', 'N/A')}")
            print(f"  Lsa_summary: {str(article.get('Lsa_summary', 'N/A'))[:100]}")
        
        # Convert to our format
        formatted_article = convert_to_our_format(article)
        
        # Debug: Show converted article for first few
        if idx < 3:
            print(f"[DEBUG] Converted article:")
            print(f"  title: {formatted_article.get('title', '')[:100]}")
            print(f"  description: {formatted_article.get('description', '')[:100]}")
            print(f"  content: {formatted_article.get('content', '')[:100]}")
            print(f"  publishedAt: {formatted_article.get('publishedAt', '')}")
        
        if ticker not in ticker_articles:
            ticker_articles[ticker] = []
        
        ticker_articles[ticker].append(formatted_article)
    
    print(f"  [OK] Found articles for {len(ticker_articles)} tickers")
    
    # Save to JSON files
    print(f"\n[6/6] Saving to JSON files in {output_dir}...")
    total_articles_saved = 0
    
    for ticker, articles in ticker_articles.items():
        # Sort by date
        articles_sorted = sorted(
            articles,
            key=lambda x: x.get('publishedAt', ''),
            reverse=True
        )
        
        # Save to JSON
        output_file = output_dir / f"{ticker}_news.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(articles_sorted, f, indent=2, ensure_ascii=False)
        
        total_articles_saved += len(articles_sorted)
    
    print(f"  [OK] Saved {total_articles_saved:,} articles to {len(ticker_articles)} JSON files")
    
    # Print statistics
    print("\n" + "=" * 60)
    print("PROCESSING SUMMARY")
    print("=" * 60)
    print(f"Total articles downloaded: {len(df):,}")
    print(f"Articles after keyword filtering: {len(df_filtered):,}")
    print(f"Tickers with news coverage: {len(ticker_articles)}")
    print(f"Total articles saved: {total_articles_saved:,}")
    
    if ticker_articles:
        avg_articles = total_articles_saved / len(ticker_articles)
        print(f"Average articles per ticker: {avg_articles:.1f}")
        
        # Show top tickers by article count
        ticker_counts = {t: len(a) for t, a in ticker_articles.items()}
        top_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        print(f"\nTop 10 tickers by article count:")
        for ticker, count in top_tickers:
            print(f"  {ticker}: {count:,} articles")
    
    # Remove checkpoint file on success (ignore permission errors on Windows)
    if checkpoint_file.exists():
        try:
            checkpoint_file.unlink()
        except (PermissionError, OSError):
            pass
    
    print("=" * 60)
    print("[SUCCESS] Processing complete!")
    print(f"  Output directory: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process FNSPID dataset')
    parser.add_argument(
        '--input',
        type=str,
        default='data/raw/fnspid_nasdaq_news.csv',
        help='Input FNSPID CSV file path'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/news',
        help='Output directory for JSON files (default: data/news)'
    )
    parser.add_argument(
        '--date-start',
        type=str,
        default='2020-01-01',
        help='Start date filter (YYYY-MM-DD, default: 2020-01-01)'
    )
    parser.add_argument(
        '--date-end',
        type=str,
        default='2022-12-31',
        help='End date filter (YYYY-MM-DD, default: 2022-12-31)'
    )
    parser.add_argument(
        '--no-filter-universe',
        action='store_true',
        help='Process all tickers, not just universe tickers'
    )
    
    args = parser.parse_args()
    
    process_fnspid(
        input_path=args.input,
        output_dir=args.output,
        date_start=args.date_start,
        date_end=args.date_end,
        filter_universe=not args.no_filter_universe
    )
