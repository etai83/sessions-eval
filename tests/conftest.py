"""Shared fixtures for bench-suite tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / ".scratch/bench-suite/task-schema.json"
FIXTURE_PATH = REPO_ROOT / ".scratch/bench-suite/fixtures/offline_golden_task.json"
CONFIG_PATH = REPO_ROOT / ".scratch/bench-suite/config.json"


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def schema_path() -> Path:
    return SCHEMA_PATH


@pytest.fixture
def offline_fixture() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def tmp_suite(tmp_path: Path, schema_path: Path) -> Path:
    """Isolated data root with schema + config copied in."""
    data = tmp_path / ".scratch" / "bench-suite"
    data.mkdir(parents=True)
    shutil.copy(schema_path, data / "task-schema.json")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)
    # Paths stay relative; load_config resolves against repo_root=tmp_path
    with (data / "config.json").open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    (data / "dataset" / "tasks").mkdir(parents=True)
    (data / "fixtures").mkdir(parents=True)
    shutil.copy(FIXTURE_PATH, data / "fixtures" / "offline_golden_task.json")
    return tmp_path
