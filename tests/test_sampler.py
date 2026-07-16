"""Sampler: stratified selection → pending-review + dataset promotion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bench_suite.sampler import Sampler
from bench_suite.store import DatasetStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate(conv_id: str, category: str, *, extra: dict | None = None) -> dict[str, Any]:
    c = {
        "conversation_id": conv_id,
        "timestamp": "2026-07-01T10:00:00Z",
        "user_request": "do something",
        "tool_invocations": [],
        "duration_seconds": 10.0,
        "transcript_path": f"/fake/{conv_id}/transcript_full.jsonl",
        "taxonomy": {"output_type": "code", "complexity": "multi_tool", "intent": "generate"},
        "domain": {"category": category, "subcategory": "Miscellaneous"},
    }
    if extra:
        c.update(extra)
    return c


def _make_candidates(spec: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Build a list of candidates from (conv_id, category) pairs."""
    return [_candidate(cid, cat) for cid, cat in spec]


# ---------------------------------------------------------------------------
# Slice 1: sample() — stratified selection with dedup
# ---------------------------------------------------------------------------

class TestSample:
    def test_empty_pool_returns_empty(self) -> None:
        sampler = Sampler(target_total=20)
        result = sampler.sample(candidates=[], existing_ids=set())
        assert result == []

    def test_proportional_quota_fill(self) -> None:
        """5 Trading (50%) + 5 AI (50%) → quota of 2+2 from target=4."""
        candidates = _make_candidates(
            [(f"t-{i}", "Trading") for i in range(5)]
            + [(f"a-{i}", "AI") for i in range(5)]
        )
        sampler = Sampler(target_total=4)
        result = sampler.sample(candidates=candidates, existing_ids=set())
        assert len(result) == 4
        cats = [c["domain"]["category"] for c in result]
        assert cats.count("Trading") == 2
        assert cats.count("AI") == 2

    def test_skips_already_in_dataset(self) -> None:
        candidates = _make_candidates(
            [(f"t-{i}", "Trading") for i in range(5)]
        )
        existing = {"t-0", "t-1", "t-2"}
        sampler = Sampler(target_total=10)
        result = sampler.sample(candidates=candidates, existing_ids=existing)
        ids = {c["conversation_id"] for c in result}
        assert ids.isdisjoint(existing)

    def test_never_exceeds_target(self) -> None:
        candidates = _make_candidates(
            [(f"c-{i}", "Software Dev") for i in range(30)]
        )
        sampler = Sampler(target_total=10)
        result = sampler.sample(candidates=candidates, existing_ids=set())
        assert len(result) <= 10

    def test_fills_remainder_when_category_exhausted(self) -> None:
        """If a category has fewer candidates than quota, fill remainder from others."""
        # 1 Trading, 10 AI — target=4 means quota ~2 each but Trading only has 1
        candidates = _make_candidates(
            [("t-0", "Trading")]
            + [(f"a-{i}", "AI") for i in range(10)]
        )
        sampler = Sampler(target_total=4)
        result = sampler.sample(candidates=candidates, existing_ids=set())
        assert len(result) == 4

    def test_no_duplicate_conv_ids_in_result(self) -> None:
        """Result must never contain two candidates with the same conversation_id."""
        candidates = _make_candidates(
            [(f"c-{i}", "General") for i in range(20)]
        )
        sampler = Sampler(target_total=10)
        result = sampler.sample(candidates=candidates, existing_ids=set())
        ids = [c["conversation_id"] for c in result]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Slice 2: write_pending() — land candidates in pending-review dir
# ---------------------------------------------------------------------------

class TestWritePending:
    def test_writes_candidate_json_files(self, tmp_path: Path) -> None:
        pending_dir = tmp_path / "pending-review"
        candidates = [_candidate("aaaa-1111", "Trading")]
        sampler = Sampler(target_total=20)
        paths = sampler.write_pending(candidates, pending_dir=pending_dir)

        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].name == "candidate_aaaa-1111.json"
        data = json.loads(paths[0].read_text())
        assert data["conversation_id"] == "aaaa-1111"

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        pending_dir = tmp_path / "nested" / "pending-review"
        sampler = Sampler(target_total=20)
        sampler.write_pending([_candidate("x-1", "AI")], pending_dir=pending_dir)
        assert pending_dir.is_dir()

    def test_does_not_overwrite_existing_candidate(self, tmp_path: Path) -> None:
        """Idempotent: existing pending files are not overwritten."""
        pending_dir = tmp_path / "pending-review"
        pending_dir.mkdir()
        existing = pending_dir / "candidate_aaaa-1111.json"
        existing.write_text('{"sentinel": true}', encoding="utf-8")

        sampler = Sampler(target_total=20)
        sampler.write_pending([_candidate("aaaa-1111", "Trading")], pending_dir=pending_dir)

        # Should still have the sentinel content, not overwritten
        data = json.loads(existing.read_text())
        assert data.get("sentinel") is True

    def test_returns_empty_list_for_empty_candidates(self, tmp_path: Path) -> None:
        sampler = Sampler(target_total=20)
        paths = sampler.write_pending([], pending_dir=tmp_path / "pending-review")
        assert paths == []


