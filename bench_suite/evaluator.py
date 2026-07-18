"""DoD evaluator: deterministic rules + optional llm_judge overlay."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

# Cap artifact text sent to the judge to keep prompts bounded.
_MAX_ARTIFACT_CHARS = 12_000

JUDGE_SYSTEM_INSTRUCTION = """You are a strict evaluation judge for coding-agent benchmarks.
Score the provided artifact against the rubric on a continuous scale from 0.0 to 1.0.
Respond with ONLY a single JSON object (no markdown fences), shape:
{"score": <float 0.0-1.0>, "rationale": "<short reason>"}
Do not reward the model under evaluation for style alone — apply the rubric literally.
"""


class JudgeClient(Protocol):
    """Minimal client surface needed for llm_judge (matches GeminiClient.generate)."""

    def generate(
        self,
        *,
        model_name: str,
        prompt: str,
        system_instruction: str,
        model_config: dict[str, Any],
    ) -> Any: ...


def parse_judge_score(text: str) -> float:
    """
    Extract a 0.0–1.0 score from a judge model response.

    Accepts JSON ``{"score": …}`` (optionally fenced), or a bare float.
    Unparseable / missing → 0.0. Out-of-range values are clamped.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return 0.0

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    # Prefer JSON object with "score"
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "score" in data:
            return _clamp01(float(data["score"]))
        if isinstance(data, (int, float)):
            return _clamp01(float(data))
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # First {...} blob containing score
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            if isinstance(data, dict) and "score" in data:
                return _clamp01(float(data["score"]))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Bare float anywhere in the text (prefer first match)
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if match:
        try:
            return _clamp01(float(match.group(0)))
        except ValueError:
            return 0.0
    return 0.0


