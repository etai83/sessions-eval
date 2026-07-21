"""Dataset store: TaskEntry definitions and separate evaluation history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator


class SchemaValidationError(ValueError):
    """Raised when a TaskEntry definition or EvaluationResult fails validation."""


class DatasetStore:
    """
    Two physical stores behind one join-oriented interface:

    - ``tasks_dir/<task_id>.json`` — TaskEntry definition (immutable after authoring)
    - ``results_dir/<task_id>.jsonl`` — append-only EvaluationResult history

    ``load`` / ``list_tasks`` join history under ``evaluation_results`` for ranking
    and dashboard consumers. Definition files never hold that array after save or
    migration.
    """

    def __init__(
        self,
        tasks_dir: Path,
        schema_path: Path,
        results_dir: Path | None = None,
        result_schema_path: Path | None = None,
    ) -> None:
        self.tasks_dir = Path(tasks_dir)
        self.schema_path = Path(schema_path)
        self.results_dir = (
            Path(results_dir) if results_dir is not None else self.tasks_dir.parent / "results"
        )
        self.result_schema_path = (
            Path(result_schema_path)
            if result_schema_path is not None
            else self.schema_path.with_name("evaluation-result-schema.json")
        )
        self._validator = self._load_validator(self.schema_path)
        self._result_validator = self._load_result_validator()

    @staticmethod
    def _load_validator(schema_path: Path) -> Draft7Validator:
        with schema_path.open(encoding="utf-8") as f:
            schema = json.load(f)
        return Draft7Validator(schema)

    def _load_result_validator(self) -> Draft7Validator:
        if self.result_schema_path.is_file():
            with self.result_schema_path.open(encoding="utf-8") as f:
                schema = json.load(f)
            return Draft7Validator(schema)
        # Fallback if the result schema file is absent (minimal install / old trees).
        return Draft7Validator(
            {
                "type": "object",
                "properties": {
                    "model_name": {"type": "string"},
                    "model_config": {"type": "object", "additionalProperties": True},
                    "completeness_percent": {"type": "number", "minimum": 0, "maximum": 100},
                    "input_tokens": {"type": "integer"},
                    "output_tokens": {"type": "integer"},
                    "tool_calls": {"type": "integer"},
                    "cost_usd": {"type": "number"},
                    "latency_seconds": {"type": "number"},
                    "earned_roi": {"type": "number"},
                    "cost_effectiveness_roi_per_usd": {"type": "number"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "run_id": {"type": "string"},
                    "run_pack_path": {"type": "string"},
                },
                "required": [
                    "model_name",
                    "model_config",
                    "completeness_percent",
                    "input_tokens",
                    "output_tokens",
                    "tool_calls",
                    "cost_usd",
                    "latency_seconds",
                    "earned_roi",
                    "cost_effectiveness_roi_per_usd",
                    "timestamp",
                ],
            }
        )

    @staticmethod
    def _split_definition(task: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
        embedded = task.get("evaluation_results")
        definition = {k: v for k, v in task.items() if k != "evaluation_results"}
        if embedded is None:
            return definition, None
        if not isinstance(embedded, list):
            raise SchemaValidationError("evaluation_results must be an array when present")
        return definition, list(embedded)

    def validate(self, task: dict[str, Any]) -> None:
        definition, _ = self._split_definition(task)
        errors = sorted(self._validator.iter_errors(definition), key=lambda e: list(e.path))
        if errors:
            messages = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
            raise SchemaValidationError("; ".join(messages))

    def validate_result(self, result: dict[str, Any]) -> None:
        errors = sorted(self._result_validator.iter_errors(result), key=lambda e: list(e.path))
        if errors:
            messages = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
            raise SchemaValidationError("; ".join(messages))

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def results_path(self, task_id: str) -> Path:
        return self.results_dir / f"{task_id}.jsonl"

    def load(self, task_id: str, *, with_results: bool = True) -> dict[str, Any]:
        path = self.task_path(task_id)
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
        definition, embedded = self._split_definition(raw)
        self.validate(definition)
        if not with_results:
            return definition
        joined = dict(definition)
        joined["evaluation_results"] = self._resolve_results(task_id, embedded)
        return joined

    def load_path(self, path: Path, *, with_results: bool = False) -> dict[str, Any]:
        with Path(path).open(encoding="utf-8") as f:
            raw = json.load(f)
        definition, embedded = self._split_definition(raw)
        self.validate(definition)
        if not with_results:
            return definition
        task_id = str(definition.get("task_id") or "")
        joined = dict(definition)
        # Prefer results store when this path is the managed TaskEntry definition.
        if task_id and path.resolve() == self.task_path(task_id).resolve():
            joined["evaluation_results"] = self._resolve_results(task_id, embedded)
        else:
            joined["evaluation_results"] = list(embedded or [])
        return joined

    def save(self, task: dict[str, Any]) -> Path:
        """Persist TaskEntry definition only. Never writes evaluation history."""
        definition, _ = self._split_definition(task)
        self.validate(definition)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        path = self.task_path(definition["task_id"])
        self._write_definition(path, definition)
        return path

    def list_results(self, task_id: str) -> list[dict[str, Any]]:
        path = self.results_path(task_id)
        embedded: list[dict[str, Any]] | None = None
        task_def_path = self.task_path(task_id)
        if task_def_path.is_file():
            with task_def_path.open(encoding="utf-8") as f:
                raw = json.load(f)
            _, embedded = self._split_definition(raw)
        if path.is_file():
            return self._resolve_results(task_id, embedded)
        return list(embedded or [])

    def append_result(self, task_id: str, result: dict[str, Any]) -> Path:
        """Append one EvaluationResult to the task's JSONL history."""
        self.validate_result(result)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_path(task_id)
        # If history still lives only in the definition, materialize it first so
        # append does not drop legacy rows.
        if not path.is_file():
            legacy = self.list_results(task_id)
            if legacy:
                self._write_jsonl(path, legacy)
                self._strip_embedded_results(task_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False))
            f.write("\n")
        return path

    def list_tasks(self, *, with_results: bool = True) -> list[dict[str, Any]]:
        if not self.tasks_dir.is_dir():
            return []
        tasks: list[dict[str, Any]] = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            with path.open(encoding="utf-8") as f:
                raw = json.load(f)
            definition, embedded = self._split_definition(raw)
            self.validate(definition)
            if with_results:
                task = dict(definition)
                task["evaluation_results"] = self._resolve_results(
                    definition["task_id"], embedded
                )
                tasks.append(task)
            else:
                tasks.append(definition)
        return tasks

    def migrate_embedded_results(self) -> dict[str, int]:
        """
        Move embedded ``evaluation_results`` out of TaskEntry definitions into
        JSONL history. Idempotent. When both embedded rows and a non-empty JSONL
        exist, merges without dropping either side (JSONL order first, then
        embedded-only rows), then strips the definition.
        """
        tasks_migrated = 0
        results_moved = 0
        if not self.tasks_dir.is_dir():
            return {"tasks_migrated": 0, "results_moved": 0}

        self.results_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.tasks_dir.glob("*.json")):
            with path.open(encoding="utf-8") as f:
                raw = json.load(f)
            definition, embedded = self._split_definition(raw)
            if "evaluation_results" not in raw:
                continue

            task_id = definition["task_id"]
            out = self.results_path(task_id)
            external = self._read_jsonl(out) if out.is_file() else []
            merged = self._merge_results(external, list(embedded or []))
            for row in merged:
                self.validate_result(row)

            if merged:
                self._write_jsonl(out, merged)
            elif out.is_file() and out.stat().st_size == 0:
                out.unlink(missing_ok=True)

            self.validate(definition)
            self._write_definition(path, definition)
            tasks_migrated += 1
            # Count newly externalized rows (embedded that weren't already external).
            if embedded:
                results_moved += max(0, len(merged) - len(external))

        return {"tasks_migrated": tasks_migrated, "results_moved": results_moved}

    def _resolve_results(
        self,
        task_id: str,
        embedded: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        path = self.results_path(task_id)
        external = self._read_jsonl(path) if path.is_file() else []
        if external and embedded:
            return self._merge_results(external, embedded)
        if external:
            return external
        return list(embedded or [])

    @staticmethod
    def _result_identity(row: dict[str, Any]) -> tuple[Any, ...]:
        run_id = row.get("run_id")
        if run_id:
            return ("run_id", run_id)
        return (
            "metrics",
            row.get("model_name"),
            json.dumps(row.get("model_config") or {}, sort_keys=True, separators=(",", ":")),
            row.get("timestamp"),
            row.get("completeness_percent"),
            row.get("cost_usd"),
            row.get("run_pack_path"),
        )

    def _merge_results(
        self,
        primary: list[dict[str, Any]],
        secondary: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Preserve primary order; append secondary rows not already present."""
        seen = {self._result_identity(row) for row in primary}
        merged = list(primary)
        for row in secondary:
            key = self._result_identity(row)
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
        return merged

    def _strip_embedded_results(self, task_id: str) -> None:
        path = self.task_path(task_id)
        if not path.is_file():
            return
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
        if "evaluation_results" not in raw:
            return
        definition, _ = self._split_definition(raw)
        self.validate(definition)
        self._write_definition(path, definition)

    @staticmethod
    def _write_definition(path: Path, definition: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(definition, f, indent=2, ensure_ascii=False)
            f.write("\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SchemaValidationError(
                        f"{path}:{line_no}: invalid JSONL row: {exc}"
                    ) from exc
                if not isinstance(row, dict):
                    raise SchemaValidationError(
                        f"{path}:{line_no}: evaluation result must be a JSON object"
                    )
                rows.append(row)
        return rows

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False))
                f.write("\n")


def dataset_store_from_paths(paths: dict[str, str]) -> DatasetStore:
    """Build a DatasetStore from config ``_resolved_paths``."""
    result_schema = Path(paths["schema"]).with_name("evaluation-result-schema.json")
    return DatasetStore(
        Path(paths["dataset_tasks"]),
        Path(paths["schema"]),
        results_dir=Path(paths["dataset_results"]),
        result_schema_path=result_schema if result_schema.is_file() else None,
    )
