"""Runner seam: setup_steps, model response → sandbox files, cost/tokens."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench_suite.registry import Registry
from bench_suite.runner import (
    AlreadyEvaluatedError,
    MockGeminiClient,
    Runner,
    estimate_cost_usd,
    parse_model_files_response,
)


def test_estimate_cost_usd() -> None:
    # 1M input + 1M output at flash rates
    cost = estimate_cost_usd(
        "gemini-2.5-flash",
        1_000_000,
        1_000_000,
        pricing={"gemini-2.5-flash": {"input_per_mtok": 0.15, "output_per_mtok": 0.60}},
    )
    assert cost == 0.75


def test_parse_model_files_response_plain_and_fenced() -> None:
    plain = json.dumps(
        {
            "files": [{"path": "output/summary.json", "content": '{"status":"ok"}'}],
            "tool_calls": 2,
        }
    )
    files, tools = parse_model_files_response(plain)
    assert tools == 2
    assert files[0]["path"] == "output/summary.json"

    fenced = "```json\n" + plain + "\n```"
    files2, tools2 = parse_model_files_response(fenced)
    assert tools2 == 2
    assert files2[0]["path"] == "output/summary.json"


def test_runner_applies_setup_and_model_files(tmp_path: Path, offline_fixture: dict) -> None:
    summary = {
        "status": "ok",
        "greeting": "Hello bench-suite",
    }
    response = json.dumps(
        {
            "files": [
                {
                    "path": "output/summary.json",
                    "content": json.dumps(summary),
                }
            ],
            "tool_calls": 1,
        }
    )
    client = MockGeminiClient(text=response, input_tokens=1200, output_tokens=300)
    runner = Runner(
        client,
        pricing={"gemini-2.5-flash": {"input_per_mtok": 0.15, "output_per_mtok": 0.60}},
    )
    sandbox = tmp_path / "sandbox"
    result = runner.run(
        offline_fixture,
        sandbox,
        model_name="gemini-2.5-flash",
        model_config={"thinking_level": "high"},
    )

    # setup_steps wrote seed
    assert (sandbox / "input" / "seed.txt").read_text(encoding="utf-8") == "seed"
    # model wrote DoD file
    written = json.loads((sandbox / "output" / "summary.json").read_text(encoding="utf-8"))
    assert written["status"] == "ok"
    assert "Hello bench-suite" in written["greeting"]

    assert result.execution["input_tokens"] == 1200
    assert result.execution["output_tokens"] == 300
    assert result.execution["tool_calls"] == 1
    assert result.execution["cost_usd"] > 0
    assert result.execution["latency_seconds"] >= 0
    assert client.calls[0]["model_name"] == "gemini-2.5-flash"
    assert offline_fixture["prompt"] in client.calls[0]["prompt"]
    assert result.files_parsed is True


def test_runner_registry_guard_blocks_api(tmp_path: Path, offline_fixture: dict) -> None:
    reg = Registry(tmp_path / "registry.json")
    cfg = {"thinking_level": "high"}
    reg.record("gemini-2.5-flash", cfg, offline_fixture["task_id"])

    client = MockGeminiClient(text="{}")
    runner = Runner(client)
    with pytest.raises(AlreadyEvaluatedError, match="refusing live API call"):
        runner.run(
            offline_fixture,
            tmp_path / "sandbox",
            model_name="gemini-2.5-flash",
            model_config=cfg,
            registry=reg,
        )
    assert client.calls == []
