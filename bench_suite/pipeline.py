"""High-level pipeline helpers that compose suite components."""

from __future__ import annotations

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
