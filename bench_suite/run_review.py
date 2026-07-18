"""Run Review Pack writer: multi-file on-disk artifact for one inference."""

from __future__ import annotations

import copy
import json
import secrets
from pathlib import Path
from typing import Any

from bench_suite.config import DEFAULT_RUN_REVIEW_CAPS, resolve_run_review_caps
from bench_suite.registry import registry_key

TRUNCATION_SENTINEL_TMPL = (
    "<<RUN_REVIEW_TRUNCATED original_bytes={original} stored_bytes={stored} reason={reason}>>"
)
MANIFEST_HEADROOM = 64 * 1024  # reserve space so manifest never needs truncating


def make_run_id(timestamp: str, *, suffix: str | None = None) -> str:
    """
    Form ``{YYYYMMDDTHHMMSSZ}_{8 lowercase hex}`` from an EvaluationResult timestamp.

    Example: ``2026-07-18T19:59:38Z`` → ``20260718T195938Z_a3f1c2b0``.
    """
    ts = timestamp.strip()
    if ts.endswith("Z"):
        body = ts[:-1]
    elif "+" in ts:
        body = ts.split("+", 1)[0]
    else:
        body = ts
    # Drop fractional seconds: 2026-07-18T19:59:38[.ffffff]
    body = body.split(".", 1)[0]
    compact = body.replace("-", "").replace(":", "") + "Z"
    hex_suffix = suffix if suffix is not None else secrets.token_hex(4)
    return f"{compact}_{hex_suffix}"


def model_key_urlsafe(model_key: str) -> str:
    """Replace ``:`` with ``__`` for HTML path segments only."""
    return model_key.replace(":", "__")


def pack_relative_path(
    task_id: str,
    model_key: str,
    run_id: str,
    *,
    runs_rel: str = ".scratch/bench-suite/runs",
) -> str:
    """Repo-relative pack root path (no trailing slash)."""
    runs = runs_rel.rstrip("/")
    return f"{runs}/{task_id}/{model_key}/{run_id}"


def is_binary_bytes(data: bytes) -> bool:
    """Treat as binary if NUL in first 8 KiB or content is not valid UTF-8."""
    sample = data[:8192]
    if b"\x00" in sample:
        return True
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _truncate_text(
    text: str,
    max_bytes: int | None,
    *,
    reason: str,
) -> tuple[str, dict[str, Any]]:
    """
    Cap text by UTF-8 byte length; append sentinel when truncated.

    Returns (stored_text, meta) where meta has truncated/original_bytes/stored_bytes/reason.
    """
    original = text.encode("utf-8")
    original_bytes = len(original)
    if max_bytes is None or original_bytes <= max_bytes:
        return text, {
            "truncated": False,
            "original_bytes": original_bytes,
            "stored_bytes": original_bytes,
            "reason": None,
        }

    # Keep a UTF-8-safe prefix of at most max_bytes content bytes, then append sentinel.
    prefix = original[:max_bytes]
    # Back up if we split a multi-byte character
    while prefix and (prefix[-1] & 0xC0) == 0x80:
        prefix = prefix[:-1]
    # Provisional sentinel with stored_bytes unknown; iterate once for exact stored_bytes.
    # stored_bytes includes sentinel; content prefix may need shrink so total ≈ max + sentinel.
    # Spec: prefix keep max_file_bytes of content, then append sentinel (extra on top).
    content = prefix.decode("utf-8", errors="ignore")
    # First pass sentinel using content length as stored estimate
    provisional_stored = len(prefix)
    sentinel = TRUNCATION_SENTINEL_TMPL.format(
        original=original_bytes,
        stored=provisional_stored,  # will rewrite
        reason=reason,
    )
    # Final stored_bytes = content + sentinel
    final_stored = len(prefix) + len(sentinel.encode("utf-8"))
    sentinel = TRUNCATION_SENTINEL_TMPL.format(
        original=original_bytes,
        stored=final_stored,
        reason=reason,
    )
    final_stored = len(prefix) + len(sentinel.encode("utf-8"))
    # Align sentinel's stored_bytes field with actual (one more pass if digit length shifted)
    sentinel = TRUNCATION_SENTINEL_TMPL.format(
        original=original_bytes,
        stored=final_stored,
        reason=reason,
    )
    stored_text = content + sentinel
    final_stored = _utf8_len(stored_text)
    # If digit width of stored changed the length, fix once more
    sentinel = TRUNCATION_SENTINEL_TMPL.format(
        original=original_bytes,
        stored=final_stored,
        reason=reason,
    )
    stored_text = content + sentinel
    final_stored = _utf8_len(stored_text)
    return stored_text, {
        "truncated": True,
        "original_bytes": original_bytes,
        "stored_bytes": final_stored,
        "reason": reason,
    }


