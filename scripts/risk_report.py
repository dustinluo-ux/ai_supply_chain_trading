"""
Risk report: drawdown, vol, beta, VaR from trading.db portfolio_daily.

Reads last_optimized_weights.json for max concentration; queries portfolio_daily
for returns, computes equity curve, max drawdown, 20d vol, beta vs SPY, VaR 95%.
Writes outputs/risk_report_YYYY-MM-DD.md. Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Risk report from portfolio_daily.")
    parser.add_argument("--db", type=Path, default=ROOT / "outputs" / "trading.db", help="Path to trading.db")
    parser.add_argument("--weights", type=Path, default=ROOT / "outputs" / "last_optimized_weights.json", help="Path to last_optimized_weights.json")
    args = parser.parse_args()

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Load weights → max concentration
    weights: dict = {}
    if args.weights.exists():
        try:
            with open(args.weights, "r", encoding="utf-8") as f:
                data = json.load(f)
            weights = data.get("weights") or {}
        except Exception:
            pass
    max_conc = (max(weights.values()) * 100) if weights else None

    # 2. Query portfolio_daily
    if not args.db.exists():
        n_rows = 0
        df = pd.DataFrame(columns=["date", "port_return", "spy_return"])
    else:
        try:
            conn = sqlite3.connect(str(args.db))
            df = pd.read_sql_query(
                "SELECT date, port_return, spy_return FROM portfolio_daily ORDER BY date",
                conn,
            )
            conn.close()
        except Exception:
            df = pd.DataFrame(columns=["date", "port_return", "spy_return"])
    n_rows = len(df)

    if n_rows == 0:
        max_dd = None
        port_vol_20d = None
        spy_vol_20d = None
        beta = None
        var_95 = None
        latest_return = None
    else:
        # 3. Equity curve
        df["port_return"] = pd.to_numeric(df["port_return"], errors="coerce").fillna(0)
        df["spy_return"] = pd.to_numeric(df["spy_return"], errors="coerce").fillna(0)
        equity = (1 + df["port_return"]).cumprod()
        equity.iloc[0] = 1.0

        # 4. Max drawdown
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_dd = float(drawdown.min())

        # 5. Metrics requiring >= 20 rows
        if n_rows >= 20:
            port_last = df["port_return"].iloc[-20:]
            spy_last = df["spy_return"].iloc[-20:]
            port_vol_20d = float(port_last.std() * np.sqrt(252)) * 100
            spy_vol_20d = float(spy_last.std() * np.sqrt(252)) * 100
            cov = np.cov(port_last, spy_last)
            var_spy = np.var(spy_last)
            beta = float(cov[0, 1] / var_spy) if var_spy > 0 else None
            var_95 = float(np.percentile(port_last, 5)) * 100
        else:
            port_vol_20d = None
            spy_vol_20d = None
            beta = None
            var_95 = None

        # 6. Latest daily return
        latest_return = float(df["port_return"].iloc[-1]) * 100

    # 7. Build report text
    lines = [
        f"=== Risk Report — {today_str} ===",
        f"Data window: {n_rows} trading days",
        "",
        "PORTFOLIO METRICS",
        f"  Max Drawdown:        {max_dd:.2%}" if max_dd is not None else "  Max Drawdown:        N/A",
        f"  Port Vol (20d ann.): {port_vol_20d:.2f}%" if port_vol_20d is not None else "  Port Vol (20d ann.): N/A",
        f"  Beta vs SPY:         {beta:.2f}" if beta is not None else "  Beta vs SPY:         N/A",
        f"  VaR 95% 1d:         {var_95:.2f}%" if var_95 is not None else "  VaR 95% 1d:         N/A",
        "",
        "POSITION RISK",
        f"  Active Positions:    {len(weights)}",
        f"  Max Concentration:   {max_conc:.1f}%" if max_conc is not None else "  Max Concentration:   N/A",
        f"  Latest Daily Return: {latest_return:+.2f}%" if latest_return is not None else "  Latest Daily Return: N/A",
        "",
        "RISK STATUS",
    ]
    dd_breach = max_dd is not None and max_dd < -0.10
    daily_breach = latest_return is not None and latest_return < -3.0
    if dd_breach:
        lines.append("  Drawdown guard:   BREACH")
    else:
        lines.append("  Drawdown guard:   OK")
    if daily_breach:
        lines.append("  Daily loss guard: BREACH")
    else:
        lines.append("  Daily loss guard: OK")

    report = "\n".join(lines)
    print(report, flush=True)

    # 8. Write to file
    out_path = ROOT / "outputs" / f"risk_report_{today_str}.md"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    except Exception as e:
        print(f"WARN: Could not write {out_path}: {e}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(_main())
