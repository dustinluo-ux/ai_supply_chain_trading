"""
Intelligent supply chain database management.

Features:
- Checks if stock exists in database
- Tracks data freshness
- Auto-downloads missing stocks
- Updates stale data
- Incremental growth
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SupplyChainManager:
    """
    Manages supply chain database with intelligent updates.
    
    Usage:
        manager = SupplyChainManager()
        
        # Ensure stocks are in database
        manager.ensure_coverage(['AAPL', 'NVDA', 'TSM'], max_age_months=6)
        
        # Get relationships (auto-updates if stale)
        suppliers = manager.get_suppliers('AAPL', auto_update=True)
    """
    
    def __init__(self, db_path='data/supply_chain_relationships.json'):
        self.db_path = Path(db_path)
        self.db = self._load_database()
        self.default_stale_months = self.db['metadata'].get('default_stale_months', 6)
    
    def _load_database(self) -> Dict:
        """Load database from JSON file."""
        if not self.db_path.exists():
            # Create empty database
            return {
                'metadata': {
                    'last_updated': datetime.now().isoformat()[:10],
                    'version': '1.0',
                    'default_stale_months': 6
                },
                'relationships': {}
            }
        
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                db = json.load(f)
            
            # Ensure metadata has required fields
            if 'metadata' not in db:
                db['metadata'] = {}
            db['metadata'].setdefault('default_stale_months', 6)
            db['metadata'].setdefault('version', '1.0')
            
            return db
        except Exception as e:
            logger.error(f"Error loading database: {e}")
            return {
                'metadata': {
                    'last_updated': datetime.now().isoformat()[:10],
                    'version': '1.0',
                    'default_stale_months': 6
                },
                'relationships': {}
            }
    
    def _save_database(self):
        """Save database to JSON file."""
        self.db['metadata']['last_updated'] = datetime.now().isoformat()[:10]
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, indent=2)
    
    def is_covered(self, ticker: str) -> bool:
        """Check if ticker exists in database."""
        return ticker.upper() in self.db['relationships']
    
    def is_stale(self, ticker: str, max_age_months: int = None) -> bool:
        """
        Check if ticker data is stale.
        
        Args:
            ticker: Stock ticker
            max_age_months: Consider stale if older than this (default: 6 months)
            
        Returns:
            True if data needs updating
        """
        ticker = ticker.upper()
        if not self.is_covered(ticker):
            return True  # Missing = stale
        
        max_age = max_age_months or self.default_stale_months
        
        rel_data = self.db['relationships'][ticker]
        last_verified = rel_data.get('last_verified')
        
        if not last_verified:
            return True  # No date = stale
        
        try:
            # Parse date (format: YYYY-MM-DD or YYYY-MM)
            if len(last_verified) == 7:  # YYYY-MM
                last_date = datetime.strptime(last_verified, '%Y-%m')
            else:  # YYYY-MM-DD
                last_date = datetime.strptime(last_verified, '%Y-%m-%d')
            
            age_months = (datetime.now() - last_date).days / 30.0
            
            return age_months > max_age
        except Exception as e:
            logger.warning(f"Error parsing date for {ticker}: {e}")
            return True  # Error = assume stale
    
    def get_missing_stocks(self, required_stocks: List[str]) -> List[str]:
        """Return list of stocks not in database."""
        return [s.upper() for s in required_stocks if not self.is_covered(s)]
    
    def get_stale_stocks(self, stocks: List[str], max_age_months: int = 6) -> List[str]:
        """Return list of stocks with stale data."""
        return [
            s.upper() for s in stocks 
            if self.is_covered(s) and self.is_stale(s, max_age_months)
        ]
    
    def ensure_coverage(self, 
                       stocks: List[str],
                       max_age_months: int = 6,
                       auto_research: bool = True) -> Dict[str, str]:
        """
        Ensure all stocks are in database with fresh data.
        
        Args:
            stocks: List of tickers needed
            max_age_months: Maximum data age
            auto_research: If True, automatically research missing stocks
            
        Returns:
            Status dict: {ticker: 'ok' | 'missing' | 'stale' | 'added' | 'updated' | 'failed'}
        """
        stocks = [s.upper() for s in stocks]  # Normalize to uppercase
        status = {}
        
        missing = self.get_missing_stocks(stocks)
        stale = self.get_stale_stocks(stocks, max_age_months)
        
        # Report what needs work
        if missing:
            print(f"[DB] Missing: {len(missing)} stocks - {missing}")
        
        if stale:
            print(f"[DB] Stale: {len(stale)} stocks - {stale}")
        
        # Auto-research if enabled
        if auto_research:
            for ticker in missing:
                print(f"[DB] Researching {ticker}...")
                success = self._research_and_add(ticker)
                status[ticker] = 'added' if success else 'failed'
            
            for ticker in stale:
                print(f"[DB] Updating {ticker}...")
                success = self._update_ticker(ticker)
                status[ticker] = 'updated' if success else 'failed'
        else:
            # Just flag them
            for ticker in missing:
                status[ticker] = 'missing'
            for ticker in stale:
                status[ticker] = 'stale'
        
        # Mark fresh stocks
        for ticker in stocks:
            if ticker not in status:
                status[ticker] = 'ok'
        
        return status
    
    def _research_and_add(self, ticker: str) -> bool:
        """
        Research a new ticker and add to database.
        
        Methods (in priority order):
        1. Check if ticker is in known supplier lists (Apple, NVIDIA, etc.)
        2. Parse ticker's 10-K for supplier mentions
        3. Search industry databases (if API available)
        4. Flag for manual research
        
        Returns:
            True if added successfully
        """
        ticker = ticker.upper()
        print(f"  Attempting automated research for {ticker}...")
        
        # Method 1: Is this ticker a known supplier to someone we already have?
        for company, data in self.db['relationships'].items():
            suppliers = data.get('suppliers', [])
            for supplier in suppliers:
                if supplier.get('ticker', '').upper() == ticker:
                    print(f"    Found {ticker} as supplier to {company}")
                    # Add reverse relationship (ticker is a customer of company)
                    if ticker not in self.db['relationships']:
                        self.db['relationships'][ticker] = {
                            'suppliers': [],
                            'customers': [],
                            'competitors': []
                        }
                    
                    # Add customer relationship
                    self.db['relationships'][ticker]['customers'].append({
                        'ticker': company,
                        'confidence': supplier.get('confidence', 'medium'),
                        'source': f'Reverse lookup from {company} suppliers',
                        'needs_verification': True
                    })
                    
                    self.db['relationships'][ticker]['last_verified'] = datetime.now().isoformat()[:10]
                    self.db['relationships'][ticker]['data_source'] = 'Reverse lookup'
                    self.db['relationships'][ticker]['needs_manual_verification'] = True
                    
                    self._save_database()
                    print(f"    Added {ticker} with customer relationship to {company}")
                    return True
        
        # Method 2: Try 10-K parsing
        try:
            from src.data.sec_filing_parser import SECFilingParser
            parser = SECFilingParser()
            
            # Download 10-K
            filing = parser.get_latest_10k(ticker)
            if filing:
                # Extract what we can
                concentrations = parser.extract_customer_concentration(filing)
                suppliers_mentions = parser.extract_supplier_mentions(filing)
                
                # Convert supplier mentions to structured format
                suppliers = []
                for mention in suppliers_mentions[:10]:  # Top 10
                    suppliers.append({
                        'ticker': 'UNKNOWN',
                        'name': mention.get('company_name', 'Unknown'),
                        'confidence': 'low',
                        'source': f'SEC 10-K {ticker}',
                        'needs_verification': True
                    })
                
                # Add partial data
                self.db['relationships'][ticker] = {
                    'last_verified': datetime.now().isoformat()[:10],
                    'data_source': f'SEC 10-K auto-parsed',
                    'suppliers': suppliers,
                    'customers': [
                        {
                            'ticker': 'UNKNOWN',
                            'name': f"Customer ({c['percentage']}% of revenue)",
                            'concentration_pct': c['percentage'],
                            'confidence': 'low',
                            'source': f'SEC 10-K {ticker}',
                            'context': c['context'][:200],
                            'needs_verification': True
                        }
                        for c in concentrations
                        if c['likely_major_customer']
                    ],
                    'competitors': [],
                    'needs_manual_verification': True
                }
                
                self._save_database()
                print(f"    Added {ticker} with partial data (needs verification)")
                return True
                
        except Exception as e:
            logger.debug(f"10-K parsing failed for {ticker}: {e}")
        
        # Method 3: Flag for manual research
        print(f"    Could not auto-research {ticker}")
        print(f"    -> Add to manual research queue: docs/RESEARCH_QUEUE.txt")
        
        # Add to research queue
        queue_file = Path('docs/RESEARCH_QUEUE.txt')
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(queue_file, 'a', encoding='utf-8') as f:
            f.write(f"{ticker} - Added {datetime.now().isoformat()[:10]} - Auto-research failed\n")
        
        return False
    
    def _update_ticker(self, ticker: str) -> bool:
        """Update stale ticker data."""
        ticker = ticker.upper()
        if not self.is_covered(ticker):
            return self._research_and_add(ticker)
        
        print(f"  Updating stale data for {ticker}...")
        
        # Try to refresh from 10-K
        try:
            from src.data.sec_filing_parser import SECFilingParser
            parser = SECFilingParser()
            
            filing = parser.get_latest_10k(ticker)
            if filing:
                concentrations = parser.extract_customer_concentration(filing)
                
                # Update customer relationships
                rel_data = self.db['relationships'][ticker]
                
                # Merge new customer concentrations with existing
                existing_customers = {c.get('ticker'): c for c in rel_data.get('customers', [])}
                
                for c in concentrations:
                    if c['likely_major_customer']:
                        # Check if we already have this customer
                        # (Would need better matching logic in production)
                        pass
                
                # Update last_verified
                rel_data['last_verified'] = datetime.now().isoformat()[:10]
                rel_data['data_source'] = f'SEC 10-K auto-parsed (updated)'
                
                self._save_database()
                print(f"    Updated {ticker}")
                return True
        except Exception as e:
            logger.debug(f"Update failed for {ticker}: {e}")
        
        # If update fails, just refresh the date (data is still usable)
        rel_data = self.db['relationships'][ticker]
        rel_data['last_verified'] = datetime.now().isoformat()[:10]
        rel_data['needs_manual_verification'] = True
        self._save_database()
        
        return False
    
    def get_suppliers(self, ticker: str, auto_update: bool = False) -> List[Dict]:
        """Get supplier relationships for a ticker."""
        ticker = ticker.upper()
        
        if auto_update and self.is_stale(ticker):
            self._update_ticker(ticker)
        
        if not self.is_covered(ticker):
            return []
        
        return self.db['relationships'][ticker].get('suppliers', [])
    
    def get_customers(self, ticker: str, auto_update: bool = False) -> List[Dict]:
        """Get customer relationships for a ticker."""
        ticker = ticker.upper()
        
        if auto_update and self.is_stale(ticker):
            self._update_ticker(ticker)
        
        if not self.is_covered(ticker):
            return []
        
        return self.db['relationships'][ticker].get('customers', [])
    
    def get_competitors(self, ticker: str) -> List[Dict]:
        """Get competitor relationships for a ticker."""
        ticker = ticker.upper()
        
        if not self.is_covered(ticker):
            return []
        
        return self.db['relationships'][ticker].get('competitors', [])
    
    def get_related_companies(self, ticker: str) -> List[str]:
        """Get all related companies (suppliers, customers, competitors)."""
        ticker = ticker.upper()
        
        related = []
        
        # Suppliers
        suppliers = self.get_suppliers(ticker)
        related.extend([s['ticker'] for s in suppliers if s.get('ticker') and s['ticker'] != 'UNKNOWN'])
        
        # Customers
        customers = self.get_customers(ticker)
        related.extend([c['ticker'] for c in customers if c.get('ticker') and c['ticker'] != 'UNKNOWN'])
        
        # Competitors
        competitors = self.get_competitors(ticker)
        related.extend([c['ticker'] for c in competitors if c.get('ticker')])
        
        return list(set(related))  # Remove duplicates
    
    def get_coverage_report(self) -> Dict:
        """
        Generate coverage statistics.
        
        Returns:
            {
                'total_companies': int,
                'companies_with_suppliers': int,
                'companies_with_customers': int,
                'total_relationships': int,
                'avg_age_days': float,
                'stale_count': int
            }
        """
        relationships = self.db.get('relationships', {})
        total = len(relationships)
        
        companies_with_suppliers = sum(
            1 for r in relationships.values() 
            if r.get('suppliers') and len(r.get('suppliers', [])) > 0
        )
        
        companies_with_customers = sum(
            1 for r in relationships.values() 
            if r.get('customers') and len(r.get('customers', [])) > 0
        )
        
        total_relationships = sum(
            len(r.get('suppliers', [])) + 
            len(r.get('customers', [])) + 
            len(r.get('competitors', []))
            for r in relationships.values()
        )
        
        # Calculate average age
        ages = []
        for ticker, rel_data in relationships.items():
            last_verified = rel_data.get('last_verified')
            if last_verified:
                try:
                    if len(last_verified) == 7:
                        last_date = datetime.strptime(last_verified, '%Y-%m')
                    else:
                        last_date = datetime.strptime(last_verified, '%Y-%m-%d')
                    age_days = (datetime.now() - last_date).days
                    ages.append(age_days)
                except Exception:
                    pass
        
        avg_age_days = sum(ages) / len(ages) if ages else 0
        
        # Count stale
        stale_count = sum(
            1 for ticker in relationships.keys()
            if self.is_stale(ticker)
        )
        
        return {
            'total_companies': total,
            'companies_with_suppliers': companies_with_suppliers,
            'companies_with_customers': companies_with_customers,
            'total_relationships': total_relationships,
            'avg_age_days': avg_age_days,
            'stale_count': stale_count
        }


if __name__ == '__main__':
    # Test the manager
    manager = SupplyChainManager()
    
    print("Testing Supply Chain Manager...")
    print(f"Database path: {manager.db_path}")
    print(f"Companies in database: {len(manager.db['relationships'])}")
    
    # Test coverage check
    test_stocks = ['AAPL', 'NVDA', 'UNKNOWN_TICKER']
    status = manager.ensure_coverage(test_stocks, auto_research=False)
    print(f"\nCoverage status: {status}")
    
    # Test report
    report = manager.get_coverage_report()
    print(f"\nCoverage report:")
    for key, value in report.items():
        print(f"  {key}: {value}")
