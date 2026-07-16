"""Classifier: deterministic keyword rules → taxonomy + domain labels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Classifier:
    """
    Assign taxonomy + domain labels to a TaskCandidate.

    Keyword rules map user_request text → output_type, intent, category, subcategory.
    Complexity is derived deterministically from tool_invocations (count + subagent tools).
    """

    def __init__(self, rules: dict[str, Any]) -> None:
        self.defaults: dict[str, Any] = dict(rules.get("defaults") or {})
        self.rules: list[dict[str, Any]] = list(rules.get("rules") or [])
        complexity = rules.get("complexity") or {}
        self.single_step_max_tools = int(complexity.get("single_step_max_tools", 2))
        self.multi_agent_tools = {
            name.lower() for name in (complexity.get("multi_agent_tools") or ["invoke_subagent"])
        }

    @classmethod
    def from_rules_path(cls, path: Path | str) -> Classifier:
        with Path(path).open(encoding="utf-8") as f:
            return cls(json.load(f))

    def classify(self, candidate: dict[str, Any]) -> dict[str, Any]:
        text = (candidate.get("user_request") or "").lower()
        labels = {
            "output_type": self.defaults.get("output_type", "code"),
            "intent": self.defaults.get("intent", "generate"),
            "category": self.defaults.get("category", "General"),
            "subcategory": self.defaults.get("subcategory", "Miscellaneous"),
        }

        for rule in self.rules:
            patterns = rule.get("match") or []
            if not any(str(p).lower() in text for p in patterns):
                continue
            for key in ("output_type", "intent", "category", "subcategory"):
                if key in rule:
                    labels[key] = rule[key]

        complexity = self._complexity(candidate.get("tool_invocations") or [])

        classified = dict(candidate)
        classified["taxonomy"] = {
            "output_type": labels["output_type"],
            "complexity": complexity,
            "intent": labels["intent"],
        }
        classified["domain"] = {
            "category": labels["category"],
            "subcategory": labels["subcategory"],
        }
        return classified

    def _complexity(self, tool_invocations: list[dict[str, Any]]) -> str:
        names = [(t.get("tool_name") or "").lower() for t in tool_invocations]
        if any(name in self.multi_agent_tools for name in names):
            return "multi_agent"
        if len(tool_invocations) <= self.single_step_max_tools:
            return "single_step"
        return "multi_tool"
