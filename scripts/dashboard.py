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


def _load_yaml(path: str | Path) -> dict:
    """Return parsed YAML or empty dict."""
    p = Path(path) if not isinstance(path, Path) else path
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return {}
    try:
        import yaml
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


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

# Connection Status (execution_status.json)
exec_status = load_json("outputs/execution_status.json")
ibkr_state = "UNKNOWN"
can_rebalance = True
as_of = None
data_quality_issues = []
if exec_status is not None:
    ibkr_state = str(exec_status.get("ibkr_state", "UNKNOWN")).upper()
    can_rebalance = bool(exec_status.get("can_rebalance", True))
    as_of = exec_status.get("as_of")
    data_quality_issues = exec_status.get("data_quality_issues")
    if not isinstance(data_quality_issues, list):
        data_quality_issues = []

if ibkr_state in ("FROZEN", "DISCONNECTED"):
    banner_color = "#c00000"
    banner_text = f"⚠ IBKR: {ibkr_state} — Manual Intervention Required."
    banner_style = "font-weight: bold;"
elif ibkr_state == "DEGRADED":
    banner_color = "#b8860b"
    banner_text = "IBKR: DEGRADED — monitor latency."
    banner_style = ""
elif ibkr_state == "CONNECTED":
    banner_color = "#1a7f37"
    banner_text = "IBKR: CONNECTED"
    banner_style = ""
else:
    banner_color = "#1a7f37"
    banner_text = "IBKR: State unknown (no run yet)."
    banner_style = ""

st.markdown(
    f'<div style="background: {banner_color}; color: white; padding: 0.6rem 1.2rem; border-radius: 6px; margin-bottom: 0.5rem; font-size: 1.1rem; {banner_style}">{banner_text}</div>',
    unsafe_allow_html=True,
)
if not can_rebalance:
    st.warning("Rebalancing BLOCKED — data quality gate failed. Check execution_status.json for details.")
if data_quality_issues:
    n = len(data_quality_issues)
    with st.expander(f"Data Quality Issues ({n})"):
        for issue in data_quality_issues:
            st.markdown(f"- {issue}")
if as_of is not None:
    st.caption(f"Execution status as of: {as_of}")
else:
    st.caption("No execution run recorded yet.")

# Panel 1 — Probabilistic Regime Assignment
st.subheader("Probabilistic Regime Assignment")
meta_weights_data = load_json("outputs/meta_weights.json")
if meta_weights_data is None or not meta_weights_data.get("weights"):
    st.markdown(
        '<span style="color: #888; background: #f0f0f0; padding: 0.5rem 1rem; border-radius: 4px;">Regime probabilities unavailable.</span>',
        unsafe_allow_html=True,
    )
