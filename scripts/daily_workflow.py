"""
Task 7: Standalone daily workflow runner.

Runs update_price_data (with SPY), update_news_data, then generate_daily_weights
via subprocess. Reads watchlist from data_config.yaml (no CLI args required).
Non-fatal step failures; exits 0 when all steps have been attempted.
UI: after generate_daily_weights, renders system health table from last_signal.json + news files.

Usage:
  python scripts/daily_workflow.py
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.core.config import NEWS_DIR as _NEWS_DIR

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _render_health_table(last_signal_path: Path, news_dir: Path, today_str: str) -> None:
    """Load last_signal.json and news files; render health table (rich or plain)."""
    if not last_signal_path.exists():
        print("last_signal.json not found, skipping health table", flush=True)
        return
    try:
        with open(last_signal_path, "r", encoding="utf-8") as f:
            last_signal = json.load(f)
    except Exception as e:
        logger.warning("Failed to read last_signal.json: %s", e)
        return
    if not last_signal:
        return
    today = datetime.now().date()
    stale_cutoff = today - timedelta(days=7)
    tickers = list(last_signal.keys())
    headlines = {}
    news_stale = {}
    for t in tickers:
        headlines[t] = "-"
        news_stale[t] = False
        path = news_dir / f"{t}_news.json"
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            articles = raw if isinstance(raw, list) else []
            if not articles:
                continue
            date_key = "published_at" if "published_at" in (articles[0] or {}) else "date"
            articles = sorted(articles, key=lambda a: (a or {}).get(date_key) or "", reverse=True)
            first = articles[0] if articles else {}
            title = (first or {}).get("title") or (first or {}).get("headline")
            if title is not None:
                headlines[t] = str(title)
            dt_str = (first or {}).get(date_key)
            if dt_str:
                try:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).date()
                    if dt < stale_cutoff:
                        news_stale[t] = True
                except Exception:
                    pass
        except Exception:
            pass

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title=f"System Health - {today_str}")
        table.add_column("Ticker")
        table.add_column("ML_Score")
        table.add_column("VolFilter")
        table.add_column("Final_Weight")
        table.add_column("Top_News_Headline", max_width=55)
        for t in tickers:
            rec = last_signal.get(t) or {}
            score = rec.get("score")
            if score is not None:
                sc_str = f"{float(score):.3f}"
                if score > 0.6:
                    sc_style = "green"
                elif score < 0.4:
                    sc_style = "red"
                else:
                    sc_style = "white"
            else:
                sc_str = "N/A"
                sc_style = "white"
            vol_triggered = rec.get("vol_triggered", False)
            vf_str = "YES" if vol_triggered else "NO"
            vf_style = "red" if vol_triggered else "green"
            w = rec.get("weight", 0.0)
            w_str = f"{float(w):.1%}"
            head = (headlines.get(t) or "-")[:55]
            if len(headlines.get(t) or "-") > 55:
                head = head[:52] + "..."
            table.add_row(
                t,
                f"[{sc_style}]{sc_str}[/]",
                f"[{vf_style}]{vf_str}[/]",
                w_str,
                head,
            )
        console.print(table)
        for t in tickers:
            if news_stale.get(t):
                console.print(f"WARNING: {t} - news feed may be lagging (last article > 7 days ago)", style="bold yellow")
    except ImportError:
        sep = "-" * 100
        print(sep, flush=True)
        print(f"{'Ticker':<8} {'ML_Score':>10} {'VolFilter':>10} {'Final_Weight':>12}  Top_News_Headline", flush=True)
        print(sep, flush=True)
        for t in tickers:
            rec = last_signal.get(t) or {}
            score = rec.get("score")
            sc_str = f"{float(score):.3f}" if score is not None else "N/A"
            vf_str = "YES" if rec.get("vol_triggered") else "NO"
            w_str = f"{float(rec.get('weight', 0)):.1%}"
            head = (headlines.get(t) or "-")[:55]
            if len(headlines.get(t) or "-") > 55:
                head = head[:52] + "..."
            print(f"{t:<8} {sc_str:>10} {vf_str:>10} {w_str:>12}  {head}", flush=True)
        for t in tickers:
            if news_stale.get(t):
                print(f"WARNING: {t} - news feed may be lagging (last article > 7 days ago)", flush=True)


def main() -> int:
    try:
        from src.utils.config_manager import get_config
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        return 1

    cfg = get_config()
    watchlist = cfg.get_watchlist()
    if not watchlist:
        logger.error("Watchlist empty in data_config.yaml")
        return 1
    watchlist_tickers = ",".join(watchlist)
    benchmark = "SPY"
    try:
        bench = cfg.get_param("data_config.universe_selection.benchmark", "SPY")
        if bench:
            benchmark = str(bench)
    except Exception:
        pass
    tickers_with_spy = watchlist_tickers + "," + benchmark if benchmark not in watchlist else watchlist_tickers

    py = sys.executable
    scripts_dir = ROOT / "scripts"

    # 1. Price update (watchlist + SPY)
    r1 = subprocess.run(
        [py, str(scripts_dir / "update_price_data.py"), "--tickers", tickers_with_spy],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("update_price_data.py exit code: %s", r1.returncode)

    # 2. News update (watchlist only)
    r2 = subprocess.run(
        [py, str(scripts_dir / "update_news_data.py"), "--tickers", watchlist_tickers],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("update_news_data.py exit code: %s", r2.returncode)

    # 3. Generate daily weights
    r3 = subprocess.run(
        [py, str(scripts_dir / "generate_daily_weights.py")],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("generate_daily_weights.py exit code: %s", r3.returncode)

    # 4. Upsert signal DB + compute forward returns
    r4 = subprocess.run(
        [py, str(scripts_dir / "update_signal_db.py")],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("update_signal_db.py exit code: %s", r4.returncode)

    # UI: system health table from last_signal.json + news files (canonical NEWS_DIR from .env)
    news_dir = Path(_NEWS_DIR)
    last_signal_path = ROOT / "outputs" / "last_signal.json"
    today_str = datetime.now().strftime("%Y-%m-%d")
    _render_health_table(last_signal_path, news_dir, today_str)

    print("Daily workflow complete.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
