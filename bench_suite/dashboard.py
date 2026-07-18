"""Dashboard generator: leaderboard.md + static multi-page run review HTML."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from bench_suite.registry import registry_key
from bench_suite.run_review import model_key_urlsafe


def config_key(model_config: dict[str, Any]) -> str:
    return json.dumps(model_config, sort_keys=True, separators=(",", ":"))


def select_latest(
    results: list[dict[str, Any]],
    *,
    model_name: str,
    model_config: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Ranking run for one model×config: max by (timestamp, append_index).

    Primary: lexicographic max ISO-8601 UTC timestamp.
    Tie-break: maximum append index in the provided list (later write wins).
    """
    cfg_key = config_key(model_config)
    best: tuple[str, int, dict[str, Any]] | None = None
    for append_index, result in enumerate(results):
        if result.get("model_name") != model_name:
            continue
        if config_key(result.get("model_config") or {}) != cfg_key:
            continue
        ts = str(result.get("timestamp") or "")
        candidate = (ts, append_index, result)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    return best[2] if best else None


def select_latest_per_model_config(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One ranking run per model×config group within a single task's results."""
    groups: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
    for append_index, result in enumerate(results):
        name = result["model_name"]
        ck = config_key(result.get("model_config") or {})
        groups.setdefault((name, ck), []).append((append_index, result))
    latest: list[dict[str, Any]] = []
    for items in groups.values():
        best = max(items, key=lambda t: (str(t[1].get("timestamp") or ""), t[0]))
        latest.append(best[1])
    return latest


def is_ranking_run(
    result: dict[str, Any],
    results: list[dict[str, Any]],
) -> bool:
    """True when ``result`` is the ranking (latest) run for its model×config.

    Identity is the object returned by ``select_latest`` (same list element /
    append-index winner), not metric equality — duplicate metrics must not
    both show as ranking.
    """
    latest = select_latest(
        results,
        model_name=result["model_name"],
        model_config=result.get("model_config") or {},
    )
    if latest is None:
        return False
    if latest is result:
        return True
    # Same list element found by append index (defensive if copies appear).
    try:
        return results.index(latest) == results.index(result)
    except ValueError:
        if latest.get("run_id") and result.get("run_id"):
            return latest.get("run_id") == result.get("run_id")
        return False


def aggregate_models(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Aggregate evaluation_results across tasks into per model×config rows.

    Only the **ranking run** (latest) per task × model×config contributes.
    """
    buckets: dict[tuple[str, str], dict[str, Any]] = {}

    for task in tasks:
        results = list(task.get("evaluation_results") or [])
        for result in select_latest_per_model_config(results):
            model_name = result["model_name"]
            model_config = result["model_config"]
            ck = config_key(model_config)
            key = (model_name, ck)
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
        avg_latency = (
            sum(bucket["latencies"]) / len(bucket["latencies"]) if bucket["latencies"] else 0.0
        )
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
    """One point per task × model×config ranking run: cost_usd vs completeness."""
    points: list[dict[str, Any]] = []
    for task in tasks:
        task_id = task.get("task_id", "?")
        results = list(task.get("evaluation_results") or [])
        for result in select_latest_per_model_config(results):
            mkey = registry_key(
                result["model_name"], result.get("model_config") or {}
            )
            points.append(
                {
                    "x": round(float(result["cost_usd"]), 6),
                    "y": round(float(result["completeness_percent"]), 2),
                    "label": f"{result['model_name']} / {task_id}",
                    "task_id": task_id,
                    "model_key_urlsafe": model_key_urlsafe(mkey),
                }
            )
    return points


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def _model_page_href(model_key: str, *, from_index: bool = True) -> str:
    safe = model_key_urlsafe(model_key)
    prefix = "review/models/" if from_index else ""
    return f"{prefix}{safe}.html"


def render_index_html(
    rows: list[dict[str, Any]],
    *,
    chartjs_cdn: str,
    scatter: list[dict[str, Any]] | None = None,
    model_links: dict[str, str] | None = None,
) -> str:
    labels = [r["model_name"] for r in rows]
    success = [round(r["avg_success_rate"], 2) for r in rows]
    scatter = scatter if scatter is not None else []
    model_links = model_links or {}
    table_rows = []
    for row in rows:
        config = json.dumps(row["model_config"], sort_keys=True, separators=(",", ":"))
        mkey = registry_key(row["model_name"], row["model_config"])
        href = model_links.get(mkey, _model_page_href(mkey, from_index=True))
        name_cell = f'<a href="{_esc(href)}">{_esc(row["model_name"])}</a>'
        table_rows.append(
            "<tr>"
            f"<td>{row['rank']}</td>"
            f"<td>{name_cell}</td>"
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
    a {{ color: #0369a1; }}
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
  <p>Ranked by average success rate, then cost-effectiveness (ROI/$). Latest run per task × model only. Click column headers to sort. Model names open run review.</p>
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
          label: 'Cost vs Success (latest per task × model)',
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
        }},
        onClick: (evt, elements, chart) => {{
          if (!elements.length) return;
          const p = chart.data.datasets[0].data[elements[0].index];
          if (p && p.task_id) {{
            window.location.href = 'review/tasks/' + p.task_id + '.html';
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


_SHARED_CSS = """
    body { font-family: system-ui, sans-serif; margin: 2rem; color: #0f172a; max-width: 1100px; }
    a { color: #0369a1; }
    .crumbs { color: #64748b; font-size: 0.9rem; margin-bottom: 1rem; }
    .crumbs a { color: #0369a1; text-decoration: none; }
    .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px;
             font-size: 0.75rem; font-weight: 600; margin-right: 0.35rem; }
    .badge-ranking { background: #dcfce7; color: #166534; }
    .badge-historical { background: #f1f5f9; color: #475569; }
    .badge-pack { background: #e0f2fe; color: #075985; }
    .badge-nopack { background: #fef3c7; color: #92400e; }
    .badge-truncated { background: #fee2e2; color: #991b1b; }
    table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
    th, td { border: 1px solid #e2e8f0; padding: 0.45rem 0.65rem; text-align: left; vertical-align: top; }
    th { background: #f1f5f9; }
    .metrics { display: flex; flex-wrap: wrap; gap: 0.75rem; margin: 1rem 0; }
    .metric { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.6rem 0.9rem; min-width: 7rem; }
    .metric .label { font-size: 0.75rem; color: #64748b; }
    .metric .value { font-size: 1.1rem; font-weight: 600; }
    .callout { background: #fffbeb; border: 1px solid #fbbf24; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
    .banner { background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 0.75rem 1rem; margin: 1rem 0; }
    pre, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; }
    pre { background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 8px; overflow: auto; max-height: 28rem; white-space: pre-wrap; }
    .two-pane { display: grid; grid-template-columns: 14rem 1fr; gap: 1rem; }
    .file-list { list-style: none; padding: 0; margin: 0; border: 1px solid #e2e8f0; border-radius: 8px; max-height: 24rem; overflow: auto; }
    .file-list li { padding: 0.35rem 0.6rem; border-bottom: 1px solid #e2e8f0; }
    .file-list li.omitted { color: #94a3b8; }
    .preview { border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.75rem; min-height: 8rem; background: #f8fafc; }
    details { margin: 0.5rem 0; }
    footer.pack-path { margin-top: 2rem; color: #64748b; font-size: 0.85rem; }
"""


def _breadcrumbs(parts: list[tuple[str, str | None]]) -> str:
    bits = []
    for label, href in parts:
        if href:
            bits.append(f'<a href="{_esc(href)}">{_esc(label)}</a>')
        else:
            bits.append(_esc(label))
    return '<nav class="crumbs">' + " / ".join(bits) + "</nav>"


def render_model_page(
    *,
    model_name: str,
    model_config: dict[str, Any],
    model_key: str,
    task_rows: list[dict[str, Any]],
) -> str:
    """
    task_rows items: task_id, completeness, cost, ranking_run_id, ranking_href, task_href
    """
    config = json.dumps(model_config, sort_keys=True, separators=(",", ":"))
    rows_html = []
    for tr in task_rows:
        rows_html.append(
            "<tr>"
            f'<td><a href="{_esc(tr["task_href"])}">{_esc(tr["task_id"])}</a></td>'
            f"<td>{tr['completeness']:.1f}%</td>"
            f"<td>${tr['cost']:.4f}</td>"
            f'<td><a href="{_esc(tr["ranking_href"])}">Open ranking run</a></td>'
            "</tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Model — {_esc(model_name)}</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {_breadcrumbs([("Leaderboard", "../../index.html"), (model_name, None)])}
  <h1>{_esc(model_name)}</h1>
  <p><code>{_esc(config)}</code> · key <code>{_esc(model_key)}</code></p>
  <table>
    <thead><tr><th>Task</th><th>Success</th><th>Cost</th><th>Ranking run</th></tr></thead>
    <tbody>{"".join(rows_html) if rows_html else "<tr><td colspan=4>No runs</td></tr>"}</tbody>
  </table>
</body>
</html>
"""


def render_task_page(
    *,
    task_id: str,
    task_name: str,
    groups: list[dict[str, Any]],
) -> str:
    """
    groups: list of {model_name, model_config, model_key, runs: [{timestamp, success, cost, has_pack, ranking|historical, href}]}
    Runs within each group should already be newest-first.
    """
    sections = []
    crumb_model: tuple[str, str] | None = None
    for g in groups:
        config = json.dumps(g["model_config"], sort_keys=True, separators=(",", ":"))
        safe = model_key_urlsafe(g["model_key"])
        model_href = f"../models/{safe}.html"
        if crumb_model is None:
            crumb_model = (g["model_name"], model_href)
        rows = []
        for r in g["runs"]:
            badge = (
                '<span class="badge badge-ranking">ranking</span>'
                if r["role"] == "ranking"
                else '<span class="badge badge-historical">historical</span>'
            )
            pack = (
                '<span class="badge badge-pack">pack</span>'
                if r["has_pack"]
                else '<span class="badge badge-nopack">no pack</span>'
            )
            rows.append(
                "<tr>"
                f"<td>{_esc(r['timestamp'])}</td>"
                f"<td>{r['success']:.1f}%</td>"
                f"<td>${r['cost']:.4f}</td>"
                f"<td>{pack}</td>"
                f"<td>{badge}</td>"
                f'<td><a href="{_esc(r["href"])}">Review</a></td>'
                "</tr>"
            )
        sections.append(
            f'<h2><a href="{_esc(model_href)}">{_esc(g["model_name"])}</a></h2>'
            f"<p><code>{_esc(config)}</code></p>"
            "<table><thead><tr>"
            "<th>Timestamp</th><th>Success</th><th>Cost</th><th>Pack</th><th>Role</th><th></th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    crumb_parts: list[tuple[str, str | None]] = [
        ("Leaderboard", "../../index.html"),
    ]
    # When a single model×config group exists, include it in the trail (§7.2).
    if crumb_model and len(groups) == 1:
        crumb_parts.append((crumb_model[0], crumb_model[1]))
    crumb_parts.append((task_id, None))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Task — {_esc(task_id)}</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {_breadcrumbs(crumb_parts)}
  <h1>{_esc(task_name or task_id)}</h1>
  <p class="mono">{_esc(task_id)}</p>
  {"".join(sections) if sections else "<p>No evaluation results.</p>"}
</body>
</html>
"""


def render_run_detail_page(
    *,
    task_id: str,
    model_name: str,
    model_config: dict[str, Any],
    model_key: str,
    result: dict[str, Any],
    role: str,
    manifest: dict[str, Any] | None,
    response_text: str | None,
    file_previews: list[dict[str, Any]] | None,
    judge_doc: dict[str, Any] | None,
    pack_rel_href: str | None,
    force_cli: str,
) -> str:
    config = json.dumps(model_config, sort_keys=True, separators=(",", ":"))
    run_id = result.get("run_id") or "(no run id)"
    has_pack = bool(result.get("run_pack_path") and manifest is not None)
    badges = []
    badges.append(
        '<span class="badge badge-ranking">ranking</span>'
        if role == "ranking"
        else '<span class="badge badge-historical">historical</span>'
    )
    badges.append(
        '<span class="badge badge-pack">pack</span>'
        if has_pack
        else '<span class="badge badge-nopack">no pack</span>'
    )
    if manifest and manifest.get("truncation", {}).get("truncated"):
        badges.append('<span class="badge badge-truncated">truncated</span>')

    crumbs = _breadcrumbs(
        [
            ("Leaderboard", "../../../../index.html"),
            (model_name, f"../../../models/{model_key_urlsafe(model_key)}.html"),
            (task_id, f"../../../tasks/{task_id}.html"),
            (str(run_id), None),
        ]
    )

    # Prefer EvaluationResult for the metrics strip (§7.3); values align with
    # manifest.metrics when a pack exists.
    metric_keys = [
        ("Success", f"{float(result.get('completeness_percent', 0)):.1f}%"),
        ("Cost", f"${float(result.get('cost_usd', 0)):.4f}"),
        ("ROI", f"{float(result.get('earned_roi', 0)):.1f}"),
        ("Cost-eff", f"{float(result.get('cost_effectiveness_roi_per_usd', 0)):.1f}"),
        ("Latency", f"{float(result.get('latency_seconds', 0)):.2f}s"),
        ("In tok", str(int(result.get("input_tokens", 0)))),
        ("Out tok", str(int(result.get("output_tokens", 0)))),
        ("Tools", str(int(result.get("tool_calls", 0)))),
    ]
    metrics_html = '<div class="metrics">' + "".join(
        f'<div class="metric"><div class="label">{_esc(lab)}</div>'
        f'<div class="value">{_esc(val)}</div></div>'
        for lab, val in metric_keys
    ) + "</div>"

    if not has_pack:
        body = f"""
  {crumbs}
  <h1>Run detail</h1>
  <p>{"".join(badges)}</p>
  <p><code>{_esc(model_name)}</code> · <code>{_esc(config)}</code> · {_esc(str(result.get("timestamp") or ""))}</p>
  {metrics_html}
  <div class="callout">
    <strong>Metrics only — no Run Review Pack</strong>
    <p>This EvaluationResult has no sidecar pack (legacy metrics-only row).
    Re-run with <code>--force</code> to create a new inference, metrics row, and pack
    (never mutates this historical row).</p>
    <pre>{_esc(force_cli)}</pre>
  </div>
"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Run — {_esc(str(run_id))}</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""

    # Full pack detail
    trunc = manifest.get("truncation") or {}
    trunc_banner = ""
    if trunc.get("truncated"):
        rows = []
        for f in trunc.get("files") or []:
            rows.append(
                f"<tr><td>{_esc(f.get('path',''))}</td><td>{_esc(f.get('status',''))}</td>"
                f"<td>{f.get('original_bytes', 0)}</td><td>{f.get('stored_bytes', 0)}</td>"
                f"<td>{_esc(str(f.get('reason')))}</td></tr>"
            )
        trunc_banner = f"""
  <div class="banner">
    <strong>Pack content was truncated by soft size caps.</strong>
    <details>
      <summary>Truncation table</summary>
      <table>
        <thead><tr><th>Path</th><th>Status</th><th>Original</th><th>Stored</th><th>Reason</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
      <p>Response: truncated={trunc.get("response", {}).get("truncated")}
         reason={_esc(str(trunc.get("response", {}).get("reason")))}</p>
    </details>
  </div>
"""

    rules = manifest.get("rule_outcomes") or []
    rule_rows = []
    for o in rules:
        detail = json.dumps(o.get("detail") or {}, ensure_ascii=False)
        passed = "✓" if o.get("passed") else "✗"
        rule_rows.append(
            f"<tr><td>{o.get('index')}</td><td>{_esc(str(o.get('type')))}</td>"
            f"<td>{passed}</td><td class=\"mono\">{_esc(detail)}</td></tr>"
        )
    rules_html = f"""
  <h2>Rule outcomes</h2>
  <table>
    <thead><tr><th>#</th><th>Type</th><th>Pass</th><th>Detail</th></tr></thead>
    <tbody>{"".join(rule_rows) if rule_rows else "<tr><td colspan=4>(none)</td></tr>"}</tbody>
  </table>
"""

    response_html = f"""
  <h2>Raw response</h2>
  <pre>{_esc(response_text or "")}</pre>
"""

    file_previews = file_previews or []
    list_items = []
    previews = []
    for i, fp in enumerate(file_previews):
        status = fp.get("status", "stored")
        cls = "omitted" if status == "omitted" else ""
        reason = f" ({fp.get('reason')})" if fp.get("reason") else ""
        list_items.append(
            f'<li class="{cls}"><a href="#file-{i}">{_esc(fp["path"])}</a> '
            f'<span class="mono">{_esc(status)}{_esc(reason)}</span></li>'
        )
        body = fp.get("preview") or ""
        if status == "omitted":
            body = f"(omitted: {fp.get('reason')})"
        previews.append(
            f'<div class="preview" id="file-{i}"><strong class="mono">{_esc(fp["path"])}</strong>'
            f"<pre>{_esc(body)}</pre></div>"
        )
    files_html = f"""
  <h2>Sandbox files</h2>
  <div class="two-pane">
    <ul class="file-list">{"".join(list_items) if list_items else "<li>(empty)</li>"}</ul>
    <div>{"".join(previews) if previews else "<div class='preview'>(no files)</div>"}</div>
  </div>
"""

    judge_html = ""
    if judge_doc is not None:
        judge_html = f"""
  <h2>Judge</h2>
  <pre>{_esc(json.dumps(judge_doc, indent=2, ensure_ascii=False))}</pre>
"""

    pack_path = result.get("run_pack_path") or ""
    footer = f"""
  <footer class="pack-path">
    Pack: <code>{_esc(pack_path)}</code>
    · <a href="{_esc(pack_rel_href or '#')}/manifest.json">manifest.json</a>
    · <a href="{_esc(pack_rel_href or '#')}/response.txt">response.txt</a>
    · <a href="{_esc(pack_rel_href or '#')}/files">files/</a>
  </footer>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Run — {_esc(str(run_id))}</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {crumbs}
  <h1>Run detail</h1>
  <p>{"".join(badges)}</p>
  <p><code>{_esc(model_name)}</code> · <code>{_esc(config)}</code> · {_esc(str(result.get("timestamp") or ""))}
     · run_id <code>{_esc(str(run_id))}</code></p>
  {metrics_html}
  {trunc_banner}
  {rules_html}
  {response_html}
  {files_html}
  {judge_html}
  {footer}
</body>
</html>
"""


class DashboardGenerator:
    def __init__(self, *, chartjs_cdn: str) -> None:
        self.chartjs_cdn = chartjs_cdn

    def generate(
        self,
        tasks: list[dict[str, Any]],
        *,
        leaderboard_path: Path,
        html_path: Path,
        repo_root: Path | None = None,
        runs_rel: str = ".scratch/bench-suite/runs",
    ) -> list[dict[str, Any]]:
        rows = aggregate_models(tasks)
        leaderboard_path = Path(leaderboard_path)
        html_path = Path(html_path)
        if repo_root is not None:
            root = Path(repo_root)
        else:
            # Assume html at {repo}/.scratch/bench-suite/index.html when possible.
            parent = html_path.parent
            if parent.name == "bench-suite" and parent.parent.name == ".scratch":
                root = parent.parent.parent
            else:
                root = parent
        # When html is .scratch/bench-suite/index.html, review/ lives beside it.
        review_root = html_path.parent / "review"
        leaderboard_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        review_root.mkdir(parents=True, exist_ok=True)
        (review_root / "models").mkdir(parents=True, exist_ok=True)
        (review_root / "tasks").mkdir(parents=True, exist_ok=True)
        (review_root / "runs").mkdir(parents=True, exist_ok=True)

        leaderboard_path.write_text(render_leaderboard_md(rows), encoding="utf-8")

        # Build model → task ranking rows for model pages
        model_task_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            mkey = registry_key(row["model_name"], row["model_config"])
            model_task_map[mkey] = {
                "model_name": row["model_name"],
                "model_config": row["model_config"],
                "model_key": mkey,
                "task_rows": [],
            }

        for task in tasks:
            task_id = task["task_id"]
            results = list(task.get("evaluation_results") or [])
            for result in select_latest_per_model_config(results):
                mkey = registry_key(
                    result["model_name"], result.get("model_config") or {}
                )
                if mkey not in model_task_map:
                    model_task_map[mkey] = {
                        "model_name": result["model_name"],
                        "model_config": result.get("model_config") or {},
                        "model_key": mkey,
                        "task_rows": [],
                    }
                run_id = result.get("run_id") or f"legacy-{result.get('timestamp', 'unknown')}"
                safe = model_key_urlsafe(mkey)
                model_task_map[mkey]["task_rows"].append(
                    {
                        "task_id": task_id,
                        "completeness": float(result["completeness_percent"]),
                        "cost": float(result["cost_usd"]),
                        "ranking_run_id": run_id,
                        "ranking_href": f"../runs/{task_id}/{safe}/{run_id}.html",
                        "task_href": f"../tasks/{task_id}.html",
                    }
                )

        for mkey, info in model_task_map.items():
            safe = model_key_urlsafe(mkey)
            page = render_model_page(
                model_name=info["model_name"],
                model_config=info["model_config"],
                model_key=mkey,
                task_rows=info["task_rows"],
            )
            (review_root / "models" / f"{safe}.html").write_text(page, encoding="utf-8")

        # Task pages + run pages
        for task in tasks:
            task_id = task["task_id"]
            task_name = str(task.get("name") or task_id)
            results = list(task.get("evaluation_results") or [])
            groups_map: dict[tuple[str, str], dict[str, Any]] = {}
            for append_index, result in enumerate(results):
                mname = result["model_name"]
                mcfg = result.get("model_config") or {}
                mkey = registry_key(mname, mcfg)
                ck = config_key(mcfg)
                gkey = (mname, ck)
                if gkey not in groups_map:
                    groups_map[gkey] = {
                        "model_name": mname,
                        "model_config": mcfg,
                        "model_key": mkey,
                        "runs": [],
                    }
                role = (
                    "ranking"
                    if is_ranking_run(result, results)
                    else "historical"
                )
                run_id = result.get("run_id") or f"legacy-{result.get('timestamp', append_index)}"
                safe = model_key_urlsafe(mkey)
                href = f"../runs/{task_id}/{safe}/{run_id}.html"
                groups_map[gkey]["runs"].append(
                    {
                        "timestamp": str(result.get("timestamp") or ""),
                        "success": float(result.get("completeness_percent") or 0),
                        "cost": float(result.get("cost_usd") or 0),
                        "has_pack": bool(result.get("run_pack_path")),
                        "role": role,
                        "href": href,
                        "sort_key": (str(result.get("timestamp") or ""), append_index),
                        "result": result,
                        "run_id": run_id,
                        "append_index": append_index,
                    }
                )

            groups = []
            for g in groups_map.values():
                g["runs"].sort(key=lambda r: r["sort_key"], reverse=True)
                groups.append(g)

            task_page = render_task_page(
                task_id=task_id, task_name=task_name, groups=groups
            )
            (review_root / "tasks" / f"{task_id}.html").write_text(
                task_page, encoding="utf-8"
            )

            for g in groups:
                mkey = g["model_key"]
                safe = model_key_urlsafe(mkey)
                run_dir = review_root / "runs" / task_id / safe
                run_dir.mkdir(parents=True, exist_ok=True)
                for r in g["runs"]:
                    result = r["result"]
                    run_id = r["run_id"]
                    manifest = None
                    response_text = None
                    file_previews: list[dict[str, Any]] = []
                    judge_doc = None
                    pack_rel_href = None
                    run_html_path = run_dir / f"{run_id}.html"
                    if result.get("run_pack_path"):
                        pack_dir = (root / result["run_pack_path"]).resolve()
                        man_path = pack_dir / "manifest.json"
                        if man_path.is_file():
                            with man_path.open(encoding="utf-8") as f:
                                manifest = json.load(f)
                            resp_path = pack_dir / "response.txt"
                            if resp_path.is_file():
                                response_text = resp_path.read_text(
                                    encoding="utf-8", errors="replace"
                                )
                            # File inventory from truncation + try previews
                            trunc_files = (manifest.get("truncation") or {}).get(
                                "files"
                            ) or []
                            for tf in trunc_files:
                                preview = ""
                                status = tf.get("status", "stored")
                                if status != "omitted":
                                    fpath = pack_dir / "files" / tf["path"]
                                    if fpath.is_file():
                                        try:
                                            preview = fpath.read_text(
                                                encoding="utf-8", errors="replace"
                                            )[:8000]
                                        except OSError:
                                            preview = "(unreadable)"
                                file_previews.append(
                                    {
                                        "path": tf["path"],
                                        "status": status,
                                        "reason": tf.get("reason"),
                                        "preview": preview,
                                    }
                                )
                            if (manifest.get("artifacts") or {}).get("judge"):
                                jpath = pack_dir / "judge.json"
                                if jpath.is_file():
                                    with jpath.open(encoding="utf-8") as f:
                                        judge_doc = json.load(f)
                            pack_rel_href = Path(
                                os.path.relpath(
                                    str(pack_dir),
                                    str(run_html_path.parent.resolve()),
                                )
                            ).as_posix()

                    force_cli = (
                        f"python -m bench_suite.cli live-run --task-id {task_id} "
                        f"--model {g['model_name']} --force"
                    )
                    page = render_run_detail_page(
                        task_id=task_id,
                        model_name=g["model_name"],
                        model_config=g["model_config"],
                        model_key=mkey,
                        result=result,
                        role=r["role"],
                        manifest=manifest,
                        response_text=response_text,
                        file_previews=file_previews,
                        judge_doc=judge_doc,
                        pack_rel_href=pack_rel_href,
                        force_cli=force_cli,
                    )
                    run_html_path.write_text(page, encoding="utf-8")

        model_links = {
            mkey: _model_page_href(mkey, from_index=True) for mkey in model_task_map
        }
        html_path.write_text(
            render_index_html(
                rows,
                chartjs_cdn=self.chartjs_cdn,
                scatter=scatter_points(tasks),
                model_links=model_links,
            ),
            encoding="utf-8",
        )
        return rows
