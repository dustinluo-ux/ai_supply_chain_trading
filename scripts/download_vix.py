from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OUT_PATH = Path(r"C:\ai_supply_chain_trading\trading_data\benchmarks\VIX.csv")


def ensure_vix_csv() -> Path:
    token = os.getenv("EODHD_API_KEY", "").strip()
    if not token:
        raise RuntimeError("EODHD_API_KEY not found in .env")

    url = f"https://eodhd.com/api/eod/VIX.INDX?api_token={token}&fmt=csv&from=2021-01-01"
    r = requests.get(url, timeout=60)
    r.raise_for_status()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(r.text, encoding="utf-8")

    df = pd.read_csv(OUT_PATH)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "close" not in df.columns and "adjusted_close" in df.columns:
        df["close"] = df["adjusted_close"]
    df.to_csv(OUT_PATH, index=False)
    return OUT_PATH


def main() -> int:
    try:
        out = ensure_vix_csv()
        n_rows = len(pd.read_csv(out))
        print(f"Done: {n_rows} rows written to {out}", flush=True)
        return 0
    except Exception as e:
        print(f"[ERROR] Could not download VIX: {e}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

