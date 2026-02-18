# Canonical execution entrypoint: mock (default) or paper (IB paper account).
"""
Canonical execution: spine -> Intent -> delta trades.
--mode mock: print only (no broker).
--mode paper: connect to IB paper; print orders; submit only with --confirm-paper.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Cache for --rebalance: last valid weights from last non-rebalance run
LAST_VALID_WEIGHTS_PATH = ROOT / "outputs" / "last_valid_weights.json"

BENCHMARK_TICKER = "SPY"
SMA_KILL_SWITCH_DAYS = 200
KILL_SWITCH_MODE = "cash"
REQUIRED_REGIME_KEYS = (
    "regime_state",
    "spy_below_sma200",
    "kill_switch_active",
    "sideways_risk_scale",
    "kill_switch_mode",
)


def load_config():
    path = ROOT / "config" / "data_config.yaml"
    if not path.exists():
        return {"data_dir": ROOT / "data" / "stock_market_data"}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    ds = data.get("data_sources", {})
    data_dir = Path(ds.get("data_dir", str(ROOT / "data" / "stock_market_data")))
    return {"data_dir": data_dir}


def find_csv_path(data_dir: Path, ticker: str) -> Path | None:
    for sub in ["nasdaq/csv", "sp500/csv", "nyse/csv", "forbes2000/csv"]:
        p = data_dir / sub / f"{ticker}.csv"
        if p.exists():
            return p
    return None


def load_prices(data_dir: Path, tickers: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    for t in tickers:
        path = find_csv_path(data_dir, t)
        if not path:
            continue
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True, dayfirst=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            df.columns = [c.lower() for c in df.columns]
            if "close" not in df.columns:
                continue
            for c in ["open", "high", "low"]:
                if c not in df.columns:
                    df[c] = df["close"]
            if "volume" not in df.columns:
                df["volume"] = 0.0
            if df.empty or len(df) < 60:
                continue
            out[t] = df
        except Exception:
            continue
    return out


def ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    for c in ["open", "high", "low"]:
        if c not in df.columns and "close" in df.columns:
            df[c] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = 0.0
    return df


def _spy_benchmark_series(data_dir: Path) -> tuple[pd.Series, pd.Series] | None:
    path = find_csv_path(data_dir, BENCHMARK_TICKER)
    if not path:
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True, dayfirst=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df.columns = [c.lower() for c in df.columns]
        if "close" not in df.columns or len(df) < SMA_KILL_SWITCH_DAYS:
            return None
        close = df["close"]
        sma = close.rolling(SMA_KILL_SWITCH_DAYS, min_periods=SMA_KILL_SWITCH_DAYS).mean()
        return (close, sma)
    except Exception:
        return None


def compute_target_weights(
    as_of: pd.Timestamp,
    tickers: list[str],
    prices_dict: dict[str, pd.DataFrame],
    data_dir: Path,
    *,
    top_n: int = 3,
    sideways_risk_scale: float = 0.5,
) -> pd.Series:
    """
    Target weights from canonical spine (SignalEngine -> PolicyEngine -> PortfolioEngine).
    Delegates to src.core.target_weight_pipeline.compute_target_weights (path="weekly").
    Used by parity harness and by main(); returns intent.weights before delta computation.
    """
    from src.core.target_weight_pipeline import compute_target_weights as _compute_target_weights

    return _compute_target_weights(
        as_of,
        tickers,
        prices_dict,
        data_dir,
        top_n=top_n,
        sideways_risk_scale=sideways_risk_scale,
        weight_mode="fixed",
        path="weekly",
    )


def _create_paper_executor():
    """Create IB executor in paper mode using config/trading_config.yaml (host, port, paper_account)."""
    trading_config_path = ROOT / "config" / "trading_config.yaml"
    if not trading_config_path.exists():
        raise FileNotFoundError("config/trading_config.yaml required for --mode paper")
    with open(trading_config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    trading = config.get("trading", {})
    ib_config = trading.get("ib", {})
    execution_config = trading.get("execution", {})
    paper_account = execution_config.get("paper_account")
    if not paper_account:
        raise ValueError("trading.execution.paper_account required for --mode paper")
    from src.data.provider_factory import DataProviderFactory
    from src.execution.ib_executor import IBExecutor
    data_provider = DataProviderFactory.create("ib", **ib_config)
    return IBExecutor(ib_provider=data_provider, account=paper_account)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Canonical execution: spine -> Intent -> delta trades (mock or IB paper)."
    )
    parser.add_argument("--tickers", type=str, required=True, help="Comma-separated tickers (e.g. AAPL,NVDA,SPY)")
    parser.add_argument("--date", type=str, default=None, help="Signal date YYYY-MM-DD; default: latest Monday in data")
    parser.add_argument("--top-n", type=int, default=3, help="Top N for portfolio")
    parser.add_argument("--sideways-risk-scale", type=float, default=0.5, help="Sideways regime scale")
    parser.add_argument("--mode", type=str, default="mock", choices=["mock", "paper"], help="mock (print only) or paper (IB paper account)")
    parser.add_argument("--confirm-paper", action="store_true", help="With --mode paper: actually submit orders; without: dry-run print only")
    parser.add_argument("--rebalance", action="store_true", help="Rebalance mode: use last valid weights from cache; only propose trades for tickers that drifted past threshold (see strategy_params.rebalancing)")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        print("ERROR: No tickers provided.", flush=True)
        return 1

    config = load_config()
    data_dir = config["data_dir"]
    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        print("ERROR: No price data loaded.", flush=True)
        return 1

    all_dates = sorted(set().union(*[df.index for df in prices_dict.values()]))
    if not all_dates:
        print("ERROR: No dates in price data.", flush=True)
        return 1

    if args.date:
        as_of = pd.to_datetime(args.date).normalize()
        if as_of not in all_dates and as_of not in pd.DatetimeIndex(all_dates):
            mondays = pd.date_range(min(all_dates), max(all_dates), freq="W-MON")
            mondays = mondays[mondays <= as_of]
            as_of = mondays[-1] if len(mondays) else pd.Timestamp(all_dates[-1])
    else:
        mondays = pd.date_range(min(all_dates), max(all_dates), freq="W-MON")
        as_of = mondays[-1] if len(mondays) else pd.Timestamp(all_dates[-1])

    if args.rebalance:
        # Rebalance mode: pull last valid weights from cache (no fresh signal generation)
        if not LAST_VALID_WEIGHTS_PATH.exists():
            print("ERROR: --rebalance requires last valid weights. Run without --rebalance once to populate outputs/last_valid_weights.json", flush=True)
            return 1
        with open(LAST_VALID_WEIGHTS_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        target_weights_dict = cache.get("weights") or {}
        if not target_weights_dict:
            print("No weights in cache. Run without --rebalance first.", flush=True)
            return 1
        optimal_weights_series = pd.Series(target_weights_dict).reindex(tickers, fill_value=0.0).fillna(0.0)
        intent_tickers = [t for t, w in target_weights_dict.items() if float(w) > 0]
        intent = SimpleNamespace(tickers=intent_tickers, weights=dict(optimal_weights_series))
    else:
        optimal_weights_series = compute_target_weights(
            as_of,
            tickers,
            prices_dict,
            data_dir,
            top_n=args.top_n,
            sideways_risk_scale=args.sideways_risk_scale,
        )
        if optimal_weights_series.sum() == 0:
            print("No target tickers from portfolio engine.", flush=True)
            return 0
        intent_tickers = list(optimal_weights_series[optimal_weights_series > 0].index)
        intent = SimpleNamespace(tickers=intent_tickers, weights=optimal_weights_series.to_dict())
        # Persist for next --rebalance
        LAST_VALID_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LAST_VALID_WEIGHTS_PATH, "w", encoding="utf-8") as f:
            json.dump({"as_of": str(as_of.date()), "weights": optimal_weights_series.to_dict()}, f, indent=2)

    from src.execution.executor_factory import ExecutorFactory
    from src.execution.mock_executor import MockExecutor
    from src.portfolio.position_manager import PositionManager

    if args.mode == "mock":
        executor = ExecutorFactory.from_config_file()
        if not isinstance(executor, MockExecutor):
            raise RuntimeError(
                "With --mode mock, config must specify executor: mock. "
                "Use --mode paper for IB paper."
            )
    else:
        executor = _create_paper_executor()

    position_manager = PositionManager(executor)
    current_positions = position_manager.get_current_positions()
    current_weights = position_manager.positions_to_weights(current_positions)
    account_value = position_manager.get_account_value()
    # Live bridge: when IB is used, refresh account from provider so sizing uses live NAV
    if args.mode == "paper" and hasattr(executor, "ib_provider"):
        try:
            from src.execution.ibkr_bridge import AccountMonitor
            monitor_for_nav = AccountMonitor(executor.ib_provider)
            monitor_for_nav.refresh()
            live_nav = monitor_for_nav.get_net_liquidation()
            if live_nav > 0:
                account_value = live_nav
        except Exception:
            pass
    trading_config_path = ROOT / "config" / "trading_config.yaml"
    if account_value <= 0 and trading_config_path.exists():
        with open(trading_config_path, "r", encoding="utf-8") as f:
            tc = yaml.safe_load(f)
        account_value = float(tc.get("trading", {}).get("initial_capital", 100_000))

    if args.rebalance:
        # Portfolio-level rebalance: only orders for tickers that drifted past threshold
        from src.execution.ibkr_bridge import RebalanceLogic
        positions_df = position_manager.get_current_positions()
        current_positions_list = []
        for _, row in positions_df.iterrows():
            current_positions_list.append({
                "symbol": row.get("symbol", ""),
                "position": float(row.get("quantity", 0)),
                "avgCost": float(row.get("avg_cost", 0)),
                "market_value": float(row.get("market_value", 0)),
            })
        prices_last = {}
        for sym, df in prices_dict.items():
            if df.empty or "close" not in df.columns:
                continue
            try:
                mask = df.index <= as_of
                up_to = df.loc[mask] if hasattr(mask, "any") and mask.any() else df
            except Exception:
                up_to = df
            if up_to.empty:
                continue
            close = up_to["close"].iloc[-1]
            if pd.notna(close):
                prices_last[sym] = float(close)
        rebalance_logic = RebalanceLogic()
        rebalance_orders = rebalance_logic.calculate_rebalance_orders(
            target_weights=intent.weights,
            current_positions=current_positions_list,
            nav=account_value,
            prices=prices_last,
        )
        executable = pd.DataFrame([
            {
                "symbol": o.ticker,
                "side": o.side,
                "quantity": o.quantity,
                "delta_weight": o.target_weight - o.current_weight,
                "drift": o.drift,
                "delta_dollars": o.delta_dollars,
            }
            for o in rebalance_orders
        ])
        if executable.empty:
            executable = pd.DataFrame(columns=["symbol", "side", "quantity", "delta_weight", "drift", "delta_dollars"])
    else:
        # Build last-close prices as of as_of so PositionManager can compute share quantities.
        # Without prices, quantity = int(delta_dollars / 0) = 0 and executable is always empty.
        prices_last = {}
        for sym, df in prices_dict.items():
            if df.empty or "close" not in df.columns:
                continue
            try:
                mask = df.index <= as_of
                up_to = df.loc[mask] if hasattr(mask, "any") and mask.any() else df
            except Exception:
                up_to = df
            if up_to.empty:
                continue
            close_val = up_to["close"].iloc[-1]
            if pd.notna(close_val) and float(close_val) > 0:
                prices_last[sym] = float(close_val)
        prices_series = pd.Series(prices_last) if prices_last else None

        delta_trades = position_manager.calculate_delta_trades(
            current_weights=current_weights,
            optimal_weights=optimal_weights_series,
            account_value=account_value,
            prices=prices_series,
            min_trade_size=0.005,
            significance_threshold=0.02,
        )
        executable = delta_trades[delta_trades["should_trade"] & (delta_trades["quantity"] > 0)]

    mode_label = "mock" if args.mode == "mock" else "paper"
    title = "rebalance (drift threshold)" if args.rebalance else "delta trades"
    print(f"--- Canonical execution ({mode_label}): {title} ---", flush=True)
    print(f"  As-of:       {as_of.date()}", flush=True)
    print(f"  Account:     {account_value:,.2f}", flush=True)
    print(f"  Intent:      {intent.tickers}", flush=True)
    print(f"  Executable:  {len(executable)}", flush=True)
    for _, row in executable.iterrows():
        drift_str = f" drift={row.get('drift', 0):+.1%}" if "drift" in row else ""
        print(
            f"  {row['side']} {row['quantity']} {row['symbol']} (delta_w={row['delta_weight']:+.2%}{drift_str})",
            flush=True,
        )

    if args.mode == "mock":
        print("  (Mock: no orders submitted.)", flush=True)
    elif args.mode == "paper":
        if args.confirm_paper:
            # Live Execution Bridge: circuit breaker + AccountMonitor + OrderDispatcher
            import time
            from src.execution.ibkr_bridge import (
                AccountMonitor,
                CircuitBreaker,
                LiveSignal,
                OrderDispatcher,
                RiskManager,
            )
            if hasattr(executor, "ib_provider"):
                monitor = AccountMonitor(executor.ib_provider)
                monitor.refresh()
                nav = monitor.get_net_liquidation()
                if nav <= 0:
                    nav = account_value
                monitor.log_nav_snapshot("Pre-Rebalance NAV", nav)
            else:
                nav = account_value
                monitor = None
            cb = CircuitBreaker()
            cb.record_nav(time.time(), nav)
            if cb.is_trading_paused():
                print("  [CIRCUIT BREAKER] Trading paused; no orders submitted.", flush=True)
            elif cb.check_and_pause_if_breach(nav):
                print("  [CIRCUIT BREAKER] 1d drawdown breach; trading paused.", flush=True)
            else:
                # Build ATR and entry price from prices for Smart Stop and sizing
                atr_per_share = {}
                entry_price_map = {}
                if prices_dict:
                    from src.portfolio.position_sizer import compute_atr_series
                    for sym, df in prices_dict.items():
                        df_ohlcv = ensure_ohlcv(df)
                        if len(df_ohlcv) < 2:
                            continue
                        up_to = df_ohlcv[df_ohlcv.index <= as_of]
                        if up_to.empty:
                            continue
                        last = up_to.iloc[-1]
                        entry_price_map[sym] = float(last.get("close", 0) or 0)
                        atr_series = compute_atr_series(
                            up_to["high"], up_to["low"], up_to["close"], period=14
                        )
                        if not atr_series.empty:
                            atr_per_share[sym] = float(atr_series.iloc[-1])
                        else:
                            atr_per_share[sym] = 0.0
                exec_config = {}
                if trading_config_path.exists():
                    with open(trading_config_path, "r", encoding="utf-8") as f:
                        tc = yaml.safe_load(f)
                    exec_config = tc.get("trading", {}).get("execution", {})
                min_sz = int(exec_config.get("min_order_size", 1))
                max_sz = int(exec_config.get("max_position_size", 10000))
                if monitor is not None:
                    risk_mgr = RiskManager()
                    dispatcher = OrderDispatcher(executor, risk_mgr, monitor)
                    for _, row in executable.iterrows():
                        if row["quantity"] <= 0:
                            continue
                        sym = row["symbol"]
                        result = dispatcher.dispatch_from_delta(
                            ticker=sym,
                            quantity=int(row["quantity"]),
                            side=row["side"],
                            entry_price=entry_price_map.get(sym, 0.0) or 1.0,
                            atr_per_share=atr_per_share.get(sym, 0.0),
                            is_propagated=False,
                            order_type="MARKET",
                        )
                        if result.get("status") == "error":
                            print(f"  [ORDER ERROR] {sym}: {result.get('error', 'unknown')}", flush=True)
                    if monitor is not None:
                        monitor.refresh()
                        monitor.log_nav_snapshot("Post-Rebalance NAV", monitor.get_net_liquidation())
                    cb.record_nav(time.time(), monitor.get_net_liquidation() if monitor else nav)
                else:
                    for _, row in executable.iterrows():
                        if row["quantity"] > 0:
                            executor.submit_order(
                                ticker=row["symbol"],
                                quantity=int(row["quantity"]),
                                side=row["side"],
                                order_type="MARKET",
                            )
                print("  (Paper: orders submitted to IB paper account.)", flush=True)
        else:
            print("  (Paper: DRY-RUN. Use --confirm-paper to submit orders.)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
