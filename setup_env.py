"""
Setup script to create .env file from template
Run this once to set up your environment
"""
import os
from pathlib import Path

def create_env_file():
    """Create .env file from template if it doesn't exist"""
    project_root = Path(__file__).parent
    env_path = project_root / ".env"
    template_path = project_root / ".env.template"
    
    if env_path.exists():
        print(f"[OK] .env file already exists at {env_path}")
        return
    
    if not template_path.exists():
        # Create template if it doesn't exist
        template_content = """# API Keys - Fill in your keys below

# News API Keys (choose based on source in config.yaml)
# NewsAPI (free tier: 100 requests/day)
# Get key from: https://newsapi.org/register
NEWS_API_KEY=your_newsapi_key_here

# Alpha Vantage (free tier: 5 calls/min, 500/day, has historical data)
# Get key from: https://www.alphavantage.co/support/#api-key
ALPHAVANTAGE_API_KEY=your_alphavantage_key_here

# Finnhub (free tier: 60 calls/min)
# Get key from: https://finnhub.io/register
FINNHUB_API_KEY=your_finnhub_key_here

# LLM API Keys (choose based on provider in config.yaml)
# Gemini 2.0 Flash (free tier available, recommended)
# Get key from: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_key_here
# Note: FinBERT (local, free) - no API key needed if using FinBERT

# Alpaca Trading API (for paper trading in Phase 4)
# Get key from: https://alpaca.markets/
ALPACA_API_KEY=your_alpaca_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
"""
        with open(template_path, 'w') as f:
            f.write(template_content)
        print(f"[OK] Created .env.template at {template_path}")
    
    # Create .env from template
    with open(template_path, 'r') as f:
        template = f.read()
    
    with open(env_path, 'w') as f:
        f.write(template)
    
    print(f"[OK] Created .env file at {env_path}")
    print("\n[IMPORTANT] Edit .env file and add your API keys!")
    print("   News Source API Keys (choose based on config.yaml):")
    print("   - NEWS_API_KEY: https://newsapi.org/register")
    print("   - ALPHAVANTAGE_API_KEY: https://www.alphavantage.co/support/#api-key (recommended - has historical data)")
    print("   - FINNHUB_API_KEY: https://finnhub.io/register")
    print("   - GEMINI_API_KEY: https://aistudio.google.com/app/apikey (for Gemini LLM, recommended)")
    print("   - ALPACA keys: https://alpaca.markets/ (for Phase 4)")
    print("\nLLM Options:")
    print("   - Gemini 2.0 Flash: Requires GEMINI_API_KEY (free tier available)")
    print("   - FinBERT: Local, free, no API key needed")

if __name__ == "__main__":
    create_env_file()
