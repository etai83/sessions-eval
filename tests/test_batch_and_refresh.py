"""Ticket 15: batch eval CLI + additive corpus refresh."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from bench_suite.pipeline import batch_eval, refresh_corpus
from bench_suite.registry import Registry
from bench_suite.runner import GenerateResult, MockGeminiClient
from bench_suite.store import DatasetStore

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / ".scratch/bench-suite/task-schema.json"
FIXTURES_DIR = REPO_ROOT / ".scratch/bench-suite/fixtures/transcripts"
TRANSCRIPT_A = (
    FIXTURES_DIR
    / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    / ".system_generated/logs/transcript_full.jsonl"
)
TRANSCRIPT_B = (
    FIXTURES_DIR
    / "11111111-2222-3333-4444-555555555555"
    / ".system_generated/logs/transcript_full.jsonl"
)
RULES_PATH = REPO_ROOT / ".scratch/bench-suite/classifier_rules.json"
CORPUS_FIXTURE = REPO_ROOT / ".scratch/bench-suite/fixtures/trading_btc_backtest_01.json"


def _minimal_task(task_id: str, conv_id: str, *, validation_path: str = "out.txt") -> dict:
    return {
        "task_id": task_id,
        "name": f"Batch Task {task_id}",
        "taxonomy": {"output_type": "code", "complexity": "single_step", "intent": "generate"},
        "domain": {"category": "General", "subcategory": "Miscellaneous"},
        "source": {
            "conversation_id": conv_id,
            "transcript_path": "/dev/null",
            "timestamp": "2026-07-17T00:00:00Z",
        },
        "prompt": f"Write {validation_path} with content ok",
        "required_tools": [],
        "required_skills": [],
        "roi_value": 20.0,
        "target_token_budget": 1000,
        "target_tool_call_budget": 3,
        "setup_steps": [],
        "validation_rules": [{"type": "file_exists", "path": validation_path}],
        "evaluation_results": [],
    }


def _files_client(path: str = "out.txt", content: str = "ok") -> MockGeminiClient:
    body = {"files": [{"path": path, "content": content}], "tool_calls": 1}
    return MockGeminiClient(text=json.dumps(body), input_tokens=200, output_tokens=40)


class MultiTaskMockClient:
    """Return files JSON tailored to the task prompt (for multi-task batch)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        model_name: str,
        prompt: str,
        system_instruction: str,
        model_config: dict[str, Any],
    ) -> GenerateResult:
        self.calls.append(
            {
                "model_name": model_name,
                "prompt": prompt,
                "system_instruction": system_instruction,
                "model_config": model_config,
            }
        )
        # Infer path from prompt "Write <path> with content ok"
        path = "out.txt"
        for token in prompt.split():
            if token.endswith(".txt") or token.endswith(".json") or "/" in token:
                path = token.rstrip(".,")
                break
        body = {"files": [{"path": path, "content": "ok"}], "tool_calls": 1}
        return GenerateResult(text=json.dumps(body), input_tokens=150, output_tokens=30)


def _setup_suite_with_tasks(tmp_suite: Path, tasks: list[dict]) -> DatasetStore:
    store = DatasetStore(
        tmp_suite / ".scratch/bench-suite/dataset/tasks",
        tmp_suite / ".scratch/bench-suite/task-schema.json",
    )
    for task in tasks:
        store.save(task)
    return store


