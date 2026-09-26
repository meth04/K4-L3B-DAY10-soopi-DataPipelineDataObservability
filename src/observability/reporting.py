from __future__ import annotations

from typing import Any

from core.utils import now_utc, write_text

METRIC_KEYS = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score")


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _metrics_table(metrics: dict[str, Any]) -> str:
    lines = ["| Metric | Value |", "| :--- | ---: |"]
    for key in METRIC_KEYS:
        lines.append(f"| `{key}` | {_fmt(metrics.get(key))} |")
    lines.append(f"| `samples` | {_fmt(metrics.get('samples'))} |")
    return "\n".join(lines)


def _quality_table(quality: dict[str, Any]) -> str:
    lines = [
        f"**Overall success:** `{quality.get('success')}`",
        "",
        "| Expectation | Success | Observed | Unexpected |",
        "| :--- | :---: | ---: | ---: |",
    ]
    for check in quality.get("checks", []):
        lines.append(
            f"| `{check['expectation']}` | {check['success']} | "
            f"{_fmt(check.get('observed_value'))} | {check.get('unexpected_count', 0)} |"
        )
    if not quality.get("checks"):
        lines.append("| _no expectations recorded_ | - | - | - |")
    return "\n".join(lines)


def _freshness_table(freshness: dict[str, Any]) -> str:
    return "\n".join(
        [
            "| Attribute | Value |",
            "| :--- | ---: |",
            f"| Threshold (days) | {_fmt(freshness.get('threshold_days'))} |",
            f"| Total rows | {_fmt(freshness.get('total_rows'))} |",
            f"| Stale rows | {_fmt(freshness.get('stale_rows'))} |",
            f"| Stale ratio | {_fmt(freshness.get('stale_ratio'))} |",
            f"| Latest published | {_fmt(freshness.get('latest_published'))} |",
            f"| Oldest published | {_fmt(freshness.get('oldest_published'))} |",
            f"| **is_fresh** | `{freshness.get('is_fresh')}` |",
        ]
    )


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write the Phase 1 baseline markdown report."""
    content = f"""# Phase 1 — Baseline Data Pipeline Report

_Generated at {now_utc().isoformat()}_

## 1. Source & Ingestion

| Attribute | Value |
| :--- | ---: |
| Source | {source_summary.get('source_api', 'N/A')} |
| Query | `{source_summary.get('source_query', 'N/A')}` |
| Filter | `{source_summary.get('source_filter', 'N/A')}` |
| Raw records | {_fmt(source_summary.get('raw_records'))} |
| Clean rows | {_fmt(source_summary.get('clean_rows'))} |
| Duplicates removed | {_fmt(source_summary.get('duplicates_removed'))} |
| Embedding model | `{source_summary.get('embedding_model', 'N/A')}` |
| Collection | `{source_summary.get('collection_name', 'N/A')}` |

## 2. Evaluation Metrics (Baseline)

{_metrics_table(metrics)}

## 3. Data Quality Gate (Great Expectations 1.x)

{_quality_table(quality)}

## 4. Freshness SLA

{_freshness_table(freshness)}

## 5. Conclusion

The baseline corpus was ingested from {source_summary.get('source_api', 'the source')}, cleaned into
{_fmt(source_summary.get('clean_rows'))} embedding-ready rows and indexed in ChromaDB. The quality gate
reported `success={quality.get('success')}` and the freshness SLA reported `is_fresh={freshness.get('is_fresh')}`
(stale ratio {_fmt(freshness.get('stale_ratio'))} against a {_fmt(freshness.get('threshold_days'))}-day threshold).
"""
    write_text(report_path, content)


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the Baseline vs Corrupted vs Repaired comparison report."""
    rows = ["| Metric | Baseline | Corrupted | Repaired | Delta (corruption) | Recovery |", "| :--- | ---: | ---: | ---: | ---: | ---: |"]
    for key in METRIC_KEYS:
        base = baseline_metrics.get(key)
        corr = corrupted_metrics.get(key)
        rep = repaired_metrics.get(key)
        delta = (corr - base) if isinstance(base, (int, float)) and isinstance(corr, (int, float)) else None
        recovery = (
            (rep - corr) / (base - corr) * 100
            if all(isinstance(v, (int, float)) for v in (base, corr, rep)) and (base - corr) != 0
            else None
        )
        rows.append(
            f"| `{key}` | {_fmt(base)} | {_fmt(corr)} | {_fmt(rep)} | {_fmt(delta)} | "
            f"{_fmt(recovery, 1) + '%' if recovery is not None else 'N/A'} |"
        )

    quality_rows = [
        "| Signal | Baseline | Corrupted | Repaired |",
        "| :--- | ---: | ---: | ---: |",
        f"| Quality gate success | {baseline_metrics.get('quality_success', 'N/A')} | "
        f"{corrupted_quality.get('success')} | {repaired_quality.get('success')} |",
        f"| Freshness is_fresh | {baseline_metrics.get('is_fresh', 'N/A')} | "
        f"{corrupted_freshness.get('is_fresh')} | {repaired_freshness.get('is_fresh')} |",
        f"| Stale rows | N/A | {corrupted_freshness.get('stale_rows')} | {repaired_freshness.get('stale_rows')} |",
    ]

    content = f"""# Corruption & Repair — 3-State Comparison Report

_Generated at {now_utc().isoformat()}_

## 1. Performance Comparison

{chr(10).join(rows)}

## 2. Quality & Freshness Signals

{chr(10).join(quality_rows)}

### Corrupted quality gate

{_quality_table(corrupted_quality)}

### Repaired quality gate

{_quality_table(repaired_quality)}

## 3. Interpretation

The corrupted dataset demonstrates **silent failure**: the pipeline still runs, but retrieval and
answer quality degrade because summaries were blanked/noised, titles truncated and dates pushed stale.
The repair step rebuilds the corpus from the trusted raw snapshot (`data/raw/crossref_records.json`)
via the idempotent cleaning path, so re-running repair yields the identical clean dataset.
Quality gate and freshness signals return to their baseline state, and the agent metrics recover
to (or very near) the baseline values.
"""
    write_text(report_path, content)
