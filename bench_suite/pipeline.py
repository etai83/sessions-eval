"""High-level pipeline helpers that compose suite components."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from bench_suite.classifier import Classifier
from bench_suite.ingester import Ingester


def transcript_to_candidate(
    transcript_path: Path | str,
    *,
    rules_path: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """
    Ingest one transcript_full.jsonl and classify it into a labeled TaskCandidate.

    No sampling, evaluation, or API calls — deterministic extraction + keyword rules.
    """
    path = Path(transcript_path)
    root = Path(repo_root) if repo_root else Path.cwd()
    rules = (
        Path(rules_path)
        if rules_path
        else root / ".scratch/bench-suite/classifier_rules.json"
    )
    candidate = Ingester().ingest(path)
    return Classifier.from_rules_path(rules).classify(candidate)


def sample_and_write_pending(
    transcript_paths: list[Path | str],
    *,
    rules_path: Path | str | None = None,
    pending_dir: Path | str,
    existing_ids: set[str] | None = None,
    target_total: int = 20,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """
    Ingest + classify a pool of transcripts, run stratified sampling, and write
    selected candidates to pending_dir awaiting human DoD authoring.

    Returns summary dict: {candidates_ingested, candidates_selected, paths_written}.
    """
    from bench_suite.sampler import Sampler

    root = Path(repo_root) if repo_root else Path.cwd()
    rules = (
        Path(rules_path)
        if rules_path
        else root / ".scratch/bench-suite/classifier_rules.json"
    )

    classifier = Classifier.from_rules_path(rules)
    ingester = Ingester()
    pool: list[dict[str, Any]] = []
    for tp in transcript_paths:
        candidate = ingester.ingest(Path(tp))
        pool.append(classifier.classify(candidate))

    sampler = Sampler(target_total=target_total)
    selected = sampler.sample(candidates=pool, existing_ids=existing_ids or set())
    written = sampler.write_pending(selected, pending_dir=Path(pending_dir))

    return {
        "candidates_ingested": len(pool),
        "candidates_selected": len(selected),
        "paths_written": [str(p) for p in written],
    }


def promote_task(
    pending_path: Path | str,
    *,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """
    Promote a human-reviewed pending-review JSON to dataset/tasks/.

    Loads the file, validates against the task schema, refuses to overwrite
    an existing task (additive-only growth). Returns summary dict.
    """
    from bench_suite.config import load_config
    from bench_suite.sampler import Sampler
    from bench_suite.store import DatasetStore

    root = (Path(repo_root) if repo_root else Path.cwd()).resolve()
    config = load_config(repo_root=root)
    paths = config["_resolved_paths"]

    store = DatasetStore(
        Path(paths["dataset_tasks"]),
        Path(paths["schema"]),
    )

    with Path(pending_path).open(encoding="utf-8") as f:
        task = json.load(f)

    sampler = Sampler()
    dest = sampler.promote(task, store=store)
    return {
        "task_id": task["task_id"],
        "dataset_path": str(dest),
    }


def discover_transcripts(root: Path | str) -> list[Path]:
    """Find all ``transcript_full.jsonl`` files under a corpus root (sorted)."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise FileNotFoundError(f"Transcripts root is not a directory: {root_path}")
    return sorted(root_path.rglob("transcript_full.jsonl"))


