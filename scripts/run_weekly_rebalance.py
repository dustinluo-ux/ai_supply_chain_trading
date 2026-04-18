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
import os
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import update_news_data
import update_price_data
from src.data.csv_provider import load_data_config, load_prices
from src.utils.audit_logger import log_audit_record


def _as_of_capped_for_overlay(ts) -> "pd.Timestamp":
    """Clamp signal date to calendar today so forward-dated price rows do not skew RiskOverlay."""
    import pandas as pd

    cap = pd.Timestamp(date.today())
    t = pd.Timestamp(ts).normalize()
    return t if t <= cap else cap


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


def _append_risk_metadata_from_constraints(constraints, as_of_str: str) -> None:
    """Backward-compatible risk_metadata_history.csv row (RiskOverlay fields replaced by RiskPolicy summary)."""
    from src.execution.risk_manager import append_risk_metadata_csv

    try:
        append_risk_metadata_csv(
            {
                "tier1_trend": "RiskPolicy",
                "tier2_vix": "RiskPolicy",
                "allocation_multiplier": float(constraints.position_scale),
                "max_positions_override": None,
                "tier3_corr": 0.0,
                "as_of": as_of_str,
            }
        )
    except Exception as exc:
        print(f"[RISK][WARN] append_risk_metadata_csv: {exc}", flush=True)


def _resolve_nav_usd() -> float:
    """IBKR net_liquidation if available, else last_valid_weights.json metadata, else 100_000."""
    try:
        from src.data import ibkr_live_provider as _ibkr
        from src.risk.policy import _load_trading_ib_config

        host, port, base_cid = _load_trading_ib_config()
        ib = _ibkr.connect(host, port, client_id=base_cid + (int(time.time()) % 89))
        try:
            acct = _ibkr.get_account_summary(ib)
            nl = float(acct.get("net_liquidation", 0.0) or 0.0)
            if nl > 0:
                return nl
        finally:
            ib.disconnect()
    except Exception:
        pass
    lw_path = ROOT / "outputs" / "last_valid_weights.json"
    if lw_path.exists():
        try:
            with open(lw_path, encoding="utf-8") as f:
                j = json.load(f)
            for key in ("nav_usd", "net_liquidation", "portfolio_nav", "nav"):
                v = j.get(key)
                if v is not None:
                    fv = float(v)
                    if fv > 0:
                        return fv
            meta = j.get("metadata")
            if isinstance(meta, dict):
                for key in ("nav_usd", "net_liquidation", "portfolio_nav", "nav"):
                    v = meta.get(key)
                    if v is not None:
                        fv = float(v)
                        if fv > 0:
                            return fv
        except Exception:
            pass
    return 100_000.0


def _get_nq_price_or_none() -> Decimal | None:
    """Live NQ front-month price for ExecutionPlanner overlay; None skips overlay (logged)."""
    try:
        from src.data import ibkr_live_provider as _ibkr
        from src.data.contract_resolver import resolve as _resolve
        from src.risk.policy import _load_trading_ib_config

        host, port, base_cid = _load_trading_ib_config()
        ib = _ibkr.connect(host, port, client_id=base_cid + (int(time.time()) % 89))
        try:
            nq = _resolve("NQ", "future", ib)
            pxm = _ibkr.get_live_prices(ib, [nq])
            sym = str(getattr(nq, "symbol", "") or "NQ")
            px = pxm.get(sym)
            if px is None and pxm:
                px = next(iter(pxm.values()))
            if px is not None and float(px) > 0:
                return Decimal(str(px))
        finally:
            ib.disconnect()
    except Exception as exc:
        print(f"[PLAN][WARN] NQ live price unavailable, overlay skipped: {exc}", flush=True)
    return None


def _ts_iso(ts) -> str:
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


def _ensure_plan_audit(plan):
    from dataclasses import replace

    if plan.audit_log:
        return plan
    return replace(plan, audit_log=["[PLAN] reconcile complete (no prior audit lines)"])


def _execution_plan_to_dict(plan, target) -> dict:
    from src.risk.types import TargetPortfolio

    out: dict = {
        "as_of": _ts_iso(plan.as_of),
        "long_orders": {k: str(v) for k, v in plan.long_orders.items()},
        "overlay_orders": [
            {
                "symbol": o.symbol,
                "contracts": o.contracts,
                "notional_usd": str(o.notional_usd),
                "reason": o.reason,
            }
            for o in plan.overlay_orders
        ],
        "audit_log": list(plan.audit_log),
    }
    if isinstance(target, TargetPortfolio):
        out["target_portfolio"] = {
            "as_of": _ts_iso(target.as_of),
            "weights": {k: str(v) for k, v in target.weights.items()},
            "scores": {k: float(v) for k, v in target.scores.items()},
            "construction_meta": dict(target.construction_meta),
        }
    return out


