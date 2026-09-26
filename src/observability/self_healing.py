"""Automated self-healing: detect quality-gate violations and auto-repair from the trusted source.

This implements the B2 bonus: the pipeline itself decides whether the current dataset is
healthy, and when it is not, it automatically triggers an idempotent repair (rollback to the
trusted raw snapshot) and re-validates the result — no manual intervention required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import run_data_quality_checks


@dataclass
class HealingOutcome:
    """Result of a self-healing attempt."""

    healthy_before: bool
    repaired: bool
    healthy_after: bool
    violations: list[str] = field(default_factory=list)
    repaired_rows: int = 0
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "healthy_before": self.healthy_before,
            "repaired": self.repaired,
            "healthy_after": self.healthy_after,
            "violations": self.violations,
            "repaired_rows": self.repaired_rows,
            "actions": self.actions,
        }


def auto_heal(
    df: pd.DataFrame,
    settings: Settings,
    run_date: datetime | None = None,
    max_attempts: int = 1,
) -> tuple[pd.DataFrame, HealingOutcome]:
    """Validate `df`; if unhealthy, rebuild it from the trusted raw snapshot.

    Returns the (possibly repaired) dataframe together with an audit record. The repair is
    idempotent because it re-derives the dataset from `data/raw/crossref_records.json`
    through the same cleaning path used by the baseline.
    """
    run_date = run_date or now_utc()
    outcome = HealingOutcome(healthy_before=False, repaired=False, healthy_after=False)

    report = run_data_quality_checks(df, settings, "self_heal_precheck")
    outcome.healthy_before = report["success"]
    outcome.violations = list(report["failed_checks"])

    if outcome.healthy_before:
        outcome.healthy_after = True
        outcome.actions.append("Dataset already healthy; no repair needed.")
        write_json(settings.paths.quality_dir / "self_healing_log.json", outcome.to_dict())
        return df, outcome

    outcome.actions.append(
        f"Detected {len(outcome.violations)} quality violation(s): {', '.join(outcome.violations) or 'freshness SLA'}."
    )

    raw_path = settings.paths.raw_records_json
    if not raw_path.exists():
        outcome.actions.append(f"Repair aborted: trusted snapshot missing at {raw_path}.")
        write_json(settings.paths.quality_dir / "self_healing_log.json", outcome.to_dict())
        return df, outcome

    for attempt in range(1, max_attempts + 1):
        repaired_df = build_clean_dataframe(load_raw_records(raw_path), run_date)
        verify = run_data_quality_checks(repaired_df, settings, f"self_heal_verify_{attempt}")
        outcome.repaired_rows = len(repaired_df)
        outcome.actions.append(
            f"Attempt {attempt}: rebuilt {len(repaired_df)} rows from {raw_path.name}; "
            f"post-repair gate success={verify['success']}."
        )
        if verify["success"]:
            outcome.repaired = True
            outcome.healthy_after = True
            outcome.actions.append("Self-healing succeeded; dataset restored to a healthy state.")
            write_json(settings.paths.quality_dir / "self_healing_log.json", outcome.to_dict())
            return repaired_df, outcome

    outcome.actions.append("Self-healing failed after all attempts; manual investigation required.")
    write_json(settings.paths.quality_dir / "self_healing_log.json", outcome.to_dict())
    return df, outcome
