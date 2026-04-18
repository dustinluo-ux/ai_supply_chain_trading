#!/usr/bin/env python3
"""
Daily risk snapshot (market hours): RiskPolicy -> outputs/risk_status.json.
Scheduled 09:00 and 16:00 Mon–Fri (weekend no-op when invoked on Sat/Sun).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(payload, indent=2)
    if len(body) < 10:
        raise ValueError("risk_status JSON would be empty")
    tmp.write_text(body, encoding="utf-8")
    if tmp.stat().st_size < 10:
        raise ValueError("risk_status temp file unexpectedly small")
    os.replace(tmp, path)


def _constraints_to_dict(c) -> dict:
    return {
        "as_of": pd.Timestamp(c.as_of).isoformat(),
        "beta_cap": str(c.beta_cap),
        "position_scale": str(c.position_scale),
        "stop_loss_active": bool(c.stop_loss_active),
        "margin_headroom_pct": str(c.margin_headroom_pct),
        "audit_log": list(c.audit_log),
    }


def _load_target_from_plan(plan: dict):
    from src.risk.types import TargetPortfolio

    raw = plan.get("target_portfolio")
    if not isinstance(raw, dict):
        return None
    w = raw.get("weights") or {}
    scores = raw.get("scores") or {}
    meta = raw.get("construction_meta") or {}
    as_of_s = raw.get("as_of") or plan.get("as_of")
    as_of_ts = pd.to_datetime(as_of_s).normalize() if as_of_s else pd.Timestamp.today().normalize()
    weights = {str(k).upper(): Decimal(str(v)) for k, v in w.items()}
    scores_f = {str(k): float(v) for k, v in scores.items()}
    return TargetPortfolio(as_of=as_of_ts, weights=weights, scores=scores_f, construction_meta=meta)


def main() -> int:
    if date.today().weekday() >= 5:
        return 0

    today = pd.Timestamp(date.today()).normalize()
    from src.execution.planner import ExecutionPlanner
    from src.risk.policy import RiskPolicy

    constraints = RiskPolicy().evaluate(today)
    out_path = ROOT / "outputs" / "risk_status.json"
    _atomic_write_json(out_path, _constraints_to_dict(constraints))

    if constraints.stop_loss_active:
        print("ALERT: FLATTEN ALL", flush=True)
        return 2

    beta_cap = float(constraints.beta_cap)
    plan_path = ROOT / "outputs" / "execution_plan_latest.json"
    if beta_cap < 0.5 and plan_path.exists():
        try:
            with open(plan_path, encoding="utf-8") as f:
                plan = json.load(f)
        except Exception as exc:
            print(f"[RISK_DAILY][WARN] could not read execution plan: {exc}", flush=True)
            return 0
        long_exp = sum(float(v) for v in (plan.get("long_orders") or {}).values())
        if long_exp > 0.5:
            tgt = _load_target_from_plan(plan)
            if tgt is not None:
                import run_weekly_rebalance as _rwb

                nav_v = float(_rwb._resolve_nav_usd())
                nq = _rwb._get_nq_price_or_none()
                planner = ExecutionPlanner()
                new_plan = planner.reconcile(
                    tgt,
                    constraints,
                    nav=Decimal(str(nav_v)),
                    nq_price=nq,
                )
                print(
                    "[RISK_DAILY] beta_cap<0.5 and plan long exposure>0.5 — "
                    "recomputed overlay (not submitted). Operator confirm:",
                    flush=True,
                )
                for line in new_plan.audit_log:
                    print(f"  {line}", flush=True)
                for ov in new_plan.overlay_orders:
                    print(
                        f"  OVERLAY {ov.symbol} contracts={ov.contracts} "
                        f"notional_usd={ov.notional_usd} ({ov.reason})",
                        flush=True,
                    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
