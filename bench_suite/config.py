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
    # Fixed judge model — never the model under evaluation (conflict of interest).
    # Prefer a cheap stable model distinct from default_model.
    "llm_judge_reference_model": "gemini-3.1-flash-lite",
    "dynamic_growth_trigger": "manual",
    "chartjs_cdn": "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
    # gemini-2.5-flash is no longer available to new API users (404 NOT_FOUND).
    "default_model": "gemini-3.5-flash",
    "default_model_config": {"thinking_level": "high"},
    "gemini_pricing": {**DEFAULT_PRICING, "default": {"input_per_mtok": 0.25, "output_per_mtok": 1.50}},
    "paths": {
        "data_root": ".scratch/bench-suite",
        "schema": ".scratch/bench-suite/task-schema.json",
        "dataset_tasks": ".scratch/bench-suite/dataset/tasks",
        "dataset_results": ".scratch/bench-suite/dataset/results",
        "registry": ".scratch/bench-suite/registry.json",
        "leaderboard": ".scratch/bench-suite/leaderboard.md",
        "dashboard_html": ".scratch/bench-suite/index.html",
        "pending_review": ".scratch/bench-suite/pending-review",
        "classifier_rules": ".scratch/bench-suite/classifier_rules.json",
        "runs": ".scratch/bench-suite/runs",
    },
}

DEFAULT_RUN_REVIEW_CAPS: dict[str, int] = {
    "max_response_bytes": 1_048_576,
    "max_file_bytes": 262_144,
    "max_files": 100,
    "max_pack_bytes": 8_388_608,
}

# Soft size caps for Run Review Pack write only (evaluation still sees full data).
DEFAULT_CONFIG["run_review_caps"] = dict(DEFAULT_RUN_REVIEW_CAPS)


def resolve_run_review_caps(
    config: dict[str, Any] | None = None,
    *,
    overrides: dict[str, int | None] | None = None,
    caps_off: bool = False,
) -> dict[str, int | None]:
    """
    Effective pack soft-cap map.

    Missing config keys fall back to defaults. ``caps_off`` forces all four to
    ``null`` (no truncation). ``overrides`` replace individual keys.
    """
    if caps_off:
        return {
            "max_response_bytes": None,
            "max_file_bytes": None,
            "max_files": None,
            "max_pack_bytes": None,
        }
    base = dict(DEFAULT_RUN_REVIEW_CAPS)
    if config:
        raw = config.get("run_review_caps") or {}
        for key in DEFAULT_RUN_REVIEW_CAPS:
            if key in raw and raw[key] is not None:
                base[key] = int(raw[key])
    if overrides:
        for key, value in overrides.items():
            if key not in DEFAULT_RUN_REVIEW_CAPS:
                raise ValueError(f"Unknown run review cap: {key}")
            base[key] = value if value is None else int(value)
    return base  # type: ignore[return-value]


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
