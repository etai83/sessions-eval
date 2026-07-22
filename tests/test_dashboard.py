"""Dashboard seam: ranking and output files."""

from __future__ import annotations

from pathlib import Path

from bench_suite.dashboard import (
    DashboardGenerator,
    aggregate_models,
    select_latest,
    select_latest_per_model_config,
)


def test_select_latest_by_timestamp_then_append_index() -> None:
    results = [
        {
            "model_name": "m",
            "model_config": {},
            "timestamp": "2026-07-18T10:00:00Z",
            "completeness_percent": 50.0,
            "cost_usd": 0.1,
            "earned_roi": 5.0,
            "latency_seconds": 1.0,
        },
        {
            "model_name": "m",
            "model_config": {},
            "timestamp": "2026-07-18T12:00:00Z",
            "completeness_percent": 80.0,
            "cost_usd": 0.2,
            "earned_roi": 8.0,
            "latency_seconds": 1.0,
        },
        {
            "model_name": "m",
            "model_config": {},
            "timestamp": "2026-07-18T12:00:00Z",
            "completeness_percent": 100.0,
            "cost_usd": 0.3,
            "earned_roi": 10.0,
            "latency_seconds": 1.0,
        },
    ]
    latest = select_latest(results, model_name="m", model_config={})
    assert latest is not None
    assert latest["completeness_percent"] == 100.0  # later append wins on equal timestamp
    only = select_latest_per_model_config(results)
    assert len(only) == 1
    assert only[0]["completeness_percent"] == 100.0


def test_aggregate_uses_latest_only() -> None:
    tasks = [
        {
            "task_id": "t1",
            "evaluation_results": [
                {
                    "model_name": "model-a",
                    "model_config": {},
                    "completeness_percent": 50.0,
                    "cost_usd": 1.0,
                    "earned_roi": 5.0,
                    "latency_seconds": 1.0,
                    "timestamp": "2026-07-18T10:00:00Z",
                },
                {
                    "model_name": "model-a",
                    "model_config": {},
                    "completeness_percent": 100.0,
                    "cost_usd": 0.10,
                    "earned_roi": 10.0,
                    "latency_seconds": 1.0,
                    "timestamp": "2026-07-18T12:00:00Z",
                },
            ],
        }
    ]
    rows = aggregate_models(tasks)
    assert len(rows) == 1
    assert rows[0]["avg_success_rate"] == 100.0
    assert rows[0]["total_cost_usd"] == 0.10  # not 1.10
    assert rows[0]["total_earned_roi"] == 10.0


def test_lexicographic_ranking() -> None:
    tasks = [
        {
            "task_id": "t1",
            "evaluation_results": [
                {
                    "model_name": "model-a",
                    "model_config": {"thinking_level": "low"},
                    "completeness_percent": 80.0,
                    "cost_usd": 0.10,
                    "earned_roi": 8.0,
                    "latency_seconds": 1.0,
                },
                {
                    "model_name": "model-b",
                    "model_config": {"thinking_level": "high"},
                    "completeness_percent": 95.0,
                    "cost_usd": 0.50,
                    "earned_roi": 9.5,
                    "latency_seconds": 2.0,
                },
            ],
        },
        {
            "task_id": "t2",
            "evaluation_results": [
                {
                    "model_name": "model-a",
                    "model_config": {"thinking_level": "low"},
                    "completeness_percent": 100.0,
                    "cost_usd": 0.05,
                    "earned_roi": 10.0,
                    "latency_seconds": 1.0,
                },
                {
                    "model_name": "model-b",
                    "model_config": {"thinking_level": "high"},
                    "completeness_percent": 95.0,
                    "cost_usd": 0.50,
                    "earned_roi": 9.5,
                    "latency_seconds": 2.0,
                },
            ],
        },
    ]
    rows = aggregate_models(tasks)
    # model-b: avg success 95, model-a: avg success 90 → b first
    assert rows[0]["model_name"] == "model-b"
    assert rows[0]["rank"] == 1
    assert rows[1]["model_name"] == "model-a"
    # cost-effectiveness secondary when success ties
    tasks_tie = [
        {
            "task_id": "t1",
            "evaluation_results": [
                {
                    "model_name": "cheap",
                    "model_config": {},
                    "completeness_percent": 100.0,
                    "cost_usd": 0.01,
                    "earned_roi": 10.0,
                    "latency_seconds": 1.0,
                },
                {
                    "model_name": "expensive",
                    "model_config": {},
                    "completeness_percent": 100.0,
                    "cost_usd": 1.0,
                    "earned_roi": 10.0,
                    "latency_seconds": 1.0,
                },
            ],
        }
    ]
    ranked = aggregate_models(tasks_tie)
    assert ranked[0]["model_name"] == "cheap"
    assert ranked[0]["avg_cost_effectiveness"] > ranked[1]["avg_cost_effectiveness"]


def test_writes_leaderboard_and_html(tmp_path: Path) -> None:
    tasks = [
        {
            "task_id": "offline_golden_01",
            "evaluation_results": [
                {
                    "model_name": "gemini-3.5-flash",
                    "model_config": {"thinking_level": "high"},
                    "completeness_percent": 100.0,
                    "cost_usd": 0.05,
                    "earned_roi": 10.0,
                    "latency_seconds": 2.5,
                }
            ],
        }
    ]
    md = tmp_path / "leaderboard.md"
    html = tmp_path / "index.html"
    gen = DashboardGenerator(
        chartjs_cdn="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"
    )
    rows = gen.generate(tasks, leaderboard_path=md, html_path=html)
    assert rows[0]["rank"] == 1
    text = md.read_text(encoding="utf-8")
    assert "gemini-3.5-flash" in text
    assert "100.0%" in text
    html_text = html.read_text(encoding="utf-8")
    assert "chart.js@4.4.1" in html_text
    assert "successChart" in html_text
    assert "latest per task × model" in html_text
    assert "data-col=" in html_text
    assert 'href="sessions/index.html"' in html_text
    assert 'href="session-logs/index.html"' in html_text
    assert "Antigravity Conversations" in html_text
    assert "Session Logs" in html_text
    # Multi-page review surface
    review = tmp_path / "review"
    assert (review / "tasks" / "offline_golden_01.html").is_file()
    assert (review / "models").is_dir()
    model_pages = list((review / "models").glob("*.html"))
    assert model_pages
    run_pages = list((review / "runs").rglob("*.html"))
    assert run_pages
    # Missing pack callout for legacy metrics-only rows
    legacy_html = run_pages[0].read_text(encoding="utf-8")
    assert "Metrics only — no Run Review Pack" in legacy_html
    assert "--force" in legacy_html