# ---------------------------------------------------------------------------
# Slice 3: promote() — move a reviewed TaskEntry into dataset/tasks
# ---------------------------------------------------------------------------

def _minimal_task_entry(task_id: str, conv_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "name": f"Test Task {task_id}",
        "taxonomy": {"output_type": "code", "complexity": "multi_tool", "intent": "generate"},
        "domain": {"category": "Software Dev", "subcategory": "Feature Dev"},
        "source": {
            "conversation_id": conv_id,
            "transcript_path": "/fake/transcript_full.jsonl",
            "timestamp": "2026-07-01T10:00:00Z",
        },
        "prompt": "Build a new feature for the project.",
        "required_tools": [],
        "required_skills": [],
        "roi_value": 25.0,
        "target_token_budget": 5000,
        "target_tool_call_budget": 15,
        "setup_steps": [],
        "validation_rules": [
            {"type": "file_exists", "path": "output/result.txt"}
        ],
        "evaluation_results": [],
    }


SCHEMA_PATH = Path(__file__).resolve().parents[1] / ".scratch/bench-suite/task-schema.json"


class TestPromote:
    def test_promote_writes_to_dataset(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / "dataset" / "tasks"
        tasks_dir.mkdir(parents=True)
        store = DatasetStore(tasks_dir, SCHEMA_PATH)
        sampler = Sampler(target_total=20)

        task = _minimal_task_entry("sw_feature_01", "aaaaaaaa-0000-4000-8000-000000000001")
        path = sampler.promote(task, store=store)

        assert path.exists()
        saved = json.loads(path.read_text())
        assert saved["task_id"] == "sw_feature_01"

    def test_promote_validates_schema(self, tmp_path: Path) -> None:
        from bench_suite.store import SchemaValidationError

        tasks_dir = tmp_path / "dataset" / "tasks"
        tasks_dir.mkdir(parents=True)
        store = DatasetStore(tasks_dir, SCHEMA_PATH)
        sampler = Sampler(target_total=20)

        bad_task = {"task_id": "x"}  # missing required fields
        with pytest.raises(SchemaValidationError):
            sampler.promote(bad_task, store=store)

    def test_promote_refuses_to_overwrite_existing(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / "dataset" / "tasks"
        tasks_dir.mkdir(parents=True)
        store = DatasetStore(tasks_dir, SCHEMA_PATH)
        sampler = Sampler(target_total=20)

        task = _minimal_task_entry("sw_feature_01", "aaaaaaaa-0000-4000-8000-000000000001")
        sampler.promote(task, store=store)

        with pytest.raises(FileExistsError, match="sw_feature_01"):
            sampler.promote(task, store=store)

    def test_promote_does_not_strip_evaluation_results(self, tmp_path: Path) -> None:
        """Promote accepts tasks that already have evaluation_results."""
        tasks_dir = tmp_path / "dataset" / "tasks"
        tasks_dir.mkdir(parents=True)
        store = DatasetStore(tasks_dir, SCHEMA_PATH)
        sampler = Sampler(target_total=20)

        task = _minimal_task_entry("sw_feature_02", "bbbbbbbb-0000-4000-8000-000000000002")
        task["evaluation_results"] = [
            {
                "model_name": "gemini-2.5-flash",
                "model_config": {"thinking_level": "high"},
                "completeness_percent": 100.0,
                "input_tokens": 100,
                "output_tokens": 50,
                "tool_calls": 1,
                "cost_usd": 0.001,
                "latency_seconds": 5.0,
                "earned_roi": 25.0,
                "cost_effectiveness_roi_per_usd": 25000.0,
                "timestamp": "2026-07-01T10:00:00Z",
            }
        ]
        path = sampler.promote(task, store=store)
        saved = json.loads(path.read_text())
        assert len(saved["evaluation_results"]) == 1
