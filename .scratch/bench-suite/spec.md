# Antigravity Benchmarking Suite — Specification

> **Status**: Hand-off ready · Version 1.0 · 2026-07-16  
> **Scope**: Gemini family models only. Cross-provider comparison is out of scope.  
> **Output of this effort**: This spec document. No code is written here.

---

## 1. Executive Summary

The Antigravity Benchmarking Suite ingests raw session transcripts from the Antigravity AI coding assistant, structures them into a formal dataset of representative tasks, and provides a reproducible evaluation pipeline that ranks Gemini models by DoD success rate and cost-effectiveness.

### Scope constraints
| In scope | Out of scope |
|---|---|
| Gemini API models | OpenAI, Anthropic, other providers |
| Antigravity transcript JSONLs | Other log formats |
| Flat-file, no-infra implementation | Databases, cloud storage, build pipelines |
| Spec only (this document) | Implementation code |

---

## 2. Source Data

### 2.1 Transcript location
```
~/.gemini/antigravity/brain/<conv-id>/.system_generated/logs/transcript_full.jsonl
```

**Always use `transcript_full.jsonl`**, not `transcript.jsonl` (compact):
- Full version has no truncation and clean tool argument encoding
- Compact version double-escapes `tool_calls[].args` string values

### 2.2 Transcript step schema

Every line is a JSON object (one step):

| Field | Type | Present | Notes |
|---|---|---|---|
| `step_index` | int | always | 0-based; may have gaps |
| `source` | enum | always | `USER_EXPLICIT` · `SYSTEM` · `MODEL` |
| `type` | enum | always | See taxonomy below |
| `status` | enum | always | `DONE` · `RUNNING` (transient) |
| `created_at` | ISO 8601 UTC | always | Wall-clock timestamp |
| `content` | string | conditional | Absent on empty PLANNER_RESPONSE and CONVERSATION_HISTORY |
| `tool_calls` | array | conditional | PLANNER_RESPONSE steps with tool use only |
| `thinking` | string | conditional | Model chain-of-thought when present |
| `error` / `error_code` | string / int | conditional | ERROR_MESSAGE steps only |

### 2.3 Step-type taxonomy

| `type` | `source` | Role in task extraction |
|---|---|---|
| `USER_INPUT` | `USER_EXPLICIT` | **User intent** — canonical task entry point |
| `PLANNER_RESPONSE` | `MODEL` | Model reasoning + tool dispatch |
| `VIEW_FILE` `LIST_DIRECTORY` `RUN_COMMAND` `CODE_ACTION` `GENERIC` `ASK_QUESTION` `INVOKE_SUBAGENT` | `MODEL` | Tool result steps |
| `CONVERSATION_HISTORY` `CHECKPOINT` `EPHEMERAL_MESSAGE` `SYSTEM_MESSAGE` `ERROR_MESSAGE` | `SYSTEM` | System/infra steps — **ignore for task extraction** |

### 2.4 What is extractable

| Signal | How to extract |
|---|---|
| User request | `content` of first `source=USER_EXPLICIT, type=USER_INPUT`; strip `<USER_REQUEST>…</USER_REQUEST>` XML tags |
| Tool invocations | `tool_calls[].name` + `tool_calls[].args` from PLANNER_RESPONSE steps |
| Tool results | Subsequent MODEL non-PLANNER_RESPONSE steps (infer by sequence; no `tool_call_id`) |
| Session duration | `created_at` delta: first step → last step |
| **Cost / tokens** | ❌ **Not in transcript.** Must be captured from Gemini API response at runner time. |

---

## 3. Task Taxonomy

Three independent classification axes. Applied by the Classifier component using deterministic keyword rules.

### Axis 1: `output_type` (primary — most evaluation signal)

| Value | Meaning |
|---|---|
| `code` | Source files written or modified |
| `plan_or_spec` | Architecture docs, wayfinder maps, specs, ADRs |

### Axis 2: `complexity` (secondary)

| Value | Meaning |
|---|---|
| `single_step` | No or minimal tool use (1–2 calls); rare in practice |
| `multi_tool` | Several tools called sequentially; dominant pattern |
| `multi_agent` | Subagents spawned; uncommon |

### Axis 3: `intent` (tertiary)

| Value | Meaning |
|---|---|
| `generate` | Produce something new from a prompt |
| `modify` | Change existing code or docs |
| `debug` | Diagnose a failure and fix it |
| `research` | Investigate and synthesise findings (answer only) |

**Domain rejected**: category/subcategory domain axes are kept on the schema for legacy cross-reference only; they are not used for sampling or ranking.

---

## 4. Dataset Schema

### 4.1 Files

| File | Purpose |
|---|---|
| `.scratch/bench-suite/task-schema.json` | JSON Schema (draft-07) — canonical validation |
| `.scratch/bench-suite/task-example.json` | Filled example from a real session |
| `.scratch/bench-suite/dataset/tasks/<task_id>.json` | One file per task entry |

