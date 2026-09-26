"""Interactive observability dashboard generator (B1 bonus).

Reads the pipeline artifacts and renders a self-contained HTML dashboard:
quality-gate status, freshness distribution, metric comparison and corruption impact.
No extra dependencies — the report is a single static HTML file.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from core.config import load_settings
from core.utils import read_json, write_text


def _load(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return read_json(path)
    except Exception:
        return default


def _metric_cards(metrics: dict | None, title: str) -> str:
    if not metrics:
        return f"<section><h2>{title}</h2><p class='muted'>Artifact not found.</p></section>"
    cards = []
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        value = metrics.get(key)
        shown = f"{value:.4f}" if isinstance(value, (int, float)) else "N/A"
        cards.append(f"<div class='card'><div class='label'>{key}</div><div class='value'>{shown}</div></div>")
    return f"<section><h2>{title}</h2><div class='cards'>{''.join(cards)}</div></section>"


def _bar(value: float, color: str) -> str:
    width = max(0.0, min(1.0, float(value))) * 100
    return f"<div class='bar'><span style='width:{width:.1f}%;background:{color}'></span></div>"


def _comparison_table(baseline: dict | None, corrupted: dict | None, repaired: dict | None) -> str:
    rows = []
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        base = (baseline or {}).get(key)
        corr = (corrupted or {}).get(key)
        rep = (repaired or {}).get(key)
        cells = []
        for value in (base, corr, rep):
            shown = f"{value:.4f}" if isinstance(value, (int, float)) else "N/A"
            cells.append(f"<td>{shown}</td>")
        rows.append(f"<tr><th>{key}</th>{''.join(cells)}</tr>")
    return (
        "<table><thead><tr><th>Metric</th><th>Baseline</th><th>Corrupted</th><th>Repaired</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _freshness_section(freshness: dict | None) -> str:
    if not freshness:
        return "<section><h2>Freshness SLA</h2><p class='muted'>Artifact not found.</p></section>"
    ratio = float(freshness.get("stale_ratio") or 0.0)
    status = "FRESH" if freshness.get("is_fresh") else "STALE"
    cls = "ok" if freshness.get("is_fresh") else "bad"
    return f"""
    <section>
      <h2>Freshness SLA</h2>
      <div class="card wide">
        <div class="label">Status <span class="pill {cls}">{status}</span></div>
        <div class="row"><span>Stale rows</span><b>{freshness.get('stale_rows')} / {freshness.get('total_rows')}</b></div>
        <div class="row"><span>Stale ratio</span><b>{ratio:.1%}</b></div>
        {_bar(ratio, '#ef4444' if not freshness.get('is_fresh') else '#22c55e')}
        <div class="row"><span>Threshold</span><b>{freshness.get('threshold_days')} days</b></div>
        <div class="row"><span>Latest published</span><b>{freshness.get('latest_published')}</b></div>
        <div class="row"><span>Oldest published</span><b>{freshness.get('oldest_published')}</b></div>
      </div>
    </section>"""


def _age_distribution_section(settings) -> str:
    """Render an offline, interactive age histogram for the three pipeline states."""
    dataset_paths = {
        "Baseline": settings.paths.clean_json,
        "Corrupted": settings.paths.corrupted_clean_json,
        "Repaired": settings.paths.repaired_clean_json,
    }
    age_data = {}
    for label, path in dataset_paths.items():
        records = _load(path, []) or []
        age_data[label] = [
            int(record["age_days"])
            for record in records
            if isinstance(record, dict) and record.get("age_days") is not None
        ]
    # Only numeric arrays are embedded in the script, so paper metadata cannot
    # become executable markup or JavaScript.
    encoded = json.dumps(age_data, separators=(",", ":"))
    return f"""
    <section>
      <h2>Publication Age Distribution</h2>
      <div class="card wide">
        <div class="chart-controls">
          <label for="age-dataset">Dataset</label>
          <select id="age-dataset">
            <option>Baseline</option><option>Corrupted</option><option>Repaired</option>
          </select>
          <label for="age-bins">Number of groups</label>
          <select id="age-bins"><option value="5">5</option><option value="8" selected>8</option><option value="12">12</option></select>
        </div>
        <div id="age-histogram" class="histogram" role="img" aria-label="Distribution of paper age in days"></div>
        <p id="age-summary" class="muted" aria-live="polite"></p>
      </div>
    </section>
    <script>
      const ageData = {encoded};
      const datasetPicker = document.getElementById('age-dataset');
      const binPicker = document.getElementById('age-bins');
      function renderAgeHistogram() {{
        const values = ageData[datasetPicker.value] || [];
        const count = Number(binPicker.value);
        const chart = document.getElementById('age-histogram');
        const summary = document.getElementById('age-summary');
        if (!values.length) {{
          chart.innerHTML = '<p class="muted">No age data available for this dataset.</p>';
          summary.textContent = '';
          return;
        }}
        const min = Math.min(...values), max = Math.max(...values);
        const width = Math.max(1, Math.ceil((max - min + 1) / count));
        const bins = Array.from({{length: count}}, (_, i) => ({{start: min + i * width, count: 0}}));
        values.forEach(age => {{
          const index = Math.min(count - 1, Math.floor((age - min) / width));
          bins[index].count++;
        }});
        const peak = Math.max(1, ...bins.map(bin => bin.count));
        chart.innerHTML = bins.map(bin => {{
          const end = bin.start + width - 1;
          const height = Math.max(2, bin.count / peak * 100);
          return `<div class="histogram-column" title="${{bin.count}} papers, ${{bin.start}}–${{end}} days">
            <div class="histogram-bar" style="height:${{height}}%"></div>
            <span>${{bin.start}}–${{end}}</span><b>${{bin.count}}</b></div>`;
        }}).join('');
        const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
        summary.textContent = `${{values.length}} papers · mean age ${{mean.toFixed(1)}} days · range ${{min}}–${{max}} days`;
      }}
      datasetPicker.addEventListener('change', renderAgeHistogram);
      binPicker.addEventListener('change', renderAgeHistogram);
      renderAgeHistogram();
    </script>""".strip()


def _quality_section(quality: dict | None, title: str) -> str:
    if not quality:
        return f"<section><h2>{title}</h2><p class='muted'>Artifact not found.</p></section>"
    cls = "ok" if quality.get("success") else "bad"
    rows = []
    for check in quality.get("checks", []):
        flag = "<span class='pill ok'>PASS</span>" if check["success"] else "<span class='pill bad'>FAIL</span>"
        rows.append(
            f"<tr><td><code>{html.escape(check['expectation'])}</code></td><td>{flag}</td>"
            f"<td>{html.escape(str(check.get('observed_value')))}</td>"
            f"<td>{check.get('unexpected_count', 0)}</td></tr>"
        )
    return f"""
    <section>
      <h2>{title} <span class="pill {cls}">{'PASS' if quality.get('success') else 'FAIL'}</span></h2>
      <table><thead><tr><th>Expectation</th><th>Result</th><th>Observed</th><th>Unexpected</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table>
    </section>"""


def _corruption_section(log: dict | None) -> str:
    if not log:
        return "<section><h2>Corruption Scenarios</h2><p class='muted'>Artifact not found.</p></section>"
    rows = [
        f"<tr><td><code>{html.escape(e['type'])}</code></td><td>{e['affected_rows']}</td>"
        f"<td>{html.escape(e['description'])}</td></tr>"
        for e in log.get("events", [])
    ]
    return f"""
    <section>
      <h2>Corruption Scenarios ({log.get('total_corruptions', 0)} injected)</h2>
      <table><thead><tr><th>Type</th><th>Affected rows</th><th>Description</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table>
    </section>"""


def _healing_section(log: dict | None) -> str:
    if not log:
        return ""
    cls = "ok" if log.get("healthy_after") else "bad"
    actions = "".join(f"<li>{html.escape(a)}</li>" for a in log.get("actions", []))
    return f"""
    <section>
      <h2>Automated Self-Healing <span class="pill {cls}">{'RECOVERED' if log.get('healthy_after') else 'FAILED'}</span></h2>
      <div class="card wide">
        <div class="row"><span>Healthy before</span><b>{log.get('healthy_before')}</b></div>
        <div class="row"><span>Repaired</span><b>{log.get('repaired')}</b></div>
        <div class="row"><span>Healthy after</span><b>{log.get('healthy_after')}</b></div>
        <div class="row"><span>Repaired rows</span><b>{log.get('repaired_rows')}</b></div>
        <ul>{actions}</ul>
      </div>
    </section>"""


def build_dashboard(settings) -> Path:
    paths = settings.paths
    baseline = _load(paths.baseline_metrics)
    corrupted = _load(paths.corrupted_metrics)
    repaired = _load(paths.repaired_metrics)
    baseline_quality = _load(paths.baseline_quality_report)
    corrupted_quality = _load(paths.corrupted_quality_report)
    freshness = _load(paths.freshness_report)
    corruption_log = _load(paths.corruption_log)
    healing_log = _load(paths.quality_dir / "self_healing_log.json")

    body = f"""
    {_metric_cards(baseline, 'Baseline Metrics')}
    {_comparison_table(baseline, corrupted, repaired)}
    {_quality_section(baseline_quality, 'Baseline Quality Gate')}
    {_quality_section(corrupted_quality, 'Corrupted Quality Gate')}
    {_freshness_section(freshness)}
    {_age_distribution_section(settings)}
    {_corruption_section(corruption_log)}
    {_healing_section(healing_log)}
    """

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data Observability Dashboard</title>
<style>
  :root {{
    --bg: #0b1120; --panel: #111827; --border: #1f2937; --text: #e5e7eb;
    --muted: #94a3b8; --accent: #38bdf8; --ok: #22c55e; --bad: #ef4444;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--text);
    font: 15px/1.6 -apple-system, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 1000px; margin: 0 auto; }}
  h1 {{ font-size: 26px; margin: 0 0 4px; }}
  .sub {{ color: var(--muted); margin-bottom: 28px; }}
  h2 {{ font-size: 17px; margin: 32px 0 12px; display: flex; align-items: center; gap: 10px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
  .card, table {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; }}
  .card {{ padding: 14px 16px; }}
  .card.wide {{ display: flex; flex-direction: column; gap: 8px; }}
  .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }}
  .value {{ font-size: 24px; font-weight: 600; margin-top: 6px; font-variant-numeric: tabular-nums; }}
  table {{ width: 100%; border-collapse: collapse; overflow: hidden; }}
  th, td {{ padding: 9px 14px; text-align: left; border-bottom: 1px solid var(--border); font-size: 14px; }}
  thead th {{ color: var(--muted); font-weight: 600; background: #0f172a; }}
  tbody tr:last-child th, tbody tr:last-child td {{ border-bottom: none; }}
  code {{ color: var(--accent); font-size: 13px; }}
  .pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px;
    font-weight: 600; letter-spacing: .04em; }}
  .pill.ok {{ background: rgba(34,197,94,.15); color: var(--ok); }}
  .pill.bad {{ background: rgba(239,68,68,.15); color: var(--bad); }}
  .row {{ display: flex; justify-content: space-between; gap: 12px; font-size: 14px; }}
  .row span {{ color: var(--muted); }}
  .chart-controls {{ display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }}
  .chart-controls label {{ color: var(--muted); font-size: 13px; }}
  .chart-controls select {{ color: var(--text); background: #0f172a; border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 8px; margin-right: 14px; }}
  .histogram {{ display: flex; align-items: end; gap: 8px; height: 210px; padding: 12px 4px 0;
    border-bottom: 1px solid var(--border); }}
  .histogram-column {{ flex: 1; height: 100%; min-width: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: end; gap: 3px; font-size: 11px; color: var(--muted); }}
  .histogram-bar {{ width: min(100%, 42px); min-height: 2px; background: linear-gradient(180deg, #38bdf8, #2563eb);
    border-radius: 4px 4px 0 0; }}
  .histogram-column b {{ color: var(--text); font-weight: 500; }}
  .bar {{ height: 6px; background: #1e293b; border-radius: 999px; overflow: hidden; margin: 4px 0 8px; }}
  .bar span {{ display: block; height: 100%; }}
  .muted {{ color: var(--muted); }}
  ul {{ margin: 6px 0 0; padding-left: 18px; color: var(--muted); font-size: 14px; }}
  footer {{ margin-top: 40px; color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
<main>
  <h1>Data Pipeline Observability Dashboard</h1>
  <div class="sub">Crossref → clean → ChromaDB → evaluate → quality gate → corruption → repair</div>
  {body}
  <footer>Interactive dashboard generated from pipeline artifacts in <code>data/</code>. Regenerate with
  <code>python script/run_dashboard.py</code>.</footer>
</main>
</body>
</html>
"""
    output = settings.paths.quality_dir.parent / "reports" / "observability_dashboard.html"
    write_text(output, document)
    return output


def main() -> None:
    settings = load_settings()
    output = build_dashboard(settings)
    print(f"[dashboard] Wrote {output}")


if __name__ == "__main__":
    main()
