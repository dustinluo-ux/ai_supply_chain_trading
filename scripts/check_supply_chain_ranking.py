"""
Quick script to check supply chain rankings from existing extraction files
Shows top 15 stocks by supply_chain_score to verify AAL fix
"""
import os
import sys
import json
import pandas as pd
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.signals.supply_chain_scanner import SupplyChainScanner

def check_rankings():
    """Check rankings from existing extraction files"""
    data_dir = Path("data")
    extraction_files = list(data_dir.glob("*_extractions.json"))
    
    if not extraction_files:
        print("No extraction files found. Run backtest first.")
        return
    
    print(f"Found {len(extraction_files)} extraction files\n")
    
    # Load extractions and calculate scores
    results = []
    scanner = SupplyChainScanner(llm_provider="gemini")  # Use same scanner logic
    
    for ext_file in extraction_files:
        ticker = ext_file.stem.replace("_extractions", "")
        
        try:
            with open(ext_file, 'r', encoding='utf-8') as f:
                extractions = json.load(f)
            
            if not extractions:
                continue
            
            # Aggregate using scanner's method
            aggregated = scanner.aggregate_supply_chain_mentions(extractions)
            score = scanner.calculate_supply_chain_score(aggregated)
            
            results.append({
                'ticker': ticker,
                'supply_chain_score': score,
                'ai_related_count': aggregated['ai_related_count'],
                'supplier_mentions': aggregated['supplier_mentions'],
                'customer_mentions': aggregated['customer_mentions'],
                'total_articles': aggregated['total_articles']
            })
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            continue
    
    if not results:
        print("No valid results found.")
        return
    
    # Create DataFrame and sort
    df = pd.DataFrame(results)
    df_sorted = df.sort_values('supply_chain_score', ascending=False)
    
    print("=" * 80)
    print("TOP 15 STOCKS BY SUPPLY CHAIN SCORE")
    print("=" * 80)
    print(f"\nTotal stocks analyzed: {len(df_sorted)}")
    print(f"\nTop 15:\n")
    
    top_15 = df_sorted.head(15)
    for idx, row in top_15.iterrows():
        print(f"{row['ticker']:6s} | Score: {row['supply_chain_score']:.3f} | "
              f"AI-related: {row['ai_related_count']:3d} | "
              f"Suppliers: {row['supplier_mentions']:2d} | "
              f"Customers: {row['customer_mentions']:2d} | "
              f"Articles: {row['total_articles']:4d}")
    
    # Check for problematic stocks
    print("\n" + "=" * 80)
    print("VERIFICATION: Problematic Stocks (should be LOW)")
    print("=" * 80)
    
    problematic = ['AAL', 'AEM', 'ADM']
    for ticker in problematic:
        ticker_data = df_sorted[df_sorted['ticker'] == ticker]
        if not ticker_data.empty:
            row = ticker_data.iloc[0]
            status = "[PASS]" if row['supply_chain_score'] < 0.3 else "[FAIL]"
            print(f"{ticker}: Score={row['supply_chain_score']:.3f} {status}")
        else:
            print(f"{ticker}: Not found in results")
    
    # Check for expected AI stocks
    print("\n" + "=" * 80)
    print("VERIFICATION: Expected AI Stocks (should be HIGH)")
    print("=" * 80)
    
    ai_stocks = ['NVDA', 'AMD', 'TSM', 'AAPL', 'MSFT']
    for ticker in ai_stocks:
        ticker_data = df_sorted[df_sorted['ticker'] == ticker]
        if not ticker_data.empty:
            row = ticker_data.iloc[0]
            status = "[PASS]" if row['supply_chain_score'] > 0.5 else "[LOW]"
            print(f"{ticker}: Score={row['supply_chain_score']:.3f} {status}")
        else:
            print(f"{ticker}: Not found in results")

if __name__ == "__main__":
    check_rankings()
