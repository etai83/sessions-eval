"""Live path: registry guard before API, then evaluate → board."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench_suite.live import run_live_task
from bench_suite.registry import Registry
from bench_suite.runner import AlreadyEvaluatedError, MockGeminiClient
from bench_suite.store import DatasetStore


def _passing_client() -> MockGeminiClient:
    body = {
        "files": [
            {
                "path": "output/summary.json",
                "content": json.dumps(
                    {"status": "ok", "greeting": "Hello bench-suite from live mock"}
                ),
            }
        ],
        "tool_calls": 2,
    }
    return MockGeminiClient(text=json.dumps(body), input_tokens=500, output_tokens=100)


def test_live_run_success(tmp_suite: Path) -> None:
    client = _passing_client()
    result = run_live_task(
        repo_root=tmp_suite,
        model_name="gemini-2.5-flash",
        model_config={"thinking_level": "high"},
        client=client,
    )

    assert result["skipped_duplicate"] is False
    assert result["task_id"] == "offline_golden_01"
    assert result["evaluation_result"]["completeness_percent"] == 100.0
    assert result["evaluation_result"]["input_tokens"] == 500
    assert result["evaluation_result"]["cost_usd"] > 0
    assert "output/summary.json" in result["files_written"]
    assert len(client.calls) == 1

    store = DatasetStore(
        tmp_suite / ".scratch/bench-suite/dataset/tasks",
        tmp_suite / ".scratch/bench-suite/task-schema.json",
    )
    saved = store.load("offline_golden_01")
    assert len(saved["evaluation_results"]) == 1

    reg = Registry(tmp_suite / ".scratch/bench-suite/registry.json")
    assert reg.has_run("gemini-2.5-flash", {"thinking_level": "high"}, "offline_golden_01")

    md = (tmp_suite / ".scratch/bench-suite/leaderboard.md").read_text(encoding="utf-8")
    assert "gemini-2.5-flash" in md
    html = (tmp_suite / ".scratch/bench-suite/index.html").read_text(encoding="utf-8")
    assert "chart.js@4.4.1" in html


def test_live_run_refuses_duplicate_before_api(tmp_suite: Path) -> None:
    client = _passing_client()
    run_live_task(
        repo_root=tmp_suite,
        model_name="gemini-2.5-flash",
        model_config={"thinking_level": "high"},
        client=client,
    )
    assert len(client.calls) == 1

    client2 = _passing_client()
    with pytest.raises(AlreadyEvaluatedError, match="refusing live API call"):
        run_live_task(
            repo_root=tmp_suite,
            model_name="gemini-2.5-flash",
            model_config={"thinking_level": "high"},
            client=client2,
        )
    assert len(client2.calls) == 0  # never called the API

    store = DatasetStore(
        tmp_suite / ".scratch/bench-suite/dataset/tasks",
        tmp_suite / ".scratch/bench-suite/task-schema.json",
    )
    assert len(store.load("offline_golden_01")["evaluation_results"]) == 1
