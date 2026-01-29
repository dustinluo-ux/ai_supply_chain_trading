"""
Semi-automated supply chain database builder.

Workflow:
1. Download Apple's official supplier list → auto-populate AAPL suppliers
2. For each supplier in our universe, check their 10-K for customer concentration
3. If they mention "major customer 20%", try to deduce who it is
4. Save to supply_chain_relationships.json with confidence scores
5. Flag relationships that need manual verification
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.sec_filing_parser import SECFilingParser
from src.data.apple_supplier_list import download_apple_suppliers, get_us_listed_suppliers
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_initial_database():
    """Build starter database with high-confidence relationships."""
    
    db = {
        'metadata': {
            'last_updated': datetime.now().strftime('%Y-%m-%d'),
            'method': 'SEC 10-K parsing + Apple supplier list',
            'coverage': 'Top 20 AI supply chain stocks',
            'version': '1.0'
        },
        'relationships': {}
    }
    
    parser = SECFilingParser()
    
    # Step 1: Get Apple's suppliers from official list
    print("[1/4] Downloading Apple supplier list...")
    apple_suppliers = download_apple_suppliers()
    
    db['relationships']['AAPL'] = {
        'suppliers': [
            {
                'ticker': s['ticker'],
                'name': s['name'],
                'supplies': s['supplies'],
                'country': s.get('country', 'Unknown'),
                'confidence': 'high',
                'source': 'Apple Supplier List 2024',
                'last_verified': '2026-01',
                'needs_verification': False
            }
            for s in apple_suppliers
        ],
        'customers': [],
        'competitors': []
    }
    
    print(f"  Added {len(apple_suppliers)} Apple suppliers")
    
    # Step 2: For key suppliers, check their 10-Ks for other relationships
    print("\n[2/4] Analyzing supplier 10-Ks for customer concentrations...")
    
    us_suppliers = get_us_listed_suppliers()
    print(f"  Analyzing {len(us_suppliers)} US-listed suppliers...")
    
    analyzed_count = 0
    for supplier in us_suppliers[:10]:  # Start with top 10 to avoid rate limits
        ticker = supplier['ticker']
        if not ticker or '.' in ticker:  # Skip non-US tickers
            continue
        
        print(f"\n  Analyzing {ticker} ({supplier['name']})...")
        
        try:
            filing = parser.get_latest_10k(ticker)
            if filing:
                concentrations = parser.extract_customer_concentration(filing)
                
                if concentrations:
                    major_customers = [c for c in concentrations if c['likely_major_customer']]
                    print(f"    Found {len(major_customers)} major customer disclosures")
                    
                    for c in major_customers[:3]:  # Top 3
                        print(f"      {c['percentage']}%: {c['match_text'][:80]}...")
                        
                        # Initialize supplier entry if not exists
                        if ticker not in db['relationships']:
                            db['relationships'][ticker] = {
                                'suppliers': [],
                                'customers': [],
                                'competitors': []
                            }
                        
                        # Add customer relationship (needs manual verification)
                        db['relationships'][ticker]['customers'].append({
                            'ticker': 'UNKNOWN',  # Need to deduce
                            'name': f"Customer ({c['percentage']}% of revenue)",
                            'concentration_pct': c['percentage'],
                            'confidence': 'low',
                            'source': f'SEC 10-K {ticker}',
                            'context': c['context'][:300],
                            'needs_verification': True,
                            'verification_notes': 'Customer name not disclosed - needs manual research'
                        })
                
                # Extract supply chain sections for manual review
                sections = parser.extract_supply_chain_sections(filing)
                if sections:
                    print(f"    Extracted {len(sections)} supply chain sections")
                
                analyzed_count += 1
            else:
                print(f"    Could not download 10-K")
        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}")
            continue
    
    print(f"\n  Analyzed {analyzed_count} suppliers")
    
    # Step 3: Add known competitor relationships (from LLM test results)
    print("\n[3/4] Adding known competitor relationships...")
    
    known_competitors = {
        'NVDA': ['AMD', 'INTC'],
        'AMD': ['NVDA', 'INTC'],
        'AAPL': ['GOOGL', 'MSFT'],
        'MSFT': ['GOOGL', 'AMZN', 'AAPL'],
        'TSLA': ['F', 'GM', 'RIVN']
    }
    
    for ticker, competitors in known_competitors.items():
        if ticker not in db['relationships']:
            db['relationships'][ticker] = {
                'suppliers': [],
                'customers': [],
                'competitors': []
            }
        
        for competitor in competitors:
            # Check if already exists
            existing = [c for c in db['relationships'][ticker]['competitors'] if c.get('ticker') == competitor]
            if not existing:
                db['relationships'][ticker]['competitors'].append({
                    'ticker': competitor,
                    'confidence': 'high',
                    'source': 'Known industry relationships',
                    'needs_verification': False
                })
    
    print(f"  Added competitor relationships for {len(known_competitors)} companies")
    
    # Step 4: Save database
    print("\n[4/4] Saving database...")
    output_path = Path('data/supply_chain_relationships.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2)
    
    # Print summary
    total_companies = len(db['relationships'])
    total_suppliers = sum(len(r.get('suppliers', [])) for r in db['relationships'].values())
    total_customers = sum(len(r.get('customers', [])) for r in db['relationships'].values())
    total_competitors = sum(len(r.get('competitors', [])) for r in db['relationships'].values())
    needs_verification = sum(
        sum(1 for rel in r.get('suppliers', []) if rel.get('needs_verification', False)) +
        sum(1 for rel in r.get('customers', []) if rel.get('needs_verification', False))
        for r in db['relationships'].values()
    )
    
    print(f"\n[OK] Database saved to {output_path}")
    print(f"\nSummary:")
    print(f"  Total companies: {total_companies}")
    print(f"  Total supplier relationships: {total_suppliers}")
    print(f"  Total customer relationships: {total_customers}")
    print(f"  Total competitor relationships: {total_competitors}")
    print(f"  Relationships needing verification: {needs_verification}")
    
    return db


if __name__ == '__main__':
    print("=" * 60)
    print("SUPPLY CHAIN DATABASE BUILDER")
    print("=" * 60)
    print()
    
    db = build_initial_database()
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Review data/supply_chain_relationships.json")
    print("2. Manually verify relationships marked 'needs_verification: true'")
    print("3. Research 'UNKNOWN' customers from 10-K disclosures")
    print("4. See docs/VERIFICATION_CHECKLIST.md for verification guide")
