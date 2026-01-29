"""
Gemini 2.5 Flash Lite Analyzer
Uses Google's Gemini 2.5 Flash Lite API (Paid Tier) to extract supply chain relationships from news articles
"""
import os
import json
import time
import warnings
from typing import Dict, List, Optional
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# Suppress deprecation warning for google.generativeai BEFORE import
# TODO: Migrate to google.genai when stable (see https://github.com/google-gemini/deprecated-generative-ai-python)
warnings.filterwarnings("ignore", category=FutureWarning, message=".*google.generativeai.*")

# Disable proxy for Gemini API calls (fixes connection issues with misconfigured proxies)
# This prevents the google-generativeai library from using invalid proxy settings
_proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
_original_proxies = {}
for var in _proxy_vars:
    _original_proxies[var] = os.environ.get(var)
    os.environ.pop(var, None)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed. Run: pip install google-generativeai")


class GeminiAnalyzer:
    """Analyzes articles using Gemini 2.5 Flash Lite to extract supply chain information"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash-lite"):
        """
        Initialize Gemini analyzer
        
        Args:
            api_key: Gemini API key (if None, reads from GEMINI_API_KEY env var)
            model: Gemini model name (default: gemini-2.5-flash-lite for paid tier)
        """
        if not GEMINI_AVAILABLE:
            raise ImportError("google-generativeai not installed. Run: pip install google-generativeai")
        
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables or provided as argument")
        
        self.model_name = model
        
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"Initialized Gemini analyzer with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Error initializing Gemini: {e}")
            raise
    
    def _create_prompt(self, article: Dict) -> str:
        """
        Create prompt for Gemini to extract supply chain information
        
        Args:
            article: Article dict with title, description, content, etc.
        
        Returns:
            Formatted prompt string
        """
        title = article.get('title', '')
        description = article.get('description', '')
        content = article.get('content', '') or description
        
        # Combine text
        article_text = f"{title}\n\n{description}\n\n{content}".strip()
        
        # Truncate if too long (Gemini has token limits)
        max_chars = 30000  # Gemini 2.0 Flash can handle more tokens
        if len(article_text) > max_chars:
            article_text = article_text[:max_chars] + "..."
        
        prompt = f"""Analyze this news article and extract supply chain relationships and AI relevance.

Article:
{article_text}

Extract the following information and return ONLY valid JSON (no markdown, no code blocks):

{{
  "supplier": "company name that supplies to AI companies (or null if not mentioned)",
  "customer_type": "hyperscaler/AI lab/datacenter/other (or null if not mentioned)",
  "product": "what product/service is supplied (or null if not mentioned)",
  "ai_related": true/false,
  "sentiment": "positive/negative/neutral",
  "relevance_score": 0.0-1.0
}}

Rules:
- supplier: Only if article mentions a company/product supplying to AI companies (OpenAI, Google, Microsoft, NVIDIA, etc.)
- customer_type: Type of customer (hyperscaler = AWS/Azure/GCP, AI lab = OpenAI/Anthropic, datacenter = data center operators, other = other types)
- product: Specific product/service mentioned (e.g., "GPUs", "storage solutions", "semiconductors")
- ai_related: true if article mentions AI, machine learning, LLMs, or related technologies
- sentiment: Overall sentiment about the supply chain relationship
- relevance_score: How relevant to AI supply chain theme (0.0 = not relevant, 1.0 = highly relevant)