else:
    weights = meta_weights_data.get("weights") or {}
    core_w = float(weights.get("core", 0))
    ext_w = float(weights.get("extension", 0))
    ballast_w = float(weights.get("ballast", 0))
    total = core_w + ext_w + ballast_w
    if total <= 0:
        core_w, ext_w, ballast_w = 1 / 3, 1 / 3, 1 / 3
        total = 1.0
    core_pct = core_w / total
    ext_pct = ext_w / total
    ballast_pct = ballast_w / total
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=["Regime"],
        x=[core_pct * 100],
        name="BULL",
        orientation="h",
        marker_color="rgb(34, 139, 34)",
        text=[f"{core_pct * 100:.0f}%"],
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=["Regime"],
        x=[ext_pct * 100],
        name="TRANSITION",
        orientation="h",
        marker_color="rgb(255, 191, 0)",
        text=[f"{ext_pct * 100:.0f}%"],
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=["Regime"],
        x=[ballast_pct * 100],
        name="BEAR",
        orientation="h",
        marker_color="rgb(178, 34, 34)",
        text=[f"{ballast_pct * 100:.0f}%"],
        textposition="inside",
    ))
    fig.update_layout(
        barmode="stack",
        xaxis=dict(tickformat=".0f", ticksuffix="%", range=[0, 100]),
        yaxis=dict(showticklabels=False),
        showlegend=True,
        legend=dict(orientation="h"),
        height=120,
        margin=dict(l=80, r=80, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    regime_label = str(meta_weights_data.get("regime", "—")).upper()
    as_of = meta_weights_data.get("as_of", "—")
    st.caption(f"Regime: {regime_label}  |  As of: {as_of}")

# Panel 2 — Tiered Alerts
st.subheader("Tiered Alerts")
breakdown = load_json("outputs/structural_breakdown.json")
drawdown_data = load_json("outputs/drawdown_tracker.json")
mcfg = _load_yaml("config/model_config.yaml")
risk_cfg = mcfg.get("risk_management", {})
stop_threshold = float(risk_cfg.get("stop_loss_threshold", -0.10))
ic_baseline = float(risk_cfg.get("ic_baseline", 0.0428))

def _severity_style(s: str) -> str:
    s = (s or "ok").lower()
    if s == "critical":
        return 'color: #c00; font-weight: bold;'
    if s == "warning":
        return 'color: #b8860b;'
    return 'color: #06c;'

def _status_cell(triggered: bool) -> str:
    return "⚠ Active" if triggered else "✓ OK"

alert_rows = []
# IC Decay
ic_decay = (breakdown or {}).get("ic_decay") or {}
ic_val = ic_decay.get("rolling_ic_20d")
ic_str = f"{ic_val:.4f}" if ic_val is not None else "N/A"
ic_sev = ic_decay.get("severity", "ok")
ic_trig = ic_decay.get("triggered", False)
alert_rows.append({
    "Alert Name": "IC Decay",
    "Current Value": ic_str,
    "Threshold": f"{ic_baseline:.4f}",
    "Severity": ic_sev,
    "Status": _status_cell(ic_trig),
})

# Residual Risk
res_risk = (breakdown or {}).get("residual_risk") or {}
rr_val = res_risk.get("pnl_vol_8w")
rr_str = f"{rr_val:.4f}" if rr_val is not None else "N/A"
rr_sev = res_risk.get("severity", "ok")
rr_trig = res_risk.get("triggered", False)
alert_rows.append({
    "Alert Name": "Residual Risk",
    "Current Value": rr_str,
    "Threshold": "2× baseline",
    "Severity": rr_sev,
    "Status": _status_cell(rr_trig),
})

# Regime Misalignment
mis = (breakdown or {}).get("regime_misalignment") or {}
betas = mis.get("pod_betas") or {}
betas_str = ", ".join(f"{k}={v:.2f}" for k, v in betas.items()) if betas else "N/A"
mis_sev = mis.get("severity", "ok")
mis_trig = mis.get("triggered", False)
alert_rows.append({
    "Alert Name": "Regime Misalignment",
    "Current Value": betas_str[:40] + "…" if len(betas_str) > 40 else betas_str,
    "Threshold": "mandate ± buffer",
    "Severity": mis_sev,
    "Status": _status_cell(mis_trig),
})

# Portfolio Drawdown
dd_val = None
if drawdown_data is not None:
    dd_val = drawdown_data.get("drawdown")
dd_str = f"{dd_val:.1%}" if dd_val is not None else "N/A"
dd_sev = "critical" if (dd_val is not None and dd_val <= -0.10) else "ok"
flatten = drawdown_data.get("flatten_active", False) if drawdown_data else False
alert_rows.append({
    "Alert Name": "Portfolio Drawdown",
    "Current Value": dd_str,
    "Threshold": f"{stop_threshold:.0%}",
    "Severity": dd_sev,
    "Status": _status_cell(flatten),
})

if alert_rows:
    # Header
    h1, h2, h3, h4, h5 = st.columns([2, 2, 2, 1.5, 1.5])
    h1.write("**Alert Name**")
    h2.write("**Current Value**")
    h3.write("**Threshold**")
    h4.write("**Severity**")
    h5.write("**Status**")
    for r in alert_rows:
        cols = st.columns([2, 2, 2, 1.5, 1.5])
        cols[0].write(r["Alert Name"])
        cols[1].write(r["Current Value"])
        cols[2].write(r["Threshold"])
        cols[3].markdown(f'<span style="{_severity_style(r["Severity"])}">{r["Severity"]}</span>', unsafe_allow_html=True)
        cols[4].write(r["Status"])
else:
    st.caption("No alert data (structural_breakdown.json and/or drawdown_tracker.json missing).")

# Panel 3 — Regime & Risk (formerly Panel 1)
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
