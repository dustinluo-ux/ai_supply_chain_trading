"""
Expand database to cover 20 core AI supply chain stocks.

Uses combination of:
1. Official supplier lists (Apple, NVIDIA where available)
2. 10-K parsing
3. Manual research for critical relationships
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.supply_chain_manager import SupplyChainManager
from src.data.apple_supplier_list import download_apple_suppliers, get_us_listed_suppliers
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def expand_to_core_stocks():
    """Expand database to 20 core AI supply chain stocks."""
    
    manager = SupplyChainManager()
    
    # Core 20 stocks (priority AI supply chain companies)
    core_stocks = [
        # Current 5 (already have)
        'AAPL', 'NVDA', 'AMD', 'TSLA', 'MSFT',
        # Add 15 more (high priority)
        'TSM',      # TSMC - foundry (NVDA/AMD/AAPL supplier)
        'ASML',     # Chip equipment (TSM supplier)
        'QCOM',     # Qualcomm (AAPL supplier)
        'AVGO',     # Broadcom (AAPL supplier, 20% revenue)
        'MU',       # Micron memory (AAPL/NVDA supplier)
        'INTC',     # Intel (competitor to AMD/NVDA)
        'GOOGL',    # Google (NVDA customer, AAPL competitor)
        'AMZN',     # Amazon (NVDA customer)
        'META',     # Meta (NVDA customer)
        'LRCX',     # Lam Research (chip equipment)
        'KLAC',     # KLA Corp (chip equipment)
        'AMAT',     # Applied Materials (chip equipment)
        'SNPS',     # Synopsys (design tools, NVDA supplier)
        'CDNS',     # Cadence (design tools, NVDA supplier)
        'TXN',      # Texas Instruments (analog chips)
    ]
    
    print("=" * 60)
    print("EXPANDING SUPPLY CHAIN DATABASE")
    print("=" * 60)
    print(f"\nTarget: {len(core_stocks)} core stocks")
    print(f"Current coverage: {len(manager.db['relationships'])} companies\n")
    
    # Step 1: Add known relationships from Apple supplier list
    print("[1/3] Adding known relationships from Apple supplier list...")
    apple_suppliers = download_apple_suppliers()
    
    # Ensure AAPL exists
    if 'AAPL' not in manager.db['relationships']:
        manager.db['relationships']['AAPL'] = {
            'suppliers': [],
            'customers': [],
            'competitors': []
        }
    
    # Add Apple suppliers
    aapl_suppliers = manager.db['relationships']['AAPL'].get('suppliers', [])
    existing_tickers = {s.get('ticker', '').upper() for s in aapl_suppliers}
    
    added_count = 0
    for supplier in apple_suppliers:
        ticker = supplier['ticker']
        if ticker and not any(ticker.upper() == t for t in existing_tickers):
            aapl_suppliers.append({
                'ticker': ticker,
                'name': supplier['name'],
                'supplies': supplier['supplies'],
                'country': supplier.get('country', 'Unknown'),
                'confidence': 'high',
                'source': 'Apple Supplier List 2024',
                'last_verified': '2026-01',
                'needs_verification': False
            })
            added_count += 1
    
    manager.db['relationships']['AAPL']['suppliers'] = aapl_suppliers
    manager.db['relationships']['AAPL']['last_verified'] = '2026-01-25'
    manager.db['relationships']['AAPL']['data_source'] = 'Apple Supplier List 2024'
    manager.db['relationships']['AAPL']['needs_manual_verification'] = False
    
    print(f"  Added {added_count} Apple suppliers")
    
    # Step 2: Add known competitor relationships
    print("\n[2/3] Adding known competitor relationships...")
    
    known_competitors = {
        'NVDA': ['AMD', 'INTC'],
        'AMD': ['NVDA', 'INTC'],
        'INTC': ['NVDA', 'AMD'],
        'AAPL': ['GOOGL', 'MSFT'],
        'MSFT': ['GOOGL', 'AMZN', 'AAPL'],
        'GOOGL': ['MSFT', 'AMZN', 'AAPL'],
        'AMZN': ['MSFT', 'GOOGL'],
        'TSLA': ['F', 'GM', 'RIVN'],
        'TSM': ['GFS', 'INTC'],  # Foundry competitors
        'ASML': ['LRCX', 'KLAC', 'AMAT'],  # Chip equipment competitors
    }
    
    competitor_count = 0
    for ticker, competitors in known_competitors.items():
        ticker = ticker.upper()
        if ticker not in manager.db['relationships']:
            manager.db['relationships'][ticker] = {
                'suppliers': [],
                'customers': [],
                'competitors': []
            }
        
        existing_competitors = {c.get('ticker', '').upper() for c in manager.db['relationships'][ticker].get('competitors', [])}
        
        for competitor in competitors:
            if competitor.upper() not in existing_competitors:
                manager.db['relationships'][ticker]['competitors'].append({
                    'ticker': competitor.upper(),
                    'confidence': 'high',
                    'source': 'Known industry relationships',
                    'needs_verification': False
                })
                competitor_count += 1
    
    print(f"  Added {competitor_count} competitor relationships")
    
    # Step 3: Ensure coverage for all core stocks
    print(f"\n[3/3] Ensuring coverage for {len(core_stocks)} core stocks...")
    
    status = manager.ensure_coverage(
        core_stocks,
        max_age_months=6,
        auto_research=True  # Try automatic research first
    )
    
    # Report results
    print("\n" + "=" * 60)
    print("STATUS SUMMARY")
    print("=" * 60)
    
    ok_count = sum(1 for s in status.values() if s == 'ok')
    added_count = sum(1 for s in status.values() if s == 'added')
    updated_count = sum(1 for s in status.values() if s == 'updated')
    missing_count = sum(1 for s in status.values() if s == 'missing')
    failed_count = sum(1 for s in status.values() if s == 'failed')
    
    print(f"\nStatus breakdown:")
    print(f"  OK (fresh): {ok_count}")
    print(f"  Added: {added_count}")
    print(f"  Updated: {updated_count}")
    print(f"  Missing: {missing_count}")
    print(f"  Failed: {failed_count}")
    
    # Show what needs manual work
    manual_needed = [t for t, s in status.items() if s in ['failed', 'missing']]
    if manual_needed:
        print(f"\n[!] Manual research needed for: {manual_needed}")
        print("   See: docs/RESEARCH_QUEUE.txt")
    
    # Show coverage report
    report = manager.get_coverage_report()
    print(f"\n" + "=" * 60)
    print("COVERAGE REPORT")
    print("=" * 60)
    print(f"  Total companies: {report['total_companies']}")
    print(f"  Companies with suppliers: {report['companies_with_suppliers']}")
    print(f"  Companies with customers: {report['companies_with_customers']}")
    print(f"  Total relationships: {report['total_relationships']}")
    print(f"  Average data age: {report['avg_age_days']:.0f} days")
    print(f"  Stale entries: {report['stale_count']}")
    
    # Save database
    manager._save_database()
    print(f"\n[OK] Database saved to {manager.db_path}")
    
    return status, report


if __name__ == '__main__':
    status, report = expand_to_core_stocks()
    
    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("1. Review database: data/supply_chain_relationships.json")
    print("2. Check research queue: docs/RESEARCH_QUEUE.txt")
    print("3. Manually verify relationships marked 'needs_verification: true'")
    print("4. See docs/VERIFICATION_CHECKLIST.md for verification guide")
