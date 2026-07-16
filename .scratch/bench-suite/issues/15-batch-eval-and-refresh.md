# 15 — Batch eval CLI + additive corpus refresh

**What to build:** Operator-facing commands to (1) evaluate one model × model_config across every task in the dataset, skipping pairs already in the registry, and (2) re-run ingest → classify → stratified sample so new Antigravity sessions produce additional pending-review candidates without replacing existing dataset tasks. After a batch, the dashboard reflects the full set of new results.

**Blocked by:** 13 — Eval first corpus-derived task end-to-end; 14 — Optional llm_judge validation rule

**Status:** ready-for-agent

- [ ] A batch eval command runs all dataset tasks for a given model and model_config
- [ ] Already-evaluated pairs are skipped via the registry (no redundant API spend)
- [ ] A refresh command discovers new transcripts, classifies them, and writes new pending-review candidates only
- [ ] Existing TaskEntries and evaluation_results are never overwritten by refresh
- [ ] After batch eval, leaderboard.md and index.html reflect updated aggregates for all models
