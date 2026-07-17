# 13 — Eval first corpus-derived task end-to-end

**What to build:** Run the first real, corpus-derived TaskEntry (from ticket 12) through the live Gemini runner, deterministic evaluator, registry, and dashboard so a non-fixture task appears on the leaderboard with real cost and success metrics.

**Blocked by:** 10 — Live Gemini runner for the fixture task; 12 — Stratified sample into pending-review + first real TaskEntry

**Status:** done

- [x] The promoted real TaskEntry can be executed with the live runner (sandbox setup_steps + Gemini API)
- [x] EvaluationResult is appended with completeness, cost, tokens, latency, and ROI fields
- [x] Registry records the model×config × task_id pair
- [x] Leaderboard and dashboard include this task’s contribution to the model’s aggregates
- [x] Re-running the same pair is blocked by the registry

## Delivered

- **TaskEntry** `trading_btc_backtest_01` authored from fixture transcript `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` (BTC backtest session): human-authored DoD, `roi_value`, budgets, and setup_steps. Canonical file: `.scratch/bench-suite/fixtures/trading_btc_backtest_01.json` (dataset/tasks is gitignored runtime state — promote or `live-run --task` writes there).
- **Live path** accepts `--task-id` / `task_id=` so corpus tasks load from the dataset store without a path.
- **E2E tests** (`tests/test_first_real_task.py`): live run → full EvaluationResult → registry → multi-task leaderboard aggregates → duplicate block; setup_steps applied before the model call.

Operator:
```
bench-suite promote .scratch/bench-suite/fixtures/trading_btc_backtest_01.json   # once
# or: live-run --task .scratch/bench-suite/fixtures/trading_btc_backtest_01.json  (auto-saves into dataset)
bench-suite live-run --task-id trading_btc_backtest_01   # requires GEMINI_API_KEY
```
