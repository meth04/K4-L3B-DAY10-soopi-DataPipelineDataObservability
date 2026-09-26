from __future__ import annotations

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import run_data_quality_checks
from observability.reporting import generate_corruption_report
from observability.self_healing import auto_heal
from retrieval.index import LocalEmbeddingIndex


def _clean_dataframe_to_records(df: pd.DataFrame) -> list[dict]:
    return df.to_dict(orient="records")


def main() -> None:
    """Corruption flow: corrupt -> evaluate -> repair from raw -> compare."""
    settings = load_settings()
    print("[corruption] Starting corruption -> repair flow")

    # 1. Load the baseline metrics + freshness for comparison.
    if not settings.paths.baseline_metrics.exists():
        raise RuntimeError("Run script/run_phase1.py first: baseline_metrics.json is missing.")
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    baseline_freshness = (
        read_json(settings.paths.freshness_report) if settings.paths.freshness_report.exists() else {}
    )
    baseline_quality = (
        read_json(settings.paths.baseline_quality_report)
        if settings.paths.baseline_quality_report.exists()
        else {}
    )
    baseline_metrics["quality_success"] = baseline_quality.get("success")
    baseline_metrics["is_fresh"] = baseline_freshness.get("is_fresh")

    # 2. Load the trusted raw snapshot and rebuild the clean baseline dataframe.
    raw_records = load_raw_records(settings.paths.raw_records_json)
    clean_df = build_clean_dataframe(raw_records, now_utc())
    print(f"[corruption] Baseline clean rows: {len(clean_df)}")

    # 3. Inject the 6 corruption scenarios.
    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, _clean_dataframe_to_records(corrupted_df))
    print(f"[corruption] Corrupted rows: {len(corrupted_df)} -> {settings.paths.corruption_log}")

    # 4. Re-index and evaluate the corrupted corpus.
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, settings.paths.corrupted_embeddings_json)
    corrupted_bundle = evaluate_pipeline(
        settings,
        corrupted_index,
        settings.paths.eval_testset,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    print(f"[corruption] Corrupted metrics: {corrupted_bundle.summary}")

    # 5. Idempotent repair driven by the automated self-healing guardrail. The guardrail
    #    validates the corrupted corpus, detects the quality violations, and rebuilds the
    #    dataset from the trusted raw snapshot without manual intervention.
    repaired_df, healing = auto_heal(corrupted_df, settings, now_utc())
    print(
        f"[corruption] Self-healing guardrail: healthy_before={healing.healthy_before} "
        f"violations={healing.violations} repaired={healing.repaired}"
    )
    print(f"[corruption] Self-healing actions: {healing.actions}")

    if not healing.repaired:
        # Guardrail could not restore health; fall back to the direct idempotent repair path.
        print("[corruption] Guardrail did not restore health; running direct idempotent repair.")
        repaired_df = build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), now_utc())

    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, _clean_dataframe_to_records(repaired_df))
    print(f"[corruption] Repaired rows: {len(repaired_df)}")

    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, settings.paths.repaired_embeddings_json)
    repaired_bundle = evaluate_pipeline(
        settings,
        repaired_index,
        settings.paths.eval_testset,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    print(f"[corruption] Repaired metrics: {repaired_bundle.summary}")

    # 6. Verify repair idempotency: repairing twice must yield the same dataframe.
    repaired_again = build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), now_utc())
    idempotent = repaired_df.equals(repaired_again)
    print(f"[corruption] Repair idempotent: {idempotent}")

    # 7. Print the 3-state comparison and write the markdown report.
    print("\n=== Baseline vs Corrupted vs Repaired ===")
    header = f"{'metric':<20}{'baseline':>12}{'corrupted':>12}{'repaired':>12}"
    print(header)
    print("-" * len(header))
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        print(
            f"{key:<20}{baseline_metrics.get(key, 0):>12.4f}"
            f"{corrupted_bundle.summary.get(key, 0):>12.4f}"
            f"{repaired_bundle.summary.get(key, 0):>12.4f}"
        )

    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics,
        corrupted_bundle.summary,
        repaired_bundle.summary,
        corrupted_quality,
        repaired_quality,
        corrupted_quality["freshness"],
        repaired_quality["freshness"],
    )
    print(f"\n[corruption] Comparison report -> {settings.paths.comparison_report}")
    print("[corruption] Corruption flow complete.")


if __name__ == "__main__":
    main()
