"""Run Review Pack writer: shape, caps, sentinels, path layout."""

from __future__ import annotations

import json
from pathlib import Path

from bench_suite.config import resolve_run_review_caps
from bench_suite.evaluator import Evaluator, strip_diagnostic_fields
from bench_suite.registry import registry_key
from bench_suite.run_review import (
    make_run_id,
    model_key_urlsafe,
    write_run_review_pack,
)


def _execution(**overrides):
    base = {
        "model_name": "gemini-3.5-flash",
        "model_config": {"thinking_level": "high"},
        "input_tokens": 1000,
        "output_tokens": 200,
        "tool_calls": 3,
        "cost_usd": 0.05,
        "latency_seconds": 2.5,
    }
    base.update(overrides)
    return base


def _eval_and_pack(
    tmp_path: Path,
    offline_fixture: dict,
    *,
    sandbox_extra: dict[str, bytes] | None = None,
    model_response: str = "hello response",
    caps: dict | None = None,
    files_written: list[str] | None = None,
) -> dict:
    sandbox = tmp_path / "sandbox"
    out = sandbox / "output"
    out.mkdir(parents=True)
    (out / "summary.json").write_text(
        json.dumps({"status": "ok", "greeting": "Hello bench-suite"}),
        encoding="utf-8",
    )
    if sandbox_extra:
        for rel, data in sandbox_extra.items():
            p = sandbox / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    result = Evaluator().evaluate(
        offline_fixture,
        sandbox,
        _execution(),
        timestamp="2026-07-18T19:59:38Z",
        model_response=model_response,
    )
    runs_root = tmp_path / "runs"
    pack = write_run_review_pack(
        task=offline_fixture,
        evaluation_result=result,
        sandbox_root=sandbox,
        model_response=model_response,
        repo_root=tmp_path,
        runs_root=runs_root,
        runs_rel=".scratch/bench-suite/runs",
        caps=caps or resolve_run_review_caps(None),
        files_parsed=True,
        files_written=files_written or ["output/summary.json"],
        run_id=make_run_id("2026-07-18T19:59:38Z", suffix="a3f1c2b0"),
    )
    return {"result": result, "pack": pack, "sandbox": sandbox, "runs_root": runs_root}


def test_make_run_id_format() -> None:
    rid = make_run_id("2026-07-18T19:59:38Z", suffix="a3f1c2b0")
    assert rid == "20260718T195938Z_a3f1c2b0"
    assert model_key_urlsafe("gemini-3.5-flash:6584ecca") == "gemini-3.5-flash__6584ecca"


def test_pack_layout_and_manifest_shape(tmp_path: Path, offline_fixture: dict) -> None:
    out = _eval_and_pack(tmp_path, offline_fixture)
    pack = out["pack"]
    pack_dir = Path(pack["pack_dir"])

    assert pack["run_id"] == "20260718T195938Z_a3f1c2b0"
    key = registry_key("gemini-3.5-flash", {"thinking_level": "high"})
    assert pack["run_pack_path"] == (
        f".scratch/bench-suite/runs/offline_golden_01/{key}/20260718T195938Z_a3f1c2b0"
    )
    assert (pack_dir / "manifest.json").is_file()
    assert (pack_dir / "response.txt").is_file()
    assert (pack_dir / "files").is_dir()
    assert (pack_dir / "files" / "output" / "summary.json").is_file()
    assert not (pack_dir / "judge.json").exists()  # no llm_judge ran

    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == pack["run_id"]
    assert manifest["task_id"] == "offline_golden_01"
    assert len(manifest["rule_outcomes"]) == len(manifest["validation_rules_snapshot"])
    assert len(manifest["rule_outcomes"]) == 3
    assert all(
        set(o) >= {"index", "type", "passed", "detail"} for o in manifest["rule_outcomes"]
    )
    assert all(o["passed"] for o in manifest["rule_outcomes"])
    assert manifest["artifacts"]["judge"] is None
    assert "truncation" in manifest
    assert manifest["truncation"]["truncated"] is False
    assert set(manifest["metrics"]) == {
        "completeness_percent",
        "input_tokens",
        "output_tokens",
        "tool_calls",
        "cost_usd",
        "latency_seconds",
        "earned_roi",
        "cost_effectiveness_roi_per_usd",
    }
    assert (pack_dir / "response.txt").read_text(encoding="utf-8") == "hello response"


def test_response_cap_appends_sentinel(tmp_path: Path, offline_fixture: dict) -> None:
    long = "x" * 200
    caps = resolve_run_review_caps(
        None,
        overrides={
            "max_response_bytes": 50,
            "max_file_bytes": 10_000,
            "max_files": 100,
            "max_pack_bytes": 1_000_000,
        },
    )
    out = _eval_and_pack(
        tmp_path, offline_fixture, model_response=long, caps=caps
    )
    pack_dir = Path(out["pack"]["pack_dir"])
    body = (pack_dir / "response.txt").read_text(encoding="utf-8")
    assert "RUN_REVIEW_TRUNCATED" in body
    assert "reason=max_response_bytes" in body
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["truncation"]["truncated"] is True
    assert manifest["truncation"]["response"]["truncated"] is True
    assert manifest["truncation"]["response"]["reason"] == "max_response_bytes"
    assert manifest["truncation"]["response"]["original_bytes"] == 200


