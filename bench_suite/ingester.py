"""Ingester: transcript_full.jsonl → TaskCandidate (no labels yet)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# Tool-result step types emitted by Antigravity after PLANNER_RESPONSE tool_calls.
_TOOL_RESULT_TYPES = frozenset(
    {
        "VIEW_FILE",
        "LIST_DIRECTORY",
        "RUN_COMMAND",
        "CODE_ACTION",
        "GENERIC",
        "ASK_QUESTION",
        "INVOKE_SUBAGENT",
    }
)

_USER_REQUEST_RE = re.compile(
    r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>",
    re.DOTALL | re.IGNORECASE,
)


class TranscriptIngestError(ValueError):
    """Raised when a transcript cannot be parsed into a TaskCandidate."""


class Ingester:
    """Read one transcript_full.jsonl and extract a raw TaskCandidate."""

    def ingest(self, transcript_path: Path | str) -> dict[str, Any]:
        path = Path(transcript_path).expanduser().resolve()
        if not path.is_file():
            raise TranscriptIngestError(f"Transcript not found: {path}")
        if path.name != "transcript_full.jsonl":
            raise TranscriptIngestError(
                f"Expected transcript_full.jsonl, got {path.name} "
                "(compact transcript.jsonl double-escapes tool args)"
            )

        steps = self._read_steps(path)
        if not steps:
            raise TranscriptIngestError(f"Empty transcript: {path}")

        user_step = self._first_user_input(steps)
        user_request = strip_user_request_xml(user_step.get("content") or "")
        if not user_request.strip():
            raise TranscriptIngestError(f"No user request content in {path}")

        tool_invocations = extract_tool_invocations(steps)
        duration = session_duration_seconds(steps)
        conversation_id = conversation_id_from_path(path)

        return {
            "conversation_id": conversation_id,
            "timestamp": user_step["created_at"],
            "user_request": user_request,
            "tool_invocations": tool_invocations,
            "duration_seconds": duration,
            "transcript_path": str(path),
        }

    def _read_steps(self, path: Path) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        steps.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise TranscriptIngestError(
                            f"Invalid JSON on line {line_no} of {path}: {exc}"
                        ) from exc
        except OSError as exc:
            raise TranscriptIngestError(f"Cannot read transcript {path}: {exc}") from exc
        return steps

    def _first_user_input(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        for step in steps:
            if step.get("source") == "USER_EXPLICIT" and step.get("type") == "USER_INPUT":
                return step
        raise TranscriptIngestError("No USER_INPUT step with source=USER_EXPLICIT found")


def strip_user_request_xml(content: str) -> str:
    """Extract text inside <USER_REQUEST> tags, or return content stripped of wrappers."""
    match = _USER_REQUEST_RE.search(content)
    if match:
        return match.group(1).strip()
    # Fallback: drop known wrapper tags if present without a full pair.
    cleaned = re.sub(r"</?USER_REQUEST>", "", content, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return cleaned.strip()


def conversation_id_from_path(path: Path) -> str:
    """Infer conversation UUID from .../<conv-id>/.system_generated/logs/transcript_full.jsonl."""
    parts = path.parts
    for i, part in enumerate(parts):
        if part == ".system_generated" and i > 0:
            return parts[i - 1]
    # Fallback: parent of logs → system_generated → conv dir
    try:
        return path.parent.parent.parent.name
    except IndexError as exc:
        raise TranscriptIngestError(f"Cannot infer conversation_id from path: {path}") from exc


def extract_tool_invocations(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Collect tool_calls from PLANNER_RESPONSE steps and pair each with the next
    sequential MODEL tool-result step (no tool_call_id in the format).
    """
    invocations: list[dict[str, Any]] = []
    # Next step index to consider when looking for tool results (shared cursor).
    result_cursor = 0
    for i, step in enumerate(steps):
        if step.get("type") != "PLANNER_RESPONSE" or not step.get("tool_calls"):
            continue
        # Results for this planner call must start after the planner step itself.
        result_cursor = max(result_cursor, i + 1)
        for call in step["tool_calls"]:
            result_idx = None
            while result_cursor < len(steps):
                candidate = steps[result_cursor]
                result_cursor += 1
                if (
                    candidate.get("source") == "MODEL"
                    and candidate.get("type") in _TOOL_RESULT_TYPES
                ):
                    result_idx = candidate.get("step_index")
                    break
            invocations.append(
                {
                    "step_index": step.get("step_index"),
                    "tool_name": call.get("name") or "",
                    "args": call.get("args") if isinstance(call.get("args"), dict) else {},
                    "result_step_index": result_idx,
                }
            )
    return invocations


def session_duration_seconds(steps: list[dict[str, Any]]) -> float:
    first = steps[0].get("created_at")
    last = steps[-1].get("created_at")
    if not first or not last:
        return 0.0
    start = _parse_iso(first)
    end = _parse_iso(last)
    return max(0.0, (end - start).total_seconds())


def _parse_iso(value: str) -> datetime:
    # Accept trailing Z
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
