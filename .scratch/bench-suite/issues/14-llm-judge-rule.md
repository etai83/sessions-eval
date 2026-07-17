# 14 — Optional llm_judge validation rule

**What to build:** When a TaskEntry validation rule has type llm_judge, call a fixed reference Gemini model (from config—never the model under evaluation) with the rubric against the run’s output; count the rule as passed when the judge score is at least min_score, and fold that into completeness_percent like any other rule.

**Blocked by:** 10 — Live Gemini runner for the fixture task

**Status:** done

- [x] llm_judge rules invoke the configured reference model, not the model under test
- [x] Score is 0.0–1.0; rule passes when score ≥ min_score
- [x] Pass/fail contributes to completeness_percent and downstream ROI metrics
- [x] Tasks with only deterministic rules are unaffected when no llm_judge rule is present
- [x] Behaviour is covered by a test or demo task that includes an llm_judge rule

## Delivered

- **Evaluator** accepts optional `judge_client` + `judge_model` (default `gemini-2.0-flash` from config). Without a client, llm_judge fails closed (offline-safe).
- **Scoring**: `parse_judge_score` extracts 0.0–1.0 from JSON or bare float; pass when `score ≥ min_score`.
- **Live path** wires the suite Gemini client as judge transport with `config.llm_judge_reference_model` — never the model under evaluation.
- **Demo task**: `.scratch/bench-suite/fixtures/llm_judge_demo_task.json` (3 deterministic rules + 1 llm_judge).
- **Tests**: unit coverage in `tests/test_evaluator.py`; live integration in `tests/test_live.py`.
