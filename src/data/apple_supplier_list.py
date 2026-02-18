"""
Download and parse Apple's official supplier list.
Maps company names to stock tickers.
"""

import json
import requests
from pathlib import Path
from typing import List, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def download_apple_suppliers() -> List[Dict]:
    """
    Download Apple's latest supplier responsibility report.
    
    Apple publishes this annually at:
    https://www.apple.com/supplier-responsibility/
    
    For now, returns manually curated list from latest reports.
    In production, would scrape/download the PDF and parse.
    
    Returns:
        List of {company_name: str, ticker: str (if public), country: str, supplies: str}
    """
    # Manually curated from Apple Supplier Responsibility Report 2024
    # Sources: https://www.apple.com/supplier-responsibility/pdf/Apple-Supplier-List.pdf
    
    apple_suppliers = [
        # Semiconductor Foundries
        {'name': 'Taiwan Semiconductor Manufacturing Company', 'ticker': 'TSM', 'country': 'Taiwan', 'supplies': 'Chips/Foundry'},
        {'name': 'GlobalFoundries', 'ticker': 'GFS', 'country': 'USA', 'supplies': 'Chips/Foundry'},
        
        # Assembly & Manufacturing
        {'name': 'Hon Hai Precision Industry (Foxconn)', 'ticker': 'HON.TW', 'country': 'Taiwan', 'supplies': 'Assembly'},
        {'name': 'Pegatron', 'ticker': '4938.TW', 'country': 'Taiwan', 'supplies': 'Assembly'},
        {'name': 'Wistron', 'ticker': '3231.TW', 'country': 'Taiwan', 'supplies': 'Assembly'},
        
        # Chips & Components
        {'name': 'Qualcomm', 'ticker': 'QCOM', 'country': 'USA', 'supplies': 'Modems/RF'},
        {'name': 'Broadcom', 'ticker': 'AVGO', 'country': 'USA', 'supplies': 'RF chips'},
        {'name': 'Skyworks Solutions', 'ticker': 'SWKS', 'country': 'USA', 'supplies': 'RF chips'},
        {'name': 'Qorvo', 'ticker': 'QRVO', 'country': 'USA', 'supplies': 'RF chips'},
        {'name': 'Cirrus Logic', 'ticker': 'CRUS', 'country': 'USA', 'supplies': 'Audio chips'},
        {'name': 'Dialog Semiconductor', 'ticker': 'DLG.DE', 'country': 'Germany', 'supplies': 'Power management'},
        
        # Memory
        {'name': 'Micron Technology', 'ticker': 'MU', 'country': 'USA', 'supplies': 'Memory'},
        {'name': 'SK Hynix', 'ticker': '000660.KS', 'country': 'South Korea', 'supplies': 'Memory'},
        {'name': 'Samsung Electronics', 'ticker': '005930.KS', 'country': 'South Korea', 'supplies': 'Memory/Displays'},
        
        # Displays
        {'name': 'LG Display', 'ticker': '034220.KS', 'country': 'South Korea', 'supplies': 'Displays'},
        {'name': 'Japan Display', 'ticker': '6740.T', 'country': 'Japan', 'supplies': 'Displays'},
        {'name': 'Sharp', 'ticker': '6753.T', 'country': 'Japan', 'supplies': 'Displays'},
        
        # Camera & Sensors
        {'name': 'Sony', 'ticker': 'SONY', 'country': 'Japan', 'supplies': 'Camera sensors'},
        {'name': 'Largan Precision', 'ticker': '3008.TW', 'country': 'Taiwan', 'supplies': 'Camera lenses'},
        
        # Other Components
        {'name': 'Texas Instruments', 'ticker': 'TXN', 'country': 'USA', 'supplies': 'Analog chips'},
        {'name': 'STMicroelectronics', 'ticker': 'STM', 'country': 'Switzerland', 'supplies': 'Chips'},
        {'name': 'NXP Semiconductors', 'ticker': 'NXPI', 'country': 'Netherlands', 'supplies': 'Chips'},
        {'name': 'Infineon', 'ticker': 'IFX.DE', 'country': 'Germany', 'supplies': 'Chips'},
        
        # Battery & Power
        {'name': 'TDK', 'ticker': '6762.T', 'country': 'Japan', 'supplies': 'Batteries/Components'},
        {'name': 'Murata Manufacturing', 'ticker': '6981.T', 'country': 'Japan', 'supplies': 'Components'},
        
        # Materials
        {'name': 'Corning', 'ticker': 'GLW', 'country': 'USA', 'supplies': 'Glass'},
        {'name': '3M', 'ticker': 'MMM', 'country': 'USA', 'supplies': 'Materials'},
    ]
    
    return apple_suppliers


def get_us_listed_suppliers() -> List[Dict]:
    """Filter to only US-listed suppliers (for SEC filing analysis)"""
    all_suppliers = download_apple_suppliers()
    us_suppliers = [
        s for s in all_suppliers 
        if s['ticker'] and not any(s['ticker'].endswith(ext) for ext in ['.TW', '.KS', '.T', '.DE'])
    ]
    return us_suppliers


def map_company_name_to_ticker(company_name: str) -> Optional[str]:
    """
    Map a company name to its stock ticker.
    
    Uses the Apple supplier list as a lookup table.
    """
    suppliers = download_apple_suppliers()
    
    # Exact match
    for supplier in suppliers:
        if supplier['name'].upper() == company_name.upper():
            return supplier['ticker']
    
    # Partial match (contains)
    for supplier in suppliers:
        if company_name.upper() in supplier['name'].upper() or supplier['name'].upper() in company_name.upper():
            return supplier['ticker']
    
    return None


if __name__ == '__main__':
    print("Apple Supplier List")
    print("=" * 60)
    
    suppliers = download_apple_suppliers()
    print(f"\nTotal suppliers: {len(suppliers)}")
    
    us_suppliers = get_us_listed_suppliers()
    print(f"US-listed suppliers: {len(us_suppliers)}")
    
    print("\nUS-listed suppliers (for SEC analysis):")
    for s in us_suppliers[:10]:
        print(f"  {s['ticker']:8s} - {s['name']} ({s['supplies']})")
