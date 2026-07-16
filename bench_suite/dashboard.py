"""Dashboard generator: leaderboard.md + static index.html."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def aggregate_models(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate evaluation_results across tasks into per model×config rows."""
    buckets: dict[tuple[str, str], dict[str, Any]] = {}

    for task in tasks:
        for result in task.get("evaluation_results") or []:
            model_name = result["model_name"]
            model_config = result["model_config"]
            config_key = json.dumps(model_config, sort_keys=True, separators=(",", ":"))
            key = (model_name, config_key)
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "model_name": model_name,
                    "model_config": model_config,
                    "success_rates": [],
                    "total_cost_usd": 0.0,
                    "total_earned_roi": 0.0,
                    "latencies": [],
                }
                buckets[key] = bucket
            bucket["success_rates"].append(float(result["completeness_percent"]))
            bucket["total_cost_usd"] += float(result["cost_usd"])
            bucket["total_earned_roi"] += float(result["earned_roi"])
            bucket["latencies"].append(float(result["latency_seconds"]))

    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        rates = bucket["success_rates"]
        total_cost = bucket["total_cost_usd"]
        total_roi = bucket["total_earned_roi"]
        avg_success = sum(rates) / len(rates) if rates else 0.0
        avg_cost_eff = (total_roi / total_cost) if total_cost else 0.0
        avg_latency = sum(bucket["latencies"]) / len(bucket["latencies"]) if bucket["latencies"] else 0.0
        rows.append(
            {
                "model_name": bucket["model_name"],
                "model_config": bucket["model_config"],
                "avg_success_rate": avg_success,
                "total_cost_usd": total_cost,
                "total_earned_roi": total_roi,
                "avg_cost_effectiveness": avg_cost_eff,
                "avg_latency_seconds": avg_latency,
            }
        )

    rows.sort(key=lambda r: (-r["avg_success_rate"], -r["avg_cost_effectiveness"]))
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return rows


