"""Load suite configuration with open-question defaults from the spec."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bench_suite.runner import DEFAULT_PRICING

DEFAULT_CONFIG: dict[str, Any] = {
    "sandbox_isolation": "temp_dir",
    "registry_hash": {
        "algorithm": "sha256",
        "truncate_hex": 8,
        "json_sort_keys": True,
        "json_separators": [",", ":"],
    },
    "llm_judge_reference_model": "gemini-2.0-flash",
    "dynamic_growth_trigger": "manual",
    "chartjs_cdn": "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
    "default_model": "gemini-2.5-flash",
    "default_model_config": {"thinking_level": "high"},
    "gemini_pricing": {**DEFAULT_PRICING, "default": {"input_per_mtok": 0.15, "output_per_mtok": 0.60}},
    "paths": {
        "data_root": ".scratch/bench-suite",
        "schema": ".scratch/bench-suite/task-schema.json",
        "dataset_tasks": ".scratch/bench-suite/dataset/tasks",
        "registry": ".scratch/bench-suite/registry.json",
        "leaderboard": ".scratch/bench-suite/leaderboard.md",
        "dashboard_html": ".scratch/bench-suite/index.html",
        "pending_review": ".scratch/bench-suite/pending-review",
        "classifier_rules": ".scratch/bench-suite/classifier_rules.json",
    },
}


def load_config(path: Path | None = None, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Load config JSON and merge onto defaults. Paths are resolved against repo_root."""
    root = (repo_root or Path.cwd()).resolve()
    config_path = path or (root / ".scratch" / "bench-suite" / "config.json")
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as f:
            on_disk = json.load(f)
        _deep_merge(merged, on_disk)
    merged["_repo_root"] = str(root)
    merged["_resolved_paths"] = {
        key: str((root / rel).resolve()) if not Path(rel).is_absolute() else rel
        for key, rel in merged["paths"].items()
    }
    return merged


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
