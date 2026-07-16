"""Classifier seam: TaskCandidate + keyword rules → taxonomy + domain labels."""

from __future__ import annotations

from pathlib import Path

import pytest

from bench_suite.classifier import Classifier
from bench_suite.ingester import Ingester

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = REPO_ROOT / ".scratch/bench-suite/classifier_rules.json"
TRADING_TRANSCRIPT = (
    REPO_ROOT
    / ".scratch/bench-suite/fixtures/transcripts"
    / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    / ".system_generated/logs/transcript_full.jsonl"
)
RESEARCH_TRANSCRIPT = (
    REPO_ROOT
    / ".scratch/bench-suite/fixtures/transcripts"
    / "11111111-2222-3333-4444-555555555555"
    / ".system_generated/logs/transcript_full.jsonl"
)


def test_classify_trading_backtest_fixture() -> None:
    candidate = Ingester().ingest(TRADING_TRANSCRIPT)
    classified = Classifier.from_rules_path(RULES_PATH).classify(candidate)

    assert classified["taxonomy"]["output_type"] == "code"
    assert classified["taxonomy"]["complexity"] == "multi_tool"  # 3 tools
    assert classified["taxonomy"]["intent"] == "debug"  # "fix any import bugs"
    assert classified["domain"]["category"] == "Trading"
    assert classified["domain"]["subcategory"] == "Backtesting"
    # Original extract fields preserved
    assert classified["conversation_id"] == candidate["conversation_id"]
    assert classified["user_request"] == candidate["user_request"]


def test_classify_research_architecture_is_multi_agent_plan() -> None:
    candidate = Ingester().ingest(RESEARCH_TRANSCRIPT)
    classified = Classifier.from_rules_path(RULES_PATH).classify(candidate)

    assert classified["taxonomy"]["output_type"] == "plan_or_spec"
    assert classified["taxonomy"]["complexity"] == "multi_agent"
    assert classified["taxonomy"]["intent"] == "research"
    assert classified["domain"]["category"] == "Agent Meta"


def test_classify_defaults_when_no_keywords_match() -> None:
    candidate = {
        "conversation_id": "00000000-0000-0000-0000-000000000000",
        "timestamp": "2026-01-01T00:00:00Z",
        "user_request": "hello world please do the thing",
        "tool_invocations": [],
        "duration_seconds": 1.0,
        "transcript_path": "/tmp/x.jsonl",
    }
    classified = Classifier.from_rules_path(RULES_PATH).classify(candidate)

    assert classified["taxonomy"]["output_type"] == "code"
    assert classified["taxonomy"]["complexity"] == "single_step"
    assert classified["taxonomy"]["intent"] == "generate"
    assert classified["domain"]["category"] == "General"
    assert classified["domain"]["subcategory"] == "Miscellaneous"


def test_classify_single_step_with_one_tool() -> None:
    candidate = {
        "conversation_id": "00000000-0000-0000-0000-000000000000",
        "timestamp": "2026-01-01T00:00:00Z",
        "user_request": "create a new file foo.py",
        "tool_invocations": [
            {"step_index": 1, "tool_name": "write_to_file", "args": {}, "result_step_index": 2}
        ],
        "duration_seconds": 5.0,
        "transcript_path": "/tmp/x.jsonl",
    }
    classified = Classifier.from_rules_path(RULES_PATH).classify(candidate)
    assert classified["taxonomy"]["complexity"] == "single_step"
