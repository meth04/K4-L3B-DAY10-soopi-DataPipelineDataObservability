from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

MIN_ROWS = 10
MAX_ROWS = 100
MIN_SUMMARY_CHARS = 40
MAX_SUMMARY_CHARS = 4000
FRESHNESS_STALE_RATIO_LIMIT = 0.25


def _build_gx_batch(df: pd.DataFrame, batch_name: str):
    """Create a Great Expectations 1.x ephemeral context and return a validated batch.

    Uses the modern 1.x Data Source / Data Asset / Batch Definition API. The legacy
    `Validator` + `ExpectationSuite` flow is deliberately avoided because it crashes
    on Great Expectations >= 1.0.
    """
    import great_expectations as gx

    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name=f"papers_source_{batch_name}")
    data_asset = data_source.add_dataframe_asset(name=f"papers_asset_{batch_name}")
    batch_definition = data_asset.add_batch_definition_whole_dataframe(f"papers_batch_{batch_name}")
    return batch_definition.get_batch(batch_parameters={"dataframe": df})


def _run_gx_expectations(df: pd.DataFrame, report_name: str) -> list[dict[str, Any]]:
    """Run the four essential expectations and normalise the results."""
    import great_expectations as gx

    batch = _build_gx_batch(df, report_name)

    expectations = [
        ("ExpectTableRowCountToBeBetween", gx.expectations.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS)),
        ("ExpectColumnValuesToNotBeNull[paper_id]", gx.expectations.ExpectColumnValuesToNotBeNull(column="paper_id")),
        ("ExpectColumnValuesToNotBeNull[title]", gx.expectations.ExpectColumnValuesToNotBeNull(column="title")),
        ("ExpectColumnValuesToBeUnique[paper_id]", gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id")),
        (
            "ExpectColumnValueLengthsToBeBetween[summary]",
            gx.expectations.ExpectColumnValueLengthsToBeBetween(
                column="summary", min_value=MIN_SUMMARY_CHARS, max_value=MAX_SUMMARY_CHARS
            ),
        ),
    ]

    results: list[dict[str, Any]] = []
    for name, expectation in expectations:
        outcome = batch.validate(expectation)
        observed = outcome.result.get("observed_value") if outcome.result else None
        unexpected = len(outcome.result.get("partial_unexpected_list", [])) if outcome.result else 0
        results.append(
            {
                "expectation": name,
                "success": bool(outcome.success),
                "observed_value": observed,
                "unexpected_count": unexpected,
            }
        )
    return results


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run the Great Expectations quality gate plus a freshness SLA check."""
    try:
        checks = _run_gx_expectations(df, report_name)
        gx_error = None
    except Exception as exc:  # pragma: no cover - environment/version dependent
        checks = []
        gx_error = f"{type(exc).__name__}: {exc}"

    success = bool(checks) and all(check["success"] for check in checks)

    report = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "row_count": int(len(df)),
        "engine": "great_expectations 1.x (ephemeral context)",
        "success": success,
        "checks": checks,
        "failed_checks": [check["expectation"] for check in checks if not check["success"]],
    }
    if gx_error:
        report["error"] = gx_error

    freshness_path = (
        settings.paths.freshness_report
        if report_name == "baseline"
        else settings.paths.quality_dir / f"{report_name}_freshness_report.json"
    )
    freshness = build_freshness_report(df, settings, freshness_path)
    report["freshness"] = freshness
    report["success"] = success and freshness["is_fresh"]

    report_path = settings.paths.quality_dir / f"{report_name}_quality_report.json"
    write_json(report_path, report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarise dataset freshness against the age_days SLA."""
    threshold = settings.freshness_threshold_days
    if df.empty or "age_days" not in df.columns:
        payload = {
            "generated_at": now_utc().isoformat(),
            "threshold_days": threshold,
            "total_rows": int(len(df)),
            "stale_rows": 0,
            "stale_ratio": 0.0,
            "latest_published": None,
            "oldest_published": None,
            "is_fresh": False,
        }
        write_json(report_path, payload)
        return payload

    age_days = pd.to_numeric(df["age_days"], errors="coerce").fillna(0)
    stale_rows = int((age_days > threshold).sum())
    total_rows = int(len(df))
    stale_ratio = stale_rows / total_rows if total_rows else 0.0

    payload = {
        "generated_at": now_utc().isoformat(),
        "threshold_days": threshold,
        "total_rows": total_rows,
        "stale_rows": stale_rows,
        "stale_ratio": round(stale_ratio, 4),
        "stale_ratio_limit": FRESHNESS_STALE_RATIO_LIMIT,
        "latest_published": str(df["published"].max()),
        "oldest_published": str(df["published"].min()),
        "mean_age_days": round(float(age_days.mean()), 2),
        "is_fresh": bool(stale_ratio <= FRESHNESS_STALE_RATIO_LIMIT),
    }
    write_json(report_path, payload)
    return payload
