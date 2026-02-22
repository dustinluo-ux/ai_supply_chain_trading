"""
On-demand performance report.

Queries outputs/trading.db and generates a report for the last N calendar weeks.
Prints to console and writes to outputs/performance_report_YYYY-MM-DD.md.

Usage:
  python scripts/generate_performance_report.py [--weeks N] [--db PATH]

Default: --weeks 4. Exit 0 on success, 1 on error.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from scipy import stats as _sp_stats
    _SCIPY = True
except ImportError:
    _SCIPY = False


# ── Formatting helpers ────────────────────────────────────────────────────────

def _pct(v) -> str:
    if v is None:
        return "  N/A  "
    try:
        f = float(v)
        if np.isnan(f):
            return "  N/A  "
        return f"{f:+.2%}"
    except (TypeError, ValueError):
        return "  N/A  "


def _fmt(v, decimals: int = 3) -> str:
    if v is None:
        return "N/A"
    try:
        f = float(v)
        if np.isnan(f):
            return "N/A"
        return f"{f:.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate performance report from trading DB")
    parser.add_argument(
        "--weeks", type=int, default=4, help="Weeks to include in report (default: 4)"
    )
    parser.add_argument("--db", type=str, default=None, help="Path to trading.db")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else ROOT / "outputs" / "trading.db"
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", flush=True)
        print("Run: python scripts/update_signal_db.py", flush=True)
        return 1

    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    cutoff = (today - timedelta(weeks=args.weeks)).strftime("%Y-%m-%d")

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    port_rows = con.execute(
        "SELECT * FROM portfolio_daily WHERE date >= ? ORDER BY date", (cutoff,)
    ).fetchall()

    sig_rows = con.execute(
        "SELECT * FROM signals WHERE date >= ? ORDER BY date, ticker", (cutoff,)
    ).fetchall()

    fr_rows = con.execute(
        """SELECT f.signal_date, f.ticker, f.horizon, f.entry_price, f.exit_price,
                  f.return_pct, s.weight, s.score, s.vol_triggered
           FROM forward_returns f
           JOIN signals s ON f.signal_date = s.date AND f.ticker = s.ticker
           WHERE f.signal_date >= ?
           ORDER BY f.signal_date, f.ticker, f.horizon""",
        (cutoff,),
    ).fetchall()

    con.close()

    lines: list[str] = []

    def pr(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    pr(f"=== Performance Report: {args.weeks}-week window ending {today_str} ===")
    pr()

    # ── PORTFOLIO vs SPY ──────────────────────────────────────────────────────
    pr("PORTFOLIO vs SPY")
    if not port_rows:
        pr("  No portfolio data yet. Run update_signal_db.py after prices are updated.")
        pr()
    else:
        port_returns = [float(r["port_return"]) for r in port_rows if r["port_return"] is not None]
        spy_returns = [float(r["spy_return"]) for r in port_rows if r["spy_return"] is not None]

        if port_returns:
            # Equity curve
            equity = np.cumprod(np.array([1.0] + [1.0 + x for x in port_returns]))
            total_ret = float(equity[-1] - 1.0)
            running_max = np.maximum.accumulate(equity)
            dd = (running_max - equity) / np.where(running_max > 0, running_max, 1.0)
            max_dd = float(np.max(dd))
            std_r = float(np.std(port_returns))
            sharpe = (
                float(np.mean(port_returns) / std_r * np.sqrt(252)) if std_r > 0 else 0.0
            )

            spy_eq = np.cumprod(np.array([1.0] + [1.0 + x for x in spy_returns])) if spy_returns else np.array([1.0])
            spy_total = float(spy_eq[-1] - 1.0) if len(spy_eq) > 1 else 0.0
            total_alpha = total_ret - spy_total

            # Weekly win-rate
            port_df = pd.DataFrame([dict(r) for r in port_rows])
            port_df["date"] = pd.to_datetime(port_df["date"])
            port_df["week"] = port_df["date"].dt.to_period("W")
            weekly = port_df.groupby("week", sort=True).agg(
                port_ret=("port_return", "sum"),
                spy_ret=("spy_return", "sum"),
            )
            n_weeks = len(weekly)
            n_win = int((weekly["port_ret"] > weekly["spy_ret"]).sum())

            pr(f"  Total Return:    {_pct(total_ret)}    SPY: {_pct(spy_total)}    Alpha: {_pct(total_alpha)}")
            pr(f"  Sharpe (ann.):   {_fmt(sharpe, 2)}       Max Drawdown: {_pct(-max_dd)}")
            if n_weeks > 0:
                pr(f"  Win Rate vs SPY: {n_win}/{n_weeks} weeks  ({n_win / n_weeks:.0%})")
            else:
                pr("  Win Rate vs SPY: N/A")
            pr()

            # ── WEEKLY BREAKDOWN ──────────────────────────────────────────────
            pr("WEEKLY BREAKDOWN")
            pr(f"  {'Week':<14} {'Port':>8} {'SPY':>8} {'Alpha':>8}   Top Positions")
            pr("  " + "-" * 70)
            for wk, grp in port_df.groupby("week", sort=True):
                p_r = float(grp["port_return"].fillna(0).sum())
                s_r = float(grp["spy_return"].fillna(0).sum())
                a_r = p_r - s_r
                tickers_all: list[str] = []
                for held_str in grp["tickers_held"].dropna():
                    tickers_all.extend(str(held_str).split(","))
                tickers_uniq = list(dict.fromkeys(tickers_all))[:5]
                tickers_str = ", ".join(tickers_uniq) if tickers_uniq else "-"
                try:
                    wk_str = str(wk.start_time.date())
                except AttributeError:
                    wk_str = str(wk)[:10]
                pr(f"  {wk_str:<14} {_pct(p_r):>8} {_pct(s_r):>8} {_pct(a_r):>8}   {tickers_str}")
            pr()
        else:
            pr("  Portfolio return data present but all values are null.")
            pr()

    # ── TOP PICKS ─────────────────────────────────────────────────────────────
    pr("TOP PICKS (by selection frequency)")
    if fr_rows and sig_rows:
        fr_df = pd.DataFrame([dict(r) for r in fr_rows])
        sig_df = pd.DataFrame([dict(r) for r in sig_rows])

        active_sig = sig_df[sig_df["weight"].fillna(0).astype(float) > 0].copy()
        total_dates = sig_df["date"].nunique()

        if not active_sig.empty and total_dates > 0:
            fr_1d = fr_df[fr_df["horizon"] == "1d"][["signal_date", "ticker", "return_pct"]].rename(
                columns={"return_pct": "ret_1d", "signal_date": "date"}
            )
            fr_5d = fr_df[fr_df["horizon"] == "5d"][["signal_date", "ticker", "return_pct"]].rename(
                columns={"return_pct": "ret_5d", "signal_date": "date"}
            )
            picks = (
                active_sig
                .merge(fr_1d, on=["date", "ticker"], how="left")
                .merge(fr_5d, on=["date", "ticker"], how="left")
            )
            summary = (
                picks.groupby("ticker")
                .agg(
                    n_selected=("date", "count"),
                    avg_ret_1d=("ret_1d", "mean"),
                    avg_ret_5d=("ret_5d", "mean"),
                    avg_score=("score", "mean"),
                )
                .reset_index()
                .sort_values("n_selected", ascending=False)
            )
            pr(f"  {'Ticker':<8} {'Selected':>9} {'Avg 1d Ret':>12} {'Avg 5d Ret':>12} {'Avg Score':>10}")
            pr("  " + "-" * 57)
            for _, row in summary.iterrows():
                sel_str = f"{int(row['n_selected'])}/{total_dates}"
                pr(
                    f"  {row['ticker']:<8} {sel_str:>9} "
                    f"{_pct(row['avg_ret_1d']):>12} {_pct(row['avg_ret_5d']):>12} "
                    f"{_fmt(row['avg_score']):>10}"
                )
            pr()
        else:
            pr("  No active positions in this window.")
            pr()
    else:
        pr("  No forward return data yet.")
        pr()

    # ── LIVE IC ───────────────────────────────────────────────────────────────
    pr("LIVE IC (ML Score vs 1d Forward Return)")
    if fr_rows:
        fr_ic = pd.DataFrame([dict(r) for r in fr_rows])
        ic_df = fr_ic[
            (fr_ic["horizon"] == "1d")
            & fr_ic["score"].notna()
            & fr_ic["return_pct"].notna()
        ]
        n_obs = len(ic_df)
        if n_obs >= 5 and _SCIPY:
            pearson_r, pearson_p = _sp_stats.pearsonr(
                ic_df["score"].astype(float), ic_df["return_pct"].astype(float)
            )
            spearman_r, spearman_p = _sp_stats.spearmanr(
                ic_df["score"].astype(float), ic_df["return_pct"].astype(float)
            )
            pr(f"  Pearson r:  {pearson_r:+.3f}  (p={pearson_p:.3f})   N={n_obs}")
            pr(f"  Spearman r: {spearman_r:+.3f}  (p={spearman_p:.3f})")
        elif n_obs >= 5 and not _SCIPY:
            # Fallback: numpy corrcoef
            scores = ic_df["score"].astype(float).values
            rets = ic_df["return_pct"].astype(float).values
            corr = float(np.corrcoef(scores, rets)[0, 1])
            pr(f"  Pearson r:  {corr:+.3f}  (install scipy for p-values)   N={n_obs}")
        else:
            pr(f"  Insufficient data (N={n_obs} observations with score + 1d return). Need ≥5.")
    else:
        pr("  No forward return data.")
    pr()

    # ── VOL FILTER LOG ────────────────────────────────────────────────────────
    pr("VOL FILTER LOG")
    if sig_rows:
        sig_df_vf = pd.DataFrame([dict(r) for r in sig_rows])
        if "vol_triggered" in sig_df_vf.columns:
            sig_df_vf["vol_triggered"] = pd.to_numeric(sig_df_vf["vol_triggered"], errors="coerce").fillna(0).astype(int)
            vf = sig_df_vf[sig_df_vf["vol_triggered"] == 1]
            if vf.empty:
                pr("  No vol filter triggers in this window.")
            else:
                total_days_per_ticker = sig_df_vf.groupby("ticker")["date"].nunique()
                if fr_rows:
                    fr_vf = pd.DataFrame([dict(r) for r in fr_rows])
                    fr_1d_vf = fr_vf[fr_vf["horizon"] == "1d"][
                        ["signal_date", "ticker", "return_pct"]
                    ].rename(columns={"signal_date": "date"})
                    vf_merged = vf.merge(fr_1d_vf, on=["date", "ticker"], how="left")
                else:
                    vf_merged = vf.copy()
                    vf_merged["return_pct"] = None

                vf_summary = (
                    vf_merged.groupby("ticker")
                    .agg(n_triggered=("date", "count"), avg_ret=("return_pct", "mean"))
                    .reset_index()
                )
                pr(f"  {'Ticker':<8} {'Triggered':>12}  {'Avg 1d Ret when triggered':>26}")
                pr("  " + "-" * 50)
                for _, row in vf_summary.iterrows():
                    total = int(total_days_per_ticker.get(row["ticker"], 0))
                    pr(
                        f"  {row['ticker']:<8} {int(row['n_triggered'])}/{total:>4}        "
                        f"{_pct(row['avg_ret']):>20}"
                    )
        else:
            pr("  vol_triggered column not in DB (run generate_daily_weights.py again to populate).")
    else:
        pr("  No signal data in this window.")
    pr()

    # ── Write markdown ────────────────────────────────────────────────────────
    out_dir = ROOT / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"performance_report_{today_str}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    pr(f"Report written to: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
