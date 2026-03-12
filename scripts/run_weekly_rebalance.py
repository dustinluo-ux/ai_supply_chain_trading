# Canonical Automated Rebalancing entry point.
# Delegates to scripts/run_execution.py (same spine: target_weight_pipeline -> Intent -> PositionManager -> delta trades).
# Logic adapted from graveyard/run_weekly_rebalance.py; uses backtest-style scoring (no SignalCombiner).
"""
Weekly rebalance: signals -> target weights -> delta trades -> optional execution.

Uses canonical spine (SignalEngine -> PolicyEngine -> PortfolioEngine) via
target_weight_pipeline; tickers from config/data_config.yaml watchlist by default.

Usage:
  python scripts/run_weekly_rebalance.py --dry-run
  python scripts/run_weekly_rebalance.py --live --confirm-paper
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import update_news_data
import update_price_data
from src.utils.audit_logger import log_audit_record


def _get_watchlist() -> list[str]:
    """Load default tickers from config/data_config.yaml universe_selection.watchlist."""
    path = ROOT / "config" / "data_config.yaml"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        watchlist = data.get("universe_selection", {}).get("watchlist", [])
        return list(watchlist) if isinstance(watchlist, list) else []
    except Exception:
        return []


def main() -> int:
    # Update price data first (watchlist from config, end=today); continue on non-zero
    _saved_argv = sys.argv
    try:
        sys.argv = ["update_price_data.py"]
        _update_code = update_price_data.main()
    finally:
        sys.argv = _saved_argv
    if _update_code != 0:
        print("WARNING: Price data update returned non-zero exit code; continuing with possibly stale data.", file=sys.stderr)

    _saved_argv2 = sys.argv
    try:
        sys.argv = ["update_news_data.py"]
        _news_code = update_news_data.main()
    finally:
        sys.argv = _saved_argv2
    if _news_code != 0:
        print("WARNING: News data update returned non-zero exit code; continuing with possibly stale data.", file=sys.stderr)

    import datetime as _dt
    _run_id = f"rebalance_{_dt.datetime.now().isoformat().replace(':', '-').replace(' ', '_')}"
    parser = argparse.ArgumentParser(
        description="Weekly rebalance: canonical spine -> delta trades -> optional execution (delegates to run_execution)."
    )
    parser.add_argument("--date", type=str, default=None, help="Signal date YYYY-MM-DD; default: latest Monday")
    parser.add_argument("--top-n", type=int, default=3, help="Top N for portfolio")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers; default: watchlist from data_config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Do not submit orders (default)")
    parser.add_argument("--live", action="store_true", help="Use IB paper account (implies --confirm-paper if not --dry-run)")
    parser.add_argument("--confirm-paper", action="store_true", help="With --live: actually submit orders to paper account")
    parser.add_argument("--track", type=str, default=None,
                        help="Strategy track: D = 130/30 long/short. Default: Alpha (ML blend).")
    args = parser.parse_args()

    tickers = args.tickers
    if not tickers:
        watchlist = _get_watchlist()
        if not watchlist:
            print("ERROR: No tickers. Set --tickers or config/data_config.yaml universe_selection.watchlist.", flush=True)
            return 1
        tickers = ",".join(watchlist)
    else:
        tickers = ",".join(t.strip() for t in tickers.split(",") if t.strip())
    if not tickers:
        print("ERROR: No tickers provided.", flush=True)
        return 1

    # Factory evaluation: ensure a winner is cached; only run expensive tournament if cache stale/missing
    _factory_cache_path = ROOT / "models" / "factory_winner.json"
    _run_factory = True
    if _factory_cache_path.exists():
        _age_seconds = time.time() - _factory_cache_path.stat().st_mtime
        if _age_seconds <= 7 * 24 * 3600:
            _run_factory = False
    if not _run_factory:
        try:
            with open(_factory_cache_path, "r", encoding="utf-8") as _f:
                _cache = json.load(_f)
            _mt = _cache.get("model_type", "—")
            _ic = float(_cache.get("ic", 0))
            print(f"[REBALANCE] Using cached factory winner: {_mt} IC={_ic:.4f}", flush=True)
        except Exception as _e:
            print(f"[REBALANCE][WARN] Could not read factory cache: {_e}", flush=True)
    else:
        try:
            from src.models.factory import get_best_model
            from src.data.csv_provider import load_prices
            _data_cfg_path = ROOT / "config" / "data_config.yaml"
            _data_dir = ROOT / "data" / "stock_market_data"
            if _data_cfg_path.exists():
                with open(_data_cfg_path, "r", encoding="utf-8") as _f:
                    _dc = yaml.safe_load(_f)
                _ds = (_dc or {}).get("data_sources", {})
                if _ds.get("data_dir"):
                    _data_dir = Path(_ds["data_dir"])
            _ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
            _prices_dict = load_prices(_data_dir, _ticker_list)
            _news_signals = {}
            try:
                from src.core.config import NEWS_DIR
                import pandas as pd
                _eodhd = Path(NEWS_DIR) / "eodhd_global_backfill.parquet"
                if _eodhd.exists():
                    _df = pd.read_parquet(_eodhd, engine="fastparquet")
                    if not _df.empty and "Ticker" in _df.columns and "Date" in _df.columns and "Sentiment" in _df.columns:
                        for _ticker, _grp in _df.groupby("Ticker"):
                            _by_date = _grp.groupby("Date")["Sentiment"].mean()
                            _news_signals[_ticker] = {
                                str(_d): {"sentiment": float(_s), "supply_chain": 0.5}
                                for _d, _s in _by_date.items()
                            }
            except Exception:
                pass
            _winner_model, _winner_type, _winner_ic = get_best_model(
                prices_dict=_prices_dict,
                news_signals=_news_signals if _news_signals else None,
                config_path=ROOT / "config" / "model_config.yaml",
            )
            if _winner_type != "tech_only":
                print(f"[REBALANCE] Factory winner: {_winner_type} IC={_winner_ic:.4f} — model active", flush=True)
            else:
                print("[REBALANCE] Factory returned tech_only (no ML model passed IC gate)", flush=True)
        except Exception as _e:
            print(f"[REBALANCE][WARN] Factory skipped: {_e}", flush=True)

    if args.track == "D":
        import run_execution
        import pandas as pd
        config = run_execution.load_config()
        data_dir = config["data_dir"]
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
        prices_dict = run_execution.load_prices(data_dir, ticker_list)
        if not prices_dict:
            print("ERROR: No price data for track D.", flush=True)
            return 1
        all_dates = sorted(set().union(*[df.index for df in prices_dict.values()]))
        if not all_dates:
            print("ERROR: No dates in price data.", flush=True)
            return 1
        mondays = pd.date_range(min(all_dates), max(all_dates), freq="W-MON")
        as_of = mondays[-1] if len(mondays) else pd.Timestamp(all_dates[-1])
        if args.date:
            as_of = pd.to_datetime(args.date).normalize()
        regime_status = {}
        regime_path = ROOT / "outputs" / "regime_status.json"
        if regime_path.exists():
            try:
                with open(regime_path, "r", encoding="utf-8") as f:
                    regime_status = json.load(f)
            except Exception:
                pass
        model_cfg_path = ROOT / "config" / "model_config.yaml"
        config_d = {}
        if model_cfg_path.exists():
            with open(model_cfg_path, "r", encoding="utf-8") as f:
                model_cfg = yaml.safe_load(f)
            config_d = (model_cfg or {}).get("tracks", {}).get("D", {})
        from src.core.target_weight_pipeline import compute_target_weights
        _top_n_d = config_d.get("top_n", 15)
        _weights_series, aux = compute_target_weights(
            as_of, ticker_list, prices_dict, data_dir,
            top_n=_top_n_d, path="weekly", return_aux=True,
        )
        scores = pd.Series(aux.get("scores", {}))
        scores_df = pd.DataFrame([aux.get("scores", {})], index=[as_of]) if scores.size else pd.DataFrame()
        from src.portfolio.long_short_optimizer import rebalance_long_short
        weights_result = rebalance_long_short(scores, scores_df, prices_dict, regime_status, config_d)
        out_dir = ROOT / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "last_valid_weights.json", "w", encoding="utf-8") as f:
            json.dump({"as_of": str(as_of.date()), "weights": weights_result.to_dict()}, f, indent=2)

    # Build argv for run_execution.main()
    argv = [
        "run_execution",
        "--tickers", tickers,
        "--top-n", str(args.top_n),
    ]
    if args.date:
        argv.extend(["--date", args.date])
    if args.track == "D":
        argv.extend(["--rebalance"])
    if args.live:
        argv.extend(["--mode", "paper"])
        if args.confirm_paper and not args.dry_run:
            argv.append("--confirm-paper")
    else:
        argv.extend(["--mode", "mock"])

    # Delegate to canonical execution entry point (same spine + PositionManager + delta trades)
    import run_execution
    old_argv = sys.argv
    try:
        sys.argv = argv
        result = run_execution.main()
        _exit_code = result[0] if isinstance(result, tuple) else result
        _fill_records = result[1] if isinstance(result, tuple) and len(result) > 1 else []
        _rebalance_config = {
            "tickers": tickers,
            "top_n": args.top_n,
            "date": args.date,
            "dry_run": not args.live,
            "mode": "paper" if args.live else "mock",
        }
        log_audit_record(
            run_id=_run_id,
            model_metrics={},
            config=_rebalance_config,
            output_paths={},
            trade_summary=_fill_records,
        )
        from src.monitoring.telegram_alerts import send_alert
        _ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
        _nav = 0
        _regime = "—"
        try:
            _ps_path = ROOT / "outputs" / "portfolio_state.json"
            if _ps_path.exists():
                import json
                with open(_ps_path, "r", encoding="utf-8") as _f:
                    _ps = json.load(_f)
                _nav = float(_ps.get("last_nav") or 0)
                _regime = str(_ps.get("regime") or "—")
        except Exception:
            pass
        send_alert("rebalance_complete", {
            "n_tickers": len(_ticker_list),
            "nav": _nav,
            "regime": _regime,
            "timestamp": _dt.datetime.now().isoformat(),
        })
        return _exit_code
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    sys.exit(main())
