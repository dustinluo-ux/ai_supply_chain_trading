from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

_BENCHMARKS_DIR = (
    Path(os.environ.get("DATA_DIR", r"C:\ai_supply_chain_trading\trading_data"))
    / "benchmarks"
)
VIX_PATH = _BENCHMARKS_DIR / "VIX.csv"


def ensure_vix_csv():
    if not VIX_PATH.exists():
        import subprocess

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "download_vix.py")], check=True
        )


from src.hedging.hedging_strategy import TailHedge

SMH_PATH = _BENCHMARKS_DIR / "SMH.csv"
PORTFOLIO_USD = 740_000.0
ROLL_WEEKS = 4

WEEKLY_JSONS = (
    ROOT / "outputs" / "backtest_2022_fixedv2.json",
    ROOT / "outputs" / "backtest_2023_capped.json",
    ROOT / "outputs" / "backtest_2024_capped.json",
)


def _load_benchmark_close(path: Path) -> pd.Series:
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "close" not in df.columns and "adjusted_close" in df.columns:
        df["close"] = df["adjusted_close"]
    if "date" in df.columns:
        dt = pd.to_datetime(df["date"], errors="coerce")
        df = df.assign(date=dt).dropna(subset=["date"]).set_index("date")
    else:
        idx = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        df = df.assign(_idx=idx).dropna(subset=["_idx"]).set_index("_idx")
    s = pd.to_numeric(df["close"], errors="coerce").dropna().sort_index()
    s = s[s.index.weekday < 5]
    s = s.ffill(limit=5)
    return s


def _load_weekly_returns() -> list[float]:
    out: list[float] = []
    for p in WEEKLY_JSONS:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        wr = data.get("weekly_returns", [])
        out.extend([float(x) for x in wr])
    return out


def _sharpe_weekly(returns: pd.Series) -> float:
    std = float(returns.std())
    if std <= 0:
        return 0.0
    return float(np.sqrt(52.0) * float(returns.mean()) / std)


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min()) if len(dd) else 0.0