def test_max_files_omits_with_inventory(tmp_path: Path, offline_fixture: dict) -> None:
    extra = {
        "a.txt": b"aaa",
        "b.txt": b"bbb",
        "c.txt": b"ccc",
    }
    caps = resolve_run_review_caps(
        None,
        overrides={
            "max_response_bytes": 10_000,
            "max_file_bytes": 10_000,
            "max_files": 2,
            "max_pack_bytes": 1_000_000,
        },
    )
    # summary.json + a,b,c = 4 files; keep 2
    out = _eval_and_pack(tmp_path, offline_fixture, sandbox_extra=extra, caps=caps)
    pack_dir = Path(out["pack"]["pack_dir"])
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    files_meta = {f["path"]: f for f in manifest["truncation"]["files"]}
    # All inventory paths present
    assert "a.txt" in files_meta
    assert "b.txt" in files_meta
    assert "c.txt" in files_meta
    assert "output/summary.json" in files_meta
    stored = [f for f in files_meta.values() if f["status"] == "stored"]
    omitted = [f for f in files_meta.values() if f["status"] == "omitted"]
    assert len(stored) == 2
    assert len(omitted) == 2
    assert all(f["reason"] == "max_files" for f in omitted)
    # Lex order: a.txt, b.txt stored; c.txt and output/summary.json omitted
    assert files_meta["a.txt"]["status"] == "stored"
    assert files_meta["b.txt"]["status"] == "stored"
    assert files_meta["c.txt"]["status"] == "omitted"


def test_max_file_bytes_text_sentinel(tmp_path: Path, offline_fixture: dict) -> None:
    big = ("line\n" * 200).encode("utf-8")
    caps = resolve_run_review_caps(
        None,
        overrides={
            "max_response_bytes": 100_000,
            "max_file_bytes": 80,
            "max_files": 100,
            "max_pack_bytes": 1_000_000,
        },
    )
    out = _eval_and_pack(
        tmp_path,
        offline_fixture,
        sandbox_extra={"big.txt": big},
        caps=caps,
    )
    pack_dir = Path(out["pack"]["pack_dir"])
    body = (pack_dir / "files" / "big.txt").read_text(encoding="utf-8")
    assert "RUN_REVIEW_TRUNCATED" in body
    assert "reason=max_file_bytes" in body
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    meta = next(f for f in manifest["truncation"]["files"] if f["path"] == "big.txt")
    assert meta["status"] == "truncated"
    assert meta["reason"] == "max_file_bytes"


def test_binary_truncate_no_sentinel(tmp_path: Path, offline_fixture: dict) -> None:
    data = b"\x00\x01\x02" + b"x" * 200
    caps = resolve_run_review_caps(
        None,
        overrides={
            "max_response_bytes": 100_000,
            "max_file_bytes": 50,
            "max_files": 100,
            "max_pack_bytes": 1_000_000,
        },
    )
    out = _eval_and_pack(
        tmp_path,
        offline_fixture,
        sandbox_extra={"blob.bin": data},
        caps=caps,
    )
    pack_dir = Path(out["pack"]["pack_dir"])
    stored = (pack_dir / "files" / "blob.bin").read_bytes()
    assert b"RUN_REVIEW_TRUNCATED" not in stored
    assert len(stored) == 50
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    meta = next(f for f in manifest["truncation"]["files"] if f["path"] == "blob.bin")
    assert meta["status"] == "truncated"
    assert meta["reason"] == "max_file_bytes"


def test_caps_off_never_truncates(tmp_path: Path, offline_fixture: dict) -> None:
    long = "y" * 5000
    caps = resolve_run_review_caps(None, caps_off=True)
    out = _eval_and_pack(
        tmp_path, offline_fixture, model_response=long, caps=caps
    )
    pack_dir = Path(out["pack"]["pack_dir"])
    body = (pack_dir / "response.txt").read_text(encoding="utf-8")
    assert body == long
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["truncation"]["truncated"] is False
    assert all(v is None for v in manifest["truncation"]["caps"].values())


def test_fail_closed_judge_no_judge_json(tmp_path: Path, offline_fixture: dict) -> None:
    task = dict(offline_fixture)
    task["validation_rules"] = list(task["validation_rules"]) + [
        {"type": "llm_judge", "rubric": "good", "min_score": 0.7}
    ]
    sandbox = tmp_path / "sandbox"
    out = sandbox / "output"
    out.mkdir(parents=True)
    (out / "summary.json").write_text(
        json.dumps({"status": "ok", "greeting": "Hello bench-suite"}),
        encoding="utf-8",
    )
    result = Evaluator().evaluate(
        task, sandbox, _execution(), timestamp="2026-07-18T19:59:38Z"
    )
    pack = write_run_review_pack(
        task=task,
        evaluation_result=result,
        sandbox_root=sandbox,
        model_response="",
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        runs_rel=".scratch/bench-suite/runs",
        caps=resolve_run_review_caps(None),
        run_id=make_run_id("2026-07-18T19:59:38Z", suffix="deadbeef"),
    )
    pack_dir = Path(pack["pack_dir"])
    assert not (pack_dir / "judge.json").exists()
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["judge"] is None
    judge_outcomes = [o for o in manifest["rule_outcomes"] if o["type"] == "llm_judge"]
    assert len(judge_outcomes) == 1
    assert judge_outcomes[0]["detail"]["judge_ran"] is False
    assert judge_outcomes[0]["detail"]["reason"] == "judge_unavailable"
    # strip diagnostics leaves no private keys
    clean = strip_diagnostic_fields(result)
    assert "_rule_outcomes" not in clean
