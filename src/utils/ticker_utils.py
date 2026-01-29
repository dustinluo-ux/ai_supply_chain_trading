"""
Utilities for getting stock ticker lists (Russell 2000, etc.)
"""
import os
import pandas as pd
import requests
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def get_russell2000_tickers_from_file(file_path: str = "data/russell2000_tickers.csv") -> List[str]:
    """
    Load Russell 2000 tickers from CSV file
    Format: CSV with 'ticker' column or single column of tickers
    """
    if not os.path.exists(file_path):
        logger.warning(f"Russell 2000 ticker file not found: {file_path}")
        return []
    
    try:
        df = pd.read_csv(file_path)
        if 'ticker' in df.columns:
            tickers = df['ticker'].dropna().tolist()
        else:
            # Assume first column is tickers
            tickers = df.iloc[:, 0].dropna().tolist()
        
        # Clean tickers (remove spaces, convert to uppercase)
        tickers = [str(t).strip().upper() for t in tickers if str(t).strip()]
        logger.info(f"Loaded {len(tickers)} tickers from {file_path}")
        return tickers
    except Exception as e:
        logger.error(f"Error loading tickers from file: {e}")
        return []


def get_russell2000_tickers_from_web() -> List[str]:
    """
    Attempt to fetch Russell 2000 tickers from web sources
    Falls back to sample list if web fetch fails
    """
    # Try multiple sources
    sources = [
        # Source 1: Wikipedia (Russell 2000 page)
        {
            'url': 'https://en.wikipedia.org/wiki/Russell_2000_Index',
            'method': 'wikipedia'
        }
    ]
    
    # For MVP, we'll use a fallback list
    # In production, implement web scraping or use paid API
    logger.warning("Web-based Russell 2000 fetch not implemented - using fallback list")
    return get_fallback_ticker_list()


def get_fallback_ticker_list() -> List[str]:
    """
    Fallback list of small-cap tech/supply chain stocks for MVP testing
    These are known small-cap stocks that could be AI supply chain beneficiaries
    """
    return [
        # Storage/Memory
        'WDC', 'STX', 'MU',
        # Semiconductors (smaller players)
        'ON', 'SWKS', 'QRVO', 'MRVL', 'MCHP', 'MPWR', 'WOLF', 'ALGM', 'DIOD',
        # Data Center/Infrastructure
        'COMM', 'CALX', 'CIEN', 'ANET', 'ARRS',
        # AI/ML adjacent
        'PLTR', 'AI', 'C3AI',
        # Manufacturing/Supply Chain
        'FLEX', 'JBL', 'SANM',
        # Test with some mid-caps that might filter out
        'AMD', 'NVDA', 'INTC', 'TSM', 'ASML', 'LRCX', 'AMAT', 'KLAC'
    ]


