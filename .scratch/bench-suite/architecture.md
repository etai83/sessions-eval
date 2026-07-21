# Pipeline Architecture: Antigravity Benchmarking Suite

## Decisions Incorporated

| Ticket | Decision |
|---|---|
| 01 | Source: `transcript_full.jsonl`; cost/token absent — captured at runner time |
| 02 | Taxonomy: output_type × complexity × intent; domain axes kept alongside |
| 03 | Schema: task-schema.json; llm_judge validation rule included |
| 04 | Sampling: stratified by category, 20 tasks total, dynamic growth |
| 05 | DoD: deterministic-first; llm_judge runs optionally when rule present (ticket 03 wins conflict) |
| 06 | Ranking: success_rate primary, cost_effectiveness secondary; outputs: leaderboard.md + index.html |

---

## Component Map

```
~/.gemini/antigravity/brain/<conv-id>/          ~/Documents/session-logs/
  └─ .system_generated/logs/transcript_full.jsonl   └─ session_log_*.md
               │                                            │
               └──────────────┬─────────────────────────────┘
                              ▼
                    ┌─────────────────┐
                    │   1. INGESTER   │  reads transcript_full.jsonl
                    │                 │  extracts: user_request, tool_calls,
                    │                 │  timestamps, conversation_id
                    └────────┬────────┘
                             │  raw TaskCandidate (no labels yet)
                             ▼
                    ┌─────────────────┐
                    │  2. CLASSIFIER  │  assigns taxonomy + domain fields
                    │                 │  input:  user_request text
                    │                 │  output: output_type, complexity,
                    │                 │          intent, category, subcategory
                    └────────┬────────┘
                             │  classified TaskCandidate
                             ▼
                    ┌─────────────────┐
                    │   3. SAMPLER    │  stratified by category
                    │                 │  target: 20 tasks total
                    │                 │  deduplicates vs. existing dataset
                    └────────┬────────┘
                             │  selected TaskEntry (needs DoD authored)
                             ▼
                    ┌─────────────────────────────┐
                    │  4. DATASET STORE           │
                    │  .scratch/bench-suite/       │
                    │    dataset/                  │
                    │      tasks/<task_id>.json    │  ← definition only
                    │      results/<task_id>.jsonl │  ← append-only history
                    │    registry.json             │  ← model × task run log
                    │    task-schema.json          │  ← definition schema
                    └────────┬────────────────────┘
                             │
               ┌─────────────┴──────────────┐
               │                            │
               ▼                            ▼
   ┌─────────────────────┐      ┌─────────────────────┐
   │    5. RUNNER        │      │   7. REGISTRY       │
   │  Gemini API         │◄─────│  checks: has         │
   │  - sends prompt     │      │  model × task_id     │
   │  - captures:        │      │  already run?        │
   │    input_tokens     │      │  blocks if yes       │
   │    output_tokens    │      └─────────────────────┘
   │    cost_usd         │
   │    latency_seconds  │
   │    model_response   │
   └────────┬────────────┘
            │  execution record
            ▼
   ┌─────────────────────┐
   │   6. EVALUATOR      │
   │  per validation_rule│
   │  ┌─ file_exists     │  → pass/fail
   │  ├─ file_contains   │  → pass/fail
   │  ├─ json_field_value│  → pass/fail
   │  └─ llm_judge       │  → score 0.0–1.0 (optional)
   │                     │
   │  completeness_%     │  = rules_passed / total_rules × 100
   │  earned_roi         │  = roi_value × (completeness_% / 100)
   │  cost_effectiveness │  = earned_roi / cost_usd
   └────────┬────────────┘
            │  EvaluationResult appended to results/<task_id>.jsonl
            │  Registry updated: model × task_id = done
            ▼
   ┌─────────────────────┐
   │  8. DASHBOARD GEN   │
   │  reads joined task  │
   │  evaluation history │
   │  → leaderboard.md   │  (Markdown table, ranked)
   │  → index.html       │  (static HTML with charts)
   └─────────────────────┘
```

---

## Component Specs

### 1. Ingester
| Property | Value |
|---|---|
| **Input** | `transcript_full.jsonl` path |
| **Output** | `TaskCandidate`: `{conversation_id, timestamp, user_request, tool_invocations[], duration_seconds, transcript_path}` |
| **Logic** | Filter `source=USER_EXPLICIT, type=USER_INPUT` → strip `<USER_REQUEST>` XML; pair PLANNER_RESPONSE tool_calls with result steps |
| **Storage** | Transient (in-memory); not persisted |
| **Owns** | Extraction algorithm from ticket 01 |

### 2. Classifier
| Property | Value |
|---|---|
| **Input** | `TaskCandidate.user_request` (string) |
| **Output** | Taxonomy + domain labels |
| **Logic** | Rule-based keyword matching only (no LLM call); deterministic, zero API cost; result is **human-reviewed before entering dataset** |
| **Storage** | Transient |
| **Owns** | Mapping from request text → `{output_type, complexity, intent, category, subcategory}` |

