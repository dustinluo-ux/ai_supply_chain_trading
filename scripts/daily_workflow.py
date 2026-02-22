"""
Master Health Dashboard — daily workflow runner.

Pipeline (steps 1-4 run sequentially; all non-fatal):
  Step 1: update_price_data.py     — refresh price CSVs (watchlist + SPY)
  Step 2: update_news_data.py      — fetch latest Marketaux news
  Step 3: generate_daily_weights.py — compute signals → outputs/daily_signals.csv
  Step 4: update_signal_db.py       — upsert → outputs/trading.db

Step 5: render Command Center (rich table; plain fallback if rich not installed).
  Consolidates logic from scripts/check_data_integrity.py — no need to run both.

Usage:
  python scripts/daily_workflow.py
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

_SYS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SYS_ROOT))

from src.core.config import NEWS_DIR as _NEWS_DIR

ROOT = _SYS_ROOT
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Infrastructure checks ──────────────────────────────────────────────────────

def _check_symlink(root: Path) -> tuple[bool, str]:
    """Verify trading_data symlink/junction points to the C:\\ data root."""
    link = root / "trading_data"
    try:
        if link.is_symlink():
            target = os.readlink(str(link))
            resolved = link.resolve()
            ok = resolved.exists()
            return ok, f"{target}  [{'OK' if ok else 'BROKEN'}]"
        elif link.is_dir():
            return True, f"{link.resolve()}  [directory/junction  OK]"
    except Exception as exc:
        return False, f"check error: {exc}"
    return False, "trading_data not found"


def _check_model_status(root: Path) -> tuple[str, bool]:
    """
    Read active model path from config/model_config.yaml.
    Return (display_str, exists).  IC stamp is the validated Phase-3 result.
    """
    try:
        import yaml
        with open(root / "config" / "model_config.yaml", "r", encoding="utf-8") as f:
            mcfg = yaml.safe_load(f)
        rel_path: str = (mcfg.get("training") or {}).get("model_path", "")
        model_file = (root / rel_path) if rel_path else None
        exists = bool(model_file and model_file.exists())
        name = Path(rel_path).name if rel_path else "unknown"
        display = (
            f"{name}  IC=0.0202  PASSED" if exists else f"{name}  [FILE MISSING]"
        )
        return display, exists
    except Exception as exc:
        return f"model_config.yaml unreadable: {exc}", False


def _price_freshness_by_pillar(
    base_dir: Path, pillars: dict
) -> dict[str, dict[str, int]]:
    """
    Single os.walk pass over base_dir (stat only — no CSV read).
    Returns per-pillar counts: {pillar: {"fresh": N, "stale": N, "missing": N}}.
    Fresh = file mtime within the last 24 hours.
    """
    cutoff = datetime.now().timestamp() - 86_400  # 24 h ago

    all_tickers: set[str] = set()
    for tlist in pillars.values():
        for t in (tlist or []):
            if isinstance(t, str) and t.strip():
                all_tickers.add(t.strip().upper())

    ticker_mtime: dict[str, float | None] = {t: None for t in all_tickers}
    for dirpath, _, files in os.walk(str(base_dir)):
        for fname in files:
            if not fname.upper().endswith(".CSV"):
                continue
            stem = Path(fname).stem.upper()
            if stem not in ticker_mtime:
                continue
            mtime = Path(dirpath, fname).stat().st_mtime
            prev = ticker_mtime[stem]
            if prev is None or mtime > prev:
                ticker_mtime[stem] = mtime

    result: dict[str, dict[str, int]] = {}
    for pillar, tlist in pillars.items():
        counts = {"fresh": 0, "stale": 0, "missing": 0}
        for t in (tlist or []):
            if not isinstance(t, str):
                continue
            tu = t.strip().upper()
            mtime = ticker_mtime.get(tu)
            if mtime is None:
                counts["missing"] += 1
            elif mtime >= cutoff:
                counts["fresh"] += 1
            else:
                counts["stale"] += 1
        result[pillar] = counts
    return result


def _gather_news_data(
    news_dir: Path,
    all_tickers: list[str],
    signal_tickers: list[str],
    today_str: str,
) -> tuple[int, int, dict[str, str], dict[str, bool]]:
    """
    Single pass over news JSON files.  Returns:
      today_total       — total articles published today across universe
      today_tickers     — number of tickers that have at least one article today
      headlines         — {ticker: latest_headline} for signal_tickers only
      stale_flags       — {ticker: True if last article >7 days old}
    """
    stale_cutoff = datetime.now().date() - timedelta(days=7)
    signal_set = set(signal_tickers)
    today_total = 0
    today_tickers = 0
    headlines: dict[str, str] = {t: "-" for t in signal_tickers}
    stale_flags: dict[str, bool] = {t: False for t in signal_tickers}

    for t in all_tickers:
        path = news_dir / f"{t}_news.json"
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            articles = raw if isinstance(raw, list) else []
            if not articles:
                continue
            date_key = (
                "published_at" if "published_at" in (articles[0] or {}) else "date"
            )
            # Today count (all tickers)
            today_count = sum(
                1
                for a in articles
                if str((a or {}).get(date_key, ""))[:10] == today_str
            )
            if today_count > 0:
                today_total += today_count
                today_tickers += 1
            # Headline + stale flag (signal tickers only)
            if t in signal_set:
                sorted_arts = sorted(
                    articles,
                    key=lambda a: (a or {}).get(date_key) or "",
                    reverse=True,
                )
                first = sorted_arts[0] if sorted_arts else {}
                title = (first or {}).get("title") or (first or {}).get("headline")
                if title:
                    headlines[t] = str(title)
                dt_str = (first or {}).get(date_key)
                if dt_str:
                    try:
                        dt = datetime.fromisoformat(
                            dt_str.replace("Z", "+00:00")
                        ).date()
                        stale_flags[t] = dt < stale_cutoff
                    except Exception:
                        pass
        except Exception:
            pass

    return today_total, today_tickers, headlines, stale_flags


# ── Command Center renderer ────────────────────────────────────────────────────

def _render_command_center(
    last_signal_path: Path,
    news_dir: Path,
    data_dir: Path,
    root: Path,
    pillars: dict,
    today_str: str,
) -> None:
    """
    Render the Master Command Center.
    Three sections: Infrastructure panel / Signal table / Data Coverage by pillar.
    Uses rich if installed; falls back to plain text.
    """
    # All tickers in universe (flattened)
    all_tickers: list[str] = []
    for tlist in pillars.values():
        for t in (tlist or []):
            if isinstance(t, str) and t.strip():
                all_tickers.append(t.strip().upper())

    # Load last signal
    last_signal: dict = {}
    if last_signal_path.exists():
        try:
            with open(last_signal_path, "r", encoding="utf-8") as f:
                last_signal = json.load(f) or {}
        except Exception:
            pass
    signal_tickers = list(last_signal.keys())

    # Run all checks
    symlink_ok, symlink_str = _check_symlink(root)
    model_str, model_ok = _check_model_status(root)
    pillar_freshness = _price_freshness_by_pillar(data_dir, pillars)
    total_fresh = sum(v["fresh"] for v in pillar_freshness.values())
    total_stale = sum(v["stale"] for v in pillar_freshness.values())
    total_missing = sum(v["missing"] for v in pillar_freshness.values())
    total_tickers = total_fresh + total_stale + total_missing
    news_today, news_tickers_count, headlines, stale_flags = _gather_news_data(
        news_dir, all_tickers, signal_tickers, today_str
    )

    try:
        from rich import box as rich_box
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()

        # ── 1. Infrastructure panel ───────────────────────────────────────────
        infra = Table(
            box=rich_box.SIMPLE,
            show_header=False,
            padding=(0, 1),
            expand=False,
        )
        infra.add_column("Check", style="bold cyan", width=10)
        infra.add_column("Detail", width=64)
        infra.add_column("", width=3, justify="center")

        infra.add_row(
            "Symlink",
            symlink_str,
            "[green]✓[/]" if symlink_ok else "[red]✗[/]",
        )
        infra.add_row(
            "Model",
            model_str,
            "[green]✓[/]" if model_ok else "[red]✗[/]",
        )

        price_detail = f"{total_fresh}/{total_tickers} fresh (<24h)"
        if total_stale:
            price_detail += f"   {total_stale} stale"
        if total_missing:
            price_detail += f"   {total_missing} missing"
        price_icon = (
            "[green]✓[/]"
            if total_stale == 0 and total_missing == 0
            else ("[yellow]~[/]" if total_missing == 0 else "[red]✗[/]")
        )
        infra.add_row("Prices", price_detail, price_icon)

        news_detail = f"{news_today} articles today  ·  {news_tickers_count} tickers covered"
        infra.add_row(
            "News",
            news_detail,
            "[green]✓[/]" if news_today > 0 else "[yellow]~[/]",
        )

        console.print(
            Panel(
                infra,
                title=f"[bold bright_white]⚡ Command Center — {today_str}[/]",
                border_style="bright_blue",
                expand=False,
            )
        )

        # ── 2. Signal table ───────────────────────────────────────────────────
        if last_signal:
            sig = Table(
                title="[bold]Signal Table[/]",
                box=rich_box.SIMPLE_HEAVY,
                show_lines=False,
            )
            sig.add_column("Ticker", style="bold", width=8)
            sig.add_column("ML Score", justify="right", width=9)
            sig.add_column("VolFilter", justify="center", width=10)
            sig.add_column("Weight", justify="right", width=8)
            sig.add_column("Top News Headline", max_width=56)

            for t in signal_tickers:
                rec = last_signal.get(t) or {}
                score = rec.get("score")
                if score is not None:
                    sc_str = f"{float(score):.3f}"
                    sc_style = (
                        "green" if score > 0.6 else ("red" if score < 0.4 else "white")
                    )
                else:
                    sc_str, sc_style = "N/A", "dim"
                vt = rec.get("vol_triggered", False)
                vf_str, vf_style = ("YES", "red") if vt else ("NO", "green")
                w_str = f"{float(rec.get('weight', 0)):.1%}"
                head = headlines.get(t) or "-"
                if len(head) > 56:
                    head = head[:53] + "..."
                head_style = "yellow" if stale_flags.get(t) else "default"
                sig.add_row(
                    t,
                    f"[{sc_style}]{sc_str}[/]",
                    f"[{vf_style}]{vf_str}[/]",
                    w_str,
                    f"[{head_style}]{head}[/]",
                )
            console.print(sig)

        # ── 3. Data coverage by pillar ────────────────────────────────────────
        cov = Table(
            title="[bold]Data Coverage by Pillar[/]",
            box=rich_box.SIMPLE,
        )
        cov.add_column("Pillar", style="bold", width=10)
        cov.add_column("Tickers", justify="right", width=8)
        cov.add_column("Fresh <24h", justify="right", width=11)
        cov.add_column("Stale", justify="right", width=7)
        cov.add_column("Missing", justify="right", width=9)

        for pillar, counts in pillar_freshness.items():
            total = counts["fresh"] + counts["stale"] + counts["missing"]
            f_style = (
                "green"
                if counts["missing"] == 0 and counts["stale"] == 0
                else ("yellow" if counts["missing"] == 0 else "red")
            )
            cov.add_row(
                pillar,
                str(total),
                f"[{f_style}]{counts['fresh']}[/]",
                f"[{'yellow' if counts['stale'] else 'dim'}]{counts['stale']}[/]",
                f"[{'red' if counts['missing'] else 'dim'}]{counts['missing']}[/]",
            )
        console.print(cov)

        # Stale news warnings
        for t in signal_tickers:
            if stale_flags.get(t):
                console.print(
                    f"[bold yellow]⚠[/]  {t}: news may be lagging "
                    f"(last article >7 days ago)"
                )

    except ImportError:
        # ── Plain text fallback ───────────────────────────────────────────────
        sep = "=" * 80
        print(sep)
        print(f"  COMMAND CENTER — {today_str}")
        print(sep)
        print(f"  Symlink  : {'OK' if symlink_ok else 'FAIL'}  {symlink_str}")
        print(f"  Model    : {'OK' if model_ok else 'FAIL'}  {model_str}")
        print(
            f"  Prices   : {total_fresh}/{total_tickers} fresh (<24h)"
            f"  {total_stale} stale  {total_missing} missing"
        )
        print(
            f"  News     : {news_today} articles today  "
            f"{news_tickers_count} tickers covered"
        )
        print()
        if last_signal:
            sep2 = "-" * 90
            print(sep2)
            print(
                f"{'Ticker':<8} {'ML_Score':>10} {'VolFilter':>10}"
                f" {'Weight':>8}  Headline"
            )
            print(sep2)
            for t in signal_tickers:
                rec = last_signal.get(t) or {}
                sc = rec.get("score")
                sc_str = f"{float(sc):.3f}" if sc is not None else "N/A"
                vf = "YES" if rec.get("vol_triggered") else "NO"
                w_str = f"{float(rec.get('weight', 0)):.1%}"
                head = (headlines.get(t) or "-")[:55]
                print(f"{t:<8} {sc_str:>10} {vf:>10} {w_str:>8}  {head}")
            print()
        print("DATA COVERAGE BY PILLAR:")
        for pillar, counts in pillar_freshness.items():
            total = counts["fresh"] + counts["stale"] + counts["missing"]
            print(
                f"  {pillar:<10}: {total} tickers"
                f"  {counts['fresh']} fresh"
                f"  {counts['stale']} stale"
                f"  {counts['missing']} missing"
            )
        for t in signal_tickers:
            if stale_flags.get(t):
                print(f"WARNING: {t} — news stale (last article >7 days ago)")


# ── Main ──────────────────────────────────────────────────────────────────────

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
    tickers_with_spy = (
        watchlist_tickers + "," + benchmark
        if benchmark not in watchlist
        else watchlist_tickers
    )

    py = sys.executable
    scripts_dir = ROOT / "scripts"

    # Step 1: Price update (watchlist + SPY)
    r1 = subprocess.run(
        [py, str(scripts_dir / "update_price_data.py"), "--tickers", tickers_with_spy],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("update_price_data.py exit code: %s", r1.returncode)

    # Step 2: News update (watchlist only)
    r2 = subprocess.run(
        [py, str(scripts_dir / "update_news_data.py"), "--tickers", watchlist_tickers],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("update_news_data.py exit code: %s", r2.returncode)

    # Step 3: Generate daily weights → outputs/daily_signals.csv
    r3 = subprocess.run(
        [py, str(scripts_dir / "generate_daily_weights.py")],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("generate_daily_weights.py exit code: %s", r3.returncode)

    # Step 4: Upsert signal DB → outputs/trading.db
    r4 = subprocess.run(
        [py, str(scripts_dir / "update_signal_db.py")],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("update_signal_db.py exit code: %s", r4.returncode)

    # Step 5: Command Center
    news_dir = Path(_NEWS_DIR)
    last_signal_path = ROOT / "outputs" / "last_signal.json"
    today_str = datetime.now().strftime("%Y-%m-%d")

    try:
        from src.data.csv_provider import load_data_config
        data_dir: Path = load_data_config()["data_dir"]
    except Exception:
        data_dir = ROOT / "data" / "stock_market_data"

    pillars: dict = {}
    try:
        import yaml
        with open(ROOT / "config" / "universe.yaml", "r", encoding="utf-8") as f:
            pillars = (yaml.safe_load(f) or {}).get("pillars") or {}
    except Exception as e:
        logger.warning("Could not load universe.yaml: %s", e)

    _render_command_center(
        last_signal_path=last_signal_path,
        news_dir=news_dir,
        data_dir=data_dir,
        root=ROOT,
        pillars=pillars,
        today_str=today_str,
    )

    print("Daily workflow complete.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
