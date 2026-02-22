"""
Statistical validation of 3-year backtest: bootstrap Sharpe CI, Monte Carlo luck test,
alpha t-test vs SPY, hit rate, max drawdown percentile.

Runs backtest for 2022, 2023, 2024; collects weekly returns; runs tests with --n-sim
simulations. Writes outputs/statistical_validation_YYYY-MM-DD.md. Exit 0 always.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Statistical validation of 3-year backtest.")
    parser.add_argument("--n-sim", type=int, default=10000, help="Number of bootstrap/MC simulations")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM in backtest (faster)")
    args = parser.parse_args()

    import numpy as np
    import pandas as pd
    from src.data.csv_provider import load_data_config, find_csv_path, load_prices
    from scripts.backtest_technical_library import run_backtest_master_score

    n_sim = max(100, args.n_sim)
    years = [2022, 2023, 2024]
    port_wr_list = []

    # Step 1 — Collect weekly returns per year
    config = load_data_config()
    data_dir = Path(config["data_dir"])
    try:
        from src.utils.config_manager import get_config
        raw_tickers = get_config().get_watchlist()
    except Exception:
        raw_tickers = []
    tickers = [t for t in raw_tickers if find_csv_path(str(data_dir), t)]
    if not tickers:
        print("WARN: No watchlist or no CSVs found; cannot run backtest.", flush=True)
        port_wr = np.array([], dtype=float)
    else:
        try:
            prices_dict = load_prices(data_dir, tickers)
            if not prices_dict:
                print("WARN: No price data; cannot run backtest.", flush=True)
                port_wr = np.array([], dtype=float)
            else:
                # Filter: drop tickers with duplicate 'close' columns (EODHD global issue)
                # and tickers whose data starts after 2022-01-01 (not in 3yr window)
                cutoff = pd.Timestamp("2022-01-03")
                bad_keys = []
                for t, df in prices_dict.items():
                    if df.empty or df.index.min() > cutoff:
                        bad_keys.append(t)
                        continue
                    close_col = df.get("close", None)
                    if close_col is None or isinstance(close_col, pd.DataFrame):
                        bad_keys.append(t)
                if bad_keys:
                    print(f"WARN: Dropping {len(bad_keys)} tickers (duplicate cols or insufficient history): {bad_keys}", flush=True)
                    for k in bad_keys:
                        prices_dict.pop(k, None)
                if not prices_dict:
                    print("WARN: No valid price data after filtering.", flush=True)
                    port_wr = np.array([], dtype=float)
                else:
                    for y in years:
                        start = f"{y}-01-01"
                        end = f"{y}-12-31"
                        result = run_backtest_master_score(
                            prices_dict=prices_dict,
                            data_dir=data_dir,
                            news_dir=None,
                            start_date=start,
                            end_date=end,
                            llm_enabled=not args.no_llm,
                            verbose=False,
                        )
                        wr = result.get("weekly_returns") or []
                        port_wr_list.extend(wr)
                    port_wr = np.array(port_wr_list, dtype=float)
        except Exception as e:
            print(f"WARN: Backtest failed ({e}); reporting with available data.", flush=True)
            port_wr = np.array(port_wr_list, dtype=float) if port_wr_list else np.array([], dtype=float)

    # Step 2 — SPY weekly returns
    spy_wr = None
    try:
        spy_prices = load_prices(data_dir, ["SPY"])
        if spy_prices and "SPY" in spy_prices:
            spy_df = spy_prices["SPY"]
            if "close" in spy_df.columns and len(spy_df) > 0:
                close = spy_df["close"].copy()
                close.index = pd.to_datetime(close.index)
                weekly = close.resample("W").last()
                spy_ret = weekly.pct_change().dropna()
                spy_ret = spy_ret[(spy_ret.index >= "2022-01-01") & (spy_ret.index <= "2024-12-31")]
                spy_wr = spy_ret.values.flatten()
    except Exception as e:
        print(f"WARN: SPY prices unavailable: {e}", flush=True)

    n_obs = len(port_wr)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    np.random.seed(42)

    # Step 3 — Statistical tests
    actual_sharpe = (np.mean(port_wr) / np.std(port_wr) * np.sqrt(52)) if n_obs > 1 and np.std(port_wr) > 0 else 0.0

    # a) Bootstrap Sharpe CI
    if n_obs > 0:
        bootstrap_sharpes = []
        for _ in range(n_sim):
            samp = np.random.choice(port_wr, size=n_obs, replace=True)
            if np.std(samp) > 0:
                bootstrap_sharpes.append(np.mean(samp) / np.std(samp) * np.sqrt(52))
            else:
                bootstrap_sharpes.append(0.0)
        bootstrap_sharpes = np.array(bootstrap_sharpes)
        ci_lo = float(np.percentile(bootstrap_sharpes, 2.5))
        ci_hi = float(np.percentile(bootstrap_sharpes, 97.5))
    else:
        ci_lo = ci_hi = 0.0
    sharpe_interpret = "CI entirely above 0 -> statistically positive edge" if ci_lo > 0 else "CI straddles 0 -> inconclusive"

    # b) Monte Carlo luck test (permutation)
    if n_obs > 0:
        shuffle_sharpes = []
        for _ in range(n_sim):
            perm = np.random.permutation(port_wr)
            if np.std(perm) > 0:
                shuffle_sharpes.append(np.mean(perm) / np.std(perm) * np.sqrt(52))
            else:
                shuffle_sharpes.append(0.0)
        shuffle_sharpes = np.array(shuffle_sharpes)
        p_luck = float(np.mean(shuffle_sharpes >= actual_sharpe))
    else:
        p_luck = 1.0
    luck_verdict = "Skill signal present (p < 0.05)" if p_luck < 0.05 else "Cannot reject luck hypothesis (p >= 0.05)"

    # c) Alpha significance (paired t-test)
    mean_alpha_pct = None
    t_stat = None
    p_alpha = None
    alpha_verdict = "N/A (SPY unavailable)"
    if spy_wr is not None and len(spy_wr) > 0 and n_obs > 0:
        min_len = min(len(port_wr), len(spy_wr))
        excess_wr = port_wr[:min_len] - spy_wr[:min_len]
        mean_alpha_pct = float(np.mean(excess_wr)) * 100
        ann_alpha_pct = mean_alpha_pct * 52
        try:
            from scipy.stats import ttest_1samp
            t_stat, p_alpha = ttest_1samp(excess_wr, 0)
            t_stat = float(t_stat)
            p_alpha = float(p_alpha)
            alpha_verdict = "Alpha statistically significant" if p_alpha < 0.05 else "Not significant at 95% confidence"
        except ImportError:
            # numpy fallback: t = mean / (std/sqrt(n))
            se = np.std(excess_wr) / np.sqrt(len(excess_wr)) if np.std(excess_wr) > 0 else 0
            t_stat = float(np.mean(excess_wr) / se) if se > 0 else 0.0
            p_alpha = None
            alpha_verdict = "t-stat only (scipy not installed)"

    # d) Hit rate vs SPY
    hit_rate_pct = None
    hit_n = None
    hit_total = None
    if spy_wr is not None and n_obs > 0:
        min_len = min(len(port_wr), len(spy_wr))
        hits = np.sum(port_wr[:min_len] > spy_wr[:min_len])
        hit_total = min_len
        hit_n = int(hits)
        hit_rate_pct = 100.0 * hits / min_len

    # e) Max drawdown percentile
    if n_obs > 0:
        cum = np.cumprod(1 + port_wr)
        running_max = np.maximum.accumulate(cum)
        dd = (cum - running_max) / np.where(running_max > 0, running_max, np.nan)
        actual_mdd = float(np.nanmin(dd)) * 100
        mdd_shuffle = []
        for _ in range(n_sim):
            perm = np.random.permutation(port_wr)
            c = np.cumprod(1 + perm)
            rm = np.maximum.accumulate(c)
            d = (c - rm) / np.where(rm > 0, rm, np.nan)
            mdd_shuffle.append(np.nanmin(d) * 100)
        mdd_shuffle = np.array(mdd_shuffle)
        mdd_percentile = float(np.mean(mdd_shuffle <= actual_mdd)) * 100
        mdd_worse_pct = 100 - mdd_percentile
        mdd_interpret = "Drawdown is typical" if 20 <= mdd_percentile <= 80 else "unusually deep for this return distribution"
    else:
        actual_mdd = 0.0
        mdd_percentile = 0.0
        mdd_worse_pct = 100.0
        mdd_interpret = "No data"

    # Step 4 — Build report
    lines = [
        "=== Statistical Validation Report: 3-Year Backtest (2022-2024) ===",
        f"N weekly observations: {n_obs}   |   N simulations: {n_sim:,}   |   Seed: 42",
        "",
        "SHARPE BOOTSTRAP (95% CI)",
        f"  Actual Sharpe (3yr):   {actual_sharpe:.3f}",
        f"  95% CI:                [{ci_lo:.3f}, {ci_hi:.3f}]",
        f"  Interpretation:        {sharpe_interpret}",
        "",
        "MONTE CARLO LUCK TEST",
        f"  Actual Sharpe:         {actual_sharpe:.3f}",
        f"  p-value:               {p_luck:.3f}",
        f"  Verdict:               {luck_verdict}",
        "",
        "ALPHA vs SPY (Paired t-test)",
    ]
    if mean_alpha_pct is not None and t_stat is not None:
        ann = mean_alpha_pct * 52
        sign = "+" if mean_alpha_pct >= 0 else ""
        lines.append(f"  Mean weekly alpha:     {sign}{mean_alpha_pct:.2f}% ({sign}{ann:.1f}% annualised)")
        lines.append(f"  t-statistic:           {t_stat:.2f}")
        if p_alpha is not None:
            lines.append(f"  p-value:                {p_alpha:.3f}")
        lines.append(f"  Verdict:               {alpha_verdict}")
    else:
        lines.append("  (SPY unavailable or no paired data)")
        lines.append(f"  Verdict:               {alpha_verdict}")
    lines.extend([
        "",
        "HIT RATE vs SPY",
    ])
    if hit_total is not None and hit_n is not None:
        lines.append(f"  Weeks portfolio beat SPY:   {hit_n}/{hit_total} ({hit_rate_pct:.1f}%)")
    else:
        lines.append("  (SPY unavailable)")
    lines.extend([
        "",
        "MAX DRAWDOWN PERCENTILE",
        f"  Actual Max Drawdown:   {actual_mdd:.2f}%",
        f"  MC Percentile:         {mdd_percentile:.0f} th percentile  (worse than {mdd_worse_pct:.0f}% of random shuffles)",
        f"  Interpretation:        {mdd_interpret}",
    ])
    report = "\n".join(lines)
    out_path = ROOT / "outputs" / f"statistical_validation_{today_str}.md"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    except Exception as e:
        print(f"WARN: Could not write {out_path}: {e}", flush=True)
    try:
        print(report, flush=True)
    except UnicodeEncodeError:
        print(report.encode("ascii", "replace").decode("ascii"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
