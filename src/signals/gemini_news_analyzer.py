"""
Gemini 2.5 Flash Lite News Analyzer
Analyzes news articles using Gemini 2.5 Flash Lite (Paid Tier) with caching and batching
Returns None if no news found (no fallback/dummy values)
"""
import os
import json
import time
import warnings
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path
import logging

# Suppress deprecation warning for google.generativeai BEFORE importing gemini_analyzer
warnings.filterwarnings("ignore", category=FutureWarning, message=".*google.generativeai.*")

from src.signals.gemini_analyzer import GeminiAnalyzer

logger = logging.getLogger(__name__)

# Ensure proxy is disabled for Gemini API calls
# (gemini_analyzer.py handles this, but we ensure it here too for safety)
_proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
for var in _proxy_vars:
    os.environ.pop(var, None)


class JSONCache:
    """Cache for Gemini API responses to save tokens/cost"""
    
    def __init__(self, cache_dir: str = "data/cache"):
        """
        Initialize JSON cache
        
        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cache_path(self, ticker: str, date: str) -> Path:
        """
        Get cache file path for a ticker and date
        
        Args:
            ticker: Stock ticker symbol
            date: Date string (YYYY-MM-DD)
        
        Returns:
            Path to cache file
        """
        return self.cache_dir / f"gemini_{ticker}_{date}.json"
    
    def load(self, ticker: str, date: str) -> Optional[Dict]:
        """
        Load cached result if exists
        
        Args:
            ticker: Stock ticker symbol
            date: Date string (YYYY-MM-DD)
        
        Returns:
            Cached result dict or None if not found
        """
        cache_path = self.get_cache_path(ticker, date)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading cache for {ticker} on {date}: {e}")
        return None
    
    def save(self, ticker: str, date: str, result: Dict):
        """
        Save result to cache
        
        Args:
            ticker: Stock ticker symbol
            date: Date string (YYYY-MM-DD)
            result: Result dict to cache
        """
        cache_path = self.get_cache_path(ticker, date)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            logger.debug(f"Cached result for {ticker} on {date}")
        except Exception as e:
            logger.warning(f"Error saving cache for {ticker} on {date}: {e}")


class GeminiNewsAnalyzer:
    """
    Analyzes news articles using Gemini 2.5 Flash Lite (Paid Tier)
    Batches articles (up to 3 per API call) and uses caching to save API costs
    Returns None if no news found (no fallback values)
    """
    
    def __init__(
        self,
        news_dir: str = "data/news",
        cache_dir: str = "data/cache",
        lookback_days: int = 7,
        min_articles: int = 1,
        rate_limit_seconds: float = 0.5,
        batch_size: int = 3
    ):
        """
        Initialize Gemini News Analyzer
        
        Args:
            news_dir: Directory containing {ticker}_news.json files
            cache_dir: Directory for caching Gemini responses
            lookback_days: Number of days to look back for news analysis
            min_articles: Minimum number of articles required for analysis
            rate_limit_seconds: Delay between API calls (default 0.5s for ~300 RPM paid tier)
            batch_size: Maximum number of articles to process per API call (default 3)
        """
        self.news_dir = Path(news_dir)
        self.lookback_days = lookback_days
        self.min_articles = min_articles
        self.rate_limit_seconds = rate_limit_seconds
        self.batch_size = batch_size
        
        # Initialize cache
        self.cache = JSONCache(cache_dir)
        
        # Initialize Gemini analyzer with 2.5 Flash Lite
        try:
            self.gemini = GeminiAnalyzer(model="gemini-2.5-flash-lite")
            logger.info("GeminiNewsAnalyzer initialized with Gemini 2.5 Flash Lite (Paid Tier)")
        except Exception as e:
            logger.error(f"Gemini not available: {e}. News analysis will return None.")
            self.gemini = None
    
    def load_articles_for_ticker(self, ticker: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Load news articles for a ticker from JSON file
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            List of article dictionaries
        """
        # Try main news file first
        news_file = self.news_dir / f"{ticker}_news.json"
        
        # Also try monthly files (AMD_2023_01.json format)
        monthly_files = []
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Generate monthly file names for the date range
        current = start_dt.replace(day=1)
        while current <= end_dt:
            monthly_file = self.news_dir / f"{ticker}_{current.year}_{current.month:02d}.json"
            if monthly_file.exists():
                monthly_files.append(monthly_file)
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        
        all_articles = []
        
        # Load from main file if exists
        if news_file.exists():
            try:
                with open(news_file, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                    if isinstance(articles, list):
                        all_articles.extend(articles)
                        # Debug: Show first article structure
                        if len(articles) > 0:
                            print(f"[DEBUG] Loaded {len(articles)} articles from {news_file}", flush=True)
                            print(f"[DEBUG] First article keys: {list(articles[0].keys())}", flush=True)
                            first_article = articles[0]
                            print(f"[DEBUG] First article title: '{first_article.get('title', '')[:100]}'", flush=True)
                            print(f"[DEBUG] First article description: '{first_article.get('description', '')[:100]}'", flush=True)
                            print(f"[DEBUG] First article content: '{first_article.get('content', '')[:100]}'", flush=True)
                    elif isinstance(articles, dict) and 'articles' in articles:
                        all_articles.extend(articles['articles'])
            except Exception as e:
                logger.debug(f"Error loading main news file for {ticker}: {e}")
        
        # Load from monthly files
        for monthly_file in monthly_files:
            try:
                with open(monthly_file, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                    if isinstance(articles, list):
                        all_articles.extend(articles)
                    elif isinstance(articles, dict) and 'articles' in articles:
                        all_articles.extend(articles['articles'])
            except Exception as e:
                logger.debug(f"Error loading monthly file {monthly_file}: {e}")
        
        if not all_articles:
            logger.debug(f"No news articles found for {ticker} (checked {news_file} and {len(monthly_files)} monthly files)")
            return []
        
        # Filter by date range
        filtered = []
        for article in all_articles:
            published_at = article.get('publishedAt', '') or article.get('published_utc', '') or article.get('date', '')
            if not published_at:
                continue
            
            try:
                # Parse various date formats
                if isinstance(published_at, str):
                    # Clean up the date string
                    date_str = published_at.strip()
                    
                    # Handle ISO format with timezone (various formats)
                    if 'T' in date_str or 'Z' in date_str or '+' in date_str or (date_str.count(' ') >= 2 and ':' in date_str):
                        # Replace 'Z' with '+00:00' for proper ISO parsing
                        if date_str.endswith('Z'):
                            date_str = date_str.replace('Z', '+00:00')
                        # Parse ISO format (handles both 'T' and space-separated with timezone)
                        article_date = datetime.fromisoformat(date_str)
                    else:
                        # Try YYYY-MM-DD format
                        article_date = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    continue
                
                # Make timezone-naive for comparison
                if article_date.tzinfo:
                    article_date = article_date.replace(tzinfo=None)
                
                if start_dt <= article_date <= end_dt:
                    filtered.append(article)
            except Exception as e:
                logger.debug(f"Error parsing date '{published_at}' for article: {e}")
                print(f"  [DEBUG] Date parse error for '{published_at}': {e}", flush=True)
                continue
        
        logger.debug(f"Loaded {len(filtered)} articles for {ticker} from {start_date} to {end_date} (from {len(all_articles)} total)")
        
        # DEBUG: Post-filter analysis
        print(f"[DEBUG] ===== POST-FILTER ANALYSIS =====", flush=True)
        print(f"[DEBUG] Number of filtered articles: {len(filtered)}", flush=True)
        if len(filtered) > 0:
            print(f"[DEBUG] First article keys: {list(filtered[0].keys())}", flush=True)
            first_article_str = str(filtered[0])[:200]
            print(f"[DEBUG] First article sample: {first_article_str}...", flush=True)
            # Show date info
            pub_date = filtered[0].get('publishedAt', '') or filtered[0].get('published_utc', '') or filtered[0].get('date', '')
            print(f"[DEBUG] First article publishedAt: {pub_date}", flush=True)
        else:
            print(f"[DEBUG] ERROR: No articles after filtering!", flush=True)
            print(f"[DEBUG] Total articles loaded: {len(all_articles)}", flush=True)
            if len(all_articles) > 0:
                print(f"[DEBUG] Sample article from all_articles: {str(all_articles[0])[:200]}...", flush=True)
                sample_pub = all_articles[0].get('publishedAt', '') or all_articles[0].get('published_utc', '') or all_articles[0].get('date', '')
                print(f"[DEBUG] Sample article publishedAt: {sample_pub}", flush=True)
                print(f"[DEBUG] Date range requested: {start_date} to {end_date}", flush=True)
        
        return filtered
    
    def _create_supply_chain_prompt(self, ticker: str, articles: List[Dict], date: str) -> str:
        """
        Create supply chain analysis prompt for Gemini 2.5 Flash Lite
        Processes up to batch_size articles per call to optimize token usage
        
        Args:
            ticker: Stock ticker symbol
            articles: List of article dictionaries (should be <= batch_size)
            date: Analysis date (YYYY-MM-DD)
        
        Returns:
            Formatted prompt string
        """
        # Combine article texts (limited to batch_size)
        article_texts = []
        for article in articles[:self.batch_size]:
            title = article.get('title', '')
            description = article.get('description', '')
            content = article.get('content', '') or description
            # Use full content
            article_text = f"Title: {title}\nDescription: {description}\nContent: {content}"
            article_texts.append(article_text)
        
        combined_text = "\n\n---\n\n".join(article_texts)
        
        # Truncate if extremely long (conservative limit for token optimization)
        max_chars = 100000  # Reduced for token efficiency
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars] + "..."
            logger.warning(f"Truncated article text for {ticker} (exceeded {max_chars} chars)")
        
        prompt = f"""You are a Supply Chain Quant. For {ticker} on {date}, analyze these articles:

{combined_text}

Extract:
1. Relationship: Supplier/Buyer/Neutral (role of {ticker} in supply chain)
2. Supply Chain Health Score: -1.0 to 1.0 (negative = supply chain disruption, positive = healthy/growing)
3. Sentiment Score: -1.0 to 1.0 (negative = bad news, positive = good news, 0 = neutral)
4. Reasoning: max 15 words explaining the scores

IMPORTANT: Supply Chain Sentiment is Asymmetric:
- For Suppliers (e.g., TSMC): Positive news about raising prices = Neutral for buyers (e.g., Apple)
- For Buyers: Positive news about supplier partnerships = Positive
- Consider the role of {ticker} when scoring

Return ONLY valid JSON with these 4 fields:
{{
  "relationship": "Supplier" | "Buyer" | "Neutral",
  "supply_chain_health_score": -1.0 to 1.0,
  "sentiment_score": -1.0 to 1.0,
  "reasoning": "max 15 words"
}}

Return ONLY the JSON object, nothing else."""
        
        return prompt
    
    def analyze_news_for_ticker(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> Optional[Dict]:
        """
        Analyze news articles for a ticker and extract supply chain signals
        Uses caching to avoid redundant API calls
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with keys: supply_chain_score, sentiment_score, confidence, relationship, reasoning
            Returns None if no articles found or Gemini unavailable (NO FALLBACK VALUES)
        """
        # Load articles
        articles = self.load_articles_for_ticker(ticker, start_date, end_date)
        
        # DEBUG: Detailed logging
        print(f"\n[NEWS DEBUG] {ticker} analyzing {start_date} to {end_date}", flush=True)
        news_file = self.news_dir / f"{ticker}_news.json"
        print(f"  [DEBUG] Checking file: {news_file}", flush=True)
        print(f"  [DEBUG] File exists: {news_file.exists()}", flush=True)
        
        if news_file.exists():
            try:
                with open(news_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                if isinstance(file_data, list):
                    total_articles = len(file_data)
                elif isinstance(file_data, dict) and 'articles' in file_data:
                    total_articles = len(file_data['articles'])
                else:
                    total_articles = 0
                print(f"  [DEBUG] Total articles in file: {total_articles}", flush=True)
                
                # Show date range
                if file_data:
                    all_dates = []
                    articles_list = file_data if isinstance(file_data, list) else file_data.get('articles', [])
                    for art in articles_list[:10]:  # Check first 10
                        pub = art.get('publishedAt', '') or art.get('published_utc', '') or art.get('date', '')
                        if pub:
                            all_dates.append(pub)
                    if all_dates:
                        print(f"  [DEBUG] Sample article dates: {all_dates[:5]}", flush=True)
            except Exception as e:
                print(f"  [DEBUG] Error reading file: {e}", flush=True)
        
        logger.debug(f"Loading news for {ticker} from {start_date} to {end_date}: found {len(articles)} articles")
        print(f"  [DEBUG] Articles in range {start_date} to {end_date}: {len(articles)}", flush=True)
        
        # Return None if insufficient articles (NO FALLBACK)
        if len(articles) < self.min_articles:
            logger.debug(f"Insufficient articles for {ticker}: {len(articles)} < {self.min_articles}")
            print(f"  [WARNING] Insufficient articles: {len(articles)} < {self.min_articles}", flush=True)
            if len(articles) == 0:
                print(f"  [WARNING] No articles match the date range!", flush=True)
            print(f"[DEBUG] RETURNING: None (type: {type(None)}) - insufficient articles", flush=True)
            return None
        
        # Return None if Gemini not available (NO FALLBACK)
        if self.gemini is None:
            logger.warning(f"Gemini not available for {ticker}, returning None")
            print(f"[DEBUG] RETURNING: None (type: {type(None)}) - Gemini not available", flush=True)
            return None
        
        # Check cache first (use end_date as the analysis date)
        cached_result = self.cache.load(ticker, end_date)
        if cached_result is not None:
            logger.debug(f"Using cached result for {ticker} on {end_date}")
            print(f"[DEBUG] RETURNING: {cached_result} (type: {type(cached_result)}) - from cache", flush=True)
            return cached_result
        
        # Analyze with Gemini 2.5 Flash Lite
        # Batch articles into groups of batch_size to optimize token usage
        try:
            import google.generativeai as genai
            
            # Split articles into batches of batch_size
            article_batches = [articles[i:i + self.batch_size] for i in range(0, len(articles), self.batch_size)]
            
            logger.info(f"Calling Gemini API for {ticker} on {end_date} with {len(articles)} articles in {len(article_batches)} batch(es)...")
            
            # Process each batch and aggregate results
            all_results = []
            for batch_idx, batch_articles in enumerate(article_batches):
                prompt = self._create_supply_chain_prompt(ticker, batch_articles, end_date)
                
                logger.debug(f"Processing batch {batch_idx + 1}/{len(article_batches)} with {len(batch_articles)} articles")
                print(f"[DEBUG] About to call LLM API with {len(batch_articles)} articles in batch {batch_idx + 1}/{len(article_batches)}", flush=True)
                
                try:
                    # Use Gemini's JSON mode
                    response = self.gemini.model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.3,
                            top_p=0.8,
                            top_k=40,
                            max_output_tokens=500,
                            response_mime_type="application/json"
                        )
                    )
                    
                    print(f"[DEBUG] LLM API returned successfully", flush=True)
                    print(f"[DEBUG] Response type: {type(response)}", flush=True)
                    
                    # Parse JSON response
                    response_text = response.text.strip()
                    print(f"[DEBUG] Response preview: {str(response_text)[:200]}...", flush=True)
                    
                    # Remove markdown code blocks if present
                    if response_text.startswith("```json"):
                        response_text = response_text[7:]
                    if response_text.startswith("```"):
                        response_text = response_text[3:]
                    if response_text.endswith("```"):
                        response_text = response_text[:-3]
                    response_text = response_text.strip()
                    
                    result = json.loads(response_text)
                    print(f"[DEBUG] Parsed JSON result: {result}", flush=True)
                    
                    # Handle list responses - LLM sometimes returns a list instead of single dict
                    if isinstance(result, list):
                        print(f"[DEBUG] LLM returned list with {len(result)} items, combining...", flush=True)
                        if len(result) == 0:
                            print(f"[WARNING] Empty list returned, skipping batch", flush=True)
                            continue
                        
                        # Average the supply chain health scores
                        health_scores = [r.get('supply_chain_health_score', 0) for r in result if isinstance(r, dict)]
                        if health_scores:
                            avg_health_score = sum(health_scores) / len(health_scores)
                        else:
                            avg_health_score = 0.0
                        
                        # Average the sentiment scores separately
                        sentiment_scores = [r.get('sentiment_score', 0) for r in result if isinstance(r, dict)]
                        if sentiment_scores:
                            avg_sentiment_score = sum(sentiment_scores) / len(sentiment_scores)
                        else:
                            avg_sentiment_score = 0.0
                        
                        # Get most common relationship (or first if all same)
                        relationships = [r.get('relationship', 'Neutral') for r in result if isinstance(r, dict)]
                        most_common_relationship = max(set(relationships), key=relationships.count) if relationships else 'Neutral'
                        
                        # Combine reasoning
                        reasonings = [r.get('reasoning', '') for r in result if isinstance(r, dict) and r.get('reasoning')]
                        combined_reasoning = ' | '.join(reasonings) if reasonings else 'Combined analysis from multiple items'
                        
                        # Combine into single result
                        result = {
                            'relationship': most_common_relationship,
                            'supply_chain_health_score': avg_health_score,
                            'sentiment_score': avg_sentiment_score,
                            'reasoning': combined_reasoning
                        }
                        print(f"[DEBUG] Combined list into: health={avg_health_score:.2f}, sentiment={avg_sentiment_score:.2f}, relationship={most_common_relationship}", flush=True)
                    
                    all_results.append(result)
                    
                    # Rate limiting: wait before next API call (0.5s for ~300 RPM paid tier)
                    if batch_idx < len(article_batches) - 1:  # Don't wait after last batch
                        time.sleep(self.rate_limit_seconds)
                except Exception as e:
                    print(f"[DEBUG] LLM API FAILED: {type(e).__name__}: {str(e)}", flush=True)
                    import traceback
                    print(f"[DEBUG] Full traceback:", flush=True)
                    traceback.print_exc()
                    # Re-raise to stop immediately
                    raise
            
            # Aggregate results from all batches (average the scores)
            if len(all_results) == 1:
                result = all_results[0]
            else:
                # Average health scores and sentiment scores separately
                avg_health_score = sum(r.get('supply_chain_health_score', 0.0) for r in all_results) / len(all_results)
                avg_sentiment_score = sum(r.get('sentiment_score', 0.0) for r in all_results) / len(all_results)
                relationships = [r.get('relationship', 'Neutral') for r in all_results]
                most_common_relationship = max(set(relationships), key=relationships.count)
                reasoning_parts = [r.get('reasoning', '') for r in all_results if r.get('reasoning')]
                combined_reasoning = '; '.join(reasoning_parts[:2])  # Combine first 2 reasonings
                
                result = {
                    'supply_chain_health_score': avg_health_score,
                    'sentiment_score': avg_sentiment_score,
                    'relationship': most_common_relationship,
                    'reasoning': combined_reasoning[:100]  # Limit length
                }
            
            # Map to our format (backward compatible with existing signal combiner)
            scores = {
                'supply_chain_score': float(result.get('supply_chain_health_score', 0.0)),
                'sentiment_score': float(result.get('sentiment_score', 0.0)),  # Parse actual sentiment from LLM
                'confidence': 1.0,  # High confidence if Gemini returned result
                'relationship': result.get('relationship', 'Neutral'),
                'reasoning': result.get('reasoning', '')
            }
            
            # Validate scores are in range
            scores['supply_chain_score'] = max(-1.0, min(1.0, scores['supply_chain_score']))
            scores['sentiment_score'] = max(-1.0, min(1.0, scores['sentiment_score']))
            
            # Cache the result
            self.cache.save(ticker, end_date, scores)
            
            logger.info(f"Gemini returned for {ticker}: health={scores['supply_chain_score']:.3f}, sentiment={scores['sentiment_score']:.3f}, relationship={scores['relationship']}, reasoning={scores['reasoning']}")
            
            print(f"[DEBUG] RETURNING: {scores} (type: {type(scores)})", flush=True)
            return scores
        
        except Exception as e:
            logger.error(f"Error analyzing news for {ticker}: {e}")
            print(f"[DEBUG] RETURNING: None (type: {type(None)}) due to error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            # Return None on error (NO FALLBACK)
            return None
