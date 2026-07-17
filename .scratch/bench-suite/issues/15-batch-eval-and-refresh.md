# 15 — Batch eval CLI + additive corpus refresh

**What to build:** Operator-facing commands to (1) evaluate one model × model_config across every task in the dataset, skipping pairs already in the registry, and (2) re-run ingest → classify → stratified sample so new Antigravity sessions produce additional pending-review candidates without replacing existing dataset tasks. After a batch, the dashboard reflects the full set of new results.

**Blocked by:** 13 — Eval first corpus-derived task end-to-end; 14 — Optional llm_judge validation rule

**Status:** done

- [x] A batch eval command runs all dataset tasks for a given model and model_config
- [x] Already-evaluated pairs are skipped via the registry (no redundant API spend)
- [x] A refresh command discovers new transcripts, classifies them, and writes new pending-review candidates only
- [x] Existing TaskEntries and evaluation_results are never overwritten by refresh
- [x] After batch eval, leaderboard.md and index.html reflect updated aggregates for all models

## Delivered

### `bench-suite batch-eval`
- Runs every TaskEntry in `dataset/tasks` for `--model` × `--model-config`
- Skips registry hits (unless `--force`); continues after per-task failures
- Regenerates `leaderboard.md` + `index.html` even when all pairs were skipped

### `bench-suite refresh`
- Discovers `transcript_full.jsonl` under `--transcripts-root` and/or explicit paths
- Ingest → classify → stratified sample into `pending-review/`
- Skips conversation_ids already in the dataset; never mutates dataset tasks
- `write_pending` is idempotent (does not clobber human-in-progress pending files)
- `--target` is dataset capacity; only remaining slots are filled

### Tests
`tests/test_batch_and_refresh.py` — 9 tests covering batch skip/run/board and refresh additive behavior.
