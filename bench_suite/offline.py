"""Offline golden path: fixture task → evaluate → registry → dashboard (no Gemini)."""

from __future__ import annotations

import json
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Any

from bench_suite.config import load_config, resolve_run_review_caps
from bench_suite.dashboard import DashboardGenerator
from bench_suite.evaluator import Evaluator
from bench_suite.registry import Registry
from bench_suite.run_review import attach_pack_to_result, write_run_review_pack
from bench_suite.sandbox import apply_setup_steps
from bench_suite.store import dataset_store_from_paths


FAKE_EXECUTION = {
    "model_name": "gemini-3.5-flash",
    "model_config": {"thinking_level": "high"},
    "input_tokens": 1000,
    "output_tokens": 200,
    "tool_calls": 3,
    "cost_usd": 0.05,
    "latency_seconds": 2.5,
}


def prepare_passing_sandbox(sandbox: Path) -> None:
    """Write files that satisfy the offline golden fixture DoD rules."""
    out = sandbox / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps({"status": "ok", "greeting": "Hello bench-suite"}, indent=2) + "\n",
        encoding="utf-8",
    )


def run_offline_golden_path(
    *,
    repo_root: Path | None = None,
    fixture_path: Path | None = None,
    sandbox_dir: Path | None = None,
    fake_execution: dict[str, Any] | None = None,
    review_cap_overrides: dict[str, int | None] | None = None,
    review_caps_off: bool = False,
) -> dict[str, Any]:
    """
    End-to-end offline path:
    load fixture → validate → prepare sandbox → evaluate → write pack →
    save task → record registry → generate dashboard.
    """
    root = (repo_root or Path.cwd()).resolve()
    config = load_config(repo_root=root)
    paths = config["_resolved_paths"]

    store = dataset_store_from_paths(paths)
    fixture = Path(fixture_path) if fixture_path else root / ".scratch/bench-suite/fixtures/offline_golden_task.json"
    task = store.load_path(fixture)

    own_sandbox = sandbox_dir is None
    sandbox = Path(sandbox_dir) if sandbox_dir else Path(tempfile.mkdtemp(prefix="bench-suite-"))
    sandbox.mkdir(parents=True, exist_ok=True)
    try:
        apply_setup_steps(task, sandbox, allow_commands=False)
        prepare_passing_sandbox(sandbox)

        execution = dict(fake_execution or FAKE_EXECUTION)
        hash_cfg = config.get("registry_hash") or {}
        registry = Registry(
            Path(paths["registry"]),
            truncate_hex=int(hash_cfg.get("truncate_hex", 8)),
            algorithm=str(hash_cfg.get("algorithm", "sha256")),
        )

        already_run = registry.has_run(
            execution["model_name"], execution["model_config"], task["task_id"]
        )
        if already_run:
            warnings.warn(
                f"Registry already has {execution['model_name']} × {task['task_id']}; "
                "skipping re-evaluation to avoid double-counting.",
                stacklevel=2,
            )
            # Ensure task is in the store for dashboard generation.
            if not store.task_path(task["task_id"]).is_file():
                store.save(task)
            existing = store.load(task["task_id"])
            prior = (existing.get("evaluation_results") or [])[-1] if existing.get("evaluation_results") else None
            clean = prior or {}
        else:
            evaluator = Evaluator()
            result = evaluator.evaluate(
                task, sandbox, execution, timestamp="2026-07-16T12:00:00Z"
            )
            caps = resolve_run_review_caps(
                config,
                overrides=review_cap_overrides,
                caps_off=review_caps_off,
            )
            pack_info = write_run_review_pack(
                task=task,
                evaluation_result=result,
                sandbox_root=sandbox,
                model_response="",
                repo_root=root,
                runs_root=Path(paths["runs"]),
                runs_rel=str(config["paths"]["runs"]),
                caps=caps,
                files_parsed=True,
                files_written=["output/summary.json"],
                truncate_hex=int(hash_cfg.get("truncate_hex", 8)),
            )
            clean = attach_pack_to_result(result, pack_info)
            if not store.task_path(task["task_id"]).is_file():
                store.save(task)
            store.append_result(task["task_id"], clean)
            registry.record(execution["model_name"], execution["model_config"], task["task_id"])

        dash = DashboardGenerator(chartjs_cdn=config["chartjs_cdn"])
        rows = dash.generate(
            store.list_tasks(),
            leaderboard_path=Path(paths["leaderboard"]),
            html_path=Path(paths["dashboard_html"]),
            repo_root=root,
            runs_rel=str(config["paths"]["runs"]),
        )

        return {
            "task_id": task["task_id"],
            "evaluation_result": clean,
            "skipped_duplicate": already_run,
            "leaderboard_rows": rows,
            "leaderboard_path": paths["leaderboard"],
            "dashboard_html_path": paths["dashboard_html"],
            "registry_path": paths["registry"],
            "task_path": str(store.task_path(task["task_id"])),
        }
    finally:
        if own_sandbox and sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)
