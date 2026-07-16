# 08 — Write the Spec Document

Type: task
Status: claimed
Blocked by: 07

## Question

No remaining decisions. Assemble all resolved ticket answers into the final, hand-off-ready spec document at `.scratch/bench-suite/spec.md`. The spec must include:

- Executive summary (destination, scope, constraints)
- Dataset schema (JSON schema + CSV column spec)
- Task entry template with DoD and rubric fields
- Sampling strategy (algorithm, target counts, refresh policy)
- DoD verification mechanism (with decision rationale)
- Composite score formula and dashboard format
- Component architecture diagram and interface spec
- Open implementation questions for the implementer

This is the terminal ticket — closing it closes the map.

Status: resolved

## Answer

Spec assembled at [spec.md](file:///Users/itaiharpaz/Code/sessions-eval/.scratch/bench-suite/spec.md).

Covers all 10 sections:
1. Executive summary + scope constraints
2. Source data — transcript schema, extraction algorithm, cost/token gap
3. Task taxonomy — 3 axes (output_type, complexity, intent)
4. Dataset schema — field inventory, validation rule types, scoring formulas
5. Sampling strategy — stratified 20 tasks, dynamic growth, human review gate
6. DoD verification — deterministic primary + optional llm_judge
7. Ranking & dashboard — lexicographic sort, leaderboard.md + index.html
8. Component architecture — 8 components, file layout, registry key format
9. Open questions for implementer (6 deferred decisions with recommendations)
10. Glossary

This is the terminal ticket. Map is complete.
