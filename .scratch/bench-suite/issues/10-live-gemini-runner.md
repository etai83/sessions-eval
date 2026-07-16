# 10 — Live Gemini runner for the fixture task

**What to build:** Replace the offline fake execution record with a real Gemini run of the fixture task: apply setup_steps in an isolated sandbox, call the Gemini API with the chosen model and model_config, capture input/output tokens, cost_usd, and latency_seconds, refuse the run if the registry already has that model×config × task pair, then land a real EvaluationResult on the board through the same evaluator and dashboard path as ticket 09.

**Blocked by:** 09 — Offline golden path: schema store, score fixture task, publish board

**Status:** ready-for-agent

- [ ] setup_steps execute in a per-task sandbox before the model runs
- [ ] Gemini API call returns model output plus tokens, cost_usd, and latency_seconds
- [ ] Registry guard aborts with a clear warning when the pair was already evaluated
- [ ] Successful live run appends EvaluationResult to the fixture TaskEntry and updates the registry
- [ ] Regenerated leaderboard/dashboard include the live run metrics
