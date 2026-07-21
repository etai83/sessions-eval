# Run Review — Hand-off Specification

> **Status**: Hand-off ready · Version 1.0 · 2026-07-18  
> **Source**: Wayfinder map [Run Review Interface](https://github.com/etai83/sessions-eval/issues/1) (issues 2–7)  
> **Domain glossary**: `CONTEXT.md` (repo root)  
> **Suite code**: `bench_suite/` · data root: `.scratch/bench-suite/`  
> **This document**: product + schema contract for implementers. **No code is written here.**

---

## 1. Purpose

Enable an operator to **review every model inference**: full raw response, post-run sandbox, per-rule Definition-of-Done outcomes, optional judge rationale, and metrics — without re-opening product questions during implementation.

| In scope (v1) | Out of scope |
|---|---|
| Run Review Pack schema + on-disk layout | Live web server / multi-user product |
| Thin pointer on EvaluationResult | Cross-provider models (Gemini-only suite) |
| Immutable multi-run history; latest-only ranking | Re-scoring or editing past DoD |
| Soft size caps with explicit truncation markers | Judge API cost/tokens in pack `metrics` (v1) |
| Static multi-page dashboard review UX | Compressing packs; retention/cleanup policy |
| Config + CLI surfaces for caps / force re-run | Thin CLI `list-runs` / `show-run` (deferred) |

---

## 2. Domain terms (canonical)

See also `CONTEXT.md`. Short forms used below:

| Term | Meaning |
|---|---|
| **TaskEntry** | Benchmark task JSON: prompt, setup, validation rules, appended evaluation results |
| **EvaluationResult** | Thin per-run metrics row on a TaskEntry; optional `run_id` + pack path pointer |
| **Run Review Pack** | Multi-file on-disk artifact for one inference |
| **Run id** | Opaque identity shared by EvaluationResult, pack directory, and `manifest.run_id` |
| **Ranking run** | Latest EvaluationResult for a task × model×config; drives leaderboard (derived, not stored) |
| **Rule outcome** | One index-aligned entry in pack `rule_outcomes[]` |
| **Sidecar** | Pack under `runs/`, not embedded in TaskEntry |
| **Soft size cap** | Limit at **pack write** only; evaluation sees full sandbox/response |
| **Truncation marker** | Explicit record of partial pack storage — never silent |

---

## 3. Run Review Pack schema

### 3.1 Pack directory layout

```
<pack_root>/
  manifest.json     # required
  response.txt      # required (may be empty)
  files/            # required directory (may be empty)
  judge.json        # optional — only when ≥1 llm_judge call actually ran
```

### 3.2 `files/`

- Full **post-run sandbox tree** (setup_steps outputs + model writes).
- Paths relative to sandbox root; recursive file copy.
- Text as written; binary byte-for-byte.
- Empty directories need not be materialized; empty sandbox → empty `files/`.
- Bodies may be truncated or omitted per soft caps (§6); inventory always recorded in `manifest.truncation.files`.

### 3.3 `response.txt`

- UTF-8 full raw model response string (`Runner` / `GenerateResult.text`).
- Always present; empty file if no text.
- Do **not** store the raw SDK response object (`GenerateResult.raw`).

### 3.4 `judge.json` (optional)

Omit when there are no `llm_judge` rules, or every judge rule **failed closed without an API call** (`judge_ran: false`).

```json
{
  "schema_version": 1,
  "judges": [
    {
      "rule_index": 2,
      "score": 0.91,
      "min_score": 0.7,
      "passed": true,
      "rationale": "…",
      "raw_response": "…",
      "judge_model": "gemini-3.1-flash-lite",
      "judge_model_config": { "temperature": 0 }
    }
  ]
}
```

- One array entry per judge rule that **actually ran**.
- `rationale`: parsed from judge JSON when available; else `""` and rely on `raw_response`.
- `raw_response`: full judge model text (subject to soft caps).

### 3.5 `manifest.json` (required)

```json
{
  "schema_version": 1,
  "task_id": "string",
  "run_id": "string",
  "model_name": "string",
  "model_config": {},
  "timestamp": "ISO-8601 UTC",
  "validation_rules_snapshot": [],
  "metrics": {
    "completeness_percent": 0.0,
    "input_tokens": 0,
    "output_tokens": 0,
    "tool_calls": 0,
    "cost_usd": 0.0,
    "latency_seconds": 0.0,
    "earned_roi": 0.0,
    "cost_effectiveness_roi_per_usd": 0.0
  },
  "execution": {
    "files_parsed": true,
    "files_written": ["relative/path"]
  },
  "rule_outcomes": [],
  "artifacts": {
    "response": "response.txt",
    "files_dir": "files",
    "judge": "judge.json"
  },
  "truncation": { }
}
```

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Start at `1` |
| `task_id` | string | Required |
| `run_id` | string | Required; formation §4.2 |
| `model_name` | string | Required |
| `model_config` | object | Required (may be `{}`) |
| `timestamp` | string | ISO-8601 UTC (same as EvaluationResult) |
| `validation_rules_snapshot` | array | Deep copy of TaskEntry `validation_rules` **at run time** |
| `metrics` | object | All keys always present; **runner** cost/tokens only — no judge API cost in v1 |
| `metrics.tool_calls` | int | Count only (no tool-call argument stream today) |
| `execution.files_parsed` | bool | Model JSON yielded parseable `files` |
| `execution.files_written` | string[] | Paths from model payload (not full sandbox inventory) |
| `rule_outcomes` | array | Length **must equal** `len(validation_rules_snapshot)` |
| `artifacts.response` | string | Always `"response.txt"` |
| `artifacts.files_dir` | string | Always `"files"` |
| `artifacts.judge` | string \| null | `"judge.json"` if present; else `null` |
| `truncation` | object | Always present; see §6 |

### 3.6 `rule_outcomes[]`

Every element:

```json
{ "index": 0, "type": "file_exists", "passed": true, "detail": {} }
```

- Ordered, **index-aligned** with `validation_rules` / snapshot.
- Required keys: `index`, `type`, `passed`, `detail`.

**`detail` by rule `type`:**

| type | always | on failure only |
|---|---|---|
| `file_exists` | `path` | `reason`: `"missing"` |
| `file_contains` | `path`, `text` | `reason`: `"missing_file"` \| `"substring_missing"` \| `"unreadable"` |
| `json_field_value` | `path`, `field`, `expected` | `reason`: `"missing_file"` \| `"invalid_json"` \| `"field_missing"` \| `"field_mismatch"`; optional `actual` |
| `llm_judge` | `min_score`, `score`, `judge_ran` | if `judge_ran`: `judges_index` into `judge.json` `judges[]`; if not: `reason`: `"judge_unavailable"` |

Unknown future rule types still use `index` / `type` / `passed` / `detail`.

### 3.7 Required vs optional matrix

| Artifact / field | Rule |
|---|---|
| `manifest.json` | Always required |
| `response.txt` | Always present (may be empty) |
| `files/` | Always present (may be empty) |
| `judge.json` | Omit when unused; `artifacts.judge = null` |
| All `metrics.*` keys | Always present |
| `rule_outcomes` | Always present; `[]` if zero rules |
| `truncation` | Always present (even when nothing cut) |
| Fail-closed llm_judge (no call) | Outcome row with `judge_ran: false`; **no** `judges[]` entry |

### 3.8 Explicit non-goals (pack v1)

- No embedded full SDK raw response.
- No tool-call argument traces (not produced by current runner).
- No judge token/cost fields in `metrics`.
- No compression of pack contents.

---

## 4. Storage layout + EvaluationResult pointer

### 4.1 Path template

```
{runs_root}/{task_id}/{model_key}/{run_id}/
```

| Segment | Definition |
|---|---|
| `runs_root` | Config `paths.runs`; default `.scratch/bench-suite/runs`; resolved against **repo root** like other `paths.*` |
| `task_id` | TaskEntry `task_id` |
| `model_key` | **Identical** to registry key: `registry_key(model_name, model_config)` → `{model_name}:{sha256(sorted_json(config))[:truncate_hex]}` (see `bench_suite.registry` + `config.registry_hash`) |
| `run_id` | §4.2 |

Example:

```
.scratch/bench-suite/runs/offline_golden_01/gemini-3.5-flash:6584ecca/20260718T195938Z_a3f1c2b0/
```

Colon in `model_key` matches the registry (POSIX). If a platform forbids `:`, encode **only at the FS boundary**; logical key remains the registry string.

### 4.2 `run_id` formation

```
{YYYYMMDDTHHMMSSZ}_{8 lowercase hex}
```

- Timestamp component = EvaluationResult / manifest `timestamp` reformatted (`2026-07-18T19:59:38Z` → `20260718T195938Z`).
- Suffix = `secrets.token_hex(4)` (CSPRNG) so same-second parallel runs never collide.
- Directory name **must equal** `manifest.run_id` and EvaluationResult `run_id`.

### 4.3 EvaluationResult fields

Evaluation history lives in `dataset/results/<task_id>.jsonl` (one JSON object per line), not inside the TaskEntry definition file. Each row may include two **optional** pack pointers (omit both on legacy metrics-only rows):

| Field | Type | Meaning |
|---|---|---|
| `run_id` | string | Same as pack directory / manifest |
| `run_pack_path` | string | Repo-relative path to pack **root** (no trailing slash) |

- When a pack is written: **both** set.
- When no pack (legacy metrics-only): **omit** both (preferred over `null`).
- Consumers load `{run_pack_path}/manifest.json`, etc.
- Do **not** embed pack bytes on the EvaluationResult.

Example:

```json
{
  "model_name": "gemini-3.5-flash",
  "model_config": { "thinking_level": "high" },
  "completeness_percent": 100.0,
  "input_tokens": 1000,
  "output_tokens": 200,
  "tool_calls": 3,
  "cost_usd": 0.05,
  "latency_seconds": 2.5,
  "earned_roi": 10.0,
  "cost_effectiveness_roi_per_usd": 200.0,
  "timestamp": "2026-07-18T19:59:38Z",
  "run_id": "20260718T195938Z_a3f1c2b0",
  "run_pack_path": ".scratch/bench-suite/runs/offline_golden_01/gemini-3.5-flash:6584ecca/20260718T195938Z_a3f1c2b0"
}
```

### 4.4 Pointer relativity

- **Repo-relative** string (same convention as `paths.*`).
- Resolve: `(repo_root / run_pack_path).resolve()`.
- Not absolute; not bare relative-to-`paths.runs` only.

### 4.5 Registry interaction

| Concern | Rule |
|---|---|
| Registry purpose | “Has this model×config × task_id been run at least once?” (skip / `--force`) |
| Registry contents | Still `dict[model_key, list[task_id]]` — **no** pack paths, **no** run_ids |
| Path `model_key` | Same string as registry key |
| Force re-run | New `run_id` + new pack + **append** EvaluationResult; registry stays “has task” |
| Multi-run history | Many results/packs share a `model_key` under one `task_id` |
| Missing pack | Omitted pointer ⇒ metrics-only; pack only via `--force` re-run (new row) |

---

## 5. History vs leaderboard latest

### 5.1 Principle

- History is **immutable and append-only** (EvaluationResults + packs).
- Ranking is a **derived view**: only the **ranking run** (latest) per task × model×config feeds leaderboard aggregates.
- Do **not** store `is_ranking` on the EvaluationResult.

### 5.2 Definition of latest (`select_latest`)

For a fixed task and model×config (`model_name` + full `model_config`):

**Latest** = max by `(timestamp, append_index)` where:

1. **Primary:** maximum ISO-8601 UTC `timestamp` (lexicographic max OK for suite `…Z` form).
2. **Tie-break:** maximum **append index** in `evaluation_results[]` (later write wins).

Do **not** use wall-clock at dashboard generation, pack dir mtime, or `run_id` alone as authority (legacy rows may lack `run_id`).

### 5.3 Aggregation algorithm

Replace “average every EvaluationResult for model×config” with:

```
for each task:
  group evaluation_results by (model_name, canonical_json(model_config))
  for each group: keep select_latest(...) only
for each model×config:
  average the kept per-task latest rows
  rank as today (success desc, then cost-eff desc)
```

- Leaderboard **total cost / total ROI** = sums of **latest-per-task** only (not cumulative historical API spend).
- **Scatter chart**: same latest-only selection as leaderboard.

### 5.4 Force re-run matrix

| Action | Behavior |
|---|---|
| Normal run, registry miss | Run → write pack → append EvaluationResult with pointer → `registry.record` |
| Normal run, registry hit | **Skip** (no API, no append, no pack) |
| `--force` | Always run → **always** new pack + **always** append → registry remains “has task” |

Hard rules:

- Never overwrite/delete a prior EvaluationResult or pack.
- Never attach a new pack to an **old** row (no backfill).
- Force for “legacy needs a pack” → **new** inference, new metrics, new pack; old row stays metrics-only.

### 5.5 Surfaces: which runs

| Surface | Which runs |
|---|---|
| Leaderboard + scatter | **Latest only** per model×config×task |
| Task / model run lists | **All** EvaluationResults; newest first within group |
| Run detail | Selected run (any historical) |
| Ranking badge | Derived at render: latest → `ranking`; others → `historical` |

---

## 6. Soft size caps & truncation markers

### 6.1 Principle

Caps apply **only at pack-write time**. Runner/evaluator always see the full sandbox and full model response. Partial packs are always **explicit**.

### 6.2 Cap dimensions

| Config key | Default | Protects |
|---|---:|---|
| `max_response_bytes` | `1048576` (1 MiB) | `response.txt` |
| `max_file_bytes` | `262144` (256 KiB) | each body under `files/`; also each judge string |
| `max_files` | `100` | how many sandbox files get a body |
| `max_pack_bytes` | `8388608` (8 MiB) | total written pack size |

Config block:

```json
"run_review_caps": {
  "max_response_bytes": 1048576,
  "max_file_bytes": 262144,
  "max_files": 100,
  "max_pack_bytes": 8388608
}
```

Missing keys → defaults above. Values are **bytes** (UTF-8 length for text).

### 6.3 Application order (deterministic)

1. Snapshot full sandbox inventory (path, original size) before any omission.
2. Cap each candidate file body to `max_file_bytes` (prefix keep).
3. Walk files in **lexicographic relative path order**; store bodies until `max_files`; remainder → `omitted` (`reason: max_files`).
4. Cap `response.txt` to `max_response_bytes`.
5. Cap judge strings to `max_file_bytes` each.
6. If estimated pack size still exceeds `max_pack_bytes`: omit further file bodies from the **end** of the sorted stored list (`reason: max_pack_bytes`); if still over, further shrink `response.txt` with `reason: max_pack_bytes`.
7. Write `manifest.json` last (never truncated; reserve ~64 KiB headroom or re-check after write).

### 6.4 `manifest.truncation` (always present)

```json
"truncation": {
  "truncated": false,
  "caps": {
    "max_response_bytes": 1048576,
    "max_file_bytes": 262144,
    "max_files": 100,
    "max_pack_bytes": 8388608
  },
  "response": {
    "truncated": false,
    "original_bytes": 1200,
    "stored_bytes": 1200,
    "reason": null
  },
  "files": [
    {
      "path": "output/summary.json",
      "status": "stored",
      "original_bytes": 42,
      "stored_bytes": 42,
      "reason": null
    }
  ],
  "judge": {
    "truncated": false,
    "entries": []
  }
}
```

- File `status`: `stored` | `truncated` | `omitted`.
- `reason` when not fully stored: `max_file_bytes` | `max_files` | `max_pack_bytes` | `max_response_bytes`.
- Every sandbox file at snapshot time appears in `truncation.files` (including omitted).

### 6.5 Text content sentinel

When a **text** artifact is truncated, append after the kept prefix:

```
<<RUN_REVIEW_TRUNCATED original_bytes=N stored_bytes=M reason=max_file_bytes>>
```

- Sentinel bytes count toward `stored_bytes` and pack budget.
- **Binary** truncated files: no sentinel (manifest only). Detect binary via NUL in first 8 KiB or failed UTF-8; if ambiguous, treat as binary.

### 6.6 Config vs CLI

| Surface | Behavior |
|---|---|
| `config.json` → `run_review_caps` | Defaults for all runs |
| `--review-cap key=value` (repeatable) | Override individual caps for this invocation |
| `--review-caps-off` | Disable all four; record `caps` values as `null`; never truncate |

Effective caps used are recorded in `manifest.truncation.caps`.

### 6.7 Non-goals

- Caps do **not** change DoD evaluation or leaderboard metrics.
- No retention/cleanup policy in v1.
- No compression in v1.

---

## 7. Static dashboard run review UX

### 7.1 Architecture

**Multi-page static HTML** (no server, no SPA as primary). Regenerated whenever the suite regenerates the dashboard today.

```
.scratch/bench-suite/
  index.html                          # leaderboard + charts (links into review/)
  leaderboard.md                      # terminal-friendly; role unchanged
  review/
    models/{model_key_urlsafe}.html
    tasks/{task_id}.html
    runs/{task_id}/{model_key_urlsafe}/{run_id}.html
  runs/{task_id}/{model_key}/{run_id}/   # packs (sidecar)
```

**URL-safe model_key:** replace `:` with `__` in HTML paths only (e.g. `gemini-3.5-flash__6584ecca`). Logical key keeps `:`.

Pack bodies stay on disk; review pages **link** relatively into packs (prefer relative paths for `file://` portability).

### 7.2 Navigation

```
index.html
  → review/models/{model_key_urlsafe}.html
      → review/tasks/{task_id}.html
          → review/runs/{task_id}/{model_key_urlsafe}/{run_id}.html
```

| From | To |
|---|---|
| Leaderboard model name / “Tasks” | Model page |
| Scatter point (when linked) | Task page (preferred) |
| Model page task row | Task page |
| Model page “Open ranking run” | Ranking run detail |
| Task page “Review” | That run’s detail |

Breadcrumbs on every review page: Leaderboard / model / task / run.

**Task page run lists:** group by model×config; newest first; columns: timestamp, success, cost, pack presence, `ranking` / `historical` badge.

### 7.3 Run detail sections (order)

1. Header + breadcrumbs + badges (`ranking`|`historical`, pack|no pack, `truncated` if applicable)
2. Metrics strip (prefer EvaluationResult; align with `manifest.metrics`)
3. Truncation banner if `manifest.truncation.truncated` (collapsible full table)
4. Rule outcomes table
5. Raw response (`response.txt`)
6. Sandbox files (two-pane list + preview; omitted files listed with reason)
7. Judge section **only if** `judge.json` present
8. Pack path footer (`run_pack_path` + artifact links)

### 7.4 Missing pack (legacy)

When no `run_pack_path`:

- Show metrics + ranking/historical badge.
- Prominent callout: **Metrics only — no Run Review Pack** (no empty pack panels).
- Copy-paste CLI (generator fills ids), e.g.  
  `python -m bench_suite.cli live-eval --task <task_id> --model <model_name> --force`  
  (include whatever flags the real CLI requires for config/path).
- **Hide** rule outcomes / response / files / judge entirely.

### 7.5 Prototype reference

Throwaway UX exploration (not production generator output):

- Branch: `prototype/run-review-ux`
- File: `.scratch/bench-suite/prototype-run-review.html`
- Winner: multi-page drill-down (variant A)

---

## 8. Implementation workstreams (suggested order)

These are implementation slices, not open product questions:

1. **Schema + config** — `task-schema.json` optional fields; `paths.runs`; `run_review_caps` defaults in `bench_suite/config.py` / `config.json`.
2. **Pack writer** — after evaluate, write pack under path template; apply caps + truncation; return `run_id` + `run_pack_path`.
3. **Pipeline wire-up** — live / batch / offline paths: append EvaluationResult with pointer; force semantics unchanged except always write pack.
4. **Latest-only aggregation** — fix `aggregate_models` / scatter to `select_latest` per task × model×config.
5. **Dashboard multi-page** — extend `DashboardGenerator` for `review/**` HTML + leaderboard links.
6. **Tests** — pack shape, caps/sentinels, force append immutability, latest selection, missing-pack page.

---

## 9. Open implementer questions (deferred — not blockers)

Product route is closed. These may be decided during implementation without a new wayfinder map unless scope expands:

1. **Thin CLI** (`list-runs` / `show-run`): first implement slice vs defer (HTML is enough for v1 review).
2. **Retention/cleanup** of old packs (disk growth): ops policy later; no auto-delete in v1.
3. Exact CLI module invocation string in the missing-pack callout if `live-eval` entrypoint naming differs in production docs.
4. Whether scatter points should deep-link to task page only or offer ranking-run detail as secondary.

---

## 10. Decision index (source of truth per topic)

| Topic | Issue |
|---|---|
| Pack contents & schema | [Run Review Pack contents & schema](https://github.com/etai83/sessions-eval/issues/2) |
| Disk layout + pointer | [Sidecar runs/ layout + EvaluationResult pointer](https://github.com/etai83/sessions-eval/issues/3) |
| History vs ranking | [Re-run history vs leaderboard latest](https://github.com/etai83/sessions-eval/issues/4) |
| Soft caps | [Soft size caps & truncation markers](https://github.com/etai83/sessions-eval/issues/5) |
| Dashboard UX | [Static dashboard run review UX](https://github.com/etai83/sessions-eval/issues/6) |
| This assembly | [Write Run Review hand-off spec](https://github.com/etai83/sessions-eval/issues/7) |
| Map | [Run Review Interface — wayfinder map](https://github.com/etai83/sessions-eval/issues/1) |

---

## 11. Acceptance criteria for “done implementing”

An implementer has finished v1 when:

- [ ] Every successful live/offline eval that writes results also writes a pack (unless process fails before write — then no silent half-row without documenting failure mode).
- [ ] EvaluationResult carries `run_id` + repo-relative `run_pack_path` when pack exists.
- [ ] Pack validates against §3–§6 (manifest, artifacts, truncation always present).
- [ ] `--force` appends history and never mutates prior packs/rows.
- [ ] Leaderboard/scatter use latest-only; run lists show full history with ranking badge.
- [ ] Static `review/**` pages support nav + detail + missing-pack callout.
- [ ] Soft caps configurable; truncation never silent.
- [ ] Glossary terms in `CONTEXT.md` remain accurate.
