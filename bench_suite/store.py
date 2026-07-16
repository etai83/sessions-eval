"""Dataset store: load, save, and schema-validate TaskEntry documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator


class SchemaValidationError(ValueError):
    """Raised when a TaskEntry fails schema validation."""


class DatasetStore:
    def __init__(self, tasks_dir: Path, schema_path: Path) -> None:
        self.tasks_dir = Path(tasks_dir)
        self.schema_path = Path(schema_path)
        self._validator = self._load_validator()

    def _load_validator(self) -> Draft7Validator:
        with self.schema_path.open(encoding="utf-8") as f:
            schema = json.load(f)
        return Draft7Validator(schema)

    def validate(self, task: dict[str, Any]) -> None:
        errors = sorted(self._validator.iter_errors(task), key=lambda e: list(e.path))
        if errors:
            messages = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
            raise SchemaValidationError("; ".join(messages))

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def load(self, task_id: str) -> dict[str, Any]:
        path = self.task_path(task_id)
        with path.open(encoding="utf-8") as f:
            task = json.load(f)
        self.validate(task)
        return task

    def load_path(self, path: Path) -> dict[str, Any]:
        with Path(path).open(encoding="utf-8") as f:
            task = json.load(f)
        self.validate(task)
        return task

    def save(self, task: dict[str, Any]) -> Path:
        self.validate(task)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        path = self.task_path(task["task_id"])
        with path.open("w", encoding="utf-8") as f:
            json.dump(task, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return path

    def list_tasks(self) -> list[dict[str, Any]]:
        if not self.tasks_dir.is_dir():
            return []
        tasks: list[dict[str, Any]] = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            tasks.append(self.load_path(path))
        return tasks
