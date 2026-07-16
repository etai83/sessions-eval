"""Dashboard seam: ranking and output files."""

from __future__ import annotations

from pathlib import Path

from bench_suite.dashboard import DashboardGenerator, aggregate_models


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
                    "model_name": "gemini-2.5-flash",
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
    assert "gemini-2.5-flash" in text
    assert "100.0%" in text
    html_text = html.read_text(encoding="utf-8")
    assert "chart.js@4.4.1" in html_text
    assert "successChart" in html_text
    assert "per task × model" in html_text
    assert "data-col=" in html_text
