"""
E2E pipeline: data updates → factory (rolling window) → OOS backtest → mock execution summary.

Single entry point; does not modify other scripts. See docs/INDEX.md for canonical docs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _get_watchlist() -> list[str]:
    import yaml

    path = ROOT / "config" / "data_config.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    wl = (data.get("universe_selection") or {}).get("watchlist", [])
    return [str(t).strip() for t in wl if str(t).strip()]


def _read_training_oos_bounds(model_cfg: Path) -> tuple[str | None, str | None]:
    import yaml

    if not model_cfg.exists():
        return (None, None)
    with open(model_cfg, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    tr = cfg.get("training") or {}
    return (tr.get("test_start"), tr.get("test_end"))


def _read_factory_winner_metrics() -> tuple[str, float]:
    p = ROOT / "models" / "factory_winner.json"
    if not p.exists():
        return ("unknown", 0.0)
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        mt = str(d.get("model_type", "unknown"))
        ic = float(d.get("ic", 0.0))
        return (mt, ic)
    except Exception:
        return ("unknown", 0.0)


def _json_subset_from_backtest(result: dict) -> dict:
    keys = (
        "sharpe",
        "total_return",
        "max_drawdown",
        "n_rebalances",
        "period_start",
        "period_end",
        "tickers",
        "weekly_returns",
        "aggregator_audit_summary",
    )
    return {k: result[k] for k in keys if k in result}


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end: data → factory → OOS backtest → execution summary.")
    parser.add_argument("--skip-data", action="store_true", help="Skip Stage 1 (price + news updates).")
    parser.add_argument("--skip-model", action="store_true", help="Skip Stage 2 (use cached factory winner).")
    parser.add_argument("--force-retrain", action="store_true", help="Stage 2: delete factory cache before factory run.")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip Stage 3 OOS backtest.")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated; default: data_config watchlist.")
    parser.add_argument("--top-n", type=int, default=5, dest="top_n")
    parser.add_argument("--score-floor", type=float, default=0.0, dest="score_floor")
    parser.add_argument("--no-llm", action="store_true", default=False, dest="no_llm",
                        help="Stage 3: disable LLM signal (always True in pipeline for speed).")
    parser.add_argument("--track", type=str, default="A", choices=["A", "D"],
                        help="Strategy track: A = ML blend, D = 130/30 long/short.")
    parser.add_argument("--no-hedge", action="store_true", default=False, dest="no_hedge",
                        help="Stage 4: disable SMH hedge.")
    parser.add_argument(
        "--dry-run",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Stage 4: mock mode when true (default); use --no-dry-run for paper mode.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))

    if args.tickers:
        ticker_list = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        ticker_list = _get_watchlist()
    if not ticker_list:
        print("ERROR: No tickers (set --tickers or data_config watchlist).", flush=True)
        return 1
    tickers_str = ",".join(ticker_list)

    # --- Stage 1 ---
    if not args.skip_data:
        import update_news_data
        import update_price_data

        _saved = sys.argv
        try:
            sys.argv = ["update_price_data.py"]
            _u = update_price_data.main()
        finally:
            sys.argv = _saved
        if _u != 0:
            print(
                "WARNING: Price data update returned non-zero; continuing.",
                file=sys.stderr,
                flush=True,
            )
        try:
            sys.argv = ["update_news_data.py"]
            _n = update_news_data.main()
        finally:
            sys.argv = _saved
        if _n != 0:
            print(
                "WARNING: News data update returned non-zero; continuing.",
                file=sys.stderr,
                flush=True,
            )

    model_cfg = ROOT / "config" / "model_config.yaml"

    # --- Stage 2 ---
    if not args.skip_model:
        if args.force_retrain:
            _fw = ROOT / "models" / "factory_winner.json"
            if _fw.exists():
                _fw.unlink()
        from run_factory import CONFIG_PATH as _FACTORY_CFG_PATH
        from run_factory import _patch_model_config_training_window

        _patch_model_config_training_window(_FACTORY_CFG_PATH, 4)
        import run_factory

        _saved = sys.argv
        try:
            sys.argv = ["run_factory.py"]
            _fc = run_factory.main()
        finally:
            sys.argv = _saved
        if _fc != 0:
            print(f"WARNING: run_factory.main() exit {_fc}; continuing.", file=sys.stderr, flush=True)
    else:
        print("[STAGE 2] Using cached factory winner.", flush=True)

    oos_start, oos_end = _read_training_oos_bounds(model_cfg)
    model_type, ic = _read_factory_winner_metrics()

    # --- Stage 3 ---
    oos_sharpe: float | None = None
    oos_cagr: float | None = None
    oos_maxdd: float | None = None
    oos_out = ROOT / "outputs" / "e2e_oos_backtest.json"

    if not args.skip_backtest:
        if not oos_start or not oos_end:
            print(
                "WARNING: training.test_start/test_end missing in model_config.yaml; skipping OOS backtest.",
                flush=True,
            )
        else:
            import yaml
            from src.data.csv_provider import load_prices

            _dc_path = ROOT / "config" / "data_config.yaml"
            _data_dir = ROOT / "data" / "stock_market_data"
            if _dc_path.exists():
                with open(_dc_path, encoding="utf-8") as _f:
                    _dc = yaml.safe_load(_f) or {}
                _ds = (_dc.get("data_sources") or {})
                if _ds.get("data_dir"):
                    _data_dir = Path(_ds["data_dir"])
            import importlib.util

            _bt_path = ROOT / "scripts" / "backtest_technical_library.py"
            _spec = importlib.util.spec_from_file_location("backtest_technical_library", _bt_path)
            if _spec is None or _spec.loader is None:
                print("ERROR: Could not load backtest_technical_library.", flush=True)
            else:
                _bt = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_bt)
                run_backtest_master_score = _bt.run_backtest_master_score
                prices_dict = load_prices(_data_dir, ticker_list)
                result: dict | None = None
                try:
                    if prices_dict:
                        result = run_backtest_master_score(
                            prices_dict,
                            data_dir=_data_dir,
                            news_dir=None,
                            performance_csv=None,
                            top_n=int(args.top_n),
                            score_floor=args.score_floor,
                            start_date=str(oos_start),
                            end_date=str(oos_end),
                            llm_enabled=False,  # always off in pipeline (speed)
                            verbose=False,
                        )
                except Exception as _e:
                    print(f"WARNING: OOS backtest raised: {_e}", flush=True)
                    result = None
                if isinstance(result, dict):
                    oos_sharpe = result.get("sharpe", result.get("sharpe_ratio"))
                    if oos_sharpe is not None:
                        oos_sharpe = float(oos_sharpe)
                    oos_cagr = result.get("cagr", result.get("annualized_return"))
                    if oos_cagr is None and result.get("total_return") is not None:
                        import pandas as pd

                        try:
                            d0 = pd.to_datetime(oos_start)
                            d1 = pd.to_datetime(oos_end)
                            yrs = max((d1 - d0).days / 365.25, 1e-6)
                            tr = float(result["total_return"])
                            oos_cagr = (1.0 + tr) ** (1.0 / yrs) - 1.0
                        except Exception:
                            oos_cagr = None
                    elif oos_cagr is not None:
                        oos_cagr = float(oos_cagr)
                    mdd = result.get("max_drawdown")
                    oos_maxdd = float(mdd) if mdd is not None else None
                    oos_out.parent.mkdir(parents=True, exist_ok=True)
                    with open(oos_out, "w", encoding="utf-8") as _fj:
                        json.dump(_json_subset_from_backtest(result), _fj, indent=2)
                else:
                    if oos_out.exists():
                        try:
                            with open(oos_out, encoding="utf-8") as _fj:
                                disk = json.load(_fj)
                            oos_sharpe = disk.get("sharpe", disk.get("sharpe_ratio"))
                            if oos_sharpe is not None:
                                oos_sharpe = float(oos_sharpe)
                            oos_cagr = disk.get("cagr", disk.get("annualized_return"))
                            if oos_cagr is None and disk.get("total_return") is not None:
                                import pandas as pd

                                d0 = pd.to_datetime(oos_start)
                                d1 = pd.to_datetime(oos_end)
                                yrs = max((d1 - d0).days / 365.25, 1e-6)
                                tr = float(disk["total_return"])
                                oos_cagr = (1.0 + tr) ** (1.0 / yrs) - 1.0
                            elif oos_cagr is not None:
                                oos_cagr = float(oos_cagr)
                            mdd = disk.get("max_drawdown")
                            oos_maxdd = float(mdd) if mdd is not None else None
                        except Exception:
                            pass
    else:
        if oos_out.exists() and oos_start and oos_end:
            try:
                with open(oos_out, encoding="utf-8") as _fj:
                    disk = json.load(_fj)
                oos_sharpe = disk.get("sharpe", disk.get("sharpe_ratio"))
                if oos_sharpe is not None:
                    oos_sharpe = float(oos_sharpe)
                oos_cagr = disk.get("cagr", disk.get("annualized_return"))
                if oos_cagr is None and disk.get("total_return") is not None:
                    import pandas as pd

                    d0 = pd.to_datetime(oos_start)
                    d1 = pd.to_datetime(oos_end)
                    yrs = max((d1 - d0).days / 365.25, 1e-6)
                    tr = float(disk["total_return"])
                    oos_cagr = (1.0 + tr) ** (1.0 / yrs) - 1.0
                elif oos_cagr is not None:
                    oos_cagr = float(oos_cagr)
                mdd = disk.get("max_drawdown")
                oos_maxdd = float(mdd) if mdd is not None else None
            except Exception:
                pass

    # --- Stage 4 ---
    import run_execution

    _mode = "mock" if args.dry_run else "paper"
    _argv = [
        "run_execution",
        "--tickers",
        tickers_str,
        "--top-n",
        str(int(args.top_n)),
        "--mode",
        _mode,
        "--regime-multiplier",
        "1.0",
    ]
    if args.track == "D":
        _argv.extend(["--track", "D"])
    if args.no_hedge:
        _argv.append("--no-hedge")
    _saved = sys.argv
    try:
        sys.argv = _argv
        _ex = run_execution.main()
    finally:
        sys.argv = _saved
    _exit_tuple = _ex if isinstance(_ex, tuple) else (_ex, [])
    _exec_code = int(_exit_tuple[0])
    if _exec_code != 0:
        print(f"WARNING: run_execution exit {_exec_code}", file=sys.stderr, flush=True)

    weights_path = ROOT / "outputs" / "last_valid_weights.json"
    top3_parts: list[str] = []
    if weights_path.exists():
        try:
            with open(weights_path, encoding="utf-8") as f:
                lw = json.load(f)
            wmap = lw.get("weights") or {}
            ranked = sorted(wmap.items(), key=lambda kv: -float(kv[1]))[:3]
            for sym, wt in ranked:
                top3_parts.append(f"{sym}={100.0 * float(wt):.1f}%")
        except Exception:
            top3_parts = ["(unreadable)"]
    weights_line = " ".join(top3_parts) if top3_parts else "(none)"

    # --- Stage 5 ---
    def _fmt_sharpe(x: float | None) -> str:
        return f"{x:.3f}" if x is not None else "N/A"

    def _fmt_pct(x: float | None) -> str:
        return f"{x:.2%}" if x is not None else "N/A"

    oos_line_start = oos_start or "?"
    oos_line_end = oos_end or "?"

    if oos_sharpe is None:
        status = "WARN"
        exit_code = 0
    elif oos_sharpe > 0:
        status = "PASS"
        exit_code = 0
    else:
        status = "FAIL"
        exit_code = 1

    # ASCII separators only (cp1252 consoles cannot print box-drawing / dingbats).
    bar = "=" * 46
    print(f"\n{bar}", flush=True)
    print("E2E PIPELINE SUMMARY", flush=True)
    print(bar, flush=True)
    print(f"Model:        {model_type} (IC={ic:.4f})", flush=True)
    print(f"OOS window:   {oos_line_start} -> {oos_line_end}", flush=True)
    print(f"OOS Sharpe:   {_fmt_sharpe(oos_sharpe)}", flush=True)
    print(f"OOS CAGR:     {_fmt_pct(oos_cagr)}", flush=True)
    print(f"Max Drawdown: {_fmt_pct(oos_maxdd)}", flush=True)
    print(f"Weights:      {weights_line}", flush=True)
    print(bar, flush=True)
    if status == "PASS":
        print("STATUS: PASS [OK]", flush=True)
    elif status == "WARN":
        print("STATUS: WARN [!]", flush=True)
    else:
        print("STATUS: FAIL [X]", flush=True)
    print(bar, flush=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
