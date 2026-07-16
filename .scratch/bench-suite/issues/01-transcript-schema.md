# 01 — Transcript JSONL Schema Analysis

Type: research
Status: open

## Question

What is the exact schema of an Antigravity transcript JSONL? What fields exist on each step, what types and values do `type`, `source`, `status`, `content`, and `tool_calls` take, and what information is reliably extractable for task reconstruction (user intent, model actions, tool invocations, cost/token metadata)?

Read real transcript files at `~/.gemini/antigravity/brain/` to answer this — don't infer from the system prompt description alone.

Status: resolved

## Answer

### Complete Field Inventory

| Field | Type | Always Present | Notes |
|---|---|---|---|
| `step_index` | `integer` | ✅ | 0-based sequential |
| `source` | `string enum` | ✅ | `USER_EXPLICIT`, `SYSTEM`, `MODEL` |
| `type` | `string enum` | ✅ | see taxonomy below |
| `status` | `string enum` | ✅ | `DONE`, `RUNNING` |
| `created_at` | `string (ISO 8601 UTC)` | ✅ | wall-clock timestamp |
| `content` | `string` | conditional | absent on empty PLANNER_RESPONSE and CONVERSATION_HISTORY |
| `tool_calls` | `array` | conditional | only on PLANNER_RESPONSE with tool invocations |
| `thinking` | `string` | conditional | model reasoning block when present |
| `error` / `error_code` | `string / int` | conditional | ERROR_MESSAGE steps only |
| `truncated_fields` | `array` | conditional | compact file only — signals clipped fields |

### Step-Type Taxonomy

| `type` | `source` | Meaning |
|---|---|---|
| `USER_INPUT` | `USER_EXPLICIT` | User request — canonical task entry point |
| `CONVERSATION_HISTORY` | `SYSTEM` | Prior-turn marker; no content |
| `CHECKPOINT` | `SYSTEM` | Context-truncation summary |
| `EPHEMERAL_MESSAGE` | `SYSTEM` | System injections (planning mode etc.) |
| `SYSTEM_MESSAGE` | `SYSTEM` | Background task notifications |
| `ERROR_MESSAGE` | `SYSTEM` | Tool or model error |
| `PLANNER_RESPONSE` | `MODEL` | Model response/tool calls |
| `VIEW_FILE` / `LIST_DIRECTORY` / `RUN_COMMAND` / `CODE_ACTION` / `GENERIC` / `ASK_QUESTION` / `INVOKE_SUBAGENT` | `MODEL` | Tool result steps |

### What Is Reliably Extractable

- ✅ **User intent**: `source=USER_EXPLICIT, type=USER_INPUT` → `content` inside `<USER_REQUEST>` XML
- ✅ **Tool invocations**: `PLANNER_RESPONSE` steps with `tool_calls` array — use `transcript_full.jsonl` (compact file double-escapes args)
- ✅ **Tool results**: sequential MODEL steps following each PLANNER_RESPONSE
- ✅ **Session duration**: `created_at` on first and last steps
- ❌ **Cost/token data**: **completely absent** — no `usage`, `cost`, `inputTokens`, `outputTokens` fields exist anywhere

### Critical gaps

- Cost/tokens must come from an **external source** (captured at API call time; not in transcript)
- No session-level metadata header — conversation ID must be inferred from file path
- No explicit tool_call_id linking a call to its result step — infer by position
- `transcript_full.jsonl` must be used (compact file double-escapes tool args)

### Recommended Minimal Task Extraction Schema

```
task_id           = <conv-id>/<first-USER_INPUT-step_index>
conversation_id   = <uuid from directory name>
transcript_path   = transcript_full.jsonl path
started_at        = created_at of first USER_INPUT
ended_at          = created_at of last step
user_request      = content of USER_INPUT, stripped of XML wrapper
tool_invocations  = [{step_index, tool_name, args, result_step_index}]
model_thinking    = [thinking strings from PLANNER_RESPONSE steps]
cost_usd          = null  (not in transcript)
input_tokens      = null  (not in transcript)
output_tokens     = null  (not in transcript)
```
