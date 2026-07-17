"""Evaluator seam: deterministic DoD + scoring formulas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench_suite.evaluator import Evaluator, strip_diagnostic_fields


def _execution(**overrides):
    base = {
        "model_name": "gemini-2.5-flash",
        "model_config": {"thinking_level": "high"},
        "input_tokens": 100,
        "output_tokens": 50,
        "tool_calls": 1,
        "cost_usd": 0.10,
        "latency_seconds": 1.0,
    }
    base.update(overrides)
    return base


def test_all_deterministic_rules_pass(tmp_path: Path, offline_fixture: dict) -> None:
    sandbox = tmp_path / "sandbox"
    out = sandbox / "output"
    out.mkdir(parents=True)
    (out / "summary.json").write_text(
        json.dumps({"status": "ok", "greeting": "Hello bench-suite"}),
        encoding="utf-8",
    )

    result = Evaluator().evaluate(
        offline_fixture,
        sandbox,
        _execution(cost_usd=0.05),
        timestamp="2026-07-16T12:00:00Z",
    )

    assert result["completeness_percent"] == 100.0
    assert result["earned_roi"] == 10.0  # 10 * 1.0
    assert result["cost_effectiveness_roi_per_usd"] == 200.0  # 10 / 0.05
    assert result["timestamp"] == "2026-07-16T12:00:00Z"
    clean = strip_diagnostic_fields(result)
    assert "_rules_passed" not in clean


def test_partial_pass(tmp_path: Path, offline_fixture: dict) -> None:
    sandbox = tmp_path / "sandbox"
    out = sandbox / "output"
    out.mkdir(parents=True)
    # file exists and contains text, but wrong status field
    (out / "summary.json").write_text(
        json.dumps({"status": "fail", "greeting": "Hello bench-suite"}),
        encoding="utf-8",
    )

    result = Evaluator().evaluate(offline_fixture, sandbox, _execution(cost_usd=0.25))
    assert result["completeness_percent"] == pytest.approx((2 / 3) * 100)
    assert result["earned_roi"] == pytest.approx(10.0 * (2 / 3))
    assert result["cost_effectiveness_roi_per_usd"] == pytest.approx(result["earned_roi"] / 0.25)


def test_llm_judge_counts_as_fail_offline(tmp_path: Path, offline_fixture: dict) -> None:
    """Without a judge client, llm_judge fails (offline-safe default)."""
    task = dict(offline_fixture)
    task["validation_rules"] = list(task["validation_rules"]) + [
        {"type": "llm_judge", "rubric": "good", "min_score": 0.7}
    ]
    sandbox = tmp_path / "sandbox"
    out = sandbox / "output"
    out.mkdir(parents=True)
    (out / "summary.json").write_text(
        json.dumps({"status": "ok", "greeting": "Hello bench-suite"}),
        encoding="utf-8",
    )
    result = Evaluator().evaluate(task, sandbox, _execution())
    assert result["completeness_percent"] == 75.0  # 3 of 4


def _sandbox_with_summary(tmp_path: Path, offline_fixture: dict) -> Path:
    sandbox = tmp_path / "sandbox"
    out = sandbox / "output"
    out.mkdir(parents=True)
    (out / "summary.json").write_text(
        json.dumps({"status": "ok", "greeting": "Hello bench-suite from judge"}),
        encoding="utf-8",
    )
    return sandbox


def test_llm_judge_pass_when_score_meets_min(
    tmp_path: Path, offline_fixture: dict
) -> None:
    from bench_suite.runner import MockGeminiClient

    task = dict(offline_fixture)
    task["validation_rules"] = list(task["validation_rules"]) + [
        {
            "type": "llm_judge",
            "rubric": "Greeting is friendly and mentions bench-suite",
            "min_score": 0.7,
            "path": "output/summary.json",
        }
    ]
    sandbox = _sandbox_with_summary(tmp_path, offline_fixture)
    judge = MockGeminiClient(text='{"score": 0.9, "rationale": "clear greeting"}')

    result = Evaluator(
        judge_client=judge,
        judge_model="gemini-2.0-flash",
    ).evaluate(task, sandbox, _execution(model_name="gemini-2.5-flash", cost_usd=0.10))

    assert result["completeness_percent"] == 100.0  # 4 of 4
    assert result["earned_roi"] == 10.0
    assert result["_rules_passed"] == 4
    assert result["_total_rules"] == 4
    # Judge used reference model, not the model under evaluation
    assert len(judge.calls) == 1
    assert judge.calls[0]["model_name"] == "gemini-2.0-flash"
    assert "bench-suite" in judge.calls[0]["prompt"].lower() or "rubric" in judge.calls[0][
        "system_instruction"
    ].lower()


def test_llm_judge_fail_when_score_below_min(
    tmp_path: Path, offline_fixture: dict
) -> None:
    from bench_suite.runner import MockGeminiClient

    task = dict(offline_fixture)
    task["validation_rules"] = list(task["validation_rules"]) + [
        {"type": "llm_judge", "rubric": "must be excellent", "min_score": 0.8}
    ]
    sandbox = _sandbox_with_summary(tmp_path, offline_fixture)
    judge = MockGeminiClient(text='{"score": 0.5, "rationale": "weak"}')

    result = Evaluator(
        judge_client=judge,
        judge_model="gemini-2.0-flash",
    ).evaluate(task, sandbox, _execution(cost_usd=0.20))

    assert result["completeness_percent"] == 75.0  # 3 of 4
    assert result["earned_roi"] == pytest.approx(10.0 * 0.75)
    assert result["cost_effectiveness_roi_per_usd"] == pytest.approx(
        result["earned_roi"] / 0.20
    )


def test_llm_judge_never_calls_model_under_evaluation(
    tmp_path: Path, offline_fixture: dict
) -> None:
    from bench_suite.runner import MockGeminiClient

    task = dict(offline_fixture)
    task["validation_rules"] = [
        {"type": "llm_judge", "rubric": "ok", "min_score": 0.5},
    ]
    sandbox = _sandbox_with_summary(tmp_path, offline_fixture)
    judge = MockGeminiClient(text='{"score": 1.0}')

    Evaluator(
        judge_client=judge,
        judge_model="gemini-2.0-flash",
    ).evaluate(
        task,
        sandbox,
        _execution(model_name="gemini-2.5-pro"),
    )

    assert judge.calls[0]["model_name"] == "gemini-2.0-flash"
    assert judge.calls[0]["model_name"] != "gemini-2.5-pro"


def test_deterministic_only_unaffected_when_no_llm_judge(
    tmp_path: Path, offline_fixture: dict
) -> None:
    """Judge client present but no llm_judge rule → no API call, full score."""
    from bench_suite.runner import MockGeminiClient

    sandbox = _sandbox_with_summary(tmp_path, offline_fixture)
    judge = MockGeminiClient(text='{"score": 0.0}')

    result = Evaluator(
        judge_client=judge,
        judge_model="gemini-2.0-flash",
    ).evaluate(offline_fixture, sandbox, _execution(cost_usd=0.05))

    assert result["completeness_percent"] == 100.0
    assert judge.calls == []


def test_parse_judge_score_helpers() -> None:
    from bench_suite.evaluator import parse_judge_score

    assert parse_judge_score('{"score": 0.85}') == 0.85
    assert parse_judge_score('Here is my rating:\n```json\n{"score": 0.7}\n```') == 0.7
    assert parse_judge_score("0.42") == 0.42
    assert parse_judge_score("not a score") == 0.0
    assert parse_judge_score('{"score": 1.5}') == 1.0  # clamp
    assert parse_judge_score('{"score": -0.2}') == 0.0  # clamp
