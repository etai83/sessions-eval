# 02 — Task Taxonomy & Classification Axes

Type: grilling
Status: claimed
Blocked by: 01

## Question

What are the right classification axes for Antigravity tasks? We need a taxonomy that:
1. Covers the real breadth of your actual workflow (not a theoretical one)
2. Has axes that are mutually discriminating (different tasks land in different buckets)
3. Is coarse enough to be stable (won't need constant revision)

Candidate axes to decide between: by primary skill invoked, by output type (code/doc/plan/research/debug), by agent complexity (single-step vs. multi-agent), by domain (frontend/backend/infra/eval). Which set of axes will actually produce useful groupings for your sessions?

Status: resolved

## Answer

### Decided taxonomy — 3 axes

**Axis 1: `output_type`** (primary — most evaluation signal)
| Value | Meaning |
|---|---|
| `code` | Source files written or modified |
| `plan_or_spec` | Architecture docs, wayfinder maps, specs, ADRs |

Two values. Analysis/research and config/docs do not appear as primary outputs in this workflow.

**Axis 2: `complexity`** (secondary)
| Value | Meaning |
|---|---|
| `single_step` | No or minimal tool use (1-2 calls); rare in practice |
| `multi_tool` | Several tools called sequentially; dominant pattern |
| `multi_agent` | Subagents spawned; uncommon but exists |

**Axis 3: `intent`** (tertiary — meaningful for coding; less so for planning)
| Value | Meaning |
|---|---|
| `generate` | Produce something new from a prompt |
| `modify` | Change existing code or docs |
| `debug` | Diagnose a failure and fix it |
| `research` | Investigate and synthesise findings (answer only, no artifact) |

### Ruled out axes
- **Domain** (frontend/backend/AI/infra): not meaningful for benchmarking — output type + complexity + intent is sufficient.

### Cross-product coverage target
With 2 × 3 × 4 = 24 theoretical cells, many combinations won't exist in practice (e.g., `plan_or_spec × debug` rarely occurs). The sampling strategy (ticket 04) decides which cells to populate and how many tasks per cell.
