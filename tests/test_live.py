"""Live path: registry guard before API, then evaluate → board."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from bench_suite.live import run_live_task
from bench_suite.registry import Registry
from bench_suite.runner import AlreadyEvaluatedError, GenerateResult, MockGeminiClient
from bench_suite.store import DatasetStore

REPO_ROOT = Path(__file__).resolve().parents[1]
LLM_JUDGE_DEMO = REPO_ROOT / ".scratch/bench-suite/fixtures/llm_judge_demo_task.json"


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


@dataclass
class RoutingMockClient:
    """Return different payloads by model_name (runner vs llm_judge reference)."""

    by_model: dict[str, str]
    input_tokens: int = 100
    output_tokens: int = 50
    calls: list[dict[str, Any]] = field(default_factory=list)

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
        text = self.by_model.get(model_name)
        if text is None:
            raise KeyError(f"No mock response configured for model {model_name!r}")
        return GenerateResult(
            text=text,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


def test_live_run_success(tmp_suite: Path) -> None:
    client = _passing_client()
    result = run_live_task(
        repo_root=tmp_suite,
        model_name="gemini-3.5-flash",
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
    assert reg.has_run("gemini-3.5-flash", {"thinking_level": "high"}, "offline_golden_01")

    md = (tmp_suite / ".scratch/bench-suite/leaderboard.md").read_text(encoding="utf-8")
    assert "gemini-3.5-flash" in md
    html = (tmp_suite / ".scratch/bench-suite/index.html").read_text(encoding="utf-8")
    assert "chart.js@4.4.1" in html


def test_live_run_refuses_duplicate_before_api(tmp_suite: Path) -> None:
    client = _passing_client()
    run_live_task(
        repo_root=tmp_suite,
        model_name="gemini-3.5-flash",
        model_config={"thinking_level": "high"},
        client=client,
    )
    assert len(client.calls) == 1

    client2 = _passing_client()
    with pytest.raises(AlreadyEvaluatedError, match="refusing live API call"):
        run_live_task(
            repo_root=tmp_suite,
            model_name="gemini-3.5-flash",
            model_config={"thinking_level": "high"},
            client=client2,
        )
    assert len(client2.calls) == 0  # never called the API

    store = DatasetStore(
        tmp_suite / ".scratch/bench-suite/dataset/tasks",
        tmp_suite / ".scratch/bench-suite/task-schema.json",
    )
    assert len(store.load("offline_golden_01")["evaluation_results"]) == 1


def test_live_run_llm_judge_uses_reference_model(tmp_suite: Path) -> None:
    """Ticket 14: live path judges with config reference model, not model under test."""
    shutil.copy(LLM_JUDGE_DEMO, tmp_suite / ".scratch/bench-suite/fixtures" / LLM_JUDGE_DEMO.name)

    runner_body = {
        "files": [
            {
                "path": "output/summary.json",
                "content": json.dumps(
                    {
                        "status": "ok",
                        "greeting": "Hello bench-suite — a complete natural sentence.",
                    }
                ),
            }
        ],
        "tool_calls": 2,
    }
    client = RoutingMockClient(
        by_model={
            "gemini-3.5-flash": json.dumps(runner_body),
            "gemini-3.1-flash-lite": '{"score": 0.95, "rationale": "natural sentence"}',
        },
        input_tokens=400,
        output_tokens=80,
    )

    result = run_live_task(
        repo_root=tmp_suite,
        task_path=tmp_suite / ".scratch/bench-suite/fixtures" / LLM_JUDGE_DEMO.name,
        model_name="gemini-3.5-flash",
        model_config={"thinking_level": "high"},
        client=client,
    )

    assert result["task_id"] == "llm_judge_demo_01"
    # 4 rules including llm_judge all pass
    assert result["evaluation_result"]["completeness_percent"] == 100.0
    assert result["evaluation_result"]["earned_roi"] == 15.0

    models_called = [c["model_name"] for c in client.calls]
    assert "gemini-3.5-flash" in models_called  # runner
    assert "gemini-3.1-flash-lite" in models_called  # judge reference from config
    # Second call is the judge: fixed reference model only
    assert len(client.calls) == 2
    assert client.calls[1]["model_name"] == "gemini-3.1-flash-lite"
    assert "Rubric" in client.calls[1]["prompt"]

    store = DatasetStore(
        tmp_suite / ".scratch/bench-suite/dataset/tasks",
        tmp_suite / ".scratch/bench-suite/task-schema.json",
    )
    saved = store.load("llm_judge_demo_01")
    assert len(saved["evaluation_results"]) == 1
    assert saved["evaluation_results"][0]["completeness_percent"] == 100.0


def test_live_run_llm_judge_fail_lowers_completeness(tmp_suite: Path) -> None:
    shutil.copy(LLM_JUDGE_DEMO, tmp_suite / ".scratch/bench-suite/fixtures" / LLM_JUDGE_DEMO.name)
    runner_body = {
        "files": [
            {
                "path": "output/summary.json",
                "content": json.dumps(
                    {"status": "ok", "greeting": "Hello bench-suite placeholder"}
                ),
            }
        ],
        "tool_calls": 1,
    }
    client = RoutingMockClient(
        by_model={
            "gemini-3.5-flash": json.dumps(runner_body),
            "gemini-3.1-flash-lite": '{"score": 0.2, "rationale": "placeholder-like"}',
        }
    )

    result = run_live_task(
        repo_root=tmp_suite,
        task_path=tmp_suite / ".scratch/bench-suite/fixtures" / LLM_JUDGE_DEMO.name,
        model_name="gemini-3.5-flash",
        model_config={"thinking_level": "high"},
        client=client,
    )

    # 3 deterministic pass + 1 judge fail → 75%
    assert result["evaluation_result"]["completeness_percent"] == 75.0
    assert result["evaluation_result"]["earned_roi"] == pytest.approx(15.0 * 0.75)
