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
