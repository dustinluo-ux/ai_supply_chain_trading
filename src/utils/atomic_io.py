"""Small atomic write helpers for machine-written state files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


def atomic_write_text(path: Path | str, text: str, *, min_bytes: int = 1) -> None:
    """Write text via temp file, size check, and os.replace()."""
    target = Path(path)
    if len(text.encode("utf-8")) < min_bytes or not text.strip():
        raise ValueError(f"refusing to write too-small payload to {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        if tmp.stat().st_size < min_bytes:
            raise ValueError(f"atomic write temp file unexpectedly small: {tmp}")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def atomic_write_json(path: Path | str, payload: Any, *, min_bytes: int = 2) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2), min_bytes=min_bytes)


def atomic_write_yaml(path: Path | str, payload: Any, *, min_bytes: int = 2) -> None:
    atomic_write_text(
        path,
        yaml.dump(payload, default_flow_style=False, sort_keys=False, allow_unicode=True),
        min_bytes=min_bytes,
    )
