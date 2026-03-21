"""One-time download of DELL EOD price history from EODHD."""
import os
import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("EODHD_API_KEY", "")
if not TOKEN:
    raise SystemExit("EODHD_API_KEY not found in .env")

url = f"https://eodhd.com/api/eod/DELL.US?api_token={TOKEN}&fmt=csv&from=2019-01-01"
r = requests.get(url, timeout=30)
r.raise_for_status()

out = Path(r"C:\ai_supply_chain_trading\trading_data\stock_market_data\nasdaq\csv\DELL.csv")
out.write_text(r.text, encoding="utf-8")
print(f"Done: {len(r.text.splitlines())} rows written to {out}")
