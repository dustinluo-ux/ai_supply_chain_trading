"""
Standalone fill reconciliation: compare ledger positions to last signal.

Reads outputs/fills/fills.jsonl, computes net position per ticker, marks to market
via price CSVs, compares to outputs/last_signal.json. Prints table and writes
outputs/fill_reconciliation_YYYY-MM-DD.md.

Usage:
  python scripts/reconcile_fills.py [--fills PATH] [--signal PATH]

Defaults: fills → outputs/fills/fills.jsonl, signal → outputs/last_signal.json.
Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile fills to last signal.")
    parser.add_argument(
        "--fills",
        type=Path,
        default=ROOT / "outputs" / "fills" / "fills.jsonl",
        help="Path to fills.jsonl",
    )
    parser.add_argument(
        "--signal",
        type=Path,
        default=ROOT / "outputs" / "last_signal.json",
        help="Path to last_signal.json",
    )
    args = parser.parse_args()

    from src.execution.fill_ledger import read_fill_ledger

    records = read_fill_ledger(args.fills)
    if not records:
        print("No fills recorded yet.", flush=True)
        return 0

    # Net position per ticker and weighted avg fill price (BUY only; skip records with no avg_fill_price)
    net_position: dict[str, int] = {}
    total_cost: dict[str, float] = {}
    total_qty_buys: dict[str, float] = {}
    for r in records:
        if (r.get("status") or "") == "mock_skip":
            continue
        qty = int(r.get("qty_filled") or 0)
        if qty <= 0:
            continue
        ticker = (r.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        side = (r.get("side") or "").upper()
        if side == "BUY":
            net_position[ticker] = net_position.get(ticker, 0) + qty
            avg_p = r.get("avg_fill_price")
            if avg_p is not None:
                try:
                    ap = float(avg_p)
                    if ap == ap:  # not NaN
                        total_cost[ticker] = total_cost.get(ticker, 0) + qty * ap
                        total_qty_buys[ticker] = total_qty_buys.get(ticker, 0) + qty
                except (TypeError, ValueError):
                    pass
        elif side == "SELL":
            net_position[ticker] = net_position.get(ticker, 0) - qty
    avg_fill_held: dict[str, float | None] = {}
    for t in set(total_cost.keys()) | set(total_qty_buys.keys()):
        qb = total_qty_buys.get(t, 0)
        if qb > 0:
            avg_fill_held[t] = total_cost.get(t, 0) / qb
        else:
            avg_fill_held[t] = None

    # Last signal
    last_signal: dict = {}
    if args.signal.exists():
        try:
            with open(args.signal, "r", encoding="utf-8") as f:
                last_signal = json.load(f) or {}
        except Exception:
            pass

    all_tickers = sorted(set(net_position.keys()) | set(last_signal.keys()))
    if not all_tickers:
        print("No tickers in fills or signal.", flush=True)
        return 0

    # Load prices (last close per ticker)
    try:
        from src.data.csv_provider import load_data_config, load_prices
    except Exception as e:
        print(f"WARN: Could not load prices: {e}", flush=True)
        prices_dict = {}
    else:
        data_cfg = load_data_config()
        data_dir = Path(data_cfg["data_dir"])
        prices_dict = load_prices(data_dir, all_tickers)

    last_close: dict[str, float | None] = {}
    for t, df in prices_dict.items():
        if df is None or df.empty or "close" not in df.columns:
            last_close[t] = None
            continue
        try:
            idx = df.index.sort_values()
            last_date = idx[-1]
            last_close[t] = float(df.loc[last_date, "close"])
        except Exception:
            last_close[t] = None
    for t in all_tickers:
        if t not in last_close:
            last_close[t] = None

    # Build rows: intended_qty, held_qty, avg_fill, last_price, cost_basis, market_value, unreal_pnl, status
    today_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    rows: list[tuple] = []

    for ticker in all_tickers:
        sig = last_signal.get(ticker) or {}
        weight = float(sig.get("weight") or 0)
        intended_qty = int(sig.get("notional_units") or 0) if weight > 0 else 0
        held_qty = net_position.get(ticker, 0)
        price = last_close.get(ticker)
        avg_fill = avg_fill_held.get(ticker)
        cost_basis = (avg_fill * held_qty) if (avg_fill is not None and held_qty != 0) else None
        market_value = (held_qty * price) if (price is not None and held_qty != 0) else None
        unreal_pnl = ((price - avg_fill) * held_qty) if (price is not None and avg_fill is not None and held_qty != 0) else None

        # Status
        if intended_qty == 0 and held_qty == 0:
            status = "FLAT"
        elif held_qty > 0 and intended_qty == 0:
            status = "UNINTENDED"
        elif intended_qty > 0 and held_qty == 0:
            status = "MISSING"
        elif intended_qty > 0:
            tol = max(1, 0.05 * intended_qty)
            if abs(held_qty - intended_qty) <= tol:
                status = "MATCHED"
            elif held_qty > intended_qty * 1.05:
                status = "OVER"
            elif held_qty < intended_qty * 0.95:
                status = "UNDER"
            else:
                status = "MATCHED"
        else:
            status = "FLAT"

        rows.append((ticker, intended_qty, held_qty, avg_fill, price, cost_basis, market_value, unreal_pnl, status))

    # Sort: non-flat first, then by ticker
    rows.sort(key=lambda r: (0 if (r[1] != 0 or r[2] != 0) else 1, r[0]))

    # Format helpers: currency by ticker (.T, .HK → ¥ else $)
    def _currency(ticker: str) -> str:
        return "¥" if ".T" in ticker or ".HK" in ticker else "$"

    def _fmt_price(ticker: str, p: float | None) -> str:
        if p is None:
            return "—"
        c = _currency(ticker)
        if c == "¥":
            return f"¥{p:,.2f}"
        return f"${p:,.2f}"

    def _fmt_mv(ticker: str, mv: float | None) -> str:
        if mv is None:
            return "—"
        c = _currency(ticker)
        return f"{c}{mv:,.0f}"

    def _fmt_pnl(pnl: float | None) -> str:
        if pnl is None:
            return "—"
        if pnl >= 0:
            return f"+${pnl:,.0f}"
        return f"-${abs(pnl):,.0f}"

    # Build report text — columns: Ticker, Intended Qty, Held Qty, Avg Fill, Last Price, Cost Basis, Mkt Value, Unreal PnL, Status
    lines = [
        f"=== Fill Reconciliation — {today_str} ===",
        f"Last signal: {today_str}   Active positions in ledger: {sum(1 for r in rows if r[2] != 0)}",
        "",
        "  Ticker     Intended Qty   Held Qty   Avg Fill   Last Price   Cost Basis   Mkt Value   Unreal PnL   Status",
        "  " + "─" * 95,
    ]
    for r in rows:
        ticker, iq, hq, avg_fill, price, cost_basis, mv, pnl, status = r
        af_s = _fmt_price(ticker, avg_fill)
        pr_s = _fmt_price(ticker, price)
        cb_s = _fmt_mv(ticker, cost_basis) if cost_basis is not None else "—"
        mv_s = _fmt_mv(ticker, mv)
        pnl_s = _fmt_pnl(pnl)
        lines.append(
            f"  {ticker:<10} {iq:>12,} {hq:>10,}   {af_s:>9}   {pr_s:>11}   {cb_s:>11}   {mv_s:>10}   {pnl_s:>11}   {status}"
        )
    matched = sum(1 for r in rows if r[8] == "MATCHED")
    unintended = sum(1 for r in rows if r[8] == "UNINTENDED")
    missing = sum(1 for r in rows if r[8] == "MISSING")
    flat = sum(1 for r in rows if r[8] == "FLAT")
    over_under = sum(1 for r in rows if r[8] in ("OVER", "UNDER"))
    total_notional = sum(r[6] for r in rows if r[6] is not None)
    lines.extend([
        "",
        "  SUMMARY",
        f"    Matched:    {matched}    Unintended: {unintended}",
        f"    Missing:    {missing}    Flat:       {flat}",
        f"    Diverged:   {over_under}    (OVER + UNDER)",
        f"    Total held notional: ${total_notional:,.0f}",
    ])
    total_cost_basis = sum(r[5] for r in rows if r[5] is not None)
    total_mkt_value = sum(r[6] for r in rows if r[6] is not None)
    if total_cost_basis and total_cost_basis > 0:
        unreal_pnl_total = total_mkt_value - total_cost_basis
        pct = 100.0 * unreal_pnl_total / total_cost_basis
        pct_s = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"
        pnl_total_s = f"+${unreal_pnl_total:,.0f}" if unreal_pnl_total >= 0 else f"-${abs(unreal_pnl_total):,.0f}"
        lines.extend([
            "  " + "─" * 50,
            f"  Total Cost Basis:    ${total_cost_basis:,.0f}",
            f"  Total Market Value:  ${total_mkt_value:,.0f}",
            f"  Unrealized PnL:      {pnl_total_s}  ({pct_s})",
        ])
    else:
        lines.append("  Note: avg_fill_price unavailable until sync_fills_from_ibkr.py is run.")
    report = "\n".join(lines)
    print(report, flush=True)

    out_path = ROOT / "outputs" / f"fill_reconciliation_{today_str}.md"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    except Exception as e:
        print(f"WARN: Could not write {out_path}: {e}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(_main())
