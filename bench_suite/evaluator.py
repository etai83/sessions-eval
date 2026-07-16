"""Deterministic DoD evaluator and scoring formulas."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Evaluator:
    """Score a TaskEntry against a sandbox filesystem using deterministic rules."""

    def evaluate(
        self,
        task: dict[str, Any],
        sandbox_root: Path,
        execution: dict[str, Any],
        *,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        sandbox_root = Path(sandbox_root)
        rules = task.get("validation_rules") or []
        if not rules:
            completeness = 100.0
            rules_passed = 0
            total_rules = 0
        else:
            results = [self._check_rule(rule, sandbox_root) for rule in rules]
            rules_passed = sum(1 for ok in results if ok)
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

        return {
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
            # Diagnostic fields (not required by schema but useful in tests)
            "_rules_passed": rules_passed,
            "_total_rules": total_rules,
        }

    def _check_rule(self, rule: dict[str, Any], sandbox_root: Path) -> bool:
        rule_type = rule["type"]
        if rule_type == "llm_judge":
            # Offline / ticket 09: no Gemini API. Ticket 14 will implement this.
            return False
        if rule_type == "file_exists":
            return self._resolve(rule["path"], sandbox_root).exists()
        if rule_type == "file_contains":
            path = self._resolve(rule["path"], sandbox_root)
            if not path.is_file():
                return False
            return rule["text"] in path.read_text(encoding="utf-8")
        if rule_type == "json_field_value":
            path = self._resolve(rule["path"], sandbox_root)
            if not path.is_file():
                return False
            data = json.loads(path.read_text(encoding="utf-8"))
            try:
                return data[rule["field"]] == rule["expected"]
            except (KeyError, TypeError):
                return False
        raise ValueError(f"Unknown validation rule type: {rule_type}")

    def _resolve(self, path_str: str, sandbox_root: Path) -> Path:
        path = Path(path_str)
        if path.is_absolute():
            return path
        return (sandbox_root / path).resolve()


def strip_diagnostic_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Return EvaluationResult without private diagnostic keys."""
    return {k: v for k, v in result.items() if not k.startswith("_")}
