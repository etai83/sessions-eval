"""Ticket 13: first corpus-derived TaskEntry through live path end-to-end."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from bench_suite.live import run_live_task
from bench_suite.registry import Registry
from bench_suite.runner import AlreadyEvaluatedError, MockGeminiClient
from bench_suite.store import DatasetStore

REPO_ROOT = Path(__file__).resolve().parents[1]
# Canonical human-authored TaskEntry (dataset/tasks/ is gitignored runtime state)
CORPUS_TASK_PATH = (
    REPO_ROOT / ".scratch/bench-suite/fixtures/trading_btc_backtest_01.json"
)
FIXTURE_GOLDEN = REPO_ROOT / ".scratch/bench-suite/fixtures/offline_golden_task.json"
CORPUS_TASK_ID = "trading_btc_backtest_01"
DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_CONFIG = {"thinking_level": "high"}


def _corpus_passing_client() -> MockGeminiClient:
    """Mock model output that satisfies trading_btc_backtest_01 DoD."""
    body = {
        "files": [
            {
                "path": "experiments/backtest.py",
                "content": (
                    "# BTC backtest harness\n"
                    "def run_backtest(params):\n"
                    "    return {'symbol': params.get('symbol', 'BTC'), 'pnl': 0.0}\n"
                    "\n"
                    "if __name__ == '__main__':\n"
                    "    print(run_backtest({'symbol': 'BTC'}))\n"
                ),
            }
        ],
        "tool_calls": 3,
    }
    return MockGeminiClient(text=json.dumps(body), input_tokens=1200, output_tokens=350)


def _corpus_dataset_path(suite_root: Path) -> Path:
    return (
        suite_root
        / ".scratch/bench-suite/dataset/tasks"
        / f"{CORPUS_TASK_ID}.json"
    )


def _store(suite_root: Path) -> DatasetStore:
    return DatasetStore(
        suite_root / ".scratch/bench-suite/dataset/tasks",
        suite_root / ".scratch/bench-suite/task-schema.json",
    )


def _run_corpus_live(
    suite_root: Path,
    *,
    client: MockGeminiClient | None = None,
    task_id: str | None = None,
    task_path: Path | None = None,
) -> dict[str, Any]:
    """Live-run the corpus task with default model×config (mock client by default)."""
    kwargs: dict[str, Any] = {
        "repo_root": suite_root,
        "model_name": DEFAULT_MODEL,
        "model_config": dict(DEFAULT_CONFIG),
        "client": client if client is not None else _corpus_passing_client(),
    }
    if task_id is not None:
        kwargs["task_id"] = task_id
    elif task_path is not None:
        kwargs["task_path"] = task_path
    else:
        kwargs["task_path"] = _corpus_dataset_path(suite_root)
    return run_live_task(**kwargs)


@pytest.fixture
def suite_with_corpus_task(tmp_suite: Path) -> Path:
    """tmp_suite plus the corpus-derived TaskEntry (and golden fixture already present)."""
    tasks_dir = tmp_suite / ".scratch/bench-suite/dataset/tasks"
    shutil.copy(CORPUS_TASK_PATH, tasks_dir / f"{CORPUS_TASK_ID}.json")
    # Also seed golden into dataset so multi-task aggregation is exercisable
    store = _store(tmp_suite)
    golden = json.loads(FIXTURE_GOLDEN.read_text(encoding="utf-8"))
    store.save(golden)
    store.append_result(
        golden["task_id"],
        {
            "model_name": DEFAULT_MODEL,
            "model_config": dict(DEFAULT_CONFIG),
            "completeness_percent": 100.0,
            "input_tokens": 1000,
            "output_tokens": 200,
            "tool_calls": 3,
            "cost_usd": 0.05,
            "latency_seconds": 2.5,
            "earned_roi": 10.0,
            "cost_effectiveness_roi_per_usd": 200.0,
            "timestamp": "2026-07-16T12:00:00Z",
        },
    )
    return tmp_suite


class TestCorpusTaskArtifact:
    def test_committed_task_is_schema_valid(self) -> None:
        store = DatasetStore(
            REPO_ROOT / ".scratch/bench-suite/dataset/tasks",
            REPO_ROOT / ".scratch/bench-suite/task-schema.json",
        )
        task = store.load_path(CORPUS_TASK_PATH)
        assert task["task_id"] == CORPUS_TASK_ID
        assert task["source"]["conversation_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert task["task_id"] != "offline_golden_01"
        assert "evaluation_results" not in task
        assert task["validation_rules"]
        assert task["roi_value"] > 0
        assert task["setup_steps"]

    def test_committed_task_is_not_the_offline_fixture(self) -> None:
        task = json.loads(CORPUS_TASK_PATH.read_text(encoding="utf-8"))
        golden = json.loads(FIXTURE_GOLDEN.read_text(encoding="utf-8"))
        assert task["source"]["conversation_id"] != golden["source"]["conversation_id"]
        assert "backtest" in task["prompt"].lower()


class TestFirstRealTaskLiveE2E:
    def test_live_run_appends_full_evaluation_result(
        self, suite_with_corpus_task: Path
    ) -> None:
        client = _corpus_passing_client()
        result = _run_corpus_live(suite_with_corpus_task, client=client)

        assert result["task_id"] == CORPUS_TASK_ID
        assert result["skipped_duplicate"] is False
        ev = result["evaluation_result"]
        assert ev["completeness_percent"] == 100.0
        assert ev["input_tokens"] == 1200
        assert ev["output_tokens"] == 350
        assert ev["tool_calls"] == 3
        assert ev["cost_usd"] > 0
        assert ev["latency_seconds"] >= 0
        assert ev["earned_roi"] == 50.0  # roi_value * 100%
        assert ev["cost_effectiveness_roi_per_usd"] == pytest.approx(50.0 / ev["cost_usd"])
        assert "model_name" in ev and "model_config" in ev and "timestamp" in ev
        assert "experiments/backtest.py" in result["files_written"]
        assert len(client.calls) == 1
        assert "backtesting" in client.calls[0]["prompt"].lower()

        saved = _store(suite_with_corpus_task).load(CORPUS_TASK_ID)
        assert len(saved["evaluation_results"]) == 1
        assert saved["evaluation_results"][0]["completeness_percent"] == 100.0

    def test_registry_records_model_config_task_pair(
        self, suite_with_corpus_task: Path
    ) -> None:
        _run_corpus_live(suite_with_corpus_task)
        reg = Registry(suite_with_corpus_task / ".scratch/bench-suite/registry.json")
        assert reg.has_run(DEFAULT_MODEL, DEFAULT_CONFIG, CORPUS_TASK_ID)
        # Fixture golden was not re-run in this call
        assert not reg.has_run(DEFAULT_MODEL, DEFAULT_CONFIG, "offline_golden_01")

    def test_leaderboard_includes_corpus_task_contribution(
        self, suite_with_corpus_task: Path
    ) -> None:
        result = _run_corpus_live(suite_with_corpus_task)
        rows = result["leaderboard_rows"]
        assert len(rows) == 1
        row = rows[0]
        assert row["model_name"] == DEFAULT_MODEL
        # Two tasks for same model×config: golden (100%) + corpus (100%) → avg 100
        assert row["avg_success_rate"] == 100.0
        # total ROI = 10 (golden) + 50 (corpus)
        assert row["total_earned_roi"] == 60.0
        # total cost = 0.05 + corpus cost
        assert row["total_cost_usd"] > 0.05

        md = (
            suite_with_corpus_task / ".scratch/bench-suite/leaderboard.md"
        ).read_text(encoding="utf-8")
        assert DEFAULT_MODEL in md
        assert "60.0" in md or "60" in md

        html = (
            suite_with_corpus_task / ".scratch/bench-suite/index.html"
        ).read_text(encoding="utf-8")
        assert "chart.js" in html
        assert CORPUS_TASK_ID in html

    def test_rerun_same_pair_blocked_before_api(
        self, suite_with_corpus_task: Path
    ) -> None:
        first = _corpus_passing_client()
        _run_corpus_live(suite_with_corpus_task, client=first)
        assert len(first.calls) == 1

        second = _corpus_passing_client()
        with pytest.raises(AlreadyEvaluatedError, match="refusing live API call"):
            _run_corpus_live(suite_with_corpus_task, client=second)
        assert len(second.calls) == 0

        saved = _store(suite_with_corpus_task).load(CORPUS_TASK_ID)
        assert len(saved["evaluation_results"]) == 1

    def test_setup_steps_apply_before_model(self, suite_with_corpus_task: Path) -> None:
        """setup_steps leave strategy_params.json even if the model never writes it."""
        body = {
            "files": [
                {
                    "path": "experiments/backtest.py",
                    "content": "print('backtest')\n",
                }
            ],
            "tool_calls": 1,
        }
        client = MockGeminiClient(text=json.dumps(body), input_tokens=100, output_tokens=40)
        result = _run_corpus_live(suite_with_corpus_task, client=client)
        # All three rules pass: backtest exists+contains, strategy_params from setup
        assert result["evaluation_result"]["completeness_percent"] == 100.0

    def test_live_run_by_task_id(self, suite_with_corpus_task: Path) -> None:
        result = _run_corpus_live(suite_with_corpus_task, task_id=CORPUS_TASK_ID)
        assert result["task_id"] == CORPUS_TASK_ID
        assert result["evaluation_result"]["completeness_percent"] == 100.0

    def test_task_id_and_task_path_are_mutually_exclusive(
        self, suite_with_corpus_task: Path
    ) -> None:
        with pytest.raises(ValueError, match="only one of task_id or task_path"):
            run_live_task(
                repo_root=suite_with_corpus_task,
                task_id=CORPUS_TASK_ID,
                task_path=_corpus_dataset_path(suite_with_corpus_task),
                client=_corpus_passing_client(),
            )
