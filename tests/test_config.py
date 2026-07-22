"""Config seam: open-question defaults."""

from __future__ import annotations

from pathlib import Path

from bench_suite.config import DEFAULT_CONFIG, load_config


def test_defaults_include_open_question_resolutions() -> None:
    assert DEFAULT_CONFIG["sandbox_isolation"] == "temp_dir"
    assert DEFAULT_CONFIG["llm_judge_reference_model"] == "gemini-3.1-flash-lite"
    assert DEFAULT_CONFIG["dynamic_growth_trigger"] == "manual"
    assert "chart.js@4.4.1" in DEFAULT_CONFIG["chartjs_cdn"]
    assert DEFAULT_CONFIG["registry_hash"]["truncate_hex"] == 8
    assert DEFAULT_CONFIG["paths"]["runs"] == ".scratch/bench-suite/runs"
    assert DEFAULT_CONFIG["paths"]["dataset_results"] == ".scratch/bench-suite/dataset/results"
    assert DEFAULT_CONFIG["run_review_caps"]["max_files"] == 100
    assert DEFAULT_CONFIG["session_review"]["caps"]["max_steps"] == 200
    assert DEFAULT_CONFIG["session_review"]["caps"]["max_transcript_bytes"] == 524_288
    assert DEFAULT_CONFIG["session_review"]["caps"]["max_sidecar_bytes"] == 65_536
    assert DEFAULT_CONFIG["session_review"]["output"]["sessions_root"] == (
        ".scratch/bench-suite/sessions"
    )


def test_load_config_resolves_paths(tmp_suite: Path) -> None:
    cfg = load_config(repo_root=tmp_suite)
    assert Path(cfg["_resolved_paths"]["dataset_tasks"]).is_dir()
    assert cfg["sandbox_isolation"] == "temp_dir"
    assert "runs" in cfg["_resolved_paths"]