def _write_execution_plan_json(plan, path: Path, target=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(_execution_plan_to_dict(plan, target), indent=2)
    if not payload or len(payload) < 10:
        raise ValueError("execution plan JSON would be empty")
    tmp.write_text(payload, encoding="utf-8")
    if tmp.stat().st_size < 10:
        raise ValueError("execution plan temp file unexpectedly small")
    os.replace(tmp, path)


def _target_from_weights_or_aux(weights_series, as_of_ts, aux) -> "TargetPortfolio":
    from src.risk.types import TargetPortfolio

    if isinstance(aux, dict) and aux.get("target_portfolio") is not None:
        return aux["target_portfolio"]
    wmap = {str(k).upper(): Decimal(str(v)) for k, v in weights_series.items() if float(v) != 0.0}
    return TargetPortfolio(
        as_of=as_of_ts,
        weights=wmap,
        scores={},
        construction_meta={"source": "weights_series_fallback"},
    )


def _submit_plan_to_ib(plan, nav: float, prices_dict: dict, as_of, fill_run_id: str) -> list:
    """Submit equity deltas and MNQ overlay via IBExecutor / ib_insync (best-effort)."""
    import run_execution
    from ib_insync import MarketOrder
    from src.data.contract_resolver import resolve as contract_resolve
    from src.execution.fill_ledger import append_fill_record

    out: list = []
    executor = run_execution._create_paper_executor()
    ib = executor.ib
    try:
        for sym, w_dec in plan.long_orders.items():
            sym_u = str(sym).upper()
            if float(w_dec) <= 0 or sym_u in ("MNQ", "MES", "NQ", "ES"):
                continue
            df = prices_dict.get(sym) or prices_dict.get(sym_u)
            if df is None or getattr(df, "empty", True):
                continue
            up_to = df[df.index <= as_of]
            if up_to.empty:
                continue
            last = up_to.iloc[-1]
            close = float(last.get("close", 0) or 0)
            if close <= 0:
                continue
            tgt_sh = int((nav * float(w_dec)) / close)
            cur = 0
            try:
                for p in ib.positions():
                    if str(getattr(p.contract, "symbol", "")).upper() == sym_u:
                        cur = int(p.position or 0)
                        break
            except Exception:
                cur = 0
            dq = tgt_sh - cur
            if dq == 0:
                continue
            side = "BUY" if dq > 0 else "SELL"
            res = executor.submit_order(
                sym_u,
                abs(int(dq)),
                side,
                order_type="MARKET",
                order_comment="weekly_rebalance_plan",
                attach_server_stops=True,
            )
            if isinstance(res, dict):
                out.append(res)
                append_fill_record(
                    run_id=fill_run_id,
                    ticker=sym_u,
                    side=side,
                    qty_requested=abs(int(dq)),
                    qty_filled=int(res.get("filled_quantity") or 0),
                    avg_fill_price=res.get("filled_price"),
                    order_id=str(res["order_id"]) if res.get("order_id") is not None else None,
                    stop_order_id=str(res["stop_order_id"]) if res.get("stop_order_id") is not None else None,
                    status=str(res.get("status") or "submitted"),
                    fill_check_passed=False,
                    fill_check_reason="weekly_rebalance",
                    order_comment=res.get("order_comment"),
                )
        for ov in plan.overlay_orders:
            if str(ov.symbol).upper() != "MNQ" or int(ov.contracts) == 0:
                print(f"[PLAN][SKIP] overlay submit not implemented for {ov.symbol}", flush=True)
                continue
            try:
                fc = contract_resolve("MNQ", "future", ib)
                side = "SELL" if int(ov.contracts) < 0 else "BUY"
                q = abs(int(ov.contracts))
                order = MarketOrder(side, q)
                order.account = executor.account
                order.orderRef = "weekly_rebalance_overlay"[:128]
                trade = ib.placeOrder(fc, order)
                print(
                    f"[PLAN] overlay MNQ {side} {q} orderId={trade.order.orderId}",
                    flush=True,
                )
            except Exception as ex:
                print(f"[PLAN][WARN] overlay submit failed: {ex}", flush=True)
    finally:
        pass
    return out


def _finalize_rebalance_audit(
    *,
    _run_id: str,
    tickers: str,
    args: argparse.Namespace,
    regime_state: dict,
    _fill_records: list,
    _exit_code: int,
) -> None:
    import datetime as _dt

    _rebalance_config = {
        "tickers": tickers,
        "top_n": args.top_n,
        "date": args.date,
        "dry_run": not args.live,
        "mode": "paper" if args.live else "mock",
        "risk_regime": {
            "regime_state": regime_state.get("regime_state"),
            "multiplier": regime_state.get("multiplier"),
            "score_floor": regime_state.get("score_floor"),
            "n_shorts": regime_state.get("n_shorts"),
            "meta_weights": regime_state.get("meta_weights"),
        },
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
    _nav = 0.0
    _regime = "—"
    try:
        _ps_path = ROOT / "outputs" / "portfolio_state.json"
        if _ps_path.exists():
            with open(_ps_path, "r", encoding="utf-8") as _f:
                _ps = json.load(_f)
            _nav = float(_ps.get("last_nav") or 0)
            _regime = str(_ps.get("regime") or "—")
    except Exception:
        pass
    send_alert(
        "rebalance_complete",
        {
            "n_tickers": len(_ticker_list),
            "nav": _nav,
            "regime": _regime,
            "timestamp": _dt.datetime.now().isoformat(),
        },
    )


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

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

    try:
        from update_benchmarks import ensure_benchmarks

        ensure_benchmarks()
    except Exception as _be:
        print(f"WARNING: Could not refresh benchmark CSVs: {_be}", file=sys.stderr, flush=True)

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
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM in target_weight_pipeline")
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

    regime_state = {
        "regime_state": "Expansion",
        "multiplier": 1.0,
        "score_floor": 0.50,
        "max_longs": int(args.top_n),
        "n_shorts": 0,
        "meta_weights": {"core": 0.50, "extension": 0.30, "ballast": 0.20},
    }
    try:
        import pandas as pd
        import run_execution
        from src.execution.regime_controller import RegimeController

        _cfg_reg = load_data_config()
        _data_dir_reg = _cfg_reg["data_dir"]
        _tick_reg = [t.strip() for t in tickers.split(",") if t.strip()]
        _prices_reg = load_prices(_data_dir_reg, _tick_reg)
        if args.date:
            _as_reg = pd.to_datetime(args.date).normalize()
        elif _prices_reg:
            _all_d_reg = sorted(set().union(*[df.index for df in _prices_reg.values() if df is not None and not df.empty]))
            _mons_reg = pd.date_range(min(_all_d_reg), max(_all_d_reg), freq="W-MON")
            _as_reg = _mons_reg[-1] if len(_mons_reg) else pd.Timestamp(_all_d_reg[-1])
        else:
            _as_reg = pd.Timestamp.today().normalize()
        _as_reg_cap = _as_of_capped_for_overlay(_as_reg)
        _reg_ctrl = RegimeController(prices_dict=_prices_reg or {}, as_of=_as_reg_cap)
        regime_state = _reg_ctrl.compute(_as_reg_cap)
        _reg_ctrl.write_regime_status(regime_state, ROOT / "outputs" / "regime_status.json")
    except Exception as _reg_e:
        print(f"[REGIME][WARN] {str(_reg_e)}", flush=True)

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
                import datetime as _dt_news
                from src.core.config import NEWS_DIR
                from src.data.unified_news_loader import UnifiedNewsLoader

                _today = _dt_news.date.today()
                _start = (_today - _dt_news.timedelta(days=90)).isoformat()
                _end = _today.isoformat()
                _loader_data_dir = os.environ.get("DATA_DIR", NEWS_DIR)
                _loader = UnifiedNewsLoader(str(_loader_data_dir))
                _loaded = _loader.load(_ticker_list, _start, _end)
                for _ticker, _by_date in _loaded.items():
                    for _d, _payload in _by_date.items():
                        _news_signals.setdefault(_ticker, {})[_d] = {
                            "sentiment": float(_payload.get("sentiment_score", 0.5)),
                            "supply_chain": float(_payload.get("supply_chain_score", 0.5)),
                        }
            except Exception:
                pass
            _model_cfg_path = ROOT / "config" / "model_config.yaml"
            _train_years = 4
            _today = date.today()
            try:
                _train_start = _today.replace(year=_today.year - _train_years)
            except ValueError:
                _train_start = _today.replace(month=2, day=28, year=_today.year - _train_years)
            _train_end = _today - timedelta(days=365)
            _test_start = _train_end
            _test_end = _today
            with open(_model_cfg_path, "r", encoding="utf-8") as _f_mc:
                _mc = yaml.safe_load(_f_mc) or {}
            _mc.setdefault("training", {})
            _mc["training"]["train_start"] = str(_train_start)
            _mc["training"]["train_end"] = str(_train_end)
            _mc["training"]["test_start"] = str(_test_start)
            _mc["training"]["test_end"] = str(_test_end)
            with open(_model_cfg_path, "w", encoding="utf-8") as _f_mc:
                yaml.dump(_mc, _f_mc, default_flow_style=False, sort_keys=False, allow_unicode=True)
            _winner_model, _winner_type, _winner_ic = get_best_model(
                prices_dict=_prices_dict,
                news_signals=_news_signals if _news_signals else None,
                config_path=_model_cfg_path,
            )
            if _winner_type != "tech_only":
                print(f"[REBALANCE] Factory winner: {_winner_type} IC={_winner_ic:.4f} - model active", flush=True)
            else:
                print("[REBALANCE] Factory returned tech_only (no ML model passed IC gate)", flush=True)
        except Exception as _e:
            print(f"[REBALANCE][WARN] Factory skipped: {_e}", flush=True)

    if args.track == "D":
        import run_execution
        import pandas as pd
        config = load_data_config()
        data_dir = config["data_dir"]
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
        prices_dict = load_prices(data_dir, ticker_list)
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
        as_of = _as_of_capped_for_overlay(as_of)
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
        _bottom_n_d = int(regime_state.get("n_shorts", 0))
        print(
            f"[TRACK D] Regime={regime_state.get('regime_state', 'Expansion')} → n_shorts={_bottom_n_d}",
            flush=True,
        )
        config_d_run = {**config_d, "bottom_n": _bottom_n_d}
        weights_result = rebalance_long_short(
            scores, scores_df, prices_dict, regime_status, config_d_run,
        )
        out_dir = ROOT / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "last_valid_weights.json", "w", encoding="utf-8") as f:
            json.dump({"as_of": str(as_of.date()), "weights": weights_result.to_dict()}, f, indent=2)

    import pandas as pd
    import run_execution
    from src.execution.planner import ExecutionPlanner
    from src.risk.policy import RiskPolicy, _benchmarks_dir, _load_benchmark_close

    _spy_bench = _load_benchmark_close(_benchmarks_dir() / "SPY.csv")

    _plan_path = ROOT / "outputs" / "execution_plan_latest.json"
    _fill_records: list = []
    _exit_code = 0

    if args.track == "D":
        argv = [
            "run_execution",
            "--tickers",
            tickers,
            "--top-n",
            str(int(regime_state.get("max_longs", args.top_n))),
        ]
        if args.date:
            argv.extend(["--date", args.date])
        argv.extend(["--rebalance"])
        if args.live:
            argv.extend(["--mode", "paper"])
            if args.confirm_paper and not args.dry_run:
                argv.append("--confirm-paper")
        else:
            argv.extend(["--mode", "mock"])

        old_argv = sys.argv
        try:
            sys.argv = argv
            result = run_execution.main()
            _exit_code = int(result[0] if isinstance(result, tuple) else result)
            _fill_records = result[1] if isinstance(result, tuple) and len(result) > 1 else []
        finally:
            sys.argv = old_argv

        _as_cap_d = _as_of_capped_for_overlay(as_of)
        _constraints_d = RiskPolicy().evaluate(_as_cap_d)
        _tgt_d = _target_from_weights_or_aux(weights_result, _as_cap_d, {})
        _nav_d = _resolve_nav_usd()
        _nq_d = _get_nq_price_or_none()
        _plan_d = _ensure_plan_audit(
            ExecutionPlanner().reconcile(
                _tgt_d,
                _constraints_d,
                nav=Decimal(str(_nav_d)),
                nq_price=_nq_d,
                prices_dict=prices_dict,
                spy_series=_spy_bench,
            )
        )
        _write_execution_plan_json(_plan_d, _plan_path, target=_tgt_d)
        for _line in _plan_d.audit_log:
            print(f"[PLAN] {_line}", flush=True)
        _append_risk_metadata_from_constraints(_constraints_d, str(_as_cap_d.date()))
        _finalize_rebalance_audit(
            _run_id=_run_id,
            tickers=tickers,
            args=args,
            regime_state=regime_state,
            _fill_records=_fill_records,
            _exit_code=_exit_code,
        )
        try:
            from src.execution.performance_logger import update_regime_ledger

            _reg = str(regime_state.get("regime_state", "UNKNOWN"))
            _cid = json.dumps(regime_state, separators=(",", ":"), default=str)[:512]
            update_regime_ledger(
                regime=_reg,
                combination_id=_cid,
                weekly_return=0.0,
                weekly_drawdown=0.0,
                ledger_path=None,
                timestamp=pd.Timestamp(as_of).to_pydatetime(),
            )
        except Exception:
            pass
        return _exit_code

    _cfg2 = load_data_config()
    _data_dir2 = _cfg2["data_dir"]
    _tick2 = [t.strip() for t in tickers.split(",") if t.strip()]
    _prices2 = load_prices(_data_dir2, _tick2)
    if args.date:
        _as2 = pd.to_datetime(args.date).normalize()
        _as2 = _as_of_capped_for_overlay(_as2)
    elif _prices2:
        _all_d2 = sorted(
            set().union(
                *[
                    df.index
                    for df in _prices2.values()
                    if df is not None and not getattr(df, "empty", True)
                ]
            )
        )
        _mons2 = pd.date_range(min(_all_d2), max(_all_d2), freq="W-MON")
        _as2 = _mons2[-1] if len(_mons2) else pd.Timestamp(_all_d2[-1])
        _as2 = _as_of_capped_for_overlay(_as2)
    else:
        _as2 = pd.Timestamp.today().normalize()
        _as2 = _as_of_capped_for_overlay(_as2)

    from src.core.target_weight_pipeline import compute_target_weights as _pipe_ctw

    _as_capped = _as_of_capped_for_overlay(_as2)
    _score_floor = run_execution._get_score_floor()
    _top_n_alpha = int(regime_state.get("max_longs", args.top_n))
    _weights_series, _aux = _pipe_ctw(
        _as2,
        _tick2,
        _prices2,
        _data_dir2,
        top_n=_top_n_alpha,
        path="weekly",
        return_aux=True,
        llm_enabled=not args.no_llm,
        score_floor=_score_floor,
    )
    (ROOT / "outputs").mkdir(parents=True, exist_ok=True)
    with open(ROOT / "outputs" / "last_valid_weights.json", "w", encoding="utf-8") as _f_lw:
        json.dump({"as_of": str(_as2.date()), "weights": _weights_series.to_dict()}, _f_lw, indent=2)

    _constraints = RiskPolicy().evaluate(_as_capped)
    _aux_d = _aux if isinstance(_aux, dict) else {}
    _target_pf = _target_from_weights_or_aux(_weights_series, _as_capped, _aux_d)
    _nav_usd = _resolve_nav_usd()
    _nq_px = _get_nq_price_or_none()
    _plan = _ensure_plan_audit(
        ExecutionPlanner().reconcile(
            _target_pf,
            _constraints,
            nav=Decimal(str(_nav_usd)),
            nq_price=_nq_px,
            prices_dict=_prices2,
            spy_series=_spy_bench,
        )
    )
    _write_execution_plan_json(_plan, _plan_path, target=_target_pf)
    for _line in _plan.audit_log:
        print(f"[PLAN] {_line}", flush=True)
    _append_risk_metadata_from_constraints(_constraints, str(_as_capped.date()))

    if not args.dry_run and args.live and args.confirm_paper:
        try:
            _fill_records = _submit_plan_to_ib(_plan, float(_nav_usd), _prices2, _as2, _run_id)
        except Exception as _sub_e:
            print(f"[PLAN][WARN] Live submit failed: {_sub_e}", flush=True)
            _exit_code = 1
    elif args.live and not args.dry_run and not args.confirm_paper:
        print("(Paper: DRY-RUN. Use --confirm-paper to submit orders.)", flush=True)

    _finalize_rebalance_audit(
        _run_id=_run_id,
        tickers=tickers,
        args=args,
        regime_state=regime_state,
        _fill_records=_fill_records,
        _exit_code=_exit_code,
    )
    try:
        from src.execution.performance_logger import update_regime_ledger

        _reg = str(regime_state.get("regime_state", "UNKNOWN"))
        _cid = json.dumps(regime_state, separators=(",", ":"), default=str)[:512]
        update_regime_ledger(
            regime=_reg,
            combination_id=_cid,
            weekly_return=0.0,
            weekly_drawdown=0.0,
            ledger_path=None,
            timestamp=pd.Timestamp(_as_capped).to_pydatetime(),
        )
    except Exception:
        pass
    return _exit_code


if __name__ == "__main__":
    sys.exit(main())
