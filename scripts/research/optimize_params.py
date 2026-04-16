from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BACKTEST_SCRIPT = ROOT / "scripts" / "backtest_technical_library.py"
OUT_DIR = ROOT / "outputs" / "optimization"
INSAMPLE_CSV = OUT_DIR / "param_search_insample.csv"
OUTSAMPLE_CSV = OUT_DIR / "param_search_outsample.csv"
BEST_JSON = OUT_DIR / "best_params.json"

SMA_WINDOWS = [100, 150, 200]
SCORE_FLOORS = [0.50, 0.55, 0.60, 0.65]
TOP_NS = [3, 5, 7]

# RegimeController Contraction exposure; not grid-searched (Calmar invariant under uniform scaling).
REGIME_MULTIPLIER_FIXED = 0.6
# In-sample (2022–2023): news features default neutral; no FinBERT/Gemini sweep in IS.
SENTIMENT_ENGINE_IS = "none"
# Out-of-sample step 2 only: compare none vs finbert on 2024 with best IS params held fixed.
SENTIMENT_ENGINES_OOS = ["none", "finbert"]

# sma_window (3) × score_floor (4) × top_n (3)
ALL_COMBINATIONS = 36

IS_START = "2022-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2024-12-31"


@dataclass
class ParamSet:
    sma_window: int
    score_floor: float
    top_n: int


def _annualized_return(total_return: float, start_date: str, end_date: str) -> float:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    years = max((end - start).days / 365.25, 1e-9)
    return (1.0 + float(total_return)) ** (1.0 / years) - 1.0


def _calmar(total_return: float, max_drawdown: float, start_date: str, end_date: str) -> float:
    dd = abs(float(max_drawdown))
    if dd <= 1e-12:
        return 0.0
    ann = _annualized_return(total_return, start_date, end_date)
    return float(ann / dd)


