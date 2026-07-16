# 14 — Optional llm_judge validation rule

**What to build:** When a TaskEntry validation rule has type llm_judge, call a fixed reference Gemini model (from config—never the model under evaluation) with the rubric against the run’s output; count the rule as passed when the judge score is at least min_score, and fold that into completeness_percent like any other rule.

**Blocked by:** 10 — Live Gemini runner for the fixture task

**Status:** ready-for-agent

- [ ] llm_judge rules invoke the configured reference model, not the model under test
- [ ] Score is 0.0–1.0; rule passes when score ≥ min_score
- [ ] Pass/fail contributes to completeness_percent and downstream ROI metrics
- [ ] Tasks with only deterministic rules are unaffected when no llm_judge rule is present
- [ ] Behaviour is covered by a test or demo task that includes an llm_judge rule
