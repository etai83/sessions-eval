# Antigravity Benchmarking Suite

Flat-file evaluation of Gemini models on TaskEntries derived from Antigravity work: run, score against a Definition of Done, rank by completeness and cost-effectiveness, and review every inference via Run Review Packs. A separate Session Review surface browses source Antigravity Conversations and Session Logs.

## Language

### Evaluation

**TaskEntry**:
A single benchmark task **definition**: identity, taxonomy, prompt, setup steps, validation rules, budgets, and provenance. Stored under `dataset/tasks/<task_id>.json`. Does not own evaluation history.
_Avoid_: task file, benchmark case (when referring only to scores), result row

**EvaluationResult**:
The thin per-run metrics record (scores, tokens, cost, latency, timestamp) — not the full review artifacts. When a Run Review Pack was written, it also carries the run id and a thin path pointer to that pack. History is append-only under `dataset/results/<task_id>.jsonl` and joined at read time for ranking/dashboard.
_Avoid_: run result (ambiguous with Run Review Pack), score row

**Run Review Pack**:
The multi-file on-disk artifact for one model inference: manifest, raw response, full sandbox snapshot, and optional judge data.
_Avoid_: run folder, eval dump, review bundle, Session Log

**Run id**:
Opaque identity for one model inference attempt, shared by an EvaluationResult and its Run Review Pack (and the pack directory name).
_Avoid_: evaluation id, attempt id, session id, Conversation id

**Ranking run**:
The EvaluationResult selected as latest for a given task × model×config; it alone contributes to leaderboard aggregation. Derived at read time from history — not a stored flag.
_Avoid_: best run, official result, canonical score (when meaning “latest,” not “highest score”)

**Rule outcome**:
One entry in a pack’s ordered `rule_outcomes` array, aligned by index with the TaskEntry’s `validation_rules` at run time.
_Avoid_: check result, assertion result, Outcome (Session Review)

**Sidecar**:
Pack storage beside the dataset (under `runs/`), referenced from an EvaluationResult by a thin path pointer rather than embedded bytes.
_Avoid_: attachment, blob store

**Soft size cap**:
A configurable limit on how much of a run is written into a Run Review Pack; evaluation still sees the full sandbox, but pack storage may be partial.
_Avoid_: hard quota, disk quota (when meaning pack write limits)

**Truncation marker**:
An explicit record that pack content was reduced by a soft size cap — always in `manifest.truncation`, and for text artifacts also a trailing content sentinel. Never silent omission.
_Avoid_: silent truncate, implicit trim

### Session Review

**Session Review**:
The static dashboard surface for browsing source Antigravity Conversations and Session Logs — distinct from reviewing model inferences via Run Review Packs.
_Avoid_: Run Review (when meaning this surface), evaluation dashboard (when meaning source browsing)

**Antigravity Conversation**:
One Antigravity chat/work unit identified by a Conversation id; owns transcripts and optional walkthrough/task/plan artifacts under a brain root. Not a TaskEntry and not a model-inference run.
_Avoid_: session (for this unit), brain folder, TaskEntry, run

**Conversation id**:
UUID identity of an Antigravity Conversation (directory name under a brain root).
_Avoid_: session id, run id, evaluation id

**Session Log**:
An authored Markdown review note under the configured session-logs root, recording human-written narrative of work (metadata, actions, results). Not a transcript dump and not a Run Review Pack.
_Avoid_: transcript, conversation log, Run Review Pack, EvaluationResult

**Outcome**:
Review-facing statement of what a unit produced or concluded. Prefer text from a linked Session Log’s Results/Outcomes (or equivalent) section; never an EvaluationResult score, completeness metric, or Rule outcome. Synthetic fallback when no linked log exists is a separate product decision.
_Avoid_: score, completeness_percent, Rule outcome, walkthrough (as sole Outcome source)

**Antigravity Conversations** (UI section):
Top-level Session Review section whose list/detail units are Antigravity Conversations.
_Avoid_: Antigravity Sessions, Tasks

**Session Logs** (UI section):
Top-level Session Review section whose list/detail units are Session Logs.
_Avoid_: Documents, notes (when naming this section)
