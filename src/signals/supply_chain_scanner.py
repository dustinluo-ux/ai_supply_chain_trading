"""
Supply Chain Scanner
Batch processes news articles through LLM to extract supply chain relationships
Aggregates AI supply chain mentions by ticker
"""
import os
import json
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import logging
from tqdm import tqdm
import time

from src.signals.llm_analyzer import LLMAnalyzer
from src.utils.logger import setup_logger

logger = setup_logger()


class SupplyChainScanner:
    """Scans news articles to identify AI supply chain relationships"""
    
    def __init__(self, llm_provider: str = "finbert", llm_model: str = "ProsusAI/finbert",
                 data_dir: str = "data/news", output_dir: str = "data"):
        self.llm_analyzer = LLMAnalyzer(provider=llm_provider, model=llm_model)
        self.data_dir = data_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"SupplyChainScanner initialized with {llm_provider}")
    
    def load_articles_for_ticker(self, ticker: str) -> List[Dict]:
        """Load cached articles for a ticker"""
        news_path = os.path.join(self.data_dir, f"{ticker}_news.json")
        
        if not os.path.exists(news_path):
            logger.debug(f"No news file found for {ticker}")
            return []
        
        try:
            with open(news_path, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            logger.debug(f"Loaded {len(articles)} articles for {ticker}")
            return articles
        except Exception as e:
            logger.error(f"Error loading articles for {ticker}: {e}")
            return []
    
    def process_article(self, article: Dict) -> Dict:
        """Process a single article through LLM"""
        try:
            extraction = self.llm_analyzer.analyze_article(article)
            
            # FIX 1: Post-processing filter - if no relationships, not AI supply chain
            # This prevents false positives from keyword matching (e.g., "AAL" contains "ai")
            supplier = extraction.get('supplier')
            customer = extraction.get('customer')
            if (supplier is None or supplier == '') and (customer is None or customer == ''):
                # No relationships extracted = not AI supply chain, even if keywords matched
                extraction['ai_related'] = False
                # Also reduce relevance score if it was based on false positive keywords
                if extraction.get('relevance_score', 0) > 0.3:
                    extraction['relevance_score'] = min(extraction.get('relevance_score', 0) * 0.5, 0.3)
            
            # Add metadata
            extraction['ticker'] = article.get('ticker', '')
            extraction['article_date'] = article.get('publishedAt', '')
            extraction['article_url'] = article.get('url', '')
            extraction['article_title'] = article.get('title', '')
            
            return extraction
        except Exception as e:
            logger.error(f"Error processing article: {e}")
            return None
    
    def process_ticker_articles(self, ticker: str, articles: List[Dict], 
                                use_cache: bool = True) -> List[Dict]:
        """Process all articles for a ticker"""
        cache_path = os.path.join(self.output_dir, f"{ticker}_extractions.json")
        
        # Check cache
        if use_cache and os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                logger.debug(f"Loaded {len(cached)} cached extractions for {ticker}")
                return cached
            except Exception as e:
                logger.warning(f"Error loading cache for {ticker}: {e}")
        
        # Process articles
        extractions = []
        logger.info(f"Processing {len(articles)} articles for {ticker}...")
        
        for article in tqdm(articles, desc=f"Processing {ticker}", leave=False):
            extraction = self.process_article(article)
            if extraction:
                extractions.append(extraction)
            
            # Rate limiting (not needed for local FinBERT, but keeping for consistency)
            time.sleep(0.1)  # Small delay for processing
        
        # Save to cache
        if extractions:
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(extractions, f, indent=2, ensure_ascii=False)
                logger.debug(f"Saved {len(extractions)} extractions for {ticker}")
            except Exception as e:
                logger.error(f"Error saving cache for {ticker}: {e}")
        
        return extractions
    
    def aggregate_supply_chain_mentions(self, extractions: List[Dict]) -> Dict:
        """
        Aggregate supply chain mentions from extractions
        
        Returns:
            Dict with aggregated metrics per ticker
        """
        if not extractions:
            return {
                'total_articles': 0,
                'ai_related_count': 0,
                'supplier_mentions': 0,
                'customer_mentions': 0,
                'product_mentions': 0,
                'avg_relevance_score': 0.0,
                'positive_sentiment_count': 0,
                'negative_sentiment_count': 0,
                'neutral_sentiment_count': 0
            }
        
        total = len(extractions)
        ai_related = sum(1 for e in extractions if e.get('ai_related', False))
        supplier_mentions = sum(1 for e in extractions if e.get('supplier'))
        customer_mentions = sum(1 for e in extractions if e.get('customer'))
        product_mentions = sum(1 for e in extractions if e.get('product'))
        
        relevance_scores = [e.get('relevance_score', 0.0) for e in extractions]
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
        
        sentiments = [e.get('sentiment', 'neutral') for e in extractions]
        positive = sum(1 for s in sentiments if s == 'positive')
        negative = sum(1 for s in sentiments if s == 'negative')
        neutral = sum(1 for s in sentiments if s == 'neutral')
        
        return {
            'total_articles': total,
            'ai_related_count': ai_related,
            'supplier_mentions': supplier_mentions,
            'customer_mentions': customer_mentions,
            'product_mentions': product_mentions,
            'avg_relevance_score': avg_relevance,
            'positive_sentiment_count': positive,
            'negative_sentiment_count': negative,
            'neutral_sentiment_count': neutral
        }
    
    def calculate_supply_chain_score(self, aggregated: Dict) -> float:
        """
        Calculate composite supply chain score
        
        Formula:
        - Base: AI related count (normalized)
        - Boost: Supplier/customer/product mentions
        - Weight: Average relevance score
        - Sentiment adjustment: Positive sentiment boost
        
        FIX 3: If no relationships, reduce AI keyword weight to prevent false positives
        """
        if aggregated['total_articles'] == 0:
            return 0.0
        
        # Check if we have actual relationships (not just keyword matches)
        has_relationships = (aggregated['supplier_mentions'] > 0 or 
                           aggregated['customer_mentions'] > 0)
        
        # Normalize AI related count (0-1 scale, capped at 10 articles)
        ai_score = min(aggregated['ai_related_count'] / 10.0, 1.0)
        
        # Mention boost (supplier/customer/product)
        mention_score = (
            aggregated['supplier_mentions'] * 0.4 +
            aggregated['customer_mentions'] * 0.3 +
            aggregated['product_mentions'] * 0.3
        ) / max(aggregated['total_articles'], 1)
        
        # Relevance weight
        relevance_weight = aggregated['avg_relevance_score']
        
        # Sentiment adjustment
        total_sentiment = (
            aggregated['positive_sentiment_count'] +
            aggregated['negative_sentiment_count'] +
            aggregated['neutral_sentiment_count']
        )
        if total_sentiment > 0:
            sentiment_ratio = aggregated['positive_sentiment_count'] / total_sentiment
        else:
            sentiment_ratio = 0.5
        
        # FIX 3: Adjust weights based on whether we have relationships
        if has_relationships:
            # Normal formula: 40% AI + 30% relationships + 20% relevance + 10% sentiment
            score = (
                ai_score * 0.4 +
                mention_score * 0.3 +
                relevance_weight * 0.2 +
                sentiment_ratio * 0.1
            )
        else:
            # Reduced AI weight: 20% AI + 0% relationships + 20% relevance + 10% sentiment
            # This prevents false positives from scoring >0.5
            score = (
                ai_score * 0.2 +  # Reduced from 0.4
                mention_score * 0.0 +  # No relationships = 0
                relevance_weight * 0.2 +
                sentiment_ratio * 0.1
            )
            # Cap at 0.5 for cases with no relationships
            score = min(score, 0.5)
        
        return min(score, 1.0)  # Cap at 1.0
    
    def scan_all_tickers(self, tickers: List[str], use_cache: bool = True) -> pd.DataFrame:
        """
        Scan all tickers and generate supply chain scores
        
        Returns:
            DataFrame with columns: ticker, supply_chain_score, and aggregated metrics
        """
        results = []
        
        logger.info(f"Scanning {len(tickers)} tickers for supply chain mentions...")
        
        for ticker in tqdm(tickers, desc="Scanning tickers"):
            # Load articles
            articles = self.load_articles_for_ticker(ticker)
            
            if not articles:
                logger.debug(f"No articles found for {ticker}, skipping")
                continue
            
            # Process articles
            extractions = self.process_ticker_articles(ticker, articles, use_cache)
            
            if not extractions:
                continue
            
            # Aggregate
            aggregated = self.aggregate_supply_chain_mentions(extractions)
            
            # Calculate score
            score = self.calculate_supply_chain_score(aggregated)
            
            # Store result
            result = {
                'ticker': ticker,
                'supply_chain_score': score,
                **aggregated
            }
            results.append(result)
        
        # Create DataFrame
        df = pd.DataFrame(results)
        
        # Save results
        output_path = os.path.join(self.output_dir, "supply_chain_mentions.csv")
        df.to_csv(output_path, index=False)
        logger.info(f"Saved supply chain scores to {output_path}")
        
        return df


if __name__ == "__main__":
    # Test script
    logger = setup_logger()
    
    scanner = SupplyChainScanner(llm_provider="finbert")  # Using FinBERT
    test_tickers = ['NVDA', 'AMD', 'MU']
    
    results = scanner.scan_all_tickers(test_tickers)
    print(f"\n✅ Scanned {len(results)} tickers")
    print(results[['ticker', 'supply_chain_score', 'ai_related_count']].head())
