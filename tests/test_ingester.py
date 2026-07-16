"""Ingester seam: transcript_full.jsonl → TaskCandidate."""

from __future__ import annotations

from pathlib import Path

import pytest

from bench_suite.ingester import Ingester, TranscriptIngestError

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TRANSCRIPT = (
    REPO_ROOT
    / ".scratch/bench-suite/fixtures/transcripts"
    / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    / ".system_generated/logs/transcript_full.jsonl"
)


def test_ingest_extracts_conversation_id_timestamp_and_duration() -> None:
    candidate = Ingester().ingest(FIXTURE_TRANSCRIPT)

    assert candidate["conversation_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert candidate["timestamp"] == "2026-06-17T19:38:28Z"
    assert candidate["duration_seconds"] == 32.0
    assert candidate["transcript_path"] == str(FIXTURE_TRANSCRIPT.resolve())


def test_ingest_strips_user_request_xml_tags() -> None:
    candidate = Ingester().ingest(FIXTURE_TRANSCRIPT)

    assert candidate["user_request"].startswith("Create a Python backtesting script")
    assert "<USER_REQUEST>" not in candidate["user_request"]
    assert "</USER_REQUEST>" not in candidate["user_request"]
    assert "ADDITIONAL_METADATA" not in candidate["user_request"]


def test_ingest_derives_tool_invocations_with_result_steps() -> None:
    candidate = Ingester().ingest(FIXTURE_TRANSCRIPT)

    tools = candidate["tool_invocations"]
    assert [t["tool_name"] for t in tools] == [
        "write_to_file",
        "run_command",
        "view_file",
    ]
    assert tools[0]["step_index"] == 2
    assert tools[0]["result_step_index"] == 3
    assert tools[0]["args"]["TargetFile"] == "experiments/backtest.py"
    assert tools[1]["result_step_index"] == 5
    assert tools[2]["result_step_index"] == 7


def test_ingest_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TranscriptIngestError):
        Ingester().ingest(tmp_path / "missing.jsonl")
