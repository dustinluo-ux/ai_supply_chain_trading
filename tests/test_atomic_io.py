import json
import os
from pathlib import Path

import pytest
import yaml

from src.utils.atomic_io import atomic_write_json, atomic_write_text, atomic_write_yaml

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo_temp_dir():
    path = ROOT / "outputs" / f"_atomic_io_test_{os.getpid()}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        for child in path.glob("*"):
            child.unlink(missing_ok=True)
        path.rmdir()


def test_atomic_write_json_round_trips_and_removes_temp(repo_temp_dir):
    target = repo_temp_dir / "state.json"

    atomic_write_json(target, {"ok": True, "n": 1})

    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True, "n": 1}
    assert list(repo_temp_dir.glob("*.tmp")) == []


def test_atomic_write_yaml_round_trips(repo_temp_dir):
    target = repo_temp_dir / "config.yaml"

    atomic_write_yaml(target, {"alpha": {"enabled": True}})

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {
        "alpha": {"enabled": True}
    }


def test_atomic_write_text_rejects_empty_payload(repo_temp_dir):
    target = repo_temp_dir / "empty.txt"

    with pytest.raises(ValueError, match="too-small"):
        atomic_write_text(target, "")

    assert not target.exists()