def refresh_corpus(
    *,
    repo_root: Path | str | None = None,
    transcripts_root: Path | str | None = None,
    transcript_paths: list[Path | str] | None = None,
    rules_path: Path | str | None = None,
    target_total: int = 20,
) -> dict[str, Any]:
    """
    Additive corpus refresh: discover/classify new sessions → pending-review.

    - Never writes or mutates ``dataset/tasks`` (existing TaskEntries untouched).
    - Skips conversation_ids already in the dataset.
    - ``write_pending`` is idempotent (never clobbers human edits in pending-review).
    - ``target_total`` is the dataset capacity; only ``target_total - len(dataset)``
      new candidates are selected.
    """
    from bench_suite.config import load_config
    from bench_suite.store import DatasetStore

    root = (Path(repo_root) if repo_root else Path.cwd()).resolve()
    config = load_config(repo_root=root)
    paths = config["_resolved_paths"]

    discovered: list[Path] = []
    if transcript_paths:
        discovered.extend(Path(p) for p in transcript_paths)
    if transcripts_root is not None:
        discovered.extend(discover_transcripts(transcripts_root))
    # Dedup while preserving order
    seen_paths: set[Path] = set()
    unique_paths: list[Path] = []
    for p in discovered:
        resolved = p.resolve()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        unique_paths.append(p)

    store = DatasetStore(Path(paths["dataset_tasks"]), Path(paths["schema"]))
    existing_tasks = store.list_tasks()
    existing_ids = {
        t["source"]["conversation_id"] for t in existing_tasks if t.get("source")
    }
    remaining = max(0, int(target_total) - len(existing_tasks))

    if remaining == 0 or not unique_paths:
        return {
            "transcripts_discovered": len(unique_paths),
            "candidates_ingested": 0,
            "candidates_selected": 0,
            "target_new": remaining,
            "paths_written": [],
            "pending_review": paths["pending_review"],
            "dataset_task_count": len(existing_tasks),
        }

    sample_result = sample_and_write_pending(
        unique_paths,
        rules_path=rules_path,
        pending_dir=paths["pending_review"],
        existing_ids=existing_ids,
        target_total=remaining,
        repo_root=root,
    )
    return {
        "transcripts_discovered": len(unique_paths),
        "candidates_ingested": sample_result["candidates_ingested"],
        "candidates_selected": sample_result["candidates_selected"],
        "target_new": remaining,
        "paths_written": sample_result["paths_written"],
        "pending_review": paths["pending_review"],
        "dataset_task_count": len(existing_tasks),
    }


def batch_eval(
    *,
    repo_root: Path | str | None = None,
    model_name: str | None = None,
    model_config: dict[str, Any] | None = None,
    client: Any | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Evaluate every dataset TaskEntry for one model × model_config.

    Pairs already present in the registry are skipped (no API call) unless
    ``force`` is True. After the batch, leaderboard.md and index.html are
    regenerated from the full dataset.
    """
    from bench_suite.config import load_config
    from bench_suite.dashboard import DashboardGenerator
    from bench_suite.live import run_live_task
    from bench_suite.registry import Registry
    from bench_suite.runner import AlreadyEvaluatedError
    from bench_suite.store import DatasetStore

    root = (Path(repo_root) if repo_root else Path.cwd()).resolve()
    config = load_config(repo_root=root)
    paths = config["_resolved_paths"]
    model_name = model_name or str(config.get("default_model") or "gemini-3.5-flash")
    model_config = dict(
        model_config
        if model_config is not None
        else (config.get("default_model_config") or {"thinking_level": "high"})
    )

    store = DatasetStore(Path(paths["dataset_tasks"]), Path(paths["schema"]))
    hash_cfg = config.get("registry_hash") or {}
    registry = Registry(
        Path(paths["registry"]),
        truncate_hex=int(hash_cfg.get("truncate_hex", 8)),
        algorithm=str(hash_cfg.get("algorithm", "sha256")),
    )

    tasks = store.list_tasks()
    ran_ids: list[str] = []
    skipped_ids: list[str] = []
    failed: list[dict[str, str]] = []

    for task in tasks:
        task_id = task["task_id"]
        if not force and registry.has_run(model_name, model_config, task_id):
            skipped_ids.append(task_id)
            continue
        try:
            run_live_task(
                repo_root=root,
                task_id=task_id,
                model_name=model_name,
                model_config=model_config,
                client=client,
                force=force,
            )
            ran_ids.append(task_id)
        except AlreadyEvaluatedError:
            # Race: registry updated between has_run and run; treat as skip
            skipped_ids.append(task_id)
        except Exception as exc:  # noqa: BLE001 — batch continues on per-task failure
            warnings.warn(
                f"batch_eval: task {task_id} failed: {exc}",
                stacklevel=2,
            )
            failed.append({"task_id": task_id, "error": str(exc)})

    # Always regenerate dashboard so skipped-only runs still refresh the board
    rows = DashboardGenerator(chartjs_cdn=config["chartjs_cdn"]).generate(
        store.list_tasks(),
        leaderboard_path=Path(paths["leaderboard"]),
        html_path=Path(paths["dashboard_html"]),
    )

    return {
        "model_name": model_name,
        "model_config": model_config,
        "tasks_total": len(tasks),
        "ran": len(ran_ids),
        "skipped": len(skipped_ids),
        "failed": len(failed),
        "ran_task_ids": ran_ids,
        "skipped_task_ids": skipped_ids,
        "failures": failed,
        "leaderboard_rows": rows,
        "leaderboard_path": paths["leaderboard"],
        "dashboard_html_path": paths["dashboard_html"],
        "registry_path": paths["registry"],
    }

