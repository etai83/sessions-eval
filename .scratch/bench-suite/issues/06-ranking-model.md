# 06 — Ranking & Composite Score Model

Type: grilling
Status: resolved
Blocked by: 05

## Question

How are models ranked on the dashboard? Three sub-decisions:

1. **Composite score formula**: how do success_rate, cost_per_task, and latency combine into a single rank? Weighted sum? Pareto frontier? Something else?
2. **Weight calibration**: if weighted sum, what are the default weights, and can the user tune them at query time?
3. **Dashboard format**: given the "flat files, no infra" constraint — CLI table (rich/tabulate), static HTML generated from the dataset, or a Markdown report? 

Produce a proposed formula and an example dashboard row so the user can react to it concretely.

## Answer

### 1. Composite Score Formula & Ranking
- **Decision**: Primary sorting by Average Success Rate (task completeness %), with Cost-Effectiveness (total earned ROI / total cost USD) as the secondary tie-breaker.
- **Rationale**: Keeps the ranking simple, objective, and intuitive. Avoids arbitrary weight calibration. Ranks models first by capability (DoD success), then by efficiency (ROI per dollar spent).

### 2. Weight Calibration
- **Decision**: N/A (Lexicographical sorting replaces weighted sum).

### 3. Dashboard Format
- **Decision**: Both static interactive HTML (`index.html`) and Markdown report (`leaderboard.md`).
- **Rationale**: HTML provides rich UI visualization (charts, matrices) for double-click local viewing, while Markdown provides a lightweight, human-readable terminal/repo-friendly format.

### Example Dashboard Row
| Model | Thinking Level | Avg Success | Total Cost (USD) | Total Earned ROI | Cost-Effectiveness (ROI/$) | Rank |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Gemini 3.5 Flash | High | 95.0% | $0.0125 | 450.0 | 36,000.00 | 1 |
| Gemini 3.5 Flash | Low | 95.0% | $0.0050 | 450.0 | 90,000.00 | 2 |
| Gemini 1.5 Flash | Low | 80.0% | $0.0080 | 320.0 | 40,000.00 | 3 |
