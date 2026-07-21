# ADR 0001: Separate TaskEntry definition from evaluation results

## Status

Accepted — 2026-07-21

## Context

Each TaskEntry was one JSON file mixing:

1. **Definition** — identity, taxonomy, prompt, setup_steps, validation_rules, budgets, source
2. **Evaluation history** — growing `evaluation_results[]` (thin metrics + optional run-pack pointers)

Architecture already required definition immutability after authoring and append-only results, but co-locating both in one mutable file blurred authoring vs scoring and made “update task” vs “new run” harder to reason about. Run Review Packs already sidecared heavy artifacts; only the thin result rows remained embedded.

## Decision

- **Definitions** live at `dataset/tasks/<task_id>.json` and conform to `task-schema.json` **without** `evaluation_results`.
- **History** lives at `dataset/results/<task_id>.jsonl` (append-only JSONL of EvaluationResult rows), validated by `evaluation-result-schema.json`.
- **Join key** is `task_id` only.
- **`DatasetStore`** owns the split: `save` writes definition only; `append_result` appends history; `load` / `list_tasks` join history under `evaluation_results` for ranking and dashboard.
- **Migration**: `migrate_embedded_results()` moves embedded arrays into JSONL (merging with any existing JSONL without dropping rows) and strips definition files. Until migration, `load` still surfaces embedded rows (and merges with JSONL when both exist).

## Consequences

- Authoring surfaces no longer grow with every run; result appends cannot accidentally rewrite definition fields.
- Ranking, registry, and pack pointers are unchanged for consumers that use `DatasetStore.load` / `list_tasks`.
- Callers that wrote results via `task["evaluation_results"] = ...; store.save(task)` must use `append_result` (or seed via append after save).
- On-disk definition files and fixtures must not carry `evaluation_results`.