Return ONLY the JSON object, nothing else."""

        return prompt
    
    def analyze_article(self, article: Dict, max_retries: int = 3) -> Dict:
        """
        Analyze a single article and extract supply chain information
        
        Args:
            article: Article dict with title, description, content, etc.
            max_retries: Number of retry attempts if API call fails
        
        Returns:
            Dict with keys: supplier, customer_type, product, ai_related, sentiment, relevance_score
        """
        prompt = self._create_prompt(article)
        
        for attempt in range(max_retries):
            try:
                # Use Gemini's JSON mode for structured output
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=1000,
                        response_mime_type="application/json"  # Force JSON output
                    )
                )
                
                # Parse JSON response
                response_text = response.text.strip()
                
                # Remove markdown code blocks if present
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                try:
                    result = json.loads(response_text)
                    
                    # Handle list responses - Gemini sometimes returns a list instead of single dict
                    if isinstance(result, list):
                        logger.debug(f"Gemini returned list with {len(result)} items, using first item")
                        if len(result) == 0:
                            result = self._default_extraction()
                        else:
                            # Use first item if list (or could average, but single article = single result expected)
                            result = result[0] if isinstance(result[0], dict) else self._default_extraction()
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse error (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.debug(f"Response text: {response_text[:200]}")
                    if attempt < max_retries - 1:
                        time.sleep(2)  # Wait before retry
                        continue
                    # Fallback to default
                    result = self._default_extraction()
                
                # Validate and normalize result (ensure it's a dict)
                if not isinstance(result, dict):
                    logger.warning(f"Result is not a dict: {type(result)}, using default")
                    result = self._default_extraction()
                else:
                    result = self._validate_result(result)
                
                return result
            
            except Exception as e:
                logger.warning(f"Error calling Gemini API (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait before retry
                    continue
                logger.error(f"Failed to analyze article after {max_retries} attempts")
                return self._default_extraction()
        
        return self._default_extraction()
    
    def _validate_result(self, result: Dict) -> Dict:
        """
        Validate and normalize extraction result
        
        Args:
            result: Raw extraction result from Gemini
        
        Returns:
            Validated and normalized result
        """
        # Ensure all required fields exist
        validated = {
            "supplier": result.get("supplier") or None,
            "customer_type": result.get("customer_type") or None,
            "product": result.get("product") or None,
            "ai_related": bool(result.get("ai_related", False)),
            "sentiment": result.get("sentiment", "neutral").lower(),
            "relevance_score": float(result.get("relevance_score", 0.0))
        }
        
        # Validate sentiment
        if validated["sentiment"] not in ["positive", "negative", "neutral"]:
            validated["sentiment"] = "neutral"
        
        # Clamp relevance_score to 0-1
        validated["relevance_score"] = max(0.0, min(1.0, validated["relevance_score"]))
        
        return validated
    
    def _default_extraction(self) -> Dict:
        """Return default extraction when analysis fails"""
        return {
            "supplier": None,
            "customer_type": None,
            "product": None,
            "ai_related": False,
            "sentiment": "neutral",
            "relevance_score": 0.0
        }
    
    def analyze_batch(self, articles: List[Dict], delay_seconds: float = 0.5) -> List[Dict]:
        """
        Analyze multiple articles with rate limiting
        
        Args:
            articles: List of article dicts
            delay_seconds: Delay between API calls (default: 0.5s for rate limiting)
        
        Returns:
            List of extraction results
        """
        results = []
        
        logger.info(f"Analyzing {len(articles)} articles with Gemini...")
        
        for idx, article in enumerate(articles, 1):
            try:
                extraction = self.analyze_article(article)
                extraction['article_url'] = article.get('url', '')
                extraction['article_date'] = article.get('publishedAt', '') or article.get('date', '')
                extraction['ticker'] = article.get('ticker', '')
                results.append(extraction)
                
                # Rate limiting
                if idx < len(articles):
                    time.sleep(delay_seconds)
                
                # Progress logging every 10 articles
                if idx % 10 == 0:
                    logger.info(f"Processed {idx}/{len(articles)} articles...")
            
            except Exception as e:
                logger.error(f"Error analyzing article {idx}: {e}")
                continue
        
        logger.info(f"Completed analysis of {len(results)} articles")
        return results


if __name__ == "__main__":
    # Test script
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Test with sample article
    test_article = {
        'title': 'NVIDIA Partners with Western Digital for AI Data Storage Solutions',
        'description': 'NVIDIA announces partnership with Western Digital to develop high-capacity storage solutions for AI data centers.',
        'content': 'NVIDIA and Western Digital have partnered to create storage solutions optimized for AI workloads. The partnership will help hyperscalers like AWS, Microsoft Azure, and Google Cloud meet the growing demand for AI infrastructure.',
        'url': 'https://example.com/article1',
        'publishedAt': '2024-01-15T10:00:00Z'
    }
    
    print("Testing Gemini Analyzer...")
    try:
        analyzer = GeminiAnalyzer()
        result = analyzer.analyze_article(test_article)
        print(f"Gemini Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Gemini test failed: {e}")
        import traceback
        traceback.print_exc()
