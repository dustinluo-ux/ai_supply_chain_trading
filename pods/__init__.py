"""
Three-pod architecture: Core (long-only HRP + alpha tilt), Extension (alpha sleeve), Ballast (defensive/hedged).
Spec: docs/THREE_POD_ARCHITECTURE.md
"""
from pods.pod_core import PodCore
from pods.pod_extension import PodExtension
from pods.pod_ballast import PodBallast
from pods.meta_allocator import compute_pod_weights
from pods.aggregator import aggregate_pod_weights

__all__ = [
    "PodCore",
    "PodExtension",
    "PodBallast",
    "compute_pod_weights",
    "aggregate_pod_weights",
]