def _eff_ratio(total_return: float, max_dd: float) -> float:
    denom = abs(float(max_dd))
    if denom <= 0:
        return 0.0
    return float(total_return / denom)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tail-Hedge Overlay Backtest")
    parser.add_argument(
        "--expiry-days", type=int, default=45, help="Put expiry in days (default: 45)"
    )
    parser.add_argument(
        "--target-delta",
        type=float,
        default=0.20,
        help="Put delta target (default: 0.20 = 20-delta, use 0.10 for 10-delta)",
    )
    parser.add_argument(
        "--roll-weeks",
        type=int,
        default=ROLL_WEEKS,
        help="Roll frequency in weeks (default: 4)",
    )
    args = parser.parse_args()

    print(
        f"Config: expiry={args.expiry_days}d | delta={args.target_delta:.2f} | roll={args.roll_weeks}w"
    )

    if not VIX_PATH.exists():
        ensure_vix_csv()

    smh_close = _load_benchmark_close(SMH_PATH)
    vix_close = _load_benchmark_close(VIX_PATH)

    weekly_returns = _load_weekly_returns()
    mondays = pd.date_range(
        pd.Timestamp("2022-01-03"), periods=len(weekly_returns), freq="W-MON"
    )

    hedge = TailHedge(
        smh_close,
        vix_close,
        portfolio_usd=PORTFOLIO_USD,
        roll_weeks=args.roll_weeks,
        expiry_days=args.expiry_days,
        target_delta=args.target_delta,
    )

    rows = []
    long_equity = 1.0
    hedged_equity = 1.0
    roll_events = 0
    total_cost_pct = 0.0
    total_payoff_pct = 0.0
    contracts_1x_weeks = 0
    contracts_2x_weeks = 0

    for d, long_r in zip(mondays, weekly_returns):
        smh_px = float(smh_close.asof(d))
        vix_px = float(vix_close.asof(d))
        step = hedge.step(d, smh_px, vix_px)
        net_r = (
            float(long_r)
            - float(step["hedge_cost_pct"])
            + float(step["hedge_payoff_pct"])
        )

        long_equity *= 1.0 + float(long_r)
        hedged_equity *= 1.0 + net_r

        total_cost_pct += float(step["hedge_cost_pct"])
        total_payoff_pct += float(step["hedge_payoff_pct"])
        if step["roll_occurred"]:
            roll_events += 1
        if int(step["contracts"]) == 1:
            contracts_1x_weeks += 1
        elif int(step["contracts"]) == 2:
            contracts_2x_weeks += 1

        rows.append(
            {
                "date": d.date().isoformat(),
                "long_return": float(long_r),
                "hedge_cost_pct": float(step["hedge_cost_pct"]),
                "hedge_payoff_pct": float(step["hedge_payoff_pct"]),
                "net_return": net_r,
                "long_equity": long_equity,
                "hedged_equity": hedged_equity,
                "smh_close": smh_px,
                "vix_close": vix_px,
                "contracts": int(step["contracts"]),
                "strike": float(step["strike"]),
            }
        )

    out_df = pd.DataFrame(rows)
    out_path = (
        ROOT
        / "outputs"
        / f"tail_hedge_backtest_{args.expiry_days}d_{int(args.target_delta*100)}delta.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)

    long_ret_s = pd.Series([float(x) for x in weekly_returns], index=mondays)
    hedged_ret_s = pd.Series(out_df["net_return"].values, index=mondays)
    long_eq = pd.Series(out_df["long_equity"].values, index=mondays)
    hedged_eq = pd.Series(out_df["hedged_equity"].values, index=mondays)

    long_total = float(long_eq.iloc[-1] - 1.0) if len(long_eq) else 0.0
    hedged_total = float(hedged_eq.iloc[-1] - 1.0) if len(hedged_eq) else 0.0
    long_mdd = _max_drawdown(long_eq)
    hedged_mdd = _max_drawdown(hedged_eq)
    long_sharpe = _sharpe_weekly(long_ret_s)
    hedged_sharpe = _sharpe_weekly(hedged_ret_s)
    long_eff = _eff_ratio(long_total, long_mdd)
    hedged_eff = _eff_ratio(hedged_total, hedged_mdd)

    avg_hedge_cost_yr = (
        float(np.mean(out_df["hedge_cost_pct"]) * 52.0) if len(out_df) else 0.0
    )
    avg_payoff_event = float(total_payoff_pct / roll_events) if roll_events > 0 else 0.0

    print("\n=== TAIL-HEDGE OVERLAY RESULTS (2022-2024) ===")
    print("                      Long-Only    Hedged-Long")
    print(
        f"Total Return          {long_total*100:6.1f}%       {hedged_total*100:6.1f}%"
    )
    print(f"Max Drawdown          {long_mdd*100:6.1f}%       {hedged_mdd*100:6.1f}%")
    print(f"Sharpe                {long_sharpe:6.2f}         {hedged_sharpe:6.2f}")
    print(f"Efficiency Ratio      {long_eff:6.2f}         {hedged_eff:6.2f}")
    print("")
    print(f"Roll events:          {roll_events:2d}")
    warn = (
        " [WARNING] Theta bleed exceeds 5%/yr — consider 15-Delta puts or extending roll_weeks"
        if avg_hedge_cost_yr > 0.05
        else ""
    )
    print(f"Avg hedge cost/yr:    {avg_hedge_cost_yr*100:.2f}%{warn}")
    print(f"Avg payoff/event:     {avg_payoff_event*100:.2f}%")
    print(f"Base contracts (1x):  {contracts_1x_weeks} weeks")
    print(f"Doubled contracts (2x): {contracts_2x_weeks} weeks")
    print("")
    if hedged_eff > (1.2 * long_eff):
        print("SUCCESS: Hedged Efficiency Ratio > 1.2x Long-Only")
    else:
        print("WARNING: Hedged Efficiency Ratio < 1.2x Long-Only")
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
