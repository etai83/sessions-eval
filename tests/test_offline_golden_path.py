"""Integration: offline golden path end-to-end (no Gemini API)."""

from __future__ import annotations

import json
from pathlib import Path

from bench_suite.offline import run_offline_golden_path
from bench_suite.registry import Registry, registry_key
from bench_suite.store import DatasetStore


def test_offline_golden_path_end_to_end(tmp_suite: Path) -> None:
    result = run_offline_golden_path(repo_root=tmp_suite)

    assert result["task_id"] == "offline_golden_01"
    assert result["skipped_duplicate"] is False
    er = result["evaluation_result"]
    assert er["completeness_percent"] == 100.0
    assert er["earned_roi"] == 10.0
    assert er["cost_effectiveness_roi_per_usd"] == 200.0  # 10 / 0.05

    # Task persisted in dataset store
    store = DatasetStore(
        tmp_suite / ".scratch/bench-suite/dataset/tasks",
        tmp_suite / ".scratch/bench-suite/task-schema.json",
    )
    saved = store.load("offline_golden_01")
    assert len(saved["evaluation_results"]) == 1
    assert saved["evaluation_results"][0]["model_name"] == "gemini-3.5-flash"

    # Registry recorded
    reg = Registry(tmp_suite / ".scratch/bench-suite/registry.json")
    assert reg.has_run("gemini-3.5-flash", {"thinking_level": "high"}, "offline_golden_01")
    key = registry_key("gemini-3.5-flash", {"thinking_level": "high"})
    raw = json.loads((tmp_suite / ".scratch/bench-suite/registry.json").read_text(encoding="utf-8"))
    assert "offline_golden_01" in raw[key]

    # Dashboard outputs
    md = (tmp_suite / ".scratch/bench-suite/leaderboard.md").read_text(encoding="utf-8")
    assert "gemini-3.5-flash" in md
    assert "100.0%" in md
    html = (tmp_suite / ".scratch/bench-suite/index.html").read_text(encoding="utf-8")
    assert "chart.js@4.4.1" in html

    # Re-run must not double-count evaluation_results
    result2 = run_offline_golden_path(repo_root=tmp_suite)
    assert result2["skipped_duplicate"] is True
    saved2 = store.load("offline_golden_01")
    assert len(saved2["evaluation_results"]) == 1