def parse_judge_rationale(text: str) -> str:
    """Extract rationale string from judge JSON when present; else empty string."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])
    for blob in candidates:
        try:
            data = json.loads(blob)
            if isinstance(data, dict) and "rationale" in data:
                return str(data["rationale"])
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return ""


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


class Evaluator:
    """
    Score a TaskEntry against a sandbox filesystem.

    Deterministic rules always run. Optional ``llm_judge`` rules call a fixed
    reference model via ``judge_client`` (never the model under evaluation).
    Without a judge client, llm_judge rules fail closed (offline-safe).
    """

    def __init__(
        self,
        *,
        judge_client: JudgeClient | None = None,
        judge_model: str = "gemini-3.1-flash-lite",
        judge_model_config: dict[str, Any] | None = None,
    ) -> None:
        self.judge_client = judge_client
        self.judge_model = judge_model
        self.judge_model_config = dict(judge_model_config or {"temperature": 0})

    def evaluate(
        self,
        task: dict[str, Any],
        sandbox_root: Path,
        execution: dict[str, Any],
        *,
        timestamp: str | None = None,
        model_response: str | None = None,
    ) -> dict[str, Any]:
        sandbox_root = Path(sandbox_root)
        rules = task.get("validation_rules") or []
        rule_outcomes: list[dict[str, Any]] = []
        judges: list[dict[str, Any]] = []
        judge_scores: list[float] = []

        if not rules:
            completeness = 100.0
            rules_passed = 0
            total_rules = 0
        else:
            for index, rule in enumerate(rules):
                if rule.get("type") == "llm_judge":
                    outcome, judge_entry = self._check_llm_judge_detailed(
                        index, rule, sandbox_root, model_response=model_response
                    )
                    rule_outcomes.append(outcome)
                    if judge_entry is not None:
                        judges.append(judge_entry)
                    score = float(outcome["detail"].get("score") or 0.0)
                    judge_scores.append(score)
                else:
                    rule_outcomes.append(
                        self._check_rule_detailed(index, rule, sandbox_root)
                    )
            rules_passed = sum(1 for o in rule_outcomes if o["passed"])
            total_rules = len(rules)
            completeness = (rules_passed / total_rules) * 100.0

        roi_value = float(task["roi_value"])
        cost_usd = float(execution["cost_usd"])
        earned_roi = roi_value * (completeness / 100.0)
        if cost_usd == 0:
            cost_effectiveness = 0.0
        else:
            cost_effectiveness = earned_roi / cost_usd

        ts = timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )

        out: dict[str, Any] = {
            "model_name": execution["model_name"],
            "model_config": execution["model_config"],
            "completeness_percent": completeness,
            "input_tokens": int(execution["input_tokens"]),
            "output_tokens": int(execution["output_tokens"]),
            "tool_calls": int(execution["tool_calls"]),
            "cost_usd": cost_usd,
            "latency_seconds": float(execution["latency_seconds"]),
            "earned_roi": earned_roi,
            "cost_effectiveness_roi_per_usd": cost_effectiveness,
            "timestamp": ts,
            # Diagnostic fields (not required by schema but useful in tests / packs)
            "_rules_passed": rules_passed,
            "_total_rules": total_rules,
            "_rule_outcomes": rule_outcomes,
            "_judges": judges,
        }
        if judge_scores:
            out["_judge_scores"] = judge_scores
        return out

    def _check_llm_judge_detailed(
        self,
        index: int,
        rule: dict[str, Any],
        sandbox_root: Path,
        *,
        model_response: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Return (rule_outcome, judge_entry_or_None)."""
        min_score = float(rule.get("min_score", 0.7))
        if self.judge_client is None:
            outcome = {
                "index": index,
                "type": "llm_judge",
                "passed": False,
                "detail": {
                    "min_score": min_score,
                    "score": 0.0,
                    "judge_ran": False,
                    "reason": "judge_unavailable",
                },
            }
            return outcome, None

        artifact = self._artifact_for_judge(
            rule, sandbox_root, model_response=model_response
        )
        rubric = str(rule.get("rubric") or "")
        prompt = (
            f"## Rubric\n{rubric}\n\n"
            f"## Artifact under review\n{artifact}\n\n"
            "Return JSON with score in [0.0, 1.0]."
        )
        gen = self.judge_client.generate(
            model_name=self.judge_model,
            prompt=prompt,
            system_instruction=JUDGE_SYSTEM_INSTRUCTION,
            model_config=self.judge_model_config,
        )
        text = getattr(gen, "text", None) or str(gen)
        score = parse_judge_score(text)
        rationale = parse_judge_rationale(text)
        passed = score >= min_score
        # judges_index filled by pack writer when assembling judge.json order;
        # provisional index is len of judges so far — caller may rewrite.
        judge_entry = {
            "rule_index": index,
            "score": score,
            "min_score": min_score,
            "passed": passed,
            "rationale": rationale,
            "raw_response": text,
            "judge_model": self.judge_model,
            "judge_model_config": dict(self.judge_model_config),
        }
        outcome = {
            "index": index,
            "type": "llm_judge",
            "passed": passed,
            "detail": {
                "min_score": min_score,
                "score": score,
                "judge_ran": True,
                # Placeholder; pack writer sets judges_index into final judges[].
                "judges_index": 0,
            },
        }
        return outcome, judge_entry

    def _check_llm_judge(
        self,
        rule: dict[str, Any],
        sandbox_root: Path,
        *,
        model_response: str | None = None,
    ) -> tuple[bool, float]:
        """Return (passed, score). Score is 0.0 when the judge cannot run."""
        outcome, _ = self._check_llm_judge_detailed(
            0, rule, sandbox_root, model_response=model_response
        )
        return bool(outcome["passed"]), float(outcome["detail"].get("score") or 0.0)

    def _artifact_for_judge(
        self,
        rule: dict[str, Any],
        sandbox_root: Path,
        *,
        model_response: str | None = None,
    ) -> str:
        """Build the text blob the judge scores (path, sandbox files, model response)."""
        parts: list[str] = []
        path_str = rule.get("path")
        if path_str:
            path = self._resolve(str(path_str), sandbox_root)
            if not path.is_file():
                parts.append(f"(missing file: {path_str})")
            else:
                parts.append(self._read_capped(path))
        else:
            # No path: summarize relative files under the sandbox
            if not sandbox_root.is_dir():
                parts.append("(empty sandbox)")
            else:
                chunks: list[str] = []
                total = 0
                for path in sorted(sandbox_root.rglob("*")):
                    if not path.is_file():
                        continue
                    rel = path.relative_to(sandbox_root).as_posix()
                    body = self._read_capped(path, remaining=_MAX_ARTIFACT_CHARS - total)
                    chunk = f"### {rel}\n{body}\n"
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= _MAX_ARTIFACT_CHARS:
                        chunks.append("… (truncated)")
                        break
                parts.append("\n".join(chunks) if chunks else "(empty sandbox)")

        if model_response:
            capped = model_response[:_MAX_ARTIFACT_CHARS]
            if len(model_response) > _MAX_ARTIFACT_CHARS:
                capped += "\n… (truncated)"
            parts.append(f"## Model response\n{capped}")

        return "\n\n".join(parts)

    def _read_capped(self, path: Path, *, remaining: int | None = None) -> str:
        limit = _MAX_ARTIFACT_CHARS if remaining is None else max(0, remaining)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"(unreadable: {exc})"
        if len(text) > limit:
            return text[:limit] + "\n… (truncated)"
        return text

    def _check_rule_detailed(
        self, index: int, rule: dict[str, Any], sandbox_root: Path
    ) -> dict[str, Any]:
        rule_type = rule.get("type", "unknown")
        if rule_type == "file_exists":
            path = str(rule.get("path") or "")
            ok = self._resolve(path, sandbox_root).exists() if path else False
            detail: dict[str, Any] = {"path": path}
            if not ok:
                detail["reason"] = "missing"
            return {"index": index, "type": rule_type, "passed": ok, "detail": detail}

        if rule_type == "file_contains":
            path = str(rule.get("path") or "")
            text = str(rule.get("text") or "")
            detail = {"path": path, "text": text}
            resolved = self._resolve(path, sandbox_root)
            if not resolved.is_file():
                detail["reason"] = "missing_file"
                return {"index": index, "type": rule_type, "passed": False, "detail": detail}
            try:
                body = resolved.read_text(encoding="utf-8")
            except OSError:
                detail["reason"] = "unreadable"
                return {"index": index, "type": rule_type, "passed": False, "detail": detail}
            if text not in body:
                detail["reason"] = "substring_missing"
                return {"index": index, "type": rule_type, "passed": False, "detail": detail}
            return {"index": index, "type": rule_type, "passed": True, "detail": detail}

        if rule_type == "json_field_value":
            path = str(rule.get("path") or "")
            field = str(rule.get("field") or "")
            expected = rule.get("expected")
            detail = {"path": path, "field": field, "expected": expected}
            resolved = self._resolve(path, sandbox_root)
            if not resolved.is_file():
                detail["reason"] = "missing_file"
                return {"index": index, "type": rule_type, "passed": False, "detail": detail}
            try:
                data = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeError):
                detail["reason"] = "invalid_json"
                return {"index": index, "type": rule_type, "passed": False, "detail": detail}
            if not isinstance(data, dict) or field not in data:
                detail["reason"] = "field_missing"
                return {"index": index, "type": rule_type, "passed": False, "detail": detail}
            actual = data[field]
            if actual != expected:
                detail["reason"] = "field_mismatch"
                detail["actual"] = actual
                return {"index": index, "type": rule_type, "passed": False, "detail": detail}
            return {"index": index, "type": rule_type, "passed": True, "detail": detail}

        # Unknown future rule types: fail closed with empty detail keys beyond type.
        return {
            "index": index,
            "type": rule_type,
            "passed": False,
            "detail": {"reason": "unknown_rule_type"},
        }

    def _check_rule(self, rule: dict[str, Any], sandbox_root: Path) -> bool:
        rule_type = rule["type"]
        if rule_type == "llm_judge":
            ok, _ = self._check_llm_judge(rule, sandbox_root, model_response=None)
            return ok
        return bool(self._check_rule_detailed(0, rule, sandbox_root)["passed"])

    def _resolve(self, path_str: str, sandbox_root: Path) -> Path:
        path = Path(path_str)
        if path.is_absolute():
            return path
        return (sandbox_root / path).resolve()


def strip_diagnostic_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Return EvaluationResult without private diagnostic keys."""
    return {k: v for k, v in result.items() if not k.startswith("_")}
