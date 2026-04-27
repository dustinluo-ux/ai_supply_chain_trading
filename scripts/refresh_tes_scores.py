"""
Refresh TES proxy scores (Damodaran anchor) for universe tickers → DATA_DIR/tes_scores.json.

See docs/DECISIONS.md D023. Fail-open defaults; atomic write.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

UNIVERSE_PATH = ROOT / "config" / "universe.yaml"
STRATEGY_PARAMS_PATH = ROOT / "config" / "strategy_params.yaml"
DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
OUT_FILE = DATA_DIR / "tes_scores.json"
TMP_FILE = DATA_DIR / "tes_scores.json.tmp"


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    if not isinstance(obj, dict):
        return {}
    return obj


def _flatten_tickers(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, str):
                out.append(item.strip())
            else:
                out.extend(_flatten_tickers(item))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_flatten_tickers(v))
    return out


def _load_universe_tickers() -> list[str]:
    universe = _read_yaml(UNIVERSE_PATH)
    tickers: list[str] = []
    if "pillars" in universe:
        tickers.extend(_flatten_tickers(universe.get("pillars")))
    if "global_equities" in universe:
        tickers.extend(_flatten_tickers(universe.get("global_equities")))
    if "global" in (universe.get("pillars") or {}):
        tickers.extend(_flatten_tickers((universe.get("pillars") or {}).get("global")))
    tickers = [t for t in tickers if t and isinstance(t, str)]
    return sorted(set(tickers))


def _load_tes_config() -> tuple[bool, float, float | None]:
    """tes_enabled (default True), tes_min_mult (default 0.5), optional tes_score_cap."""
    tes_enabled = True
    tes_min_mult = 0.5
    tes_score_cap: float | None = None
    if not STRATEGY_PARAMS_PATH.exists():
        return tes_enabled, tes_min_mult, tes_score_cap
    try:
        raw = _read_yaml(STRATEGY_PARAMS_PATH)
        tes = raw.get("tes") or {}
        if "tes_enabled" in tes:
            tes_enabled = bool(tes["tes_enabled"])
        tes_min_mult = float(tes.get("tes_min_mult", 0.5))
        if tes.get("tes_score_cap") is not None:
            tes_score_cap = float(tes["tes_score_cap"])
    except Exception:
        pass
    return tes_enabled, tes_min_mult, tes_score_cap


def _anchor_failed(res) -> bool:
    d = getattr(res, "details", None) or {}
    return bool(d.get("error"))


def _normalized_anchor_score(res) -> float:
    """Normalized [0,1] fundamentals proxy from Damodaran anchor (success path only)."""
    mx = max(int(getattr(res, "max_score", 1) or 1), 1)
    sc = int(getattr(res, "score", 0) or 0)
    return max(0.0, min(1.0, float(sc) / float(mx)))


def _compute_multiplier(
    s: float,
    failed: bool,
    S: float,
    tes_min_mult: float,
) -> float:
    if failed:
        return 1.0
    if s <= 0.0:
        return float(max(0.0, min(1.0, tes_min_mult)))
    if S <= 0:
        return 1.0
    raw = tes_min_mult + (1.0 - tes_min_mult) * (s / S)
    return float(max(tes_min_mult, min(1.0, raw)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh TES proxy scores → DATA_DIR/tes_scores.json"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print scores; do not write file"
    )
    args = parser.parse_args()

    tes_enabled, tes_min_mult, tes_score_cap = _load_tes_config()
    if not tes_enabled and not args.dry_run:
        print(
            "[TES] tes_enabled=false in strategy_params — nothing written.", flush=True
        )
        return 0

    tickers = _load_universe_tickers()
    if not tickers:
        print("[ERROR] No tickers in config/universe.yaml", flush=True)
        return 1

    analysis_date = date.today().isoformat()
    from src.agents.damodaran_anchor import anchor_ticker

    audited_at = datetime.now(timezone.utc).isoformat()
    per_ticker: list[tuple[str, bool, float]] = []
    success_scores: list[float] = []

    for t in tickers:
        res = anchor_ticker(t, analysis_date)
        failed = _anchor_failed(res)
        if failed:
            s = 0.5
        else:
            s = _normalized_anchor_score(res)
            success_scores.append(s)
        per_ticker.append((t, failed, s))

    mx = max(success_scores) if success_scores else 0.0
    S = mx if mx > 0 else 1.0
    if tes_score_cap is not None:
        S = max(S, float(tes_score_cap))

    rows: dict[str, dict[str, Any]] = {}
    for t, failed, s in per_ticker:
        conf = "STUB" if failed else "ESTIMATED"
        mult = _compute_multiplier(s, failed, S, tes_min_mult)
        rows[t.upper()] = {
            "tes_score": float(s),
            "data_confidence": conf,
            "audited_at": audited_at,
            "multiplier": mult,
        }

    if args.dry_run:
        print(json.dumps(rows, indent=2, default=str))
        print("[DRY-RUN] no file written", flush=True)
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(rows, indent=2, default=str)
    if len(body) < 10:
        print("[ERROR] serialized output too small", flush=True)
        return 1
    TMP_FILE.write_text(body, encoding="utf-8")
    if TMP_FILE.stat().st_size < 10:
        print("[ERROR] temp file unexpectedly small", flush=True)
        return 1
    os.replace(TMP_FILE, OUT_FILE)
    print(f"[TES] wrote {OUT_FILE} ({len(rows)} tickers)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