def render_leaderboard_md(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Leaderboard",
        "",
        "| Rank | Model | Config | Avg Success | Total Cost | Total ROI | Cost-Eff (ROI/$) |",
        "|------|-------|--------|-------------|------------|-----------|------------------|",
    ]
    for row in rows:
        config = json.dumps(row["model_config"], sort_keys=True, separators=(",", ":"))
        lines.append(
            f"| {row['rank']} "
            f"| {row['model_name']} "
            f"| `{config}` "
            f"| {row['avg_success_rate']:.1f}% "
            f"| ${row['total_cost_usd']:.4f} "
            f"| {row['total_earned_roi']:.1f} "
            f"| {row['avg_cost_effectiveness']:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def scatter_points(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One point per task × model run: cost_usd vs completeness_percent."""
    points: list[dict[str, Any]] = []
    for task in tasks:
        task_id = task.get("task_id", "?")
        for result in task.get("evaluation_results") or []:
            points.append(
                {
                    "x": round(float(result["cost_usd"]), 6),
                    "y": round(float(result["completeness_percent"]), 2),
                    "label": f"{result['model_name']} / {task_id}",
                }
            )
    return points


def render_index_html(
    rows: list[dict[str, Any]],
    *,
    chartjs_cdn: str,
    scatter: list[dict[str, Any]] | None = None,
) -> str:
    labels = [r["model_name"] for r in rows]
    success = [round(r["avg_success_rate"], 2) for r in rows]
    scatter = scatter if scatter is not None else []
    table_rows = []
    for row in rows:
        config = json.dumps(row["model_config"], sort_keys=True, separators=(",", ":"))
        table_rows.append(
            "<tr>"
            f"<td>{row['rank']}</td>"
            f"<td>{_esc(row['model_name'])}</td>"
            f"<td><code>{_esc(config)}</code></td>"
            f"<td data-value=\"{row['avg_success_rate']}\">{row['avg_success_rate']:.1f}%</td>"
            f"<td data-value=\"{row['total_cost_usd']}\">${row['total_cost_usd']:.4f}</td>"
            f"<td data-value=\"{row['total_earned_roi']}\">{row['total_earned_roi']:.1f}</td>"
            f"<td data-value=\"{row['avg_cost_effectiveness']}\">{row['avg_cost_effectiveness']:.1f}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bench Suite Leaderboard</title>
  <script src="{_esc(chartjs_cdn)}"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #0f172a; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin: 1.5rem 0; }}
    canvas {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.5rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 0.5rem 0.75rem; text-align: left; }}
    th {{ background: #f1f5f9; cursor: pointer; user-select: none; }}
    th:hover {{ background: #e2e8f0; }}
  </style>
</head>
<body>
  <h1>Bench Suite Leaderboard</h1>
  <p>Ranked by average success rate, then cost-effectiveness (ROI/$). Click column headers to sort.</p>
  <div class="charts">
    <div><canvas id="successChart"></canvas></div>
    <div><canvas id="scatterChart"></canvas></div>
  </div>
  <table id="leaderboard">
    <thead>
      <tr>
        <th data-col="0">Rank</th><th data-col="1">Model</th><th data-col="2">Config</th>
        <th data-col="3">Avg Success</th><th data-col="4">Total Cost</th>
        <th data-col="5">Total ROI</th><th data-col="6">Cost-Eff (ROI/$)</th>
      </tr>
    </thead>
    <tbody>
      {"".join(table_rows)}
    </tbody>
  </table>
  <script>
    const labels = {json.dumps(labels)};
    const success = {json.dumps(success)};
    const scatter = {json.dumps(scatter)};
    new Chart(document.getElementById('successChart'), {{
      type: 'bar',
      data: {{
        labels,
        datasets: [{{ label: 'Avg Success %', data: success, backgroundColor: '#38bdf8' }}]
      }},
      options: {{ scales: {{ y: {{ beginAtZero: true, max: 100 }} }} }}
    }});
    new Chart(document.getElementById('scatterChart'), {{
      type: 'scatter',
      data: {{
        datasets: [{{
          label: 'Cost vs Success (per task × model)',
          data: scatter,
          backgroundColor: '#818cf8'
        }}]
      }},
      options: {{
        scales: {{
          x: {{ title: {{ display: true, text: 'Cost (USD)' }} }},
          y: {{ title: {{ display: true, text: 'Success %' }}, beginAtZero: true, max: 100 }}
        }},
        plugins: {{
          tooltip: {{
            callbacks: {{
              label: (ctx) => {{
                const p = ctx.raw;
                return p.label + ': $' + p.x + ', ' + p.y + '%';
              }}
            }}
          }}
        }}
      }}
    }});
    // Simple column sort for the leaderboard table
    document.querySelectorAll('#leaderboard th').forEach((th) => {{
      th.addEventListener('click', () => {{
        const table = document.getElementById('leaderboard');
        const tbody = table.tBodies[0];
        const col = Number(th.dataset.col);
        const rows = Array.from(tbody.rows);
        const asc = th.dataset.dir !== 'asc';
        th.dataset.dir = asc ? 'asc' : 'desc';
        rows.sort((a, b) => {{
          const av = a.cells[col].dataset.value ?? a.cells[col].textContent;
          const bv = b.cells[col].dataset.value ?? b.cells[col].textContent;
          const an = Number(av), bn = Number(bv);
          if (!Number.isNaN(an) && !Number.isNaN(bn)) return asc ? an - bn : bn - an;
          return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
        }});
        rows.forEach((r) => tbody.appendChild(r));
      }});
    }});
  </script>
</body>
</html>
"""


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class DashboardGenerator:
    def __init__(self, *, chartjs_cdn: str) -> None:
        self.chartjs_cdn = chartjs_cdn

    def generate(
        self,
        tasks: list[dict[str, Any]],
        *,
        leaderboard_path: Path,
        html_path: Path,
    ) -> list[dict[str, Any]]:
        rows = aggregate_models(tasks)
        leaderboard_path = Path(leaderboard_path)
        html_path = Path(html_path)
        leaderboard_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        leaderboard_path.write_text(render_leaderboard_md(rows), encoding="utf-8")
        html_path.write_text(
            render_index_html(
                rows,
                chartjs_cdn=self.chartjs_cdn,
                scatter=scatter_points(tasks),
            ),
            encoding="utf-8",
        )
        return rows
