"""Duplicate-prevention registry: model×config × task_id tracking."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def registry_key(
    model_name: str,
    model_config: dict[str, Any],
    *,
    truncate_hex: int = 8,
    algorithm: str = "sha256",
) -> str:
    """Build registry key: model_name:hash(sorted_json(config))[:truncate_hex]."""
    payload = json.dumps(model_config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if algorithm != "sha256":
        raise ValueError(f"Unsupported registry hash algorithm: {algorithm}")
    digest = hashlib.sha256(payload).hexdigest()[:truncate_hex]
    return f"{model_name}:{digest}"


class Registry:
    def __init__(
        self,
        path: Path,
        *,
        truncate_hex: int = 8,
        algorithm: str = "sha256",
    ) -> None:
        self.path = Path(path)
        self.truncate_hex = truncate_hex
        self.algorithm = algorithm
        self._data: dict[str, list[str]] = {}
        if self.path.is_file():
            with self.path.open(encoding="utf-8") as f:
                raw = json.load(f)
            self._data = {k: list(v) for k, v in raw.items()}

    def _key(self, model_name: str, model_config: dict[str, Any]) -> str:
        return registry_key(
            model_name,
            model_config,
            truncate_hex=self.truncate_hex,
            algorithm=self.algorithm,
        )

    def has_run(self, model_name: str, model_config: dict[str, Any], task_id: str) -> bool:
        key = self._key(model_name, model_config)
        return task_id in self._data.get(key, [])

    def record(self, model_name: str, model_config: dict[str, Any], task_id: str) -> None:
        key = self._key(model_name, model_config)
        tasks = self._data.setdefault(key, [])
        if task_id not in tasks:
            tasks.append(task_id)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
            f.write("\n")
