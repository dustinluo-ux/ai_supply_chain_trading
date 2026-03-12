# Telegram alerting for regime change, rebalance complete, fill miss, IC degradation.
# Loads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env; if missing, all sends are no-ops.
"""
Send alerts to Telegram. Alert types: regime_change, rebalance_complete, fill_miss, ic_degradation.
"""
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Load .env from project root (parent of src)
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if _ENV_PATH.exists() and load_dotenv:
    load_dotenv(_ENV_PATH)

_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def send_alert(alert_type: str, payload: dict) -> None:
    """Send a Telegram message. alert_type: regime_change | rebalance_complete | fill_miss | ic_degradation."""
    if not _TOKEN or not _CHAT_ID:
        print("[telegram_alerts] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing; skipping send.", file=sys.stderr)
        return
    try:
        import requests
    except ImportError:
        print("[telegram_alerts] requests not installed; skipping send.", file=sys.stderr)
        return
    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    if alert_type == "regime_change":
        old = payload.get("old", "—")
        new = payload.get("new", "—")
        vix = payload.get("vix", 0)
        spy_below_sma = payload.get("spy_below_sma", False)
        as_of = payload.get("as_of", "—")
        text = (
            "🚨 *Regime Change*\n"
            f"From: {old} → To: {new}\n"
            f"VIX: {vix:.1f} | SPY below SMA: {spy_below_sma}\n"
            f"As of: {as_of}"
        )
    elif alert_type == "rebalance_complete":
        n_tickers = payload.get("n_tickers", 0)
        nav = payload.get("nav", 0)
        regime = payload.get("regime", "—")
        timestamp = payload.get("timestamp", "—")
        text = (
            "✅ *Rebalance Complete*\n"
            f"Tickers rebalanced: {n_tickers}\n"
            f"NAV: SGD {nav:,.0f}\n"
            f"Regime: {regime}\n"
            f"Timestamp: {timestamp}"
        )
    elif alert_type == "fill_miss":
        ticker = payload.get("ticker", "—")
        side = payload.get("side", "—")
        qty_requested = payload.get("qty_requested", 0)
        qty_filled = payload.get("qty_filled", 0)
        fill_check_reason = payload.get("fill_check_reason", "—")
        text = (
            "⚠️ *Fill Miss Detected*\n"
            f"Ticker: {ticker} ({side})\n"
            f"Requested: {qty_requested} | Filled: {qty_filled}\n"
            f"Reason: {fill_check_reason}"
        )
    elif alert_type == "ic_degradation":
        ic = payload.get("ic", 0.0)
        model_path = payload.get("model_path", "—")
        date = payload.get("date", "—")
        text = (
            "📉 *IC Degradation*\n"
            f"Latest IC: {ic:.4f} (gate: 0.01)\n"
            f"Model: {model_path}\n"
            f"Date: {date}"
        )
    elif alert_type == "thesis_collapse":
        rho = payload.get("rho")
        reason = payload.get("reason", "—")
        rho_s = f"{rho:.3f}" if rho is not None else "—"
        text = (
            "⚠️ *Thesis Alert — Long/Short Decoupling*\n"
            f"Correlation ρ={rho_s} (threshold: 0.80)\n"
            "Long and short baskets trading in lockstep — edge degrading\n"
            "Gross exposure reduced 50%\n"
            f"Reason: {reason}"
        )
    else:
        print(f"[telegram_alerts] Unknown alert_type={alert_type!r}; skipping.", file=sys.stderr)
        return
    try:
        r = requests.post(url, json={"chat_id": _CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
        if not r.ok:
            print(f"[telegram_alerts] sendMessage failed: {r.status_code} {r.text}", file=sys.stderr)
    except Exception as e:
        print(f"[telegram_alerts] send failed: {e}", file=sys.stderr)
