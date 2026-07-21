"""Dataset store seam: definition vs evaluation history."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench_suite.store import DatasetStore, SchemaValidationError


def _sample_result(**overrides: object) -> dict:
    base = {
        "model_name": "gemini-3.5-flash",
        "model_config": {"thinking_level": "high"},
        "completeness_percent": 100.0,
        "input_tokens": 100,
        "output_tokens": 50,
        "tool_calls": 1,
        "cost_usd": 0.001,
        "latency_seconds": 5.0,
        "earned_roi": 10.0,
        "cost_effectiveness_roi_per_usd": 10000.0,
        "timestamp": "2026-07-01T10:00:00Z",
    }
    base.update(overrides)
    return base


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


def test_save_writes_definition_without_evaluation_results(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    store = DatasetStore(tmp_path / "tasks", schema_path, results_dir=tmp_path / "results")
    task = dict(offline_fixture)
    task["evaluation_results"] = [_sample_result()]
    path = store.save(task)

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert "evaluation_results" not in on_disk
    assert on_disk["task_id"] == "offline_golden_01"
    # save must not invent a results file from a definition write
    assert not store.results_path("offline_golden_01").exists()


def test_append_and_list_results(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    store = DatasetStore(tmp_path / "tasks", schema_path, results_dir=tmp_path / "results")
    store.save(offline_fixture)

    first = _sample_result(timestamp="2026-07-01T10:00:00Z")
    second = _sample_result(
        timestamp="2026-07-02T10:00:00Z",
        run_id="20260702T100000Z_abc",
        run_pack_path=".scratch/bench-suite/runs/offline_golden_01/m/r",
    )
    store.append_result("offline_golden_01", first)
    store.append_result("offline_golden_01", second)

    results = store.list_results("offline_golden_01")
    assert len(results) == 2
    assert results[0]["timestamp"] == "2026-07-01T10:00:00Z"
    assert results[1]["run_id"] == "20260702T100000Z_abc"
    assert results[1]["run_pack_path"] == ".scratch/bench-suite/runs/offline_golden_01/m/r"

    # JSONL on disk
    lines = store.results_path("offline_golden_01").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_load_joins_evaluation_results(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    store = DatasetStore(tmp_path / "tasks", schema_path, results_dir=tmp_path / "results")
    store.save(offline_fixture)
    store.append_result("offline_golden_01", _sample_result())

    loaded = store.load("offline_golden_01")
    assert len(loaded["evaluation_results"]) == 1
    assert loaded["evaluation_results"][0]["completeness_percent"] == 100.0
    # definition fields still present
    assert loaded["prompt"]


def test_list_tasks_joins_results(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    store = DatasetStore(tmp_path / "tasks", schema_path, results_dir=tmp_path / "results")
    store.save(offline_fixture)
    store.append_result("offline_golden_01", _sample_result())

    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert len(tasks[0]["evaluation_results"]) == 1


def test_load_without_results_omits_history(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    store = DatasetStore(tmp_path / "tasks", schema_path, results_dir=tmp_path / "results")
    store.save(offline_fixture)
    store.append_result("offline_golden_01", _sample_result())

    definition = store.load("offline_golden_01", with_results=False)
    assert "evaluation_results" not in definition


def test_migrate_embedded_results_preserves_pack_pointers(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    tasks_dir = tmp_path / "tasks"
    results_dir = tmp_path / "results"
    tasks_dir.mkdir()
    embedded = dict(offline_fixture)
    pack = ".scratch/bench-suite/runs/offline_golden_01/gemini-3.5-flash:abc/run1"
    embedded["evaluation_results"] = [
        _sample_result(run_id="run1", run_pack_path=pack),
        _sample_result(timestamp="2026-07-03T00:00:00Z", run_id="run2", run_pack_path=pack + "x"),
    ]
    (tasks_dir / "offline_golden_01.json").write_text(
        json.dumps(embedded, indent=2) + "\n", encoding="utf-8"
    )

    store = DatasetStore(tasks_dir, schema_path, results_dir=results_dir)
    summary = store.migrate_embedded_results()

    assert summary["tasks_migrated"] == 1
    assert summary["results_moved"] == 2
    on_disk = json.loads((tasks_dir / "offline_golden_01.json").read_text(encoding="utf-8"))
    assert "evaluation_results" not in on_disk
    results = store.list_results("offline_golden_01")
    assert len(results) == 2
    assert results[0]["run_pack_path"] == pack
    assert results[1]["run_id"] == "run2"


def test_legacy_embedded_results_readable_before_migration(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    """Until migrate runs, load still surfaces embedded evaluation_results."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    embedded = dict(offline_fixture)
    embedded["evaluation_results"] = [_sample_result()]
    (tasks_dir / "offline_golden_01.json").write_text(
        json.dumps(embedded, indent=2) + "\n", encoding="utf-8"
    )

    store = DatasetStore(tasks_dir, schema_path, results_dir=tmp_path / "results")
    loaded = store.load("offline_golden_01")
    assert len(loaded["evaluation_results"]) == 1


def test_results_dir_defaults_beside_tasks(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    tasks_dir = tmp_path / "dataset" / "tasks"
    store = DatasetStore(tasks_dir, schema_path)
    assert store.results_dir == tmp_path / "dataset" / "results"
    store.save(offline_fixture)
    store.append_result("offline_golden_01", _sample_result())
    assert (tmp_path / "dataset" / "results" / "offline_golden_01.jsonl").is_file()


def test_migrate_merges_when_jsonl_and_embedded_both_present(
    tmp_path: Path, schema_path: Path, offline_fixture: dict
) -> None:
    tasks_dir = tmp_path / "tasks"
    results_dir = tmp_path / "results"
    tasks_dir.mkdir()
    results_dir.mkdir()
    embedded = dict(offline_fixture)
    only_embedded = _sample_result(
        run_id="embedded-only",
        run_pack_path=".scratch/bench-suite/runs/x/e",
        timestamp="2026-07-04T00:00:00Z",
    )
    shared = _sample_result(run_id="shared", timestamp="2026-07-02T00:00:00Z")
    embedded["evaluation_results"] = [shared, only_embedded]
    (tasks_dir / "offline_golden_01.json").write_text(
        json.dumps(embedded, indent=2) + "\n", encoding="utf-8"
    )
    only_external = _sample_result(
        run_id="external-only",
        timestamp="2026-07-01T00:00:00Z",
        run_pack_path=".scratch/bench-suite/runs/x/o",
    )
    (results_dir / "offline_golden_01.jsonl").write_text(
        json.dumps(only_external) + "\n" + json.dumps(shared) + "\n",
        encoding="utf-8",
    )

    store = DatasetStore(tasks_dir, schema_path, results_dir=results_dir)
    summary = store.migrate_embedded_results()
    assert summary["tasks_migrated"] == 1
    results = store.list_results("offline_golden_01")
    ids = [r["run_id"] for r in results]
    assert ids == ["external-only", "shared", "embedded-only"]
    assert "evaluation_results" not in json.loads(
        (tasks_dir / "offline_golden_01.json").read_text(encoding="utf-8")
    )
