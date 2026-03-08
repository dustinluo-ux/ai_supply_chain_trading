# pip install streamlit plotly requests python-dotenv
"""
Streamlit dashboard: Regime, Portfolio, Weights, Signals, ML Status, Fills.
Auto-refresh every 30s; sidebar with last refreshed, manual refresh, auto-refresh toggle.
"""
import json
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent


def load_json(path: str | Path) -> dict | list | None:
    """Return parsed JSON or None if file missing or parse error; log to stderr."""
    p = Path(path) if not isinstance(path, Path) else path
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[dashboard] {p}: {e}", file=sys.stderr)
        return None


def load_jsonl(path: str | Path) -> list[dict]:
    """Return list of dicts, one per line; skip malformed lines."""
    p = Path(path) if not isinstance(path, Path) else path
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return []
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


st.set_page_config(page_title="AI SC Trading — Portfolio Monitor", layout="wide", page_icon="📈")

# Sidebar
with st.sidebar:
    st.write(f"Last refreshed: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
    if st.button("🔄 Refresh Now"):
        st.rerun()
    auto_refresh = st.toggle("Auto-refresh", value=True)

# Panel 1 — Regime & Risk
regime_data = load_json("outputs/regime_status.json")
if regime_data is None:
    st.info("⏳ outputs/regime_status.json not yet generated")
else:
    regime = str(regime_data.get("regime", "—")).upper()
    if regime == "BULL":
        st.success("🟢 BULL")
    elif regime == "BEAR":
        st.error("🔴 BEAR")
    else:
        st.warning("🟡 NEUTRAL" if regime == "—" else f"🟡 {regime}")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("VIX", f"{regime_data.get('vix', 0):.1f}" if regime_data.get("vix") is not None else "—")
    with c2:
        st.metric("SPY Close", f"{regime_data.get('spy_close', 0):.2f}" if regime_data.get("spy_close") is not None else "—")
    spy_close = regime_data.get("spy_close")
    spy_sma = regime_data.get("spy_sma200")
    delta = (float(spy_close) - float(spy_sma)) if (spy_close is not None and spy_sma is not None) else None
    with c3:
        st.metric("SPY vs SMA200 (Δ)", f"{delta:.2f}" if delta is not None else "—")
    with c4:
        smh_ret = regime_data.get("smh_daily_return")
        st.metric("SMH 1d return", f"{smh_ret:.2%}" if smh_ret is not None else "—")

# Panel 2 — Portfolio Summary
ps = load_json("outputs/portfolio_state.json")
if ps is None:
    st.info("⏳ outputs/portfolio_state.json not yet generated")
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("NAV", f"SGD {ps.get('last_nav', 0):,.0f}")
    with col2:
        cw = ps.get("cash_weight")
        st.metric("Cash weight", f"{(float(cw) * 100):.1f}%" if cw is not None else "—")
    with col3:
        wl = ps.get("weekly_lock") or {}
        locked = wl.get("locked", False)
        st.metric("Weekly lock", "Locked" if locked else "Open")

# Panel 3 — Target Weights & Holdings
col_left, col_right = st.columns(2)
with col_left:
    st.subheader("Target Weights")
    lvw = load_json("outputs/last_valid_weights.json")
    if lvw is None:
        st.info("⏳ last_valid_weights.json not yet generated")
    else:
        weights = lvw.get("weights") or {}
        rows = [{"Ticker": t, "Weight%": f"{w * 100:.2f}"} for t, w in sorted(weights.items(), key=lambda x: -x[1])]
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.write("No weights.")
with col_right:
    st.subheader("Holdings")
    if ps is None:
        st.info("⏳ portfolio_state.json not yet generated")
    else:
        holdings = ps.get("holdings") or {}
        non_zero = [(t, h.get("shares", 0), h.get("avg_cost", 0)) for t, h in holdings.items() if (h.get("shares") or 0) > 0]
        rows = [{"Ticker": t, "Shares": s, "Avg Cost": f"{c:.2f}" if c else "—"} for t, s, c in non_zero]
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.write("No holdings.")

# Panel 4 — Signal Snapshot
st.subheader("Signal Snapshot")
ls = load_json("outputs/last_signal.json")
if ls is None:
    st.info("⏳ outputs/last_signal.json not yet generated")
else:
    rows = []
    items = ls.items() if isinstance(ls, dict) else []
    for ticker, v in items:
        if not isinstance(v, dict):
            continue
        score = v.get("score")
        close = v.get("latest_close")
        vol = v.get("vol_20d")
        triggered = v.get("vol_triggered", False)
        rows.append({
            "Ticker": ticker,
            "Score": f"{score:.4f}" if score is not None else "—",
            "Latest Close": f"{close:.2f}" if close is not None else "—",
            "Vol 20d": f"{vol:.4f}" if vol is not None else "—",
            "Vol Triggered": "🔴 Yes" if triggered else "No",
        })
    if rows:
        rows.sort(key=lambda r: (r["Score"] if r["Score"] != "—" else "0"), reverse=True)
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.write("No signal data.")

# Panel 5 — ML Status
ml_col1, ml_col2 = st.columns(2)
with ml_col1:
    st.subheader("Factory Winner")
    fw = load_json("models/factory_winner.json")
    if fw is None:
        st.info("⏳ models/factory_winner.json not yet generated")
    else:
        mt = (fw.get("model_type") or "—").upper()
        st.write(f"**Model:** {mt}")
        st.write(f"**IC:** {fw.get('ic', 0):.4f}")
        st.write(f"**Selected at:** {fw.get('selected_at', '—')}")
        path = fw.get("model_path") or "—"
        if path and path != "—":
            path = Path(path).name
        st.write(f"**Model path:** {path}")
with ml_col2:
    st.subheader("IC History")
    ic_data = load_json("outputs/ic_monitor.json")
    if ic_data is None or not isinstance(ic_data, list):
        st.info("⏳ outputs/ic_monitor.json not yet generated")
    else:
        entries = ic_data if isinstance(ic_data, list) else (ic_data.get("entries") or ic_data)
        last_10 = sorted(entries, key=lambda x: x.get("date") or "", reverse=True)[:10]
        rows = []
        for e in last_10:
            passed = e.get("passed", False)
            rows.append({
                "Date": e.get("date", "—"),
                "IC": e.get("ic"),
                "Passed": "✅" if passed else "❌",
                "Model": e.get("model_path") or "—",
            })
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.write("No IC history.")

# Panel 6 — Fills
st.subheader("Fills")
fills = load_jsonl("outputs/fills/fills.jsonl")
if not fills:
    st.info("⏳ outputs/fills/fills.jsonl not yet generated")
else:
    miss_count = sum(1 for r in fills if (r.get("qty_filled") or 0) < (r.get("qty_requested") or 0))
    if miss_count > 0:
        st.warning(f"⚠️ Fill miss detected on {miss_count} order(s)")
    rows = []
    for r in sorted(fills, key=lambda x: x.get("timestamp") or "", reverse=True):
        qty_f = r.get("qty_filled")
        qty_r = r.get("qty_requested")
        rows.append({
            "Timestamp": r.get("timestamp", "—"),
            "Ticker": r.get("ticker", "—"),
            "Side": r.get("side", "—"),
            "Qty Requested": qty_r,
            "Qty Filled": qty_f,
            "Avg Fill Price": f"{r.get('avg_fill_price'):.2f}" if r.get("avg_fill_price") is not None else "—",
            "Status": r.get("status", "—"),
            "Fill Check Passed": "✅" if r.get("fill_check_passed") else "❌",
            "Fill Check Reason": r.get("fill_check_reason", "—"),
        })
    st.dataframe(rows, width="stretch", hide_index=True)

if auto_refresh:
    time.sleep(30)
    st.rerun()
