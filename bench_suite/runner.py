"""Gemini Runner: sandbox setup, API call, cost/token/latency capture."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from bench_suite.sandbox import apply_setup_steps, write_sandbox_files


class AlreadyEvaluatedError(RuntimeError):
    """Raised when registry already has this model×config × task_id pair."""


# Default USD per 1M tokens (approximate public Gemini list prices; override in config).
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input_per_mtok": 0.15, "output_per_mtok": 0.60},
    "gemini-2.0-flash": {"input_per_mtok": 0.10, "output_per_mtok": 0.40},
    "gemini-2.5-pro": {"input_per_mtok": 1.25, "output_per_mtok": 10.0},
}

RESPONSE_PROTOCOL = """You are completing a benchmark task inside a filesystem sandbox.

Respond with ONLY a single JSON object (no markdown fences), shape:
{
  "files": [{"path": "relative/path", "content": "file contents"}],
  "tool_calls": 0
}

Rules:
- Paths are relative to the sandbox root.
- Write every file needed to satisfy the user task / Definition of Done.
- Prefer exact content required by the task prompt.
"""


@dataclass
class GenerateResult:
    text: str
    input_tokens: int
    output_tokens: int
    raw: Any = None


class GeminiClient(Protocol):
    def generate(
        self,
        *,
        model_name: str,
        prompt: str,
        system_instruction: str,
        model_config: dict[str, Any],
    ) -> GenerateResult: ...


@dataclass
class MockGeminiClient:
    """Deterministic client for tests — no network."""

    text: str
    input_tokens: int = 100
    output_tokens: int = 50
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate(
        self,
        *,
        model_name: str,
        prompt: str,
        system_instruction: str,
        model_config: dict[str, Any],
    ) -> GenerateResult:
        self.calls.append(
            {
                "model_name": model_name,
                "prompt": prompt,
                "system_instruction": system_instruction,
                "model_config": model_config,
            }
        )
        return GenerateResult(
            text=self.text,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


class GoogleGenaiClient:
    """Live client using the google-genai SDK (requires GEMINI_API_KEY or GOOGLE_API_KEY)."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError(
                "Missing API key: set GEMINI_API_KEY or GOOGLE_API_KEY for live Gemini runs"
            )
        from google import genai

        self._client = genai.Client(api_key=key)

    def generate(
        self,
        *,
        model_name: str,
        prompt: str,
        system_instruction: str,
        model_config: dict[str, Any],
    ) -> GenerateResult:
        from google.genai import types

        config_kwargs: dict[str, Any] = {"system_instruction": system_instruction}
        # Pass through known generation knobs; ignore unknown model_config keys.
        if "temperature" in model_config:
            config_kwargs["temperature"] = model_config["temperature"]
        if "max_output_tokens" in model_config:
            config_kwargs["max_output_tokens"] = model_config["max_output_tokens"]
        if "thinking_level" in model_config:
            # Best-effort mapping for SDKs that expose ThinkingConfig.
            level = str(model_config["thinking_level"]).upper()
            thinking_cls = getattr(types, "ThinkingConfig", None)
            if thinking_cls is not None:
                config_kwargs["thinking_config"] = thinking_cls(
                    thinking_budget=-1 if level in {"HIGH", "DEFAULT"} else 0
                )

        response = self._client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        text = getattr(response, "text", None) or ""
        usage = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0
        return GenerateResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw=response,
        )


def estimate_cost_usd(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    pricing: dict[str, dict[str, float]] | None = None,
) -> float:
    table = pricing or DEFAULT_PRICING
    rates = table.get(model_name) or table.get("default") or {
        "input_per_mtok": 0.15,
        "output_per_mtok": 0.60,
    }
    cost = (input_tokens / 1_000_000) * float(rates["input_per_mtok"]) + (
        output_tokens / 1_000_000
    ) * float(rates["output_per_mtok"])
    return round(cost, 6)


def parse_model_files_response(text: str) -> tuple[list[dict[str, str]], int]:
    """Extract files + tool_calls from model JSON (tolerates optional fences)."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find first {...} blob
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return [], 0
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return [], 0
    files = data.get("files") or []
    normalized: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict) or "path" not in item:
            continue
        normalized.append({"path": str(item["path"]), "content": str(item.get("content") or "")})
    tool_calls = int(data.get("tool_calls") or 0)
    return normalized, tool_calls


@dataclass
class RunResult:
    model_response: str
    execution: dict[str, Any]
    files_written: list[str]
    files_parsed: bool


class Runner:
    """Owns Gemini API call + cost/token/latency capture (only place cost exists)."""

    def __init__(
        self,
        client: GeminiClient,
        *,
        pricing: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.client = client
        self.pricing = pricing or DEFAULT_PRICING

    def run(
        self,
        task: dict[str, Any],
        sandbox: Path,
        *,
        model_name: str,
        model_config: dict[str, Any] | None = None,
        registry: Any | None = None,
    ) -> RunResult:
        """
        Apply setup_steps, call Gemini, apply returned files to sandbox.

        If ``registry`` is provided, refuses the API call when this
        model×config × task_id is already recorded (architecture guard).
        """
        model_config = dict(model_config or {})
        sandbox = Path(sandbox)
        task_id = task["task_id"]

        if registry is not None and registry.has_run(model_name, model_config, task_id):
            raise AlreadyEvaluatedError(
                f"Registry already has {model_name} × {task_id} "
                f"(config={model_config}); refusing live API call to avoid double spend."
            )

        apply_setup_steps(task, sandbox, allow_commands=True)

        prompt = task["prompt"]
        t0 = time.perf_counter()
        gen = self.client.generate(
            model_name=model_name,
            prompt=prompt,
            system_instruction=RESPONSE_PROTOCOL,
            model_config=model_config,
        )
        latency = time.perf_counter() - t0

        files, tool_calls = parse_model_files_response(gen.text)
        files_parsed = bool(files)
        if files:
            write_sandbox_files(sandbox, files)

        cost = estimate_cost_usd(
            model_name, gen.input_tokens, gen.output_tokens, pricing=self.pricing
        )
        execution = {
            "model_name": model_name,
            "model_config": model_config,
            "input_tokens": gen.input_tokens,
            "output_tokens": gen.output_tokens,
            "tool_calls": tool_calls,
            "cost_usd": cost,
            "latency_seconds": round(latency, 4),
        }
        return RunResult(
            model_response=gen.text,
            execution=execution,
            files_written=[f["path"] for f in files],
            files_parsed=files_parsed,
        )
