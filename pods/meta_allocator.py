"""
Bayesian meta-allocator: compute_pod_weights from fitness; load/save pod_fitness.json.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# Bootstrap from 2024 OOS baselines when pod_fitness.json is missing
DEFAULT_FITNESS = {
    "core": {"sharpe": 0.526, "mdd": -0.094},
    "extension": {"sharpe": 0.206, "mdd": -0.233},
    "ballast": {"sharpe": 0.10, "mdd": -0.050},
}


def compute_pod_weights(
    pod_fitness: dict,
    regime_status: dict,
    prior: dict | None = None,
    temperature: float = 0.5,
    ballast_floor: float = 0.20,
) -> dict[str, float]:
    if prior is None:
        prior = {"core": 0.50, "extension": 0.30, "ballast": 0.20}

    # 1. F[pod] = fitness["sharpe"] / (1 + abs(fitness["mdd"])) — default 0.0 if missing
    F = {}
    for pod in ("core", "extension", "ballast"):
        f = pod_fitness.get(pod) or {}
        sharpe = f.get("sharpe", 0.0)
        mdd = f.get("mdd", 0.0)
        F[pod] = sharpe / (1.0 + abs(mdd)) if (sharpe is not None and mdd is not None) else 0.0

    # 2. L[pod] = exp(F[pod] / temperature)
    L = {pod: math.exp(F[pod] / temperature) for pod in F}

    # 3. w[pod] = prior[pod] × L[pod]
    w = {pod: prior.get(pod, 0.0) * L[pod] for pod in ("core", "extension", "ballast")}

    # 4. w[pod] /= sum(w.values())
    total = sum(w.values())
    if total <= 0:
        w = dict(prior)
    else:
        w = {pod: w[pod] / total for pod in w}

    # 5. w["ballast"] = max(ballast_floor, w["ballast"])
    w["ballast"] = max(ballast_floor, w["ballast"])

    # 6. Remainder = 1.0 - w["ballast"]; scale core and extension proportionally to fill remainder
    remainder = 1.0 - w["ballast"]
    core_ext_sum = w["core"] + w["extension"]
    if core_ext_sum > 0:
        scale = remainder / core_ext_sum
        w["core"] *= scale
        w["extension"] *= scale

    # 7. Return {"core": w_core, "extension": w_ext, "ballast": w_ballast}
    return {"core": w["core"], "extension": w["extension"], "ballast": w["ballast"]}


def load_pod_fitness(fitness_path: str | Path) -> dict[str, Any]:
    path = Path(fitness_path)
    if not path.exists():
        return DEFAULT_FITNESS.copy()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        out = {}
        for pod in ("core", "extension", "ballast"):
            out[pod] = dict(data.get(pod, {}))
            if "sharpe" not in out[pod]:
                out[pod]["sharpe"] = DEFAULT_FITNESS[pod]["sharpe"]
            if "mdd" not in out[pod]:
                out[pod]["mdd"] = DEFAULT_FITNESS[pod]["mdd"]
        return out
    except Exception:
        return DEFAULT_FITNESS.copy()


def save_pod_fitness(fitness: dict, fitness_path: str | Path) -> None:
    import datetime

    path = Path(fitness_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    to_write = {}
    for pod in ("core", "extension", "ballast"):
        to_write[pod] = dict(fitness.get(pod, {}))
        to_write[pod]["updated"] = today
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_write, f, indent=2)
