# 05 — DoD Verification Mechanism

Type: grilling
Status: resolved
Blocked by: 03

## Question

How is a model's output verified against a task's Definition of Done? Three candidate mechanisms need a decision:

1. **LLM-as-judge**: a separate model call scores the output against the DoD. Flexible but costly and non-deterministic.
2. **Deterministic check**: exact string match, regex, JSON schema validation, or file diff. Cheap and reproducible but brittle.
3. **Human-in-the-loop**: you review and score. Ground-truth accurate but slow and not scalable.
4. **Hybrid**: deterministic pass/fail gate, with LLM-as-judge for partial-credit scoring.

Which mechanism is acceptable for this spec? What are the non-negotiable constraints (e.g., reproducibility, cost per eval run)?

## Answer

### Verification Mechanism
- **Decision**: Deterministic checks (`file_exists`, `file_contains`, `json_field_value`).
- **Rationale**: Keeps the evaluation pipeline lightweight, fast, cheap, and 100% reproducible. Avoids API cost, latency, and non-determinism associated with LLM-as-judge methods.
- **Constraints**: Evaluated outcomes must be programmatically checkable without human or model-based verification. All tasks in the dataset must define deterministic verification rules that evaluate sandbox state changes (files, structures, outputs).
