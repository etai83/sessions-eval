"""Integration test: transcripts → stratified sample → pending-review → promote."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bench_suite.pipeline import sample_and_write_pending, promote_task
from bench_suite.store import DatasetStore

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / ".scratch/bench-suite/fixtures/transcripts"
SCHEMA_PATH = REPO_ROOT / ".scratch/bench-suite/task-schema.json"

# Both fixture transcripts
TRANSCRIPT_A = FIXTURES_DIR / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" / ".system_generated/logs/transcript_full.jsonl"
TRANSCRIPT_B = FIXTURES_DIR / "11111111-2222-3333-4444-555555555555" / ".system_generated/logs/transcript_full.jsonl"

RULES_PATH = REPO_ROOT / ".scratch/bench-suite/classifier_rules.json"


def _minimal_full_task(task_id: str, conv_id: str) -> dict:
    """Build a schema-valid TaskEntry for promotion testing."""
    return {
        "task_id": task_id,
        "name": f"Sample Integration Task {task_id}",
        "taxonomy": {"output_type": "code", "complexity": "multi_tool", "intent": "generate"},
        "domain": {"category": "Software Dev", "subcategory": "Feature Dev"},
        "source": {
            "conversation_id": conv_id,
            "transcript_path": str(TRANSCRIPT_A),
            "timestamp": "2026-06-17T19:38:28Z",
        },
        "prompt": "Create a Python backtesting script for my trading strategy on BTC.",
        "required_tools": ["write_to_file", "run_command"],
        "required_skills": [],
        "roi_value": 50.0,
        "target_token_budget": 8000,
        "target_tool_call_budget": 12,
        "setup_steps": [],
        "validation_rules": [
            {"type": "file_exists", "path": "experiments/backtest.py"}
        ],
        "evaluation_results": [],
    }


class TestSampleAndWritePending:
    def test_two_transcripts_land_in_pending_review(self, tmp_path: Path) -> None:
        pending_dir = tmp_path / "pending-review"
        result = sample_and_write_pending(
            [TRANSCRIPT_A, TRANSCRIPT_B],
            rules_path=RULES_PATH,
            pending_dir=pending_dir,
            target_total=20,
        )
        assert result["candidates_ingested"] == 2
        assert result["candidates_selected"] == 2
        assert len(result["paths_written"]) == 2
        assert pending_dir.is_dir()

        files = list(pending_dir.glob("candidate_*.json"))
        assert len(files) == 2

    def test_already_existing_ids_excluded(self, tmp_path: Path) -> None:
        pending_dir = tmp_path / "pending-review"
        existing = {"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}  # conv-id of transcript A
        result = sample_and_write_pending(
            [TRANSCRIPT_A, TRANSCRIPT_B],
            rules_path=RULES_PATH,
            pending_dir=pending_dir,
            existing_ids=existing,
            target_total=20,
        )
        assert result["candidates_selected"] == 1
        # Only transcript B should appear
        files = list(pending_dir.glob("candidate_*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["conversation_id"] == "11111111-2222-3333-4444-555555555555"

    def test_idempotent_on_second_run(self, tmp_path: Path) -> None:
        pending_dir = tmp_path / "pending-review"
        sample_and_write_pending(
            [TRANSCRIPT_A],
            rules_path=RULES_PATH,
            pending_dir=pending_dir,
            target_total=20,
        )
        # Manually modify the file to prove it won't be overwritten
        existing_file = pending_dir / "candidate_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.json"
        existing_file.write_text('{"sentinel": "do_not_overwrite"}', encoding="utf-8")

        sample_and_write_pending(
            [TRANSCRIPT_A],
            rules_path=RULES_PATH,
            pending_dir=pending_dir,
            target_total=20,
        )
        data = json.loads(existing_file.read_text())
        assert data.get("sentinel") == "do_not_overwrite"

    def test_candidate_json_has_taxonomy_and_domain(self, tmp_path: Path) -> None:
        pending_dir = tmp_path / "pending-review"
        sample_and_write_pending(
            [TRANSCRIPT_A],
            rules_path=RULES_PATH,
            pending_dir=pending_dir,
            target_total=20,
        )
        files = list(pending_dir.glob("candidate_*.json"))
        data = json.loads(files[0].read_text())
        assert "taxonomy" in data
        assert "domain" in data
        assert "conversation_id" in data


class TestPromoteTask:
    def test_promote_via_pipeline(self, tmp_path: Path) -> None:
        # Set up isolated suite
        data = tmp_path / ".scratch" / "bench-suite"
        data.mkdir(parents=True)
        shutil.copy(SCHEMA_PATH, data / "task-schema.json")
        (data / "dataset" / "tasks").mkdir(parents=True)
        config = {
            "paths": {
                "schema": ".scratch/bench-suite/task-schema.json",
                "dataset_tasks": ".scratch/bench-suite/dataset/tasks",
                "registry": ".scratch/bench-suite/registry.json",
                "leaderboard": ".scratch/bench-suite/leaderboard.md",
                "dashboard_html": ".scratch/bench-suite/index.html",
                "pending_review": ".scratch/bench-suite/pending-review",
                "classifier_rules": ".scratch/bench-suite/classifier_rules.json",
            }
        }
        (data / "config.json").write_text(json.dumps(config), encoding="utf-8")

        # Write a pending candidate as a fully-reviewed TaskEntry
        pending_dir = data / "pending-review"
        pending_dir.mkdir()
        task = _minimal_full_task("backtest_btc_01", "aaaaaaaa-0000-4000-8000-000000000001")
        pending_file = pending_dir / "candidate_aaaaaaaa-0000-4000-8000-000000000001.json"
        pending_file.write_text(json.dumps(task), encoding="utf-8")

        result = promote_task(pending_file, repo_root=tmp_path)

        assert result["task_id"] == "backtest_btc_01"
        dest = Path(result["dataset_path"])
        assert dest.exists()
        saved = json.loads(dest.read_text())
        assert saved["task_id"] == "backtest_btc_01"

    def test_promote_refuses_duplicate(self, tmp_path: Path) -> None:
        data = tmp_path / ".scratch" / "bench-suite"
        data.mkdir(parents=True)
        shutil.copy(SCHEMA_PATH, data / "task-schema.json")
        (data / "dataset" / "tasks").mkdir(parents=True)
        config = {
            "paths": {
                "schema": ".scratch/bench-suite/task-schema.json",
                "dataset_tasks": ".scratch/bench-suite/dataset/tasks",
                "registry": ".scratch/bench-suite/registry.json",
                "leaderboard": ".scratch/bench-suite/leaderboard.md",
                "dashboard_html": ".scratch/bench-suite/index.html",
                "pending_review": ".scratch/bench-suite/pending-review",
                "classifier_rules": ".scratch/bench-suite/classifier_rules.json",
            }
        }
        (data / "config.json").write_text(json.dumps(config), encoding="utf-8")
        pending_dir = data / "pending-review"
        pending_dir.mkdir()

        task = _minimal_full_task("backtest_btc_01", "aaaaaaaa-0000-4000-8000-000000000001")
        pending_file = pending_dir / "candidate_aaaaaaaa-0000-4000-8000-000000000001.json"
        pending_file.write_text(json.dumps(task), encoding="utf-8")

        promote_task(pending_file, repo_root=tmp_path)

        with pytest.raises(FileExistsError, match="backtest_btc_01"):
            promote_task(pending_file, repo_root=tmp_path)