def get_extended_small_cap_list() -> List[str]:
    """
    Extended list of small-cap stocks (150+ tickers)
    Includes tech, healthcare, industrials, and other sectors
    Focus on stocks likely to be in $500M-$5B market cap range
    """
    # Comprehensive list of small-cap stocks across sectors
    # These are known small-cap stocks that typically fall in $500M-$5B range
    tickers = [
        # Technology - Semiconductors & Hardware
        'ON', 'SWKS', 'QRVO', 'MRVL', 'MCHP', 'MPWR', 'WOLF', 'ALGM', 'DIOD', 'SLAB',
        'CRUS', 'OLED', 'UCTT', 'RMBS', 'ALOT', 'AMBA', 'LSCC', 'POWI', 'SITM', 'SYNA',
        'ACMR', 'AEIS', 'ALRM', 'AVGO', 'MXIM', 'NXPI', 'TXN', 'XLNX',
        
        # Technology - Software & Services
        'AI', 'C3AI', 'PLTR', 'DOCN', 'FROG', 'GTLB', 'MNDY', 'NCNO', 'PCTY', 'QLYS',
        'RDWR', 'RPD', 'S', 'SPLK', 'TENB', 'VEEV', 'WDAY', 'ZUO', 'ASAN',
        'BILL', 'COUP', 'ESTC', 'FRSH', 'MIME', 'OKTA',
        
        # Data Center & Infrastructure
        'COMM', 'CALX', 'CIEN', 'ANET', 'ARRS', 'CSCO', 'JNPR', 'NTGR', 'UI', 'VSH',
        'ADTN', 'ZBRA',
        
        # Storage & Memory
        'WDC', 'STX', 'MU', 'NTAP',
        
        # Industrial & Manufacturing
        'FLEX', 'JBL', 'SANM', 'TTMI', 'AOS', 'ATI', 'AXE',
        
        # Healthcare - Biotech & Pharma (small-cap)
        'ALKS', 'ALLO', 'ALNY', 'ALXO', 'ARWR', 'ASND', 'ATRA', 'AUPH', 'AVEO',
        'BLUE', 'BMRN', 'BPMC', 'BTAI', 'CABA', 'CARA', 'CBLI', 'CCXI', 'CDMO',
        'CDNA', 'CERS', 'CGEN', 'CHRS', 'CLLS', 'CLVS', 'CRIS', 'CRMD', 'CRNX',
        'CTMX', 'CUR', 'CVAC', 'CYRX', 'DAWN', 'DBVT', 'DCPH',
        
        # Healthcare - Medical Devices
        'ABMD', 'ACAD', 'ACHC', 'ACRS', 'ADUS', 'AHPI',
        
        # Consumer - Retail & Services
        'ANF', 'ASO', 'ATGE', 'AUTO', 'AVAV', 'AVT', 'AXSM', 'AYI', 'AZEK', 'AZO',
        'BBWI', 'BBY', 'BGS', 'BIG', 'BJ', 'BL', 'BLBD', 'BLDR', 'BLMN', 'BLNK',
        'BOOT', 'BRC', 'BRP', 'BSET', 'BTBT', 'BURL', 'BYON', 'CABO', 'CAL', 'CALM',
        
        # Financial Services (small-cap)
        'ABCB', 'ABG', 'ABR', 'ACGL', 'AJG', 'AKR',
        
        # Energy (small-cap)
        'AROC', 'ARLP', 'BATL', 'BKR', 'BOOM', 'BRY', 'BTU', 'CEIX', 'CLB',
        
        # Real Estate (small-cap REITs)
        'ACRE', 'ADC', 'AGNC', 'AHH', 'AHT', 'ALX', 'AMH', 'AMT', 'APLE', 'APTS',
        
        # Utilities (small-cap)
        'AEE', 'AEP', 'AES', 'AGR', 'AWR', 'AY', 'BEP', 'BIP', 'BKH', 'BMS',
        
        # Materials
        'AA', 'AAON', 'AAN', 'AAT', 'AAWW', 'AB', 'ADNT', 'AEM', 'AGCO',
        
        # Consumer Discretionary
        'ACV', 'AEO', 'AFRM', 'AIRC', 'AJRD', 'AKRO', 'ALG',
        
        # Communication Services
        'AUDC', 'AVYA', 'BAND', 'BCOM', 'BIDU',
        
        # Additional diversified small-caps
        'AIV', 'AMGN', 'BIIB',
    ]
    
    # Remove duplicates and return
    unique_tickers = list(set(tickers))
    logger.info(f"Extended small-cap list: {len(unique_tickers)} unique tickers")
    return unique_tickers


def get_russell2000_tickers(use_file: bool = True, file_path: str = "data/russell2000_tickers.csv") -> List[str]:
    """
    Get Russell 2000 tickers using best available method
    
    Priority:
    1. CSV file (if exists)
    2. Web source
    3. Fallback list
    
    Args:
        use_file: Try to load from CSV file first
        file_path: Path to CSV file with tickers
    
    Returns:
        List of ticker symbols
    """
    # Try file first
    if use_file and os.path.exists(file_path):
        tickers = get_russell2000_tickers_from_file(file_path)
        if tickers:
            return tickers
    
    # Try web
    tickers = get_russell2000_tickers_from_web()
    if tickers:
        return tickers
    
    # Fallback
    logger.warning("Using fallback ticker list - consider adding russell2000_tickers.csv")
    return get_fallback_ticker_list()


def create_russell2000_template(file_path: str = "data/russell2000_tickers.csv"):
    """
    Create a template CSV file for Russell 2000 tickers
    User can populate this with actual tickers from official source
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Create template with sample tickers
    sample_tickers = get_fallback_ticker_list()
    df = pd.DataFrame({'ticker': sample_tickers})
    df.to_csv(file_path, index=False)
    
    logger.info(f"Created template file: {file_path}")
    logger.info("Please populate with actual Russell 2000 tickers from official source")
