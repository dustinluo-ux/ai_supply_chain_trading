"""
Sync canonical 40-ticker universe from config/universe.yaml to config/data_config.yaml.

Flattens pillar lists (excludes benchmark), updates watchlist and max_tickers,
ensures trading_data/news/raw_bulk exists. No CLI args.

Usage:
  python scripts/sync_universe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML required.", flush=True)
        return 1

    universe_path = ROOT / "config" / "universe.yaml"
    if not universe_path.exists():
        print(f"ERROR: {universe_path} not found.", flush=True)
        return 1

    try:
        with open(universe_path, "r", encoding="utf-8") as f:
            universe = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to load universe.yaml: {e}", flush=True)
        return 1

    pillars = universe.get("pillars") or {}
    benchmark = universe.get("benchmark") or "SPY"
    tickers_set = set()
    for pillar_list in pillars.values():
        if isinstance(pillar_list, list):
            for t in pillar_list:
                if isinstance(t, str) and t.strip():
                    tickers_set.add(t.strip().upper())
    if benchmark in tickers_set:
        tickers_set.discard(benchmark)
    tickers = sorted(tickers_set)

    data_config_path = ROOT / "config" / "data_config.yaml"
    if not data_config_path.exists():
        print(f"ERROR: {data_config_path} not found.", flush=True)
        return 1

    try:
        from ruamel.yaml import YAML
        ryml = YAML()
        ryml.preserve_quotes = True
        with open(data_config_path, "r", encoding="utf-8") as f:
            data_cfg = ryml.load(f)
        use_ruamel = True
    except ImportError:
        use_ruamel = False
        print("Note: ruamel.yaml not available; using PyYAML (comments may be lost).", flush=True)
        with open(data_config_path, "r", encoding="utf-8") as f:
            data_cfg = yaml.safe_load(f)

    if "universe_selection" not in data_cfg:
        data_cfg["universe_selection"] = {}
    data_cfg["universe_selection"]["watchlist"] = tickers
    data_cfg["universe_selection"]["max_tickers"] = 40

    try:
        if use_ruamel:
            with open(data_config_path, "w", encoding="utf-8") as f:
                ryml.dump(data_cfg, f)
        else:
            with open(data_config_path, "w", encoding="utf-8") as f:
                yaml.dump(data_cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception as e:
        print(f"ERROR: Failed to write data_config.yaml: {e}", flush=True)
        return 1

    data_dir = data_cfg.get("data_sources") or {}
    data_dir_str = data_dir.get("data_dir", str(ROOT / "trading_data" / "stock_market_data"))
    data_dir_path = Path(data_dir_str)
    raw_bulk = data_dir_path.parent / "news" / "raw_bulk"
    raw_bulk.mkdir(parents=True, exist_ok=True)
    print(f"Directory ensured: {raw_bulk}", flush=True)

    print(f"Synced {len(tickers)} tickers to data_config.yaml", flush=True)
    print(", ".join(tickers), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
