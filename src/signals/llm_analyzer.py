"""
LLM-based supply chain analyzer
Extracts supply chain relationships and AI relevance from news articles
Supports: FinBERT (local), Gemini 2.0 Flash (API)
"""
import os
import json
import re
from typing import Dict, List, Optional
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


class LLMAnalyzer:
    """Analyzes articles using LLM to extract supply chain information"""
    
    def __init__(self, provider: str = "finbert", model: str = "ProsusAI/finbert"):
        """
        Initialize LLM analyzer
        
        Args:
            provider: "finbert" (local) or "gemini" (API)
            model: Model name (default: ProsusAI/finbert for finbert, gemini-2.0-flash-exp for gemini)
        """
        self.provider = provider.lower()
        self.model = model
        
        if self.provider == "finbert":
            try:
                from transformers import AutoTokenizer, AutoModelForSequenceClassification
                import torch
                
                # Load FinBERT model
                model_name = "ProsusAI/finbert"
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.finbert_model = AutoModelForSequenceClassification.from_pretrained(model_name)
                self.finbert_model.eval()
                logger.info("Initialized FinBERT model")
            except ImportError:
                raise ImportError("transformers and torch required for FinBERT. Run: pip install transformers torch")
            except Exception as e:
                raise ValueError(f"Error loading FinBERT model: {e}")
        
        elif self.provider == "gemini":
            try:
                # Import from same directory
                from .gemini_analyzer import GeminiAnalyzer
                self.gemini_analyzer = GeminiAnalyzer(model=model)
                logger.info(f"Initialized Gemini analyzer with model: {model}")
            except ImportError as e:
                raise ImportError("google-generativeai required for Gemini. Run: pip install google-generativeai")
            except Exception as e:
                raise ValueError(f"Error initializing Gemini: {e}")
        
        else:
            raise ValueError(f"Unknown provider: {provider}. Supported: 'finbert', 'gemini'")
    
    def _extract_with_claude(self, article: Dict) -> Dict:
        """Extract supply chain info using Claude API"""
        title = article.get('title', '')
        description = article.get('description', '')
        content = article.get('content', '') or description
        
        # Truncate content if too long (Claude has token limits)
        max_chars = 8000
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        
        prompt = f"""Analyze this news article and extract supply chain and AI-related information.

Article Title: {title}
Article Content: {content}

Extract the following information in JSON format:
{{
    "supplier": "Company/product mentioned as supplier to AI companies (or null)",
    "customer": "Company/product mentioned as customer of AI companies (or null)",
    "product": "Product/service mentioned related to AI supply chain (or null)",
    "ai_related": true/false,
    "sentiment": "positive", "negative", or "neutral",
    "relevance_score": 0.0-1.0 (how relevant to AI supply chain theme),
    "key_mentions": ["list of key companies/products mentioned"]
}}

Return ONLY valid JSON, no other text."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = message.content[0].text
            
            # Parse JSON response
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from response if wrapped in text
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    logger.warning(f"Could not parse Claude response as JSON: {response_text[:200]}")
                    result = self._default_extraction()
            
            return result
        
        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            return self._default_extraction()
    
    def _extract_with_finbert(self, article: Dict) -> Dict:
        """Extract sentiment using FinBERT (local model)"""
        import torch
        from transformers import pipeline
        
        title = article.get('title', '')
        description = article.get('description', '')
        text = f"{title}. {description}"
        
        # FinBERT sentiment analysis
        try:
            sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=self.finbert_model,
                tokenizer=self.tokenizer
            )
            
            result = sentiment_pipeline(text)[0]
            sentiment_label = result['label'].lower()
            sentiment_score = result['score']
            
            # Map FinBERT labels to our format
            if 'positive' in sentiment_label:
                sentiment = "positive"
            elif 'negative' in sentiment_label:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            
            # For FinBERT, we can only get sentiment, not supply chain extraction
            # So we do basic keyword matching for supply chain relevance
            # FIX 2: Use word boundaries to prevent false positives (e.g., "AAL" contains "ai")
            text_lower = text.lower()
            
            # Use word boundaries for "ai" to avoid matching "AAL", "daily", etc.
            ai_pattern = r'\b(ai|artificial intelligence)\b'
            ai_related = bool(re.search(ai_pattern, text_lower, re.IGNORECASE))
            
            # Other keywords (multi-word or specific terms) - check normally
            other_keywords = ['gpu', 'semiconductor', 'datacenter', 'data center']
            other_matches = any(keyword in text_lower for keyword in other_keywords)
            
            # Require AI-specific context for "supply chain" keyword
            supply_chain_match = 'supply chain' in text_lower
            if supply_chain_match:
                # Only count if also has AI context nearby
                ai_context_pattern = r'\b(ai|artificial intelligence|gpu|semiconductor|datacenter)\b'
                supply_chain_match = bool(re.search(ai_context_pattern, text_lower, re.IGNORECASE))
            
            ai_related = ai_related or other_matches or supply_chain_match
            
            # Simple relevance scoring
            keyword_count = sum(1 for keyword in other_keywords if keyword in text_lower)
            if ai_related:
                keyword_count += 1  # Count AI match
            if supply_chain_match:
                keyword_count += 1  # Count supply chain with AI context
            relevance_score = min(keyword_count / 3.0, 1.0) if ai_related else 0.0
            
            return {
                "supplier": None,  # FinBERT can't extract this
                "customer": None,
                "product": None,
                "ai_related": ai_related,
                "sentiment": sentiment,
                "relevance_score": relevance_score,
                "key_mentions": []
            }
        
        except Exception as e:
            logger.error(f"Error with FinBERT analysis: {e}")
            return self._default_extraction()
    
    def _default_extraction(self) -> Dict:
        """Return default extraction when analysis fails"""
        return {
            "supplier": None,
            "customer": None,
            "product": None,
            "ai_related": False,
            "sentiment": "neutral",
            "relevance_score": 0.0,
            "key_mentions": []
        }
    
    def analyze_article(self, article: Dict) -> Dict:
        """
        Analyze a single article and extract supply chain information
        
        Returns:
            Dict with keys: supplier, customer/customer_type, product, ai_related, sentiment, relevance_score, key_mentions
        """
        if self.provider == "finbert":
            return self._extract_with_finbert(article)
        elif self.provider == "gemini":
            return self._extract_with_gemini(article)
        else:
            logger.warning(f"Unknown provider {self.provider}, using FinBERT")
            return self._extract_with_finbert(article)
    
    def _extract_with_gemini(self, article: Dict) -> Dict:
        """Extract supply chain info using Gemini API"""
        try:
            result = self.gemini_analyzer.analyze_article(article)
            
            # Map Gemini output to our standard format
            # Gemini returns: supplier, customer_type, product, ai_related, sentiment, relevance_score
            # We need: supplier, customer, product, ai_related, sentiment, relevance_score, key_mentions
            return {
                "supplier": result.get("supplier"),
                "customer": result.get("customer_type"),  # Map customer_type to customer
                "product": result.get("product"),
                "ai_related": result.get("ai_related", False),
                "sentiment": result.get("sentiment", "neutral"),
                "relevance_score": result.get("relevance_score", 0.0),
                "key_mentions": []  # Gemini doesn't return this, but we can extract from supplier/product
            }
        except Exception as e:
            logger.error(f"Error with Gemini analysis: {e}")
            return self._default_extraction()
    
    def analyze_batch(self, articles: List[Dict]) -> List[Dict]:
        """Analyze multiple articles"""
        if self.provider == "gemini":
            # Use Gemini's batch method which has rate limiting built in
            try:
                results = self.gemini_analyzer.analyze_batch(articles)
                return results
            except Exception as e:
                logger.error(f"Error in Gemini batch analysis: {e}")
                return []
        
        # FinBERT batch processing
        results = []
        
        for article in articles:
            try:
                extraction = self.analyze_article(article)
                extraction['article_url'] = article.get('url', '')
                extraction['article_date'] = article.get('publishedAt', '')
                extraction['ticker'] = article.get('ticker', '')
                results.append(extraction)
            except Exception as e:
                logger.error(f"Error analyzing article: {e}")
                continue
        
        return results


if __name__ == "__main__":
    # Test script
    logging.basicConfig(level=logging.INFO)
    
    # Test with sample article
    test_article = {
        'title': 'NVIDIA Partners with Western Digital for AI Data Storage Solutions',
        'description': 'NVIDIA announces partnership with Western Digital to develop high-capacity storage solutions for AI data centers.',
        'content': 'NVIDIA and Western Digital have partnered to create storage solutions optimized for AI workloads...',
        'url': 'https://example.com/article1',
        'publishedAt': '2024-01-15T10:00:00Z'
    }
    
    # Test FinBERT
    print("Testing FinBERT...")
    try:
        analyzer = LLMAnalyzer(provider="finbert")
        result = analyzer.analyze_article(test_article)
        print(f"FinBERT Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"FinBERT test failed: {e}")
