# Antigravity Benchmarking Suite

Flat-file evaluation of Gemini models on TaskEntries derived from Antigravity sessions: run, score against a Definition of Done, rank by completeness and cost-effectiveness, and review every inference via Run Review Packs.

## Language

**TaskEntry**:
A single benchmark task **definition**: identity, taxonomy, prompt, setup steps, validation rules, budgets, and provenance. Stored under `dataset/tasks/<task_id>.json`. Does not own evaluation history.
_Avoid_: task file, benchmark case (when referring only to scores), result row

**EvaluationResult**:
The thin per-run metrics record (scores, tokens, cost, latency, timestamp) — not the full review artifacts. When a Run Review Pack was written, it also carries the run id and a thin path pointer to that pack. History is append-only under `dataset/results/<task_id>.jsonl` and joined at read time for ranking/dashboard.
_Avoid_: run result (ambiguous with Run Review Pack), score row

**Run Review Pack**:
The multi-file on-disk artifact for one model inference: manifest, raw response, full sandbox snapshot, and optional judge data.
_Avoid_: run folder, eval dump, review bundle

**Run id**:
Opaque identity for one model inference attempt, shared by an EvaluationResult and its Run Review Pack (and the pack directory name).
_Avoid_: evaluation id, attempt id, session id (when referring to a suite run)

**Ranking run**:
The EvaluationResult selected as latest for a given task × model×config; it alone contributes to leaderboard aggregation. Derived at read time from history — not a stored flag.
_Avoid_: best run, official result, canonical score (when meaning “latest,” not “highest score”)

**Rule outcome**:
One entry in a pack’s ordered `rule_outcomes` array, aligned by index with the TaskEntry’s `validation_rules` at run time.
_Avoid_: check result, assertion result

**Sidecar**:
Pack storage beside the dataset (under `runs/`), referenced from an EvaluationResult by a thin path pointer rather than embedded bytes.
_Avoid_: attachment, blob store

**Soft size cap**:
A configurable limit on how much of a run is written into a Run Review Pack; evaluation still sees the full sandbox, but pack storage may be partial.
_Avoid_: hard quota, disk quota (when meaning pack write limits)

**Truncation marker**:
An explicit record that pack content was reduced by a soft size cap — always in `manifest.truncation`, and for text artifacts also a trailing content sentinel. Never silent omission.
_Avoid_: silent truncate, implicit trim
