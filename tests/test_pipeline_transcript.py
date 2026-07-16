"""End-to-end seam: transcript_full.jsonl → classified TaskCandidate (no eval)."""

from __future__ import annotations

from pathlib import Path

from bench_suite.pipeline import transcript_to_candidate

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPO_ROOT
    / ".scratch/bench-suite/fixtures/transcripts"
    / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    / ".system_generated/logs/transcript_full.jsonl"
)


def test_transcript_to_candidate_golden_fixture() -> None:
    classified = transcript_to_candidate(FIXTURE, repo_root=REPO_ROOT)

    assert classified["conversation_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert "<USER_REQUEST>" not in classified["user_request"]
    assert len(classified["tool_invocations"]) == 3
    assert classified["duration_seconds"] == 32.0
    assert "taxonomy" in classified
    assert "domain" in classified
    assert classified["taxonomy"]["complexity"] == "multi_tool"
    assert classified["domain"]["category"] == "Trading"
