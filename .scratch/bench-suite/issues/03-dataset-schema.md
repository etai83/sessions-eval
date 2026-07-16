# 03 — Dataset Entry Schema (JSON/CSV)

Type: prototype
Status: resolved
Blocked by: 01, 02

## Question

What is the canonical schema for a single task entry in the benchmark dataset? The schema must cover:
- Task identification (id, source transcript, timestamp)
- Classification fields (from the taxonomy decided in 02)
- Task input (the reconstructed prompt/context a model will receive)
- Definition of Done (DoD): the objective completion criterion
- Scoring rubric: the quantifiable metric fields
- Evaluation results: per-model execution record (cost, tokens, latency, score)

Produce a concrete prototype: a JSON schema + one filled example entry from a real Antigravity session.

## Answer

### Canonical JSON Schema

The formal schema is saved as [task-schema.json](file:///Users/itaiharpaz/Code/sessions-eval/.scratch/bench-suite/task-schema.json). It defines the layout of a benchmark task including both task metadata, execution sandboxing setup, validation assertions (DoD), and historical evaluation results:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TaskEntry",
  "type": "object",
  "properties": {
    "task_id": {
      "type": "string",
      "description": "Unique identifier for the benchmark task"
    },
    "name": {
      "type": "string",
      "description": "Human-readable name of the task"
    },
    "category": {
      "type": "string",
      "enum": [
        "Trading",
        "Data Engineering",
        "AI",
        "Software Dev",
        "General",
        "Git Operations",
        "Knowledge Management",
        "Agent Meta",
        "Agent Infrastructure",
        "Finance"
      ],
      "description": "Top-level domain classification from taxonomy"
    },
    "subcategory": {
      "type": "string",
      "enum": [
        "Backtesting",
        "Data Extraction",
        "Model Training",
        "Audio Processing",
        "Feature Dev",
        "Debugging",
        "Rule Aggregation",
        "Workspace Auth",
        "Obsidian",
        "Analysis",
        "Jesse TV Alignment",
        "Repository Management",
        "Skill Customization",
        "Miscellaneous"
      ],
      "description": "Second-level domain classification from taxonomy"
    },
    "source": {
      "type": "object",
      "properties": {
        "conversation_id": {
          "type": "string",
          "pattern": "^[a-f0-9\\-]{36}$",
          "description": "UUID of the original Antigravity session"
        },
        "transcript_path": {
          "type": "string",
          "description": "Relative or absolute path to the transcript_full.jsonl"
        },
        "timestamp": {
          "type": "string",
          "format": "date-time",
          "description": "Timestamp when the original session was run"
        }
      },
      "required": ["conversation_id", "transcript_path", "timestamp"]
    },
    "required_tools": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "List of core tools required by the agent to solve this task"
    },
    "required_skills": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "List of specialized agent skills consulted or triggered"
    },
    "prompt": {
      "type": "string",
      "description": "The exact query or instruction the agent receives"
    },
    "roi_value": {
      "type": "number",
      "description": "Quantified value weight of task completion in USD/utility score"
    },
    "target_token_budget": {
      "type": "integer",
      "description": "Target/maximum token budget for optimal solution"
    },
    "target_tool_call_budget": {
      "type": "integer",
      "description": "Target/maximum tool call budget for optimal solution"
    },
    "setup_steps": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "action": {
            "type": "string",
            "enum": ["write_file", "run_command"]
          },
          "path": {
            "type": "string",
            "description": "File path (if write_file)"
          },
          "content": {
            "type": "string",
            "description": "File content (if write_file)"
          },
          "command": {
            "type": "string",
            "description": "Command string to run (if run_command)"
          }
        },
        "required": ["action"]
      },
      "description": "Steps required to set up the sandbox environment before execution"
    },
    "validation_rules": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": ["file_exists", "file_contains", "json_field_value"]
          },
          "path": {
            "type": "string",
            "description": "Path to the file being validated"
          },
          "text": {
            "type": "string",
            "description": "Target text expected in the file (for file_contains)"
          },
          "field": {
            "type": "string",
            "description": "JSON field name to check (for json_field_value)"
          },
          "expected": {
            "description": "Expected value of the JSON field (for json_field_value)"
          }
        },
        "required": ["type", "path"]
      },
      "description": "Definition of Done (DoD) assertions"
    },
    "evaluation_results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "model_name": {
            "type": "string"
          },
          "thinking_level": {
            "type": "string"
          },
          "completeness_percent": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 100.0
          },
          "tokens_used": {
            "type": "integer"
          },
          "tool_calls": {
            "type": "integer"
          },
          "cost_usd": {
            "type": "number"
          },
          "earned_roi": {
            "type": "number"
          },
          "cost_effectiveness_roi_per_usd": {
            "type": "number"
          },
          "timestamp": {
            "type": "string",
            "format": "date-time"
          }
        },
        "required": [
          "model_name",
          "thinking_level",
          "completeness_percent",
          "tokens_used",
          "tool_calls",
          "cost_usd",
          "earned_roi",
          "cost_effectiveness_roi_per_usd",
          "timestamp"
        ]
      },
      "description": "History of model evaluations on this specific task"
    }
  },
  "required": [
    "task_id",
    "name",
    "category",
    "subcategory",
    "source",
    "prompt",
    "roi_value",
    "target_token_budget",
    "target_tool_call_budget",
    "setup_steps",
    "validation_rules"
  ]
}
```

### Real-Session Filled Example Task Entry

This task entry is modeled from the real Antigravity session log `session_log_20260702_0903.md` (Conversation ID: `d315da50-63ae-418d-a449-fea46d406104`):

```json
{
  "task_id": "data_audio_transcription_01",
  "name": "Morning Walk Audio Download, Transcription, and Obsidian Daily Note Creation",
  "category": "Data Engineering",
  "subcategory": "Data Extraction",
  "source": {
    "conversation_id": "d315da50-63ae-418d-a449-fea46d406104",
    "transcript_path": "~/.gemini/antigravity/brain/d315da50-63ae-418d-a449-fea46d406104/.system_generated/logs/transcript_full.jsonl",
    "timestamp": "2026-07-02T06:02:08Z"
  },
  "required_tools": [
    "browser_subagent",
    "run_command",
    "write_to_file",
    "view_file"
  ],
  "required_skills": [
    "transcribe",
    "obsidian-markdown"
  ],
  "prompt": "* Connect to my Google Drive and transcribe the m4a file named \"morning walk <with the current date>\". Only if you found one, continue to the next steps, otherwise return a message to the user \"No file was found\".\n* Use /browser to overcome and approve my user authentication.\n* Close the opened port that is running \"./dev.sh\" command after finishing the transcription.\n* Run /obsidian-markdown skill to create a new daily out of the transcription.",
  "roi_value": 60.0,
  "target_token_budget": 15000,
  "target_tool_call_budget": 20,
  "setup_steps": [
    {
      "action": "write_file",
      "path": "sandbox_audio_env/audio_config.json",
      "content": "{\n  \"audio_source\": \"Morning walk 02072026.m4a\"\n}"
    }
  ],
  "validation_rules": [
    {
      "type": "file_exists",
      "path": "/Users/itaiharpaz/Code/second_brain/Daily/2026-07-02.md"
    },
    {
      "type": "file_contains",
      "path": "/Users/itaiharpaz/Code/second_brain/Daily/2026-07-02.md",
      "text": "# 📅 2026-07-02"
    },
    {
      "type": "file_contains",
      "path": "/Users/itaiharpaz/Code/second_brain/Daily/2026-07-02.md",
      "text": "## ☀️ Morning Standup"
    }
  ],
  "evaluation_results": [
    {
      "model_name": "Gemini 3.5 Flash",
      "thinking_level": "High",
      "completeness_percent": 100.0,
      "tokens_used": 14440,
      "tool_calls": 67,
      "cost_usd": 0.2836,
      "earned_roi": 60.0,
      "cost_effectiveness_roi_per_usd": 211.56,
      "timestamp": "2026-07-02T09:03:00+03:00"
    }
  ]
}
```


---

## Reconciled Answer (wayfinder session — supersedes prior draft)

### Changes vs. prior draft

| Field | Change | Reason |
|---|---|---|
| `category` / `subcategory` | Moved under `domain` object; kept | Ticket 02 chose output_type/complexity/intent as primary; domain kept for legacy cross-reference |
| `taxonomy` (new) | Added: `{output_type, complexity, intent}` | Ticket 02 decision |
| `thinking_level` | Renamed to `model_config: object` (key-value) | Future-proof for non-Gemini providers |
| `tokens_used` | Split into `input_tokens` + `output_tokens` | More granular; maps to Gemini API response fields |
| `latency_seconds` | Added to `evaluation_results` | Explicit decision in this session |
| `llm_judge` | Added as validation_rule type (with `rubric` + `min_score`) | Covers subjective quality checking |

### Schema files
- Full JSON Schema: [task-schema.json](file:///Users/itaiharpaz/Code/sessions-eval/.scratch/bench-suite/task-schema.json)
- Filled example: [task-example.json](file:///Users/itaiharpaz/Code/sessions-eval/.scratch/bench-suite/task-example.json)
