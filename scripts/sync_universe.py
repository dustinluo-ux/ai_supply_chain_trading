"""
Universe → data_config watchlist sync. Import `sync_universe` from this module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    return obj if isinstance(obj, dict) else {}


def _flatten_pillar_tickers(pillars: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(pillars, dict):
        return out
    for _k, v in pillars.items():
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    t = item.strip()
                    if t:
                        out.append(t)
                elif isinstance(item, dict):
                    out.extend(_flatten_pillar_tickers(item))
        elif isinstance(v, dict):
            out.extend(_flatten_pillar_tickers(v))
    return out


def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    tmp.write_text(text, encoding="utf-8")
    if len(tmp.read_text(encoding="utf-8")) == 0:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"refuse empty yaml write: {path}")
    loaded = yaml.safe_load(tmp.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        tmp.unlink(missing_ok=True)
        raise ValueError(f"invalid yaml round-trip: {path}")
    os.replace(tmp, path)


def _collect_universe_watchlist(universe_path: str | Path) -> list[str]:
    universe_path = Path(universe_path)
    universe = _read_yaml(universe_path)
    pillars = universe.get("pillars")
    tickers = sorted(set(_flatten_pillar_tickers(pillars)))
    ibkr = universe.get("ibkr_symbols") or {}
    if not isinstance(ibkr, dict):
        ibkr = {}
    missing_ibkr: list[str] = []
    for t in tickers:
        if "." in t and str(t) not in ibkr:
            missing_ibkr.append(t)
    if missing_ibkr:
        raise ValueError(f"ibkr_symbols missing for non-US tickers: {missing_ibkr}")
    return tickers


def sync_universe(universe_path: str | Path, data_config_path: str | Path) -> list[str]:
    universe_path = Path(universe_path)
    data_config_path = Path(data_config_path)
    tickers = _collect_universe_watchlist(universe_path)

    cfg = _read_yaml(data_config_path)
    usel = cfg.get("universe_selection")
    if not isinstance(usel, dict):
        usel = {}
    usel["watchlist"] = tickers
    usel["max_tickers"] = len(tickers)
    cfg["universe_selection"] = usel
    _atomic_write_yaml(data_config_path, cfg)
    return tickers
