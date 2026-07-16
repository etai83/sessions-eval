# 09 — Offline golden path: schema store, score fixture task, publish board

**What to build:** A working offline evaluation path: load and validate a fixture TaskEntry against the canonical schema, score it with deterministic DoD rules only (file exists, file contains, JSON field value), compute completeness and ROI metrics from a fake execution record (no live model), record the run in the registry so it cannot be double-counted, and publish a ranked Markdown leaderboard plus a static HTML dashboard from that result.

**Blocked by:** None — can start immediately

**Status:** done

- [x] Project skeleton and config exist with open-question defaults from the spec (sandbox isolation, registry hash, judge model reserved for later, Chart.js pin, etc.)
- [x] A fixture TaskEntry round-trips through schema validation and dataset store load/save
- [x] Deterministic DoD rules produce a correct EvaluationResult (completeness_percent, earned_roi, cost_effectiveness) for a prepared sandbox state
- [x] Registry records the model×config × task_id pair after the run
- [x] leaderboard.md and index.html reflect the fixture result with lexicographic ranking (avg success primary, cost-effectiveness secondary)
- [x] Full path is verifiable without any Gemini API call