class TestBatchEval:
    def test_runs_all_dataset_tasks(self, tmp_suite: Path) -> None:
        tasks = [
            _minimal_task("batch_a_01", "aaaaaaaa-0000-4000-8000-0000000000a1", validation_path="a.txt"),
            _minimal_task("batch_b_01", "aaaaaaaa-0000-4000-8000-0000000000b1", validation_path="b.txt"),
        ]
        _setup_suite_with_tasks(tmp_suite, tasks)
        client = MultiTaskMockClient()

        result = batch_eval(
            repo_root=tmp_suite,
            model_name="gemini-3.5-flash",
            model_config={"thinking_level": "high"},
            client=client,
        )

        assert result["tasks_total"] == 2
        assert result["ran"] == 2
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert set(result["ran_task_ids"]) == {"batch_a_01", "batch_b_01"}
        # One API call per task (no llm_judge on these)
        assert len(client.calls) == 2

        store = DatasetStore(
            tmp_suite / ".scratch/bench-suite/dataset/tasks",
            tmp_suite / ".scratch/bench-suite/task-schema.json",
        )
        for tid in ("batch_a_01", "batch_b_01"):
            saved = store.load(tid)
            assert len(saved["evaluation_results"]) == 1
            assert saved["evaluation_results"][0]["completeness_percent"] == 100.0

        reg = Registry(tmp_suite / ".scratch/bench-suite/registry.json")
        assert reg.has_run("gemini-3.5-flash", {"thinking_level": "high"}, "batch_a_01")
        assert reg.has_run("gemini-3.5-flash", {"thinking_level": "high"}, "batch_b_01")

        md = (tmp_suite / ".scratch/bench-suite/leaderboard.md").read_text(encoding="utf-8")
        assert "gemini-3.5-flash" in md
        html = (tmp_suite / ".scratch/bench-suite/index.html").read_text(encoding="utf-8")
        assert "chart.js" in html

    def test_skips_already_evaluated_pairs(self, tmp_suite: Path) -> None:
        tasks = [
            _minimal_task("batch_a_01", "aaaaaaaa-0000-4000-8000-0000000000a1", validation_path="a.txt"),
            _minimal_task("batch_b_01", "aaaaaaaa-0000-4000-8000-0000000000b1", validation_path="b.txt"),
        ]
        _setup_suite_with_tasks(tmp_suite, tasks)

        # Pre-record A in registry
        reg = Registry(tmp_suite / ".scratch/bench-suite/registry.json")
        reg.record("gemini-3.5-flash", {"thinking_level": "high"}, "batch_a_01")

        client = MultiTaskMockClient()
        result = batch_eval(
            repo_root=tmp_suite,
            model_name="gemini-3.5-flash",
            model_config={"thinking_level": "high"},
            client=client,
        )

        assert result["ran"] == 1
        assert result["skipped"] == 1
        assert result["skipped_task_ids"] == ["batch_a_01"]
        assert result["ran_task_ids"] == ["batch_b_01"]
        assert len(client.calls) == 1  # only B hit the API

        store = DatasetStore(
            tmp_suite / ".scratch/bench-suite/dataset/tasks",
            tmp_suite / ".scratch/bench-suite/task-schema.json",
        )
        # A never evaluated (only registry-stubbed)
        assert store.load("batch_a_01")["evaluation_results"] == []
        assert len(store.load("batch_b_01")["evaluation_results"]) == 1

    def test_all_skipped_still_refreshes_dashboard(self, tmp_suite: Path) -> None:
        task = _minimal_task("batch_a_01", "aaaaaaaa-0000-4000-8000-0000000000a1")
        task["evaluation_results"] = [
            {
                "model_name": "gemini-3.5-flash",
                "model_config": {"thinking_level": "high"},
                "completeness_percent": 100.0,
                "input_tokens": 10,
                "output_tokens": 5,
                "tool_calls": 0,
                "cost_usd": 0.01,
                "latency_seconds": 0.5,
                "earned_roi": 20.0,
                "cost_effectiveness_roi_per_usd": 2000.0,
                "timestamp": "2026-07-17T00:00:00Z",
            }
        ]
        _setup_suite_with_tasks(tmp_suite, [task])
        reg = Registry(tmp_suite / ".scratch/bench-suite/registry.json")
        reg.record("gemini-3.5-flash", {"thinking_level": "high"}, "batch_a_01")

        client = MultiTaskMockClient()
        result = batch_eval(
            repo_root=tmp_suite,
            model_name="gemini-3.5-flash",
            model_config={"thinking_level": "high"},
            client=client,
        )
        assert result["ran"] == 0
        assert result["skipped"] == 1
        assert len(client.calls) == 0
        assert (tmp_suite / ".scratch/bench-suite/leaderboard.md").is_file()
        assert "gemini-3.5-flash" in (
            tmp_suite / ".scratch/bench-suite/leaderboard.md"
        ).read_text(encoding="utf-8")

    def test_empty_dataset(self, tmp_suite: Path) -> None:
        result = batch_eval(
            repo_root=tmp_suite,
            model_name="gemini-3.5-flash",
            model_config={"thinking_level": "high"},
            client=MultiTaskMockClient(),
        )
        assert result["tasks_total"] == 0
        assert result["ran"] == 0
        assert result["skipped"] == 0


