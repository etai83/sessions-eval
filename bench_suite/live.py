"""Live evaluation path: registry guard → Gemini runner → evaluator → board."""

from __future__ import annotations

import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Any

from bench_suite.config import load_config
from bench_suite.dashboard import DashboardGenerator
from bench_suite.evaluator import Evaluator, strip_diagnostic_fields
from bench_suite.registry import Registry
from bench_suite.runner import (
    DEFAULT_PRICING,
    AlreadyEvaluatedError,
    GeminiClient,
    GoogleGenaiClient,
    Runner,
)
from bench_suite.store import DatasetStore

# Re-export for CLI/tests
__all__ = ["AlreadyEvaluatedError", "run_live_task"]


def run_live_task(
    *,
    repo_root: Path | None = None,
    task_path: Path | None = None,
    task_id: str | None = None,
    model_name: str = "gemini-2.5-flash",
    model_config: dict[str, Any] | None = None,
    client: GeminiClient | None = None,
    sandbox_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    End-to-end live path for one TaskEntry.

    Resolution order for the task:
    1. ``task_id`` — load from the dataset store
    2. ``task_path`` — load JSON path (and prefer dataset copy if already promoted)
    3. Default — offline golden fixture

    Runner checks registry BEFORE calling the API. On success: append
    EvaluationResult, record registry, regenerate leaderboard + index.html.
    """
    root = (repo_root or Path.cwd()).resolve()
    config = load_config(repo_root=root)
    paths = config["_resolved_paths"]
    model_config = dict(model_config or {"thinking_level": "high"})

    store = DatasetStore(Path(paths["dataset_tasks"]), Path(paths["schema"]))
    if task_id and task_path:
        raise ValueError("Pass only one of task_id or task_path, not both")
    if task_id:
        task = store.load(task_id)
    else:
        source = (
            Path(task_path)
            if task_path
            else root / ".scratch/bench-suite/fixtures/offline_golden_task.json"
        )
        loaded = store.load_path(source)
        if store.task_path(loaded["task_id"]).is_file():
            task = store.load(loaded["task_id"])
        else:
            task = loaded

    hash_cfg = config.get("registry_hash") or {}
    registry = Registry(
        Path(paths["registry"]),
        truncate_hex=int(hash_cfg.get("truncate_hex", 8)),
        algorithm=str(hash_cfg.get("algorithm", "sha256")),
    )

    pricing = config.get("gemini_pricing") or DEFAULT_PRICING
    gemini: GeminiClient = client or GoogleGenaiClient()
    runner = Runner(gemini, pricing=pricing)

    own_sandbox = sandbox_dir is None
    sandbox = Path(sandbox_dir) if sandbox_dir else Path(tempfile.mkdtemp(prefix="bench-suite-live-"))
    sandbox.mkdir(parents=True, exist_ok=True)
    try:
        # force: skip registry guard by not passing registry into Runner
        run = runner.run(
            task,
            sandbox,
            model_name=model_name,
            model_config=model_config,
            registry=None if force else registry,
        )
        if not run.files_parsed:
            warnings.warn(
                "Model response did not include parseable sandbox files JSON; "
                "DoD checks will likely fail. Response still recorded with API metrics.",
                stacklevel=2,
            )

        # Judge uses the same client transport but a fixed reference model from config
        # (never the model under evaluation — conflict of interest).
        evaluator = Evaluator(
            judge_client=gemini,
            judge_model=str(
                config.get("llm_judge_reference_model") or "gemini-2.0-flash"
            ),
        )
        result = evaluator.evaluate(
            task,
            sandbox,
            run.execution,
            model_response=run.model_response,
        )
        clean = strip_diagnostic_fields(result)

        task = dict(task)
        task["evaluation_results"] = list(task.get("evaluation_results") or []) + [clean]
        store.save(task)
        if not registry.has_run(model_name, model_config, task["task_id"]):
            registry.record(model_name, model_config, task["task_id"])
        elif force:
            # Already recorded; force re-run still appends EvaluationResult above.
            pass

        rows = DashboardGenerator(chartjs_cdn=config["chartjs_cdn"]).generate(
            store.list_tasks(),
            leaderboard_path=Path(paths["leaderboard"]),
            html_path=Path(paths["dashboard_html"]),
        )

        return {
            "task_id": task["task_id"],
            "evaluation_result": clean,
            "model_response": run.model_response,
            "files_written": run.files_written,
            "files_parsed": run.files_parsed,
            "skipped_duplicate": False,
            "leaderboard_rows": rows,
            "leaderboard_path": paths["leaderboard"],
            "dashboard_html_path": paths["dashboard_html"],
            "registry_path": paths["registry"],
            "task_path": str(store.task_path(task["task_id"])),
        }
    except AlreadyEvaluatedError as exc:
        warnings.warn(str(exc), stacklevel=2)
        raise
    finally:
        if own_sandbox and sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)
