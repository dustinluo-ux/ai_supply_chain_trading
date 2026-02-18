"""
Minimal type aliases / data structures for data_context and context
passed between engines. No behavior; caller-specific shape.
"""
from __future__ import annotations

from typing import Any

# DataContext: everything needed for signal generation (prices_dict, spy_bench,
# news_dir, config bits, or precomputed combiner for weekly path).
# Shape differs by caller; engines accept dict-like or namespace.
DataContext = dict[str, Any]

# Context: everything needed for policy and portfolio (regime_state,
# spy_below_sma200, sideways_risk_scale, top_n, weight_mode, ledger_path, etc.).
# Caller-specific; engines accept dict-like.
Context = dict[str, Any]