### 3. Sampler
| Property | Value |
|---|---|
| **Input** | Pool of classified `TaskCandidate`s + existing `dataset/tasks/*.json` |
| **Output** | Selected candidates for human DoD authoring |
| **Logic** | Group by `domain.category`; proportional quota to reach 20 total; skip already-in-dataset `conversation_id`s |
| **Storage** | Outputs a `pending-review/` list for human to author `validation_rules` and `roi_value` |
| **Owns** | Stratification and deduplication logic |

### 4. Dataset Store
| Property | Value |
|---|---|
| **Location** | Definitions: `.scratch/bench-suite/dataset/tasks/<task_id>.json`; history: `.scratch/bench-suite/dataset/results/<task_id>.jsonl` |
| **Format** | One definition JSON per task (`task-schema.json`); one JSONL of EvaluationResult rows per task |
| **Schema** | [task-schema.json](./task-schema.json) (definition); result rows validated by DatasetStore |
| **Mutability** | Definitions immutable after authoring; results JSONL append-only on each run |
| **Owns** | Ground truth definitions + evaluation history; join at read time for ranking/dashboard |

### 5. Runner
| Property | Value |
|---|---|
| **Input** | `TaskEntry` (prompt + setup_steps); target `model_name` + `model_config` |
| **Output** | Raw model response + `{input_tokens, output_tokens, cost_usd, latency_seconds}` |
| **Logic** | Execute `setup_steps` in sandbox → call Gemini API → record API response metadata → capture model output |
| **Guards** | Checks registry BEFORE calling API; aborts with user warning if already run |
| **Owns** | Cost/token capture (only place in the system this data exists) |

### 6. Evaluator
| Property | Value |
|---|---|
| **Input** | Model response + `TaskEntry.validation_rules` + runner's execution record |
| **Output** | `EvaluationResult` object appended to `dataset/results/<task_id>.jsonl` |
| **Rule engine** | `file_exists` → `os.path.exists`; `file_contains` → substring check; `json_field_value` → JSON parse + key compare; `llm_judge` → Gemini API call with rubric, returns 0.0–1.0 |
| **Score** | `completeness_percent = (rules_passed / total_rules) × 100`; llm_judge counts as pass if score ≥ `min_score` |
| **Owns** | DoD verification and score computation |

### 7. Registry
| Property | Value |
|---|---|
| **Location** | `.scratch/bench-suite/registry.json` |
| **Format** | `{ "<model_name>:<model_config_hash>": ["task_id_1", "task_id_2", ...] }` |
| **Logic** | Before any run: `if task_id in registry[model_key] → warn user, skip`. After run: append `task_id` to `registry[model_key]` |
| **Owns** | Duplicate prevention; prevents redundant API spend |

### 8. Dashboard Generator
| Property | Value |
|---|---|
| **Input** | All `dataset/tasks/*.json` files |
| **Output** | `leaderboard.md` + `index.html` in `.scratch/bench-suite/` |
| **Ranking** | Sort by `avg_success_rate DESC`, then `avg_cost_effectiveness DESC` |
| **Markdown** | Table: model \| avg_success \| total_cost \| total_earned_roi \| cost_effectiveness \| rank |
| **HTML** | Bar chart (success rate) + scatter (cost vs. success) using Chart.js CDN; no build step |
| **Owns** | Aggregation and visualization logic |

---

## Data Flow Summary

```
Transcripts → [Ingester] → [Classifier] → [Sampler] → human authors DoD
                                                              ↓
                                                    dataset/tasks/<id>.json
                                                              ↓
                                          [Registry check] → [Runner] → [Evaluator]
                                                                              ↓
                                                           results JSONL appended (evaluation history)
                                                           registry.json updated
                                                              ↓
                                                    [Dashboard Generator]
                                                    → leaderboard.md
                                                    → index.html
```

---

## File Layout

```
.scratch/bench-suite/
├── map.md                        # wayfinder map
├── task-schema.json              # canonical JSON schema
├── task-example.json             # filled example
├── architecture.md               # this file
├── registry.json                 # model × task run log  { "gemini-2.5-flash:abc123": ["task_01", ...] }
├── dataset/
│   └── tasks/
│       ├── data_audio_transcription_01.json
│       └── ...
├── pending-review/               # sampler output awaiting human DoD authoring
│   └── candidate_<id>.json
├── leaderboard.md                # dashboard: ranked Markdown table
└── index.html                    # dashboard: static HTML with charts
```

---

## Open Questions for Implementer

1. **Sandbox isolation**: Are `setup_steps` run in a temp directory per task, or against the live filesystem? Temp dir is safer but some tasks reference absolute paths.
2. **Classifier implementation**: Rule-based vs. LLM call — cost/latency tradeoff. Suggest rule-based first; upgrade if accuracy is poor.
3. **llm_judge model**: Which Gemini model and config for judge calls? Should it be the same model being evaluated (conflict of interest) or a fixed reference model?
4. **Registry key schema**: `model_name:hash(model_config)` — define the canonical hash function (JSON-sorted keys, SHA256 truncated).
5. **Dynamic growth trigger**: How does the ingester discover new transcripts? Polling interval, file-watch, or manual invocation?
