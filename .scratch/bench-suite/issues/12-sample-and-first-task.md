# 12 — Stratified sample into pending-review + first real TaskEntry

**What to build:** From a pool of classified TaskCandidates, select a stratified sample proportional by domain category toward a total of ~20 tasks, skip candidates already in the dataset (by conversation_id), write selected candidates to pending-review for human DoD authoring, and promote one reviewed candidate into the dataset as a full TaskEntry with human-authored validation_rules, roi_value, and token/tool budgets.

**Blocked by:** 11 — Transcript → classified TaskCandidate

**Status:** done

- [x] Sampler groups candidates by domain.category and fills proportional quotas toward ~20 total tasks
- [x] Candidates already present in the dataset (by conversation_id) are not re-selected
- [x] Selected candidates land in pending-review awaiting human fields
- [x] One candidate is promoted to the dataset as a schema-valid TaskEntry with authored validation_rules, roi_value, and budgets
- [x] Existing dataset tasks are never replaced (additive growth only)