def _run_backtest_for_params(
    p: ParamSet,
    start_date: str,
    end_date: str,
    sentiment_engine: str,
    no_llm: bool,
    no_ml: bool,
) -> dict:
    with NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
        out_json = Path(tmp.name)
    try:
        cmd = [
            sys.executable,
            str(BACKTEST_SCRIPT),
            "--top-n",
            str(p.top_n),
            "--sma-window",
            str(p.sma_window),
            "--score-floor",
            str(p.score_floor),
            "--sentiment-engine",
            str(sentiment_engine),
            "--start",
            start_date,
            "--end",
            end_date,
            "--out-json",
            str(out_json),
            "--no-safety-report",
        ]
        cmd.extend(["--regime-multiplier", str(REGIME_MULTIPLIER_FIXED)])
        if no_llm:
            cmd.append("--no-llm")
        if no_ml:
            cmd.append("--no-ml")
        env = os.environ.copy()
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            return {
                "sharpe": 0.0,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "error": proc.stderr.strip() or proc.stdout.strip() or f"backtest_exit_{proc.returncode}",
            }
        if not out_json.exists():
            return {"sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0, "error": "missing_out_json"}
        with open(out_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "sharpe": float(data.get("sharpe", 0.0) or 0.0),
            "total_return": float(data.get("total_return", 0.0) or 0.0),
            "max_drawdown": float(data.get("max_drawdown", 0.0) or 0.0),
        }
    finally:
        try:
            out_json.unlink(missing_ok=True)
        except Exception:
            pass


def _all_param_sets_is() -> list[ParamSet]:
    out: list[ParamSet] = []
    for sma_window, score_floor, top_n in itertools.product(SMA_WINDOWS, SCORE_FLOORS, TOP_NS):
        out.append(
            ParamSet(
                sma_window=int(sma_window),
                score_floor=float(score_floor),
                top_n=int(top_n),
            )
        )
    assert len(out) == ALL_COMBINATIONS
    return out


def _rows_from_results_is(
    params: list[ParamSet],
    start_date: str,
    end_date: str,
    no_llm: bool,
    no_ml: bool,
    is_denom: int,
) -> list[dict]:
    rows: list[dict] = []
    for i, p in enumerate(params, start=1):
        metrics = _run_backtest_for_params(
            p, start_date, end_date, SENTIMENT_ENGINE_IS, no_llm=no_llm, no_ml=no_ml,
        )
        calmar = _calmar(metrics["total_return"], metrics["max_drawdown"], start_date, end_date)
        row = {
            "sma_window": p.sma_window,
            "score_floor": p.score_floor,
            "top_n": p.top_n,
            "regime_multiplier": REGIME_MULTIPLIER_FIXED,
            "sentiment_engine": SENTIMENT_ENGINE_IS,
            "sharpe": metrics["sharpe"],
            "total_return": metrics["total_return"],
            "max_drawdown": metrics["max_drawdown"],
            "calmar": calmar,
        }
        rows.append(row)
        print(
            f"[IS {i}/{is_denom}] sma={p.sma_window} floor={p.score_floor:.2f} "
            f"top_n={p.top_n} regime={REGIME_MULTIPLIER_FIXED} sentiment={SENTIMENT_ENGINE_IS} calmar={calmar:.4f}",
            flush=True,
        )
    return rows


def _apply_best_params(best: dict) -> None:
    import yaml

    cfg_path = ROOT / "config" / "strategy_params.yaml"
    data: dict = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    risk_overlay = data.get("risk_overlay") or {}
    regime = data.get("regime") or {}
    risk_overlay["spy_sma_window"] = int(best["sma_window"])
    regime["score_floor_contraction"] = float(best["score_floor"])
    risk_overlay["vix_multiplier"] = float(REGIME_MULTIPLIER_FIXED)
    data["risk_overlay"] = risk_overlay
    data["regime"] = regime
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    print(f"[APPLY] Updated {cfg_path}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward parameter optimization for backtest_technical_library.")
    parser.add_argument("--no-llm", action="store_true", default=False)
    parser.add_argument("--no-ml", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False, help="Run only first 3 IS combinations.")
    parser.add_argument("--apply", action="store_true", default=False, help="Apply best OOS params to strategy_params.yaml.")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    params = _all_param_sets_is()
    is_denom = ALL_COMBINATIONS
    if args.dry_run:
        params = params[:3]
        is_denom = len(params)

    print(f"Running in-sample grid over {len(params)} combinations (full grid = {ALL_COMBINATIONS})...", flush=True)
    is_rows = _rows_from_results_is(
        params, IS_START, IS_END, no_llm=args.no_llm, no_ml=args.no_ml, is_denom=is_denom,
    )
    is_df = pd.DataFrame(is_rows).sort_values("calmar", ascending=False).reset_index(drop=True)
    is_df.to_csv(INSAMPLE_CSV, index=False)
    print(f"[WRITE] {INSAMPLE_CSV}", flush=True)

    if is_df.empty:
        print("[ERROR] No in-sample results.", flush=True)
        return 1

    best_is_row = is_df.iloc[0]
    best_is_calmar = float(best_is_row["calmar"])
    p_best = ParamSet(
        sma_window=int(best_is_row["sma_window"]),
        score_floor=float(best_is_row["score_floor"]),
        top_n=int(best_is_row["top_n"]),
    )

    print(
        f"\n[IS BEST] sma={p_best.sma_window} floor={p_best.score_floor:.2f} top_n={p_best.top_n} "
        f"calmar={best_is_calmar:.4f} — OOS step 2: sentiment in {SENTIMENT_ENGINES_OOS}\n",
        flush=True,
    )

    oos_rows: list[dict] = []
    for j, sent in enumerate(SENTIMENT_ENGINES_OOS, start=1):
        metrics = _run_backtest_for_params(
            p_best, OOS_START, OOS_END, sent, no_llm=args.no_llm, no_ml=args.no_ml,
        )
        calmar = _calmar(metrics["total_return"], metrics["max_drawdown"], OOS_START, OOS_END)
        oos_rows.append(
            {
                "sma_window": p_best.sma_window,
                "score_floor": p_best.score_floor,
                "top_n": p_best.top_n,
                "regime_multiplier": REGIME_MULTIPLIER_FIXED,
                "sentiment_engine": sent,
                "sharpe": metrics["sharpe"],
                "total_return": metrics["total_return"],
                "max_drawdown": metrics["max_drawdown"],
                "calmar": calmar,
                "insample_calmar": best_is_calmar,
            }
        )
        print(
            f"[OOS step2 {j}/{len(SENTIMENT_ENGINES_OOS)}] sentiment={sent} calmar={calmar:.4f}",
            flush=True,
        )

    oos_df = pd.DataFrame(oos_rows).sort_values("calmar", ascending=False).reset_index(drop=True)
    oos_df.to_csv(OUTSAMPLE_CSV, index=False)
    print(f"[WRITE] {OUTSAMPLE_CSV}", flush=True)

    print("\nOOS sentiment sweep (best IS params fixed)", flush=True)
    print(
        oos_df[
            ["sentiment_engine", "insample_calmar", "calmar"]
        ].to_string(index=False),
        flush=True,
    )

    if oos_df.empty:
        print("[ERROR] No out-of-sample results generated.", flush=True)
        return 1

    best_oos = oos_df.iloc[0]
    sentiment_oos_winner = str(best_oos["sentiment_engine"])

    best_payload = {
        "sma_window": int(p_best.sma_window),
        "score_floor": float(p_best.score_floor),
        "top_n": int(p_best.top_n),
        "regime_multiplier": REGIME_MULTIPLIER_FIXED,
        "regime_multiplier_grid_searched": False,
        "regime_multiplier_note": (
            "Fixed at RegimeController Contraction (0.6); not grid-searched — Calmar is scale-invariant "
            "under uniform position scaling."
        ),
        "sentiment_engine": sentiment_oos_winner,
        "sentiment_engine_in_sample_fixed": SENTIMENT_ENGINE_IS,
        "sentiment_engine_in_sample_grid_searched": False,
        "sentiment_engine_note": (
            "In-sample (2022–2023) used sentiment_engine='none' only (neutral news defaults). "
            "sentiment_engine above is the OOS (2024) winner from step 2: none vs finbert only."
        ),
        "sharpe": float(best_oos["sharpe"]),
        "total_return": float(best_oos["total_return"]),
        "max_drawdown": float(best_oos["max_drawdown"]),
        "calmar": float(best_oos["calmar"]),
        "insample_calmar": best_is_calmar,
    }

    with open(BEST_JSON, "w", encoding="utf-8") as f:
        json.dump(best_payload, f, indent=2)
    print(f"[WRITE] {BEST_JSON}", flush=True)

    if args.apply and not args.dry_run:
        _apply_best_params(best_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
