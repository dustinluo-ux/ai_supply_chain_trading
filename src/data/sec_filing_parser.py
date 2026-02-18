"""
Parse SEC 10-K filings to extract supplier-customer relationships.

Uses the "reverse lookup" method: find suppliers that mention major customers
in their concentration disclosures.
"""

import requests
import re
import os
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import json
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SECFilingParser:
    """
    Extract supplier relationships from SEC EDGAR filings.
    
    Focus areas:
    - Item 1 (Business) → Supply Chain sections
    - Item 1A (Risk Factors) → Supplier dependencies  
    - Financial Notes → Revenue concentration
    """
    
    def __init__(self, cache_dir: str = "data/cache/sec_filings"):
        self.base_url = "https://www.sec.gov"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # SEC requires User-Agent identification
        # Disable proxy for SEC API calls (similar to Gemini fix)
        _proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
        for var in _proxy_vars:
            os.environ.pop(var, None)
        
        self.headers = {
            'User-Agent': 'SupplyChainResearch research@example.com',
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'www.sec.gov'
        }
        
        # Rate limiting: SEC allows 10 requests per second
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
    
    def _rate_limit(self):
        """Enforce SEC rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _ticker_to_cik(self, ticker: str) -> Optional[str]:
        """
        Convert stock ticker to SEC CIK (Central Index Key).
        
        Uses SEC company tickers JSON file.
        """
        cache_file = self.cache_dir / "company_tickers.json"
        
        # Download company tickers if not cached
        if not cache_file.exists():
            self._rate_limit()
            try:
                url = f"{self.base_url}/files/company_tickers.json"
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                
                with open(cache_file, 'wb') as f:
                    f.write(response.content)
                logger.info("Downloaded SEC company tickers")
            except Exception as e:
                logger.error(f"Failed to download company tickers: {e}")
                return None
        
        # Load and search
        try:
            with open(cache_file, 'r') as f:
                companies = json.load(f)
            
            # Format: {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, ...}
            for entry in companies.values():
                if entry.get('ticker', '').upper() == ticker.upper():
                    cik_str = entry.get('cik_str', '')
                    if isinstance(cik_str, int):
                        return str(cik_str).zfill(10)  # Pad to 10 digits for SEC API
                    elif isinstance(cik_str, str):
                        return cik_str.lstrip('0').zfill(10)  # Remove leading zeros, pad to 10
                    else:
                        return str(cik_str).zfill(10)
        except Exception as e:
            logger.error(f"Error reading company tickers: {e}")
        
        return None
    
    def get_latest_10k(self, ticker: str, year: Optional[int] = None) -> Optional[str]:
        """
        Fetch latest 10-K filing text for a ticker.
        
        Args:
            ticker: Stock ticker
            year: Specific year to fetch (if None, gets latest)
            
        Returns:
            Full text of 10-K filing, or None if not found
        """
        # Check cache first
        cache_file = self.cache_dir / f"{ticker}_10k.txt"
        if cache_file.exists() and year is None:
            logger.info(f"Using cached 10-K for {ticker}")
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
        
        # Get CIK
        cik = self._ticker_to_cik(ticker)
        if not cik:
            logger.warning(f"Could not find CIK for {ticker}")
            return None
        
        # Use SEC's JSON API for more reliable access
        # Format: https://data.sec.gov/submissions/CIK{10-digit-CIK}.json
        self._rate_limit()
        submissions_url = f"{self.base_url}/submissions/CIK{cik.zfill(10)}.json"
        
        try:
            response = requests.get(submissions_url, headers=self.headers)
            response.raise_for_status()
            submissions = response.json()
            
            # Find 10-K filings
            filings = submissions.get('filings', {}).get('recent', {})
            forms = filings.get('form', [])
            filing_dates = filings.get('filingDate', [])
            accession_numbers = filings.get('accessionNumber', [])
            
            # Find latest 10-K
            latest_10k_idx = None
            for i in range(len(forms) - 1, -1, -1):  # Search backwards (most recent first)
                if forms[i] == '10-K':
                    latest_10k_idx = i
                    break
            
            if latest_10k_idx is None:
                logger.warning(f"No 10-K filings found for {ticker}")
                return None
            
            accession = accession_numbers[latest_10k_idx]
            filing_date = filing_dates[latest_10k_idx]
            
            # Convert accession number format: 0000320193-23-000077 -> 000032019323000077
            # Remove dashes and pad
            accession_clean = accession.replace('-', '')
            
            # Download the filing
            # Format: https://www.sec.gov/Archives/edgar/data/{CIK}/{accession_clean}/{accession}.txt
            doc_url = f"{self.base_url}/Archives/edgar/data/{cik.zfill(10)}/{accession_clean}/{accession}.txt"
            
            self._rate_limit()
            doc_response = requests.get(doc_url, headers=self.headers)
            doc_response.raise_for_status()
            
            filing_text = doc_response.text
            
            # Cache it
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(filing_text)
            
            logger.info(f"Downloaded 10-K for {ticker} (filed {filing_date})")
            return filing_text
            
        except Exception as e:
            logger.error(f"Error fetching 10-K for {ticker}: {e}")
            return None
    
    def extract_customer_concentration(self, filing_text: str) -> List[Dict]:
        """
        Extract customer concentration disclosures.
        
        Looks for patterns like:
        - "Customer A accounted for 42% of revenue"
        - "Our largest customer represented 18% of net sales"
        - "One customer accounted for more than 10% of revenue"
        
        Returns:
            List of {percentage: float, description: str, context: str, likely_major_customer: bool}
        """
        patterns = [
            # Pattern 1: "Customer A accounted for X% of revenue"
            r'([Cc]ustomer [A-Z]|largest customer|one customer|single customer|principal customer).*?(\d+)%.*?(revenue|sales|net sales)',
            # Pattern 2: "X% of revenue from Customer A"
            r'(\d+)%.*?(revenue|sales|net sales).*?([Cc]ustomer [A-Z]|single customer|largest customer)',
            # Pattern 3: "accounted for X percent of revenue"
            r'accounted for.*?(\d+).*?percent.*?(revenue|sales|net sales)',
            # Pattern 4: "representing approximately X%"
            r'representing.*?approximately.*?(\d+)%.*?(revenue|sales)',
            # Pattern 5: "more than X% of revenue"
            r'more than.*?(\d+)%.*?(revenue|sales)',
        ]
        
        findings = []
        seen_contexts = set()  # Avoid duplicates
        
        for pattern in patterns:
            matches = re.finditer(pattern, filing_text, re.IGNORECASE)
            for match in matches:
                # Extract surrounding context (200 chars before/after)
                start = max(0, match.start() - 200)
                end = min(len(filing_text), match.end() + 200)
                context = filing_text[start:end]
                
                # Create context hash to avoid duplicates
                context_hash = hash(context[:100])
                if context_hash in seen_contexts:
                    continue
                seen_contexts.add(context_hash)
                
                # Try to extract percentage
                pct_match = re.search(r'(\d+)%', match.group())
                if not pct_match:
                    pct_match = re.search(r'(\d+).*?percent', match.group(), re.IGNORECASE)
                
                if pct_match:
                    try:
                        percentage = int(pct_match.group(1))
                        
                        findings.append({
                            'percentage': percentage,
                            'match_text': match.group(),
                            'context': context,
                            'likely_major_customer': percentage >= 10,
                            'pattern_used': pattern
                        })
                    except ValueError:
                        continue
        
        # Sort by percentage (highest first)
        findings.sort(key=lambda x: x['percentage'], reverse=True)
        
        return findings
    
    def extract_supplier_mentions(self, filing_text: str) -> List[Dict]:
        """
        Extract explicit supplier mentions.
        
        Looks for:
        - Company names in supply chain sections
        - "We rely on [Company] for..."
        - "single-source supplier"
        - "sole supplier"
        
        Returns:
            List of {company_name: str, context: str, relationship_type: str}
        """
        # Keywords that indicate supply chain discussion
        supply_keywords = [
            r'supplier',
            r'vendor',
            r'manufacturer',
            r'foundry',
            r'outsource',
            r'third-party',
            r'contract manufacturer',
            r'single-source',
            r'sole-source',
            r'rely on.*?for',
            r'dependent on.*?for'
        ]
        
        findings = []
        
        # Find sections mentioning these keywords
        for keyword in supply_keywords:
            pattern = rf'{keyword}.*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
            matches = re.finditer(pattern, filing_text, re.IGNORECASE)
            
            for match in matches:
                # Extract company name (simplified - would need NER in production)
                company_name = match.group(1) if match.group(1) else None
                
                if company_name and len(company_name.split()) <= 4:  # Reasonable company name length
                    start = max(0, match.start() - 150)
                    end = min(len(filing_text), match.end() + 150)
                    context = filing_text[start:end]
                    
                    findings.append({
                        'company_name': company_name,
                        'context': context,
                        'relationship_type': 'supplier',
                        'keyword_matched': keyword
                    })
        
        return findings
    
    def extract_supply_chain_sections(self, filing_text: str) -> Dict[str, str]:
        """
        Extract key sections from 10-K that discuss supply chain.
        
        Returns:
            Dict with section names as keys and text as values
        """
        sections = {}
        
        # Item 1: Business
        item1_pattern = r'ITEM\s+1\.?\s*BUSINESS(.*?)(?=ITEM\s+1A|ITEM\s+2|$)'
        match = re.search(item1_pattern, filing_text, re.IGNORECASE | re.DOTALL)
        if match:
            sections['item1_business'] = match.group(1)
        
        # Item 1A: Risk Factors
        item1a_pattern = r'ITEM\s+1A\.?\s*RISK\s+FACTORS(.*?)(?=ITEM\s+2|ITEM\s+7|$)'
        match = re.search(item1a_pattern, filing_text, re.IGNORECASE | re.DOTALL)
        if match:
            sections['item1a_risk_factors'] = match.group(1)
        
        # Financial Notes (look for "Revenue Concentration" or similar)
        revenue_pattern = r'(REVENUE.*?CONCENTRATION|CUSTOMER.*?CONCENTRATION|SIGNIFICANT.*?CUSTOMER)(.*?)(?=\n\n[A-Z]{2,}|$)'
        match = re.search(revenue_pattern, filing_text, re.IGNORECASE | re.DOTALL)
        if match:
            sections['revenue_concentration'] = match.group(2)
        
        return sections
    
    def find_major_customer_candidates(self, 
                                      supplier_ticker: str,
                                      potential_customers: List[str]) -> List[Dict]:
        """
        Given a supplier and list of potential customers, try to identify
        which customer is the unnamed "Customer A" in the 10-K.
        
        Method:
        1. Get supplier's 10-K
        2. Extract customer concentration %
        3. Cross-reference with product types
        4. Match timing of revenue spikes
        
        Args:
            supplier_ticker: The supplier to analyze
            potential_customers: List of tickers that might be the customer
            
        Returns:
            List of likely matches with confidence scores
        """
        filing = self.get_latest_10k(supplier_ticker)
        if not filing:
            return []
        
        concentrations = self.extract_customer_concentration(filing)
        if not concentrations:
            return []
        
        candidates = []
        
        for concentration in concentrations:
            if concentration['likely_major_customer']:
                # Try to match context with potential customers
                context_lower = concentration['context'].lower()
                
                for customer_ticker in potential_customers:
                    # Simple heuristic: check if customer name appears in context
                    # (Would need ticker → company name mapping)
                    confidence = 0.0
                    
                    # Higher confidence if percentage is very high (>20%)
                    if concentration['percentage'] > 20:
                        confidence += 0.3
                    
                    # Would add more sophisticated matching here
                    # (product mentions, industry keywords, etc.)
                    
                    candidates.append({
                        'supplier': supplier_ticker,
                        'potential_customer': customer_ticker,
                        'concentration_pct': concentration['percentage'],
                        'confidence': min(confidence, 1.0),
                        'context': concentration['context'][:200],
                        'needs_manual_verification': True
                    })
        
        return candidates


if __name__ == '__main__':
    # Test the parser
    parser = SECFilingParser()
    
    # Test with a known ticker
    print("Testing SEC Filing Parser...")
    print("\n1. Testing ticker to CIK conversion...")
    cik = parser._ticker_to_cik('AAPL')
    print(f"   AAPL CIK: {cik}")
    
    print("\n2. Testing 10-K download (this may take a moment)...")
    filing = parser.get_latest_10k('AAPL')
    if filing:
        print(f"   Downloaded {len(filing)} characters")
        
        print("\n3. Testing customer concentration extraction...")
        concentrations = parser.extract_customer_concentration(filing)
        print(f"   Found {len(concentrations)} concentration disclosures")
        for c in concentrations[:3]:
            if c['likely_major_customer']:
                print(f"   - {c['percentage']}%: {c['match_text'][:80]}...")
    else:
        print("   Failed to download 10-K")