### 4.2 Task entry structure

```
TaskEntry
├── task_id              string          e.g. "data_audio_transcription_01"
├── name                 string          human-readable
├── taxonomy             object
│   ├── output_type      enum            code | plan_or_spec
│   ├── complexity       enum            single_step | multi_tool | multi_agent
│   └── intent           enum            generate | modify | debug | research
├── domain               object          (legacy cross-reference)
│   ├── category         enum            Trading | Data Engineering | AI | ...
│   └── subcategory      enum            Backtesting | Feature Dev | Debugging | ...
├── source               object
│   ├── conversation_id  UUID string
│   ├── transcript_path  string          absolute path to transcript_full.jsonl
│   └── timestamp        ISO 8601        created_at of first USER_INPUT step
├── prompt               string          user request text, XML tags stripped
├── required_tools       string[]        tool names the agent must invoke
├── required_skills      string[]        Antigravity skill slugs
├── roi_value            number          estimated task value (USD or utility units)
├── target_token_budget  integer         expected token ceiling for efficient solution
├── target_tool_call_budget integer      expected tool-call ceiling
├── setup_steps          object[]        sandbox init before model execution
│   └── {action, path, content, command}
├── validation_rules     object[]        Definition of Done assertions (ordered)
│   └── type: file_exists | file_contains | json_field_value | llm_judge
└── evaluation_results   object[]        grows on each run; never modified retroactively
    └── {model_name, model_config, completeness_percent, input_tokens, output_tokens,
         tool_calls, cost_usd, latency_seconds, earned_roi,
         cost_effectiveness_roi_per_usd, timestamp}
```

### 4.3 Validation rule types

| Type | Required fields | Semantics |
|---|---|---|
| `file_exists` | `path` | `os.path.exists(path)` → boolean |
| `file_contains` | `path`, `text` | `text in open(path).read()` → boolean |
| `json_field_value` | `path`, `field`, `expected` | parse JSON, compare `obj[field] == expected` |
| `llm_judge` | `rubric`, `min_score` | Gemini API call with rubric; passes if score ≥ `min_score` (0.0–1.0) |

`completeness_percent = (rules_passed / total_rules) × 100`  
`llm_judge` counts as passed when judge score ≥ `min_score`.

### 4.4 Scoring fields

| Field | Formula |
|---|---|
| `completeness_percent` | `(rules_passed / len(validation_rules)) × 100` |
| `earned_roi` | `roi_value × (completeness_percent / 100)` |
| `cost_effectiveness_roi_per_usd` | `earned_roi / cost_usd` |

---

## 5. Sampling Strategy

### 5.1 Method
Stratified sampling by `domain.category`.

**Why**: ~160 sessions across 14 categories; proportional stratification covers all active workflow areas without embedding complexity.

### 5.2 Target size
**20 tasks total**, proportional to per-category session volume.

Example distribution (adjust to actual corpus counts):

| Category | % of corpus | Target tasks |
|---|---|---|
| Trading | 25% | 5 |
| Data Engineering | 15% | 3 |
| Software Dev | 15% | 3 |
| Agent Meta | 10% | 2 |
| AI | 10% | 2 |
| General | 10% | 2 |
| Other (7 categories) | 15% | 3 |

### 5.3 Refresh policy
**Dynamic growth** — the Sampler runs after each new session batch to identify candidates not yet in the dataset. Growth is additive; existing tasks are never replaced.

### 5.4 Human review gate
The Sampler outputs to `pending-review/`. A human must author:
- `validation_rules` (the DoD)
- `roi_value`
- `target_token_budget` + `target_tool_call_budget`

Only after review does a task move to `dataset/tasks/`.

---

## 6. DoD Verification

### 6.1 Primary mechanism: deterministic checks
Deterministic rules (`file_exists`, `file_contains`, `json_field_value`) run on every task — always, reproducibly, zero API cost.

### 6.2 Optional overlay: llm_judge
When a `validation_rule` has `type: llm_judge`, the Evaluator makes a Gemini API call with the `rubric` and the model's output.

**Judge model**: A fixed reference model (not the model under evaluation — conflict of interest). Specify the reference model in the dataset's global config, separate from per-run `model_config`.

**Score**: 0.0–1.0. Passes if ≥ `min_score`.

---

## 7. Ranking & Dashboard

### 7.1 Composite score — lexicographic
No weighted sum. Two-level sort:

1. **Primary**: `avg_success_rate` (average `completeness_percent` across all tasks) — descending
2. **Secondary tiebreaker**: `avg_cost_effectiveness` (`total_earned_roi / total_cost_usd`) — descending

### 7.2 Per-model aggregate metrics

