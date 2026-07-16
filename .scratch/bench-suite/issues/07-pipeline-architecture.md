# 07 — Pipeline Architecture & Component Boundaries

Type: prototype
Status: claimed
Blocked by: 03, 04, 05, 06

## Question

Given all the schema and mechanism decisions above, what are the system's components and their interfaces? Produce a concrete architecture diagram (Mermaid or ASCII) and a component list covering:

- **Ingester**: reads transcript JSONLs → emits raw task candidates
- **Classifier**: assigns taxonomy labels
- **Sampler**: selects representative set
- **Dataset store**: canonical JSON/CSV files in-repo
- **Runner**: sends tasks to Gemini API, captures cost/token/latency
- **Evaluator**: applies DoD verification mechanism
- **Registry**: duplicate-prevention (model × task already-run tracking)
- **Dashboard generator**: reads results, emits ranked report

For each component: inputs, outputs, storage format, and the one decision it owns.

Status: resolved

## Answer

Architecture prototype produced at [architecture.md](file:///Users/itaiharpaz/Code/sessions-eval/.scratch/bench-suite/architecture.md).

### 8 components and the one decision each owns

| # | Component | Owns | Storage |
|---|---|---|---|
| 1 | **Ingester** | Extraction algorithm (transcript → TaskCandidate) | Transient |
| 2 | **Classifier** | Deterministic rule-based mapping → taxonomy + domain | Transient |
| 3 | **Sampler** | Stratified selection (20 tasks, by category) + dedup | `pending-review/` |
| 4 | **Dataset Store** | Ground truth; immutable except `evaluation_results[]` | `dataset/tasks/<id>.json` |
| 5 | **Runner** | API call + cost/token/latency capture | Writes to task file via Evaluator |
| 6 | **Evaluator** | DoD verification + score computation | Appends to `task.evaluation_results[]` |
| 7 | **Registry** | Duplicate prevention (model × task_id already-run) | `registry.json` |
| 8 | **Dashboard Generator** | Aggregation + ranked output | `leaderboard.md` + `index.html` |

### Key decisions locked in this ticket
- Classifier: **deterministic rules only** (no LLM call)
- Conflict resolved: `llm_judge` runs optionally in Evaluator when rule is present (ticket 03 > ticket 05)
- Registry key: `model_name:hash(model_config)` — implementer to define hash function
- Human review gate: Sampler → `pending-review/` → human authors DoD → `dataset/tasks/`
- Dashboard: both `leaderboard.md` and `index.html` (Chart.js CDN, no build step)

### Open questions for implementer
1. Sandbox: temp dir vs. live filesystem for `setup_steps`
2. llm_judge: use fixed reference model (not the model under test)
3. Registry hash: JSON-sorted keys + SHA256 truncated to 8 chars
4. Dynamic growth trigger: manual invocation vs. file-watch
