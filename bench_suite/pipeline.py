"""High-level pipeline helpers that compose suite components."""

from __future__ import annotations

import json
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