def _truncate_binary(
    data: bytes,
    max_bytes: int | None,
    *,
    reason: str,
) -> tuple[bytes, dict[str, Any]]:
    original_bytes = len(data)
    if max_bytes is None or original_bytes <= max_bytes:
        return data, {
            "status": "stored",
            "original_bytes": original_bytes,
            "stored_bytes": original_bytes,
            "reason": None,
        }
    prefix = data[:max_bytes]
    return prefix, {
        "status": "truncated",
        "original_bytes": original_bytes,
        "stored_bytes": len(prefix),
        "reason": reason,
    }


def inventory_sandbox(sandbox_root: Path) -> list[tuple[str, Path, int]]:
    """Sorted (rel_path, abs_path, original_bytes) for every file under sandbox."""
    root = Path(sandbox_root)
    if not root.is_dir():
        return []
    items: list[tuple[str, Path, int]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        items.append((rel, path, size))
    return items


def _assign_judges_indices(
    rule_outcomes: list[dict[str, Any]],
    judges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Set judges_index on llm_judge outcomes that ran, matching judges[] order."""
    by_rule: dict[int, int] = {}
    for j_idx, entry in enumerate(judges):
        by_rule[int(entry["rule_index"])] = j_idx
    out: list[dict[str, Any]] = []
    for outcome in rule_outcomes:
        o = copy.deepcopy(outcome)
        if o.get("type") == "llm_judge" and o.get("detail", {}).get("judge_ran"):
            idx = int(o["index"])
            if idx in by_rule:
                o["detail"]["judges_index"] = by_rule[idx]
        out.append(o)
    return out


def write_run_review_pack(
    *,
    task: dict[str, Any],
    evaluation_result: dict[str, Any],
    sandbox_root: Path,
    model_response: str,
    repo_root: Path,
    runs_root: Path,
    runs_rel: str,
    caps: dict[str, int | None] | None = None,
    rule_outcomes: list[dict[str, Any]] | None = None,
    judges: list[dict[str, Any]] | None = None,
    files_parsed: bool = True,
    files_written: list[str] | None = None,
    run_id: str | None = None,
    truncate_hex: int = 8,
) -> dict[str, Any]:
    """
    Write a Run Review Pack under ``{runs_root}/{task_id}/{model_key}/{run_id}/``.

    Returns ``{"run_id", "run_pack_path", "pack_dir", "manifest"}``.
    Caps apply only here; evaluation already saw full sandbox/response.
    """
    task_id = str(task["task_id"])
    model_name = str(evaluation_result["model_name"])
    model_config = dict(evaluation_result.get("model_config") or {})
    timestamp = str(evaluation_result["timestamp"])
    mkey = registry_key(model_name, model_config, truncate_hex=truncate_hex)
    rid = run_id or make_run_id(timestamp)
    effective_caps = (
        dict(caps)
        if caps is not None
        else resolve_run_review_caps(None)
    )

    pack_dir = Path(runs_root) / task_id / mkey / rid
    pack_dir.mkdir(parents=True, exist_ok=True)
    files_dir = pack_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    max_response = effective_caps.get("max_response_bytes")
    max_file = effective_caps.get("max_file_bytes")
    max_files = effective_caps.get("max_files")
    max_pack = effective_caps.get("max_pack_bytes")

    # --- 1. Inventory ---
    inv = inventory_sandbox(sandbox_root)

    # --- 2–3. Cap file bodies + max_files in lex order ---
    file_plans: list[dict[str, Any]] = []
    for rel, abs_path, original_bytes in inv:
        try:
            data = abs_path.read_bytes()
        except OSError:
            data = b""
            original_bytes = 0
        binary = is_binary_bytes(data)
        plan: dict[str, Any] = {
            "path": rel,
            "binary": binary,
            "original_bytes": original_bytes,
            "data": data,
            "status": "stored",
            "reason": None,
            "stored_bytes": original_bytes,
            "body": data,
        }
        if max_file is not None and original_bytes > max_file:
            if binary:
                body, meta = _truncate_binary(data, max_file, reason="max_file_bytes")
                plan["body"] = body
                plan["status"] = meta["status"]
                plan["reason"] = meta["reason"]
                plan["stored_bytes"] = meta["stored_bytes"]
            else:
                text = data.decode("utf-8")
                stored, meta = _truncate_text(text, max_file, reason="max_file_bytes")
                plan["body"] = stored.encode("utf-8")
                plan["status"] = "truncated" if meta["truncated"] else "stored"
                plan["reason"] = meta["reason"]
                plan["stored_bytes"] = meta["stored_bytes"]
        else:
            plan["body"] = data
            plan["stored_bytes"] = original_bytes
        file_plans.append(plan)

    # Apply max_files: store bodies until limit; remainder omitted
    if max_files is not None:
        kept = 0
        for plan in file_plans:
            if kept < max_files:
                kept += 1
            else:
                plan["status"] = "omitted"
                plan["reason"] = "max_files"
                plan["stored_bytes"] = 0
                plan["body"] = b""

    # --- 4. Cap response ---
    response_text = model_response if model_response is not None else ""
    response_stored, response_meta = _truncate_text(
        response_text,
        max_response,
        reason="max_response_bytes",
    )

    # --- 5. Cap judge strings ---
    raw_judges = list(judges or evaluation_result.get("_judges") or [])
    outcomes = list(rule_outcomes or evaluation_result.get("_rule_outcomes") or [])
    outcomes = _assign_judges_indices(outcomes, raw_judges)

    judge_entries_meta: list[dict[str, Any]] = []
    capped_judges: list[dict[str, Any]] = []
    judge_any_truncated = False
    for j_idx, entry in enumerate(raw_judges):
        e = copy.deepcopy(entry)
        entry_meta: dict[str, Any] = {"judges_index": j_idx, "fields": {}}
        for field in ("rationale", "raw_response"):
            value = str(e.get(field) or "")
            stored, meta = _truncate_text(value, max_file, reason="max_file_bytes")
            e[field] = stored
            entry_meta["fields"][field] = meta
            if meta["truncated"]:
                judge_any_truncated = True
        capped_judges.append(e)
        judge_entries_meta.append(entry_meta)

    write_judge = bool(capped_judges)

    # --- 6. max_pack_bytes: omit from end of sorted stored list, then shrink response ---
    def estimate_pack_size(
        plans: list[dict[str, Any]],
        resp: str,
        judge_list: list[dict[str, Any]],
        include_judge: bool,
    ) -> int:
        size = _utf8_len(resp)
        for p in plans:
            if p["status"] != "omitted":
                size += int(p["stored_bytes"])
        if include_judge and judge_list:
            # Approximate judge.json size
            size += _utf8_len(
                json.dumps(
                    {"schema_version": 1, "judges": judge_list},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        size += MANIFEST_HEADROOM
        return size

    if max_pack is not None:
        # Drop file bodies from the end of the sorted stored list
        while (
            estimate_pack_size(file_plans, response_stored, capped_judges, write_judge)
            > max_pack
        ):
            # Find last non-omitted plan
            target_idx = None
            for i in range(len(file_plans) - 1, -1, -1):
                if file_plans[i]["status"] != "omitted":
                    target_idx = i
                    break
            if target_idx is None:
                break
            file_plans[target_idx]["status"] = "omitted"
            file_plans[target_idx]["reason"] = "max_pack_bytes"
            file_plans[target_idx]["stored_bytes"] = 0
            file_plans[target_idx]["body"] = b""

        # Further shrink response if still over
        if (
            estimate_pack_size(file_plans, response_stored, capped_judges, write_judge)
            > max_pack
        ):
            # Compute budget left for response
            other = estimate_pack_size(file_plans, "", capped_judges, write_judge)
            budget = max(0, max_pack - other)
            response_stored, response_meta = _truncate_text(
                response_text,
                budget if budget < (max_response or budget) else max_response,
                reason="max_pack_bytes",
            )
            # If still over due to sentinel growth, force smaller prefix
            while (
                estimate_pack_size(file_plans, response_stored, capped_judges, write_judge)
                > max_pack
                and budget > 0
            ):
                budget = max(0, budget - 64)
                if budget == 0:
                    response_stored, response_meta = _truncate_text(
                        response_text, 0, reason="max_pack_bytes"
                    )
                    break
                response_stored, response_meta = _truncate_text(
                    response_text, budget, reason="max_pack_bytes"
                )

    # --- Write artifacts ---
    (pack_dir / "response.txt").write_text(response_stored, encoding="utf-8")

    for plan in file_plans:
        if plan["status"] == "omitted":
            continue
        dest = files_dir / plan["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(plan["body"])

    if write_judge:
        judge_doc = {"schema_version": 1, "judges": capped_judges}
        (pack_dir / "judge.json").write_text(
            json.dumps(judge_doc, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    truncation_files = [
        {
            "path": p["path"],
            "status": p["status"],
            "original_bytes": p["original_bytes"],
            "stored_bytes": p["stored_bytes"],
            "reason": p["reason"],
        }
        for p in file_plans
    ]

    any_file_truncated = any(f["status"] != "stored" for f in truncation_files)
    truncated_flag = bool(
        response_meta["truncated"] or any_file_truncated or judge_any_truncated
    )

    # Caps recorded as used (null when disabled)
    caps_record: dict[str, Any] = {
        "max_response_bytes": effective_caps.get("max_response_bytes"),
        "max_file_bytes": effective_caps.get("max_file_bytes"),
        "max_files": effective_caps.get("max_files"),
        "max_pack_bytes": effective_caps.get("max_pack_bytes"),
    }

    metrics = {
        "completeness_percent": float(evaluation_result["completeness_percent"]),
        "input_tokens": int(evaluation_result["input_tokens"]),
        "output_tokens": int(evaluation_result["output_tokens"]),
        "tool_calls": int(evaluation_result["tool_calls"]),
        "cost_usd": float(evaluation_result["cost_usd"]),
        "latency_seconds": float(evaluation_result["latency_seconds"]),
        "earned_roi": float(evaluation_result["earned_roi"]),
        "cost_effectiveness_roi_per_usd": float(
            evaluation_result["cost_effectiveness_roi_per_usd"]
        ),
    }

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "task_id": task_id,
        "run_id": rid,
        "model_name": model_name,
        "model_config": model_config,
        "timestamp": timestamp,
        "validation_rules_snapshot": copy.deepcopy(task.get("validation_rules") or []),
        "metrics": metrics,
        "execution": {
            "files_parsed": bool(files_parsed),
            "files_written": list(files_written or []),
        },
        "rule_outcomes": outcomes,
        "artifacts": {
            "response": "response.txt",
            "files_dir": "files",
            "judge": "judge.json" if write_judge else None,
        },
        "truncation": {
            "truncated": truncated_flag,
            "caps": caps_record,
            "response": {
                "truncated": response_meta["truncated"],
                "original_bytes": response_meta["original_bytes"],
                "stored_bytes": response_meta["stored_bytes"],
                "reason": response_meta["reason"],
            },
            "files": truncation_files,
            "judge": {
                "truncated": judge_any_truncated,
                "entries": judge_entries_meta,
            },
        },
    }

    (pack_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rel_path = pack_relative_path(task_id, mkey, rid, runs_rel=runs_rel)
    return {
        "run_id": rid,
        "run_pack_path": rel_path,
        "pack_dir": str(pack_dir),
        "manifest": manifest,
    }


def attach_pack_to_result(
    evaluation_result: dict[str, Any],
    pack_info: dict[str, Any],
) -> dict[str, Any]:
    """Copy EvaluationResult fields and set run_id + run_pack_path from a pack write."""
    from bench_suite.evaluator import strip_diagnostic_fields

    clean = strip_diagnostic_fields(evaluation_result)
    clean["run_id"] = pack_info["run_id"]
    clean["run_pack_path"] = pack_info["run_pack_path"]
    return clean


# Re-export for convenience
__all__ = [
    "DEFAULT_RUN_REVIEW_CAPS",
    "make_run_id",
    "model_key_urlsafe",
    "pack_relative_path",
    "write_run_review_pack",
    "attach_pack_to_result",
    "inventory_sandbox",
    "is_binary_bytes",
]
