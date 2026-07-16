"""Sampler: stratified candidate selection → pending-review + dataset promotion."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from bench_suite.store import DatasetStore


class Sampler:
    """
    Select a proportional stratified sample of TaskCandidates toward a target
    total, skip those already in the dataset, and land them in pending-review.

    Promotion to dataset/tasks requires a fully human-reviewed TaskEntry.
    """

    def __init__(self, *, target_total: int = 20) -> None:
        self.target_total = target_total

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sample(
        self,
        candidates: list[dict[str, Any]],
        *,
        existing_ids: set[str],
    ) -> list[dict[str, Any]]:
        """
        Return a stratified sample proportional by domain.category.

        - Filters out candidates whose conversation_id is in existing_ids.
        - Never returns more than target_total candidates.
        - No candidate appears twice (dedup by conversation_id).
        - If a category has fewer candidates than its quota, surplus is
          redistributed to categories that still have capacity.
        """
        # Dedup by conversation_id and filter already-in-dataset
        seen: set[str] = set()
        pool: list[dict[str, Any]] = []
        for c in candidates:
            cid = c.get("conversation_id", "")
            if cid in existing_ids or cid in seen:
                continue
            seen.add(cid)
            pool.append(c)

        if not pool:
            return []

        # Group by category
        by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for c in pool:
            cat = (c.get("domain") or {}).get("category", "General")
            by_category[cat].append(c)

        total_pool = len(pool)
        target = min(self.target_total, total_pool)

        # Compute proportional quotas (floor), then distribute remainder
        quotas: dict[str, int] = {}
        for cat, items in by_category.items():
            quotas[cat] = math.floor(len(items) / total_pool * target)

        # Remainder slots: sort categories for determinism, give 1 slot each
        remainder = target - sum(quotas.values())
        sorted_cats = sorted(
            by_category.keys(),
            key=lambda c: (-len(by_category[c]), c),
        )
        for cat in sorted_cats:
            if remainder <= 0:
                break
            quotas[cat] += 1
            remainder -= 1

        # Select up to quota from each category
        selected: list[dict[str, Any]] = []
        leftover: list[dict[str, Any]] = []
        for cat in sorted_cats:
            items = by_category[cat]
            q = quotas.get(cat, 0)
            selected.extend(items[:q])
            leftover.extend(items[q:])

        # Fill remaining slots from leftover (categories exhausted their quota
        # or had fewer items than quota — we already cap above via min)
        remaining_slots = target - len(selected)
        if remaining_slots > 0:
            selected.extend(leftover[:remaining_slots])

        return selected[:target]

    def write_pending(
        self,
        candidates: list[dict[str, Any]],
        *,
        pending_dir: Path,
    ) -> list[Path]:
        """
        Write each candidate to pending_dir/candidate_<conv_id>.json.

        Idempotent: existing files are NOT overwritten (human may have already
        started adding fields — don't clobber their work).
        """
        if not candidates:
            return []
        pending_dir = Path(pending_dir)
        pending_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for candidate in candidates:
            cid = candidate.get("conversation_id", "unknown")
            dest = pending_dir / f"candidate_{cid}.json"
            if dest.exists():
                # Idempotent: don't overwrite — human review may be in progress
                written.append(dest)
                continue
            dest.write_text(
                json.dumps(candidate, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            written.append(dest)
        return written

    def promote(
        self,
        task: dict[str, Any],
        *,
        store: DatasetStore,
    ) -> Path:
        """
        Promote a human-reviewed TaskEntry into dataset/tasks/.

        Validates against the task schema, refuses to overwrite an existing
        task (additive-only growth).
        """
        # Schema validation — raises SchemaValidationError if invalid
        store.validate(task)

        task_id = task["task_id"]
        dest = store.task_path(task_id)
        if dest.exists():
            raise FileExistsError(
                f"Task '{task_id}' already exists in dataset; "
                "existing tasks are never replaced (additive growth only). "
                f"Path: {dest}"
            )

        return store.save(task)
