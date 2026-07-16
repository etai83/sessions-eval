"""Dataset store seam: load / save / validate TaskEntry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench_suite.store import DatasetStore, SchemaValidationError


def test_load_and_save_round_trip(tmp_path: Path, schema_path: Path, offline_fixture: dict) -> None:
    store = DatasetStore(tmp_path / "tasks", schema_path)
    path = store.save(offline_fixture)
    assert path == tmp_path / "tasks" / "offline_golden_01.json"

    loaded = store.load("offline_golden_01")
    assert loaded["task_id"] == "offline_golden_01"
    assert loaded["roi_value"] == 10.0
    assert len(loaded["validation_rules"]) == 3


def test_rejects_invalid_task(tmp_path: Path, schema_path: Path) -> None:
    store = DatasetStore(tmp_path / "tasks", schema_path)
    with pytest.raises(SchemaValidationError):
        store.save({"task_id": "broken"})


def test_load_path_validates(schema_path: Path, offline_fixture: dict, tmp_path: Path) -> None:
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(offline_fixture), encoding="utf-8")
    store = DatasetStore(tmp_path / "tasks", schema_path)
    task = store.load_path(path)
    assert task["name"].startswith("Offline Golden")
