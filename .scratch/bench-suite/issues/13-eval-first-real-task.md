# 13 — Eval first corpus-derived task end-to-end

**What to build:** Run the first real, corpus-derived TaskEntry (from ticket 12) through the live Gemini runner, deterministic evaluator, registry, and dashboard so a non-fixture task appears on the leaderboard with real cost and success metrics.

**Blocked by:** 10 — Live Gemini runner for the fixture task; 12 — Stratified sample into pending-review + first real TaskEntry

**Status:** ready-for-agent

- [ ] The promoted real TaskEntry can be executed with the live runner (sandbox setup_steps + Gemini API)
- [ ] EvaluationResult is appended with completeness, cost, tokens, latency, and ROI fields
- [ ] Registry records the model×config × task_id pair
- [ ] Leaderboard and dashboard include this task’s contribution to the model’s aggregates
- [ ] Re-running the same pair is blocked by the registry
