"""
One-time migration: data/tickers.csv -> config/universe.yaml (pillars, ticker_meta, layer_etfs) + sync_universe.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sync_universe import sync_universe

TICKERS_CSV = ROOT / "data" / "tickers.csv"
UNIVERSE_PATH = ROOT / "config" / "universe.yaml"
DATA_CONFIG_PATH = ROOT / "config" / "data_config.yaml"

LAYER_ETFS: dict[str, list[str]] = {
    "application": ["AIQ", "ARKQ", "BOTZ", "ROBO"],
    "compute": ["SMH", "SOXX"],
    "energy": ["ICLN", "XLU"],
    "infrastructure": ["SRVR", "VPN"],
    "model": ["CHAT"],
}


def _pillar_key_for_layer(layer_raw: str) -> str:
    s = str(layer_raw).strip().lower()
    if s == "infrastructure":
        return "infra"
    return s


def _flatten_universe_tickers(pillars: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(pillars, dict):
        return out
    for _k, v in pillars.items():
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.strip():
                    out.add(item.strip().upper())
    return out


def _find_pillar_of_ticker(pillars: dict[str, Any], ticker: str) -> str | None:
    u = ticker.strip().upper()
    for pname, lst in pillars.items():
        if not isinstance(lst, list):
            continue
        for x in lst:
            if isinstance(x, str) and x.strip().upper() == u:
                return str(pname)
    return None


def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    txt = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    tmp.write_text(txt, encoding="utf-8")
    if len(tmp.read_text(encoding="utf-8")) == 0:
        tmp.unlink(missing_ok=True)
        raise SystemExit(1)
    r = yaml.safe_load(tmp.read_text(encoding="utf-8"))
    if not isinstance(r, dict):
        tmp.unlink(missing_ok=True)
        raise SystemExit(1)
    os.replace(tmp, path)


def main() -> int:
    if not TICKERS_CSV.exists():
        print(f"[ERROR] missing {TICKERS_CSV}", flush=True)
        return 1
    df = pd.read_csv(TICKERS_CSV)
    required = {"ticker", "company", "supply_chain_layer", "stance", "type", "note"}
    if not required.issubset(set(df.columns.str.lower())):
        print("[ERROR] tickers.csv missing required columns", flush=True)
        return 1
    df.columns = [str(c).lower() for c in df.columns]

    u = yaml.safe_load(UNIVERSE_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(u, dict):
        print("[ERROR] invalid universe.yaml", flush=True)
        return 1
    pillars = u.get("pillars")
    if not isinstance(pillars, dict):
        pillars = {}
    existing = _flatten_universe_tickers(pillars)
    added_per: dict[str, int] = {
        k: 0
        for k in set(
            list(pillars.keys())
            + [
                "application",
                "model",
                "infra",
                "compute",
                "energy",
                "adoption",
                "global",
            ]
        )
    }

    for _, row in df.iterrows():
        if str(row.get("type", "")).strip().lower() != "stock":
            continue
        sym = str(row.get("ticker", "")).strip().upper()
        if not sym or sym in existing:
            continue
        layer = str(row.get("supply_chain_layer", "")).strip()
        pk = _pillar_key_for_layer(layer)
        if pk not in pillars:
            pillars[pk] = []
        if not isinstance(pillars[pk], list):
            pillars[pk] = []
        cur = {str(x).strip().upper() for x in pillars[pk] if isinstance(x, str)}
        if sym not in cur:
            pillars[pk].append(sym)
            added_per[pk] = added_per.get(pk, 0) + 1
            existing.add(sym)

    u["pillars"] = pillars
    ticker_meta: dict[str, Any] = {}
    for _, row in df.iterrows():
        sym = str(row.get("ticker", "")).strip().upper()
        if not sym:
            continue
        ticker_meta[sym] = {
            "stance": str(row.get("stance", "neutral")).strip().lower(),
            "supply_chain_layer": str(row.get("supply_chain_layer", "")).strip(),
            "type": str(row.get("type", "stock")).strip().lower(),
        }
    for sym in sorted(existing):
        if sym in ticker_meta:
            continue
        pname = _find_pillar_of_ticker(pillars, sym)
        if pname is None:
            continue
        ticker_meta[sym] = {
            "stance": "bullish",
            "supply_chain_layer": str(pname),
            "type": "stock",
        }
    u["ticker_meta"] = ticker_meta
    u["layer_etfs"] = {
        k: [str(x).strip().upper() for x in v] for k, v in LAYER_ETFS.items()
    }

    try:
        _atomic_write_yaml(UNIVERSE_PATH, u)
    except Exception as exc:
        print(f"[ERROR] universe write: {exc}", flush=True)
        return 1

    try:
        sync_universe(UNIVERSE_PATH, DATA_CONFIG_PATH)
    except Exception as exc:
        print(f"[ERROR] sync_universe: {exc}", flush=True)
        return 1

    print("[SUMMARY] tickers added per pillar:", flush=True)
    for k, v in sorted(added_per.items()):
        if v:
            print(f"  {k}: +{v}", flush=True)
    print(f"[SUMMARY] ticker_meta entries: {len(ticker_meta)}", flush=True)
    print(f"[SUMMARY] layer_etfs layers: {list(u['layer_etfs'].keys())}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