| Metric | Computation |
|---|---|
| `avg_success_rate` | mean of `completeness_percent` across all runs for this model |
| `total_cost_usd` | sum of `cost_usd` |
| `total_earned_roi` | sum of `earned_roi` |
| `avg_cost_effectiveness` | `total_earned_roi / total_cost_usd` |
| `avg_latency_seconds` | mean of `latency_seconds` |

### 7.3 Dashboard outputs

**`leaderboard.md`** — terminal-friendly ranked table:
```markdown
| Rank | Model | Config | Avg Success | Total Cost | Total ROI | Cost-Eff (ROI/$) |
|------|-------|--------|-------------|------------|-----------|------------------|
| 1    | gemini-2.5-flash | thinking: high | 95.0% | $0.28 | 60.0 | 214.3 |
```

**`index.html`** — static HTML, no build step:
- Bar chart: avg success rate per model (Chart.js CDN)
- Scatter plot: cost_usd vs. success_rate per task × model
- Table: full leaderboard with sortable columns

---

## 8. Component Architecture

Full diagram and per-component specs: [architecture.md](./architecture.md)

### Component summary

| # | Name | Inputs | Outputs | Owns |
|---|---|---|---|---|
| 1 | **Ingester** | `transcript_full.jsonl` | `TaskCandidate` struct | Extraction algorithm |
| 2 | **Classifier** | `TaskCandidate.user_request` | taxonomy + domain labels | Deterministic keyword rules |
| 3 | **Sampler** | Classified candidates + existing dataset | `pending-review/*.json` | Stratification + dedup |
| 4 | **Dataset Store** | Human-reviewed tasks | `dataset/tasks/<id>.json` | Ground truth; immutable except eval_results |
| 5 | **Runner** | TaskEntry + target model | Raw response + cost/tokens/latency | Gemini API call; **only place cost data exists** |
| 6 | **Evaluator** | Response + validation_rules | `EvaluationResult` | DoD verification + score |
| 7 | **Registry** | model × task_id pairs | `registry.json` | Duplicate prevention |
| 8 | **Dashboard Generator** | All task files | `leaderboard.md` + `index.html` | Aggregation + ranked output |

### File layout
```
.scratch/bench-suite/
├── spec.md                       ← this document
├── task-schema.json              ← canonical JSON schema
├── task-example.json             ← filled example (real session)
├── architecture.md               ← component diagram + per-component spec
├── registry.json                 ← { "model:confighash": ["task_id", ...] }
├── dataset/
│   └── tasks/
│       └── <task_id>.json
├── pending-review/
│   └── candidate_<conv-id>.json
├── leaderboard.md
└── index.html
```

### Registry key format
```
"<model_name>:<sha256_8chars_of_sorted_json_model_config>"
```
Example: `"gemini-2.5-flash:a3f9b201"` where the hash is SHA-256 of `{"thinking_level":"high"}` (keys sorted, no spaces), truncated to 8 hex chars.

---

## 9. Open Questions for the Implementer

These decisions were deliberately deferred — the spec is complete without them, but the implementer must resolve each before shipping:

| # | Question | Recommendation |
|---|---|---|
| 1 | **Sandbox isolation for `setup_steps`** | Run in a per-task temp directory; copy any referenced absolute paths in. Avoids side effects across runs. |
| 2 | **llm_judge reference model** | Hardcode a stable reference (e.g. `gemini-2.0-flash`) in a top-level `config.json`; never use the model under evaluation. |
| 3 | **Registry hash function** | `hashlib.sha256(json.dumps(model_config, sort_keys=True).encode()).hexdigest()[:8]` |
| 4 | **Dynamic growth trigger** | Manual invocation is safest for v1; add file-watch in v2 if corpus grows rapidly. |
| 5 | **Classifier keyword rules** | Start with a simple keyword→taxonomy mapping JSON file; extend as false-positive rate is observed. |
| 6 | **Chart.js version** | Pin to a specific CDN version in `index.html` to avoid breaking changes. |

---

## 10. Glossary

| Term | Definition |
|---|---|
| **TaskEntry** | A single benchmark task conforming to `task-schema.json` |
| **DoD** | Definition of Done — the set of `validation_rules` a successful run must pass |
| **completeness_percent** | Fraction of DoD rules passed × 100; the primary per-run success metric |
| **roi_value** | Estimated task value (USD or utility); assigned by human during review |
| **earned_roi** | `roi_value × completeness_percent / 100` — value actually delivered by the model |
| **cost_effectiveness** | `earned_roi / cost_usd` — value per dollar spent |
| **Registry** | `registry.json` — tracks which model configurations have been evaluated on which tasks |
| **llm_judge** | Optional validation rule type where a fixed reference model scores output against a rubric |
| **Frontier** | Open, unblocked, unclaimed wayfinder tickets — what can be worked next |
