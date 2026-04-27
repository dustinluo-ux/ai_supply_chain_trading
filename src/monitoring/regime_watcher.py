# Watches outputs/regime_status.json for regime changes and sends Telegram alert.
"""
Poll regime_status.json; on regime change call send_alert("regime_change", ...) and update cache.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = ROOT / "outputs" / ".regime_cache.json"


def check_regime_change(
    regime_status_path: str | Path = "outputs/regime_status.json",
) -> bool:
    """
    Read regime_status.json; if current regime != cached regime, send regime_change alert, update cache, return True.
    If file missing return False. If cache missing, write current regime and return False (first run).
    """
    path = Path(regime_status_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[regime_watcher] Failed to read {path}: {e}", file=sys.stderr)
        return False
    current_regime = data.get("regime")
    if current_regime is None:
        return False
    current_regime = str(current_regime).strip()
    # Load cache
    cached_regime = None
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
            cached_regime = cache.get("regime")
            if cached_regime is not None:
                cached_regime = str(cached_regime).strip()
        except (json.JSONDecodeError, OSError):
            pass
    if cached_regime is None:
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({"regime": current_regime}, f)
        except OSError as e:
            print(f"[regime_watcher] Failed to write cache: {e}", file=sys.stderr)
        return False
    if current_regime == cached_regime:
        return False
    # Regime changed: send alert and update cache
    from src.monitoring.telegram_alerts import send_alert

    vix = data.get("vix", 0)
    spy_below_sma = data.get("spy_below_sma", False)
    as_of = data.get("as_of", "—")
    send_alert(
        "regime_change",
        {
            "old": cached_regime,
            "new": current_regime,
            "vix": float(vix) if vix is not None else 0,
            "spy_below_sma": spy_below_sma,
            "as_of": as_of,
        },
    )
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"regime": current_regime}, f)
    except OSError as e:
        print(f"[regime_watcher] Failed to update cache: {e}", file=sys.stderr)
    return True


def watch_loop(interval_seconds: int = 60) -> None:
    """Infinite loop: check_regime_change() then sleep(interval_seconds). Catch and log exceptions, never crash."""
    while True:
        try:
            check_regime_change()
        except Exception as e:
            print(f"[regime_watcher] {e}", file=sys.stderr)
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            raise


if __name__ == "__main__":
    watch_loop()
