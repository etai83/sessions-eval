# 11 — Transcript → classified TaskCandidate

**What to build:** Turn one real Antigravity transcript_full.jsonl into a classified TaskCandidate: extract conversation_id, timestamp, user request (USER_REQUEST XML tags stripped), tool invocations, and session duration; then assign taxonomy labels (output_type, complexity, intent) and domain labels used for stratification via deterministic keyword rules only—no LLM call.

**Blocked by:** 09 — Offline golden path: schema store, score fixture task, publish board

**Status:** ready-for-agent

- [ ] Ingester reads transcript_full.jsonl (not the compact transcript) and emits a TaskCandidate with the extractable fields from the spec
- [ ] User request text has USER_REQUEST XML tags stripped
- [ ] Tool invocations are derived from PLANNER_RESPONSE tool_calls (and sequential result steps where applicable)
- [ ] Classifier maps user_request → taxonomy + domain labels using a keyword rules mapping (deterministic, zero API cost)
- [ ] Behaviour is verifiable on a known transcript or fixture without sampling or evaluation