class TestRefreshCorpus:
    def test_discovers_transcripts_and_writes_pending(self, tmp_suite: Path) -> None:
        # Copy fixture transcript tree into suite
        transcripts_root = tmp_suite / "transcripts"
        shutil.copytree(FIXTURES_DIR, transcripts_root)

        result = refresh_corpus(
            repo_root=tmp_suite,
            transcripts_root=transcripts_root,
            rules_path=RULES_PATH,
            target_total=20,
        )

        assert result["transcripts_discovered"] == 2
        assert result["candidates_ingested"] == 2
        assert result["candidates_selected"] == 2
        assert result["paths_written"]
        pending = tmp_suite / ".scratch/bench-suite/pending-review"
        assert pending.is_dir()
        files = list(pending.glob("candidate_*.json"))
        assert len(files) == 2

        # Dataset untouched (still empty)
        store = DatasetStore(
            tmp_suite / ".scratch/bench-suite/dataset/tasks",
            tmp_suite / ".scratch/bench-suite/task-schema.json",
        )
        assert store.list_tasks() == []

    def test_excludes_existing_dataset_conversation_ids(self, tmp_suite: Path) -> None:
        transcripts_root = tmp_suite / "transcripts"
        shutil.copytree(FIXTURES_DIR, transcripts_root)

        # Promote a task that uses transcript A's conversation_id
        store = DatasetStore(
            tmp_suite / ".scratch/bench-suite/dataset/tasks",
            tmp_suite / ".scratch/bench-suite/task-schema.json",
        )
        corpus = json.loads(CORPUS_FIXTURE.read_text(encoding="utf-8"))
        # corpus uses aaaaaaaa-bbbb-...
        store.save(corpus)
        before = json.loads(
            (tmp_suite / ".scratch/bench-suite/dataset/tasks" / "trading_btc_backtest_01.json").read_text()
        )

        result = refresh_corpus(
            repo_root=tmp_suite,
            transcripts_root=transcripts_root,
            rules_path=RULES_PATH,
            target_total=20,
        )

        assert result["candidates_selected"] == 1
        pending_files = list(
            (tmp_suite / ".scratch/bench-suite/pending-review").glob("candidate_*.json")
        )
        assert len(pending_files) == 1
        data = json.loads(pending_files[0].read_text(encoding="utf-8"))
        assert data["conversation_id"] == "11111111-2222-3333-4444-555555555555"

        # Existing dataset task bytes unchanged
        after = json.loads(
            (tmp_suite / ".scratch/bench-suite/dataset/tasks" / "trading_btc_backtest_01.json").read_text()
        )
        assert after == before
        assert after.get("evaluation_results") == before.get("evaluation_results")

    def test_does_not_overwrite_existing_pending(self, tmp_suite: Path) -> None:
        transcripts_root = tmp_suite / "transcripts"
        shutil.copytree(FIXTURES_DIR, transcripts_root)

        pending = tmp_suite / ".scratch/bench-suite/pending-review"
        pending.mkdir(parents=True)
        existing = pending / "candidate_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.json"
        existing.write_text('{"sentinel": "human-in-progress"}', encoding="utf-8")

        refresh_corpus(
            repo_root=tmp_suite,
            transcripts_root=transcripts_root,
            rules_path=RULES_PATH,
            target_total=20,
        )

        assert json.loads(existing.read_text(encoding="utf-8"))["sentinel"] == "human-in-progress"

    def test_explicit_transcript_paths(self, tmp_suite: Path) -> None:
        result = refresh_corpus(
            repo_root=tmp_suite,
            transcript_paths=[TRANSCRIPT_B],
            rules_path=RULES_PATH,
            target_total=20,
        )
        assert result["transcripts_discovered"] == 1
        assert result["candidates_selected"] == 1
        files = list(
            (tmp_suite / ".scratch/bench-suite/pending-review").glob("candidate_*.json")
        )
        assert len(files) == 1

    def test_remaining_capacity_caps_selection(self, tmp_suite: Path) -> None:
        """target_total is dataset capacity; only fill remaining slots."""
        transcripts_root = tmp_suite / "transcripts"
        shutil.copytree(FIXTURES_DIR, transcripts_root)
        # Dataset already has 19 tasks → only 1 slot left toward 20
        store = DatasetStore(
            tmp_suite / ".scratch/bench-suite/dataset/tasks",
            tmp_suite / ".scratch/bench-suite/task-schema.json",
        )
        for i in range(19):
            cid = f"bbbbbbbb-0000-4000-8000-{i:012d}"
            store.save(_minimal_task(f"fill_{i:02d}", cid))

        result = refresh_corpus(
            repo_root=tmp_suite,
            transcripts_root=transcripts_root,
            rules_path=RULES_PATH,
            target_total=20,
        )
        assert result["target_new"] == 1
        assert result["candidates_selected"] == 1
