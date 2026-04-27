"""
Compare data/tickers.csv (stocks only) to config/universe.yaml pillars. Read-only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
TICKERS_CSV = ROOT / "data" / "tickers.csv"
UNIVERSE_PATH = ROOT / "config" / "universe.yaml"


def _flatten_pillars(pillars: dict) -> set[str]:
    out: set[str] = set()
    for lst in pillars.values():
        if isinstance(lst, list):
            for x in lst:
                if isinstance(x, str) and x.strip():
                    out.add(x.strip().upper())
    return out


def _pillar_for_ticker(pillars: dict, sym: str) -> str:
    u = sym.strip().upper()
    for pname, lst in pillars.items():
        if not isinstance(lst, list):
            continue
        for x in lst:
            if isinstance(x, str) and x.strip().upper() == u:
                return str(pname)
    return ""


def main() -> int:
    if not TICKERS_CSV.exists() or not UNIVERSE_PATH.exists():
        print("[WARN] missing tickers.csv or universe.yaml", flush=True)
        return 0
    df = pd.read_csv(TICKERS_CSV)
    df.columns = [str(c).lower() for c in df.columns]
    stocks = df[df["type"].astype(str).str.lower().eq("stock")]
    csv_syms = {
        str(r["ticker"]).strip().upper()
        for _, r in stocks.iterrows()
        if pd.notna(r.get("ticker"))
    }
    u = yaml.safe_load(UNIVERSE_PATH.read_text(encoding="utf-8")) or {}
    pillars = u.get("pillars") or {}
    if not isinstance(pillars, dict):
        pillars = {}
    uni = _flatten_pillars(pillars)
    new = sorted(csv_syms - uni)
    removed = sorted(uni - csv_syms)
    unchanged = sorted(csv_syms & uni)
    layer_by = {
        str(r["ticker"]).strip().upper(): str(r.get("supply_chain_layer", ""))
        for _, r in stocks.iterrows()
    }
    stance_by = {
        str(r["ticker"]).strip().upper(): str(r.get("stance", ""))
        for _, r in stocks.iterrows()
    }

    rows: list[tuple[str, str, str, str]] = []
    for t in new:
        rows.append((t, layer_by.get(t, ""), stance_by.get(t, ""), "new"))
    for t in removed:
        rows.append((t, _pillar_for_ticker(pillars, t), "", "removed"))
    for t in unchanged:
        rows.append((t, layer_by.get(t, ""), stance_by.get(t, ""), "unchanged"))
    rows.sort(key=lambda x: (x[3], x[0]))
    w1, w2, w3, w4 = 8, 24, 10, 12
    print(
        f"{'ticker':<{w1}} | {'layer':<{w2}} | {'stance':<{w3}} | {'status':<{w4}}",
        flush=True,
    )
    print("-" * (w1 + w2 + w3 + w4 + 9), flush=True)
    for t, ly, st, stu in rows:
        print(f"{t:<{w1}} | {ly:<{w2}} | {st:<{w3}} | {stu:<{w4}}", flush=True)
    print(
        f"[SUMMARY] new={len(new)} removed={len(removed)} unchanged={len(unchanged)} (stocks only)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
