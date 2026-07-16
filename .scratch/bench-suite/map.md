# Wayfinder Map: Antigravity Benchmarking Suite Spec

Label: `wayfinder:map`

## Destination

A complete, hand-off-ready spec for a benchmarking suite that ingests Antigravity transcript JSONLs, structures them into a formal dataset of representative tasks, and provides an evaluation pipeline and comparative dashboard for ranking Gemini models by cost-efficiency, DoD success rate, and composite score.

## Notes

- **Domain**: AI evaluation / developer tooling
- **Source data**: Antigravity transcript JSONLs at `~/.gemini/antigravity/brain/<conv-id>/`
- **Target models**: Gemini family (Gemini API) — cross-provider is out of scope for this effort
- **Output**: A spec document (flat files in this repo) ready for implementation; no code written during this effort
- **Skills to consult**: `/research`, `/grilling`, `/domain-modeling`, `/prototype`
- **Tracker**: local-markdown (`.scratch/bench-suite/issues/`)

## Decisions so far

- [Write the Spec Document](.scratch/bench-suite/issues/08-write-spec.md) — terminal ticket; spec.md assembled at .scratch/bench-suite/spec.md; all 8 prior decisions incorporated; 6 open questions deferred to implementer. Map complete.
- [Pipeline Architecture & Component Boundaries](.scratch/bench-suite/issues/07-pipeline-architecture.md) — 8 components: Ingester, Classifier (deterministic rules only), Sampler (stratified 20 tasks), Dataset Store, Runner, Evaluator (llm_judge optional), Registry (model×task dedup), Dashboard Generator (leaderboard.md + index.html). See architecture.md.
- [Dataset Entry Schema](.scratch/bench-suite/issues/03-dataset-schema.md) — schema reconciled: taxonomy (output_type/complexity/intent) + domain (category/subcategory) coexist; model_config replaces thinking_level; input/output tokens split; latency_seconds + llm_judge validation rule added. Files: task-schema.json, task-example.json.
- [Task Taxonomy & Classification Axes](.scratch/bench-suite/issues/02-task-taxonomy.md) — 3 axes: output_type (code | plan_or_spec), complexity (single_step | multi_tool | multi_agent), intent (generate | modify | debug | research); domain axis rejected as noise.
- [Transcript JSONL Schema Analysis](.scratch/bench-suite/issues/01-transcript-schema.md) — schema confirmed; cost/token data absent from transcript entirely; must be captured externally at API call time; use transcript_full.jsonl (not compact); user intent in USER_INPUT steps; tool calls in PLANNER_RESPONSE.tool_calls.
- [Write the Spec Document](.scratch/bench-suite/issues/08-write-spec.md) — terminal ticket; spec.md assembled at .scratch/bench-suite/spec.md; all 8 prior decisions incorporated; 6 open questions deferred to implementer. Map complete.
- [Pipeline Architecture & Component Boundaries](.scratch/bench-suite/issues/07-pipeline-architecture.md) — 8 components: Ingester, Classifier (deterministic rules only), Sampler (stratified 20 tasks), Dataset Store, Runner, Evaluator (llm_judge optional), Registry (model×task dedup), Dashboard Generator (leaderboard.md + index.html). See architecture.md.
- [Dataset Entry Schema](.scratch/bench-suite/issues/03-dataset-schema.md) — canonical JSON schema defined; covers metadata, sandbox setup, validation rules, and per-model execution/cost metrics; prototyped using a real-session audio-transcription task.
- [Representative Sampling Strategy](.scratch/bench-suite/issues/04-sampling-strategy.md) — stratified sampling by category; target size of 20 tasks proportional to corpus volume; dynamic growth policy to auto-incorporate new sessions.
- [DoD Verification Mechanism](.scratch/bench-suite/issues/05-dod-verification.md) — deterministic checks (file existence, content, JSON values) to ensure absolute reproducibility, zero API costs, and automated speed.
- [Ranking & Composite Score Model](.scratch/bench-suite/issues/06-ranking-model.md) — primary sorting by Average Success Rate (task completeness %), with Cost-Effectiveness (total earned ROI / total cost USD) as secondary tie-breaker. Both static HTML and Markdown reports generated.

## Not yet specified

- How the evaluation runner replays tasks against live models (prompt construction, context window management)
- Duplicate-prevention registry format and lookup semantics

## Out of scope

- GitLab / GitHub integration (no remote on this repo)
- Cross-provider benchmarking (OpenAI, Anthropic) — may be a future effort
- Building or running the actual benchmarking suite (this effort produces the spec only)
