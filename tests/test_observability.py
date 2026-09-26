"""Quality-gate, freshness, corruption and reporting tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from core.config import load_settings
from core.utils import read_json
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report, generate_phase1_report

RUN_DATE = datetime(2026, 9, 26, tzinfo=timezone.utc)


@pytest.fixture
def clean_df(raw_records_path):
    return build_clean_dataframe(load_raw_records(raw_records_path), RUN_DATE)


def test_quality_gate_passes_on_clean_data(clean_df, isolated_settings):
    result = run_data_quality_checks(clean_df, isolated_settings, "test_clean")
    assert result["success"] is True
    assert result["failed_checks"] == []
    assert len(result["checks"]) == 5
    assert result["freshness"]["is_fresh"] is True


def test_quality_gate_fails_on_corrupted_data(clean_df, isolated_settings, tmp_path):
    corrupted = corrupt_clean_dataframe(clean_df, tmp_path / "corruption_log.json")
    result = run_data_quality_checks(corrupted, isolated_settings, "test_corrupted")
    assert result["success"] is False
    # Duplicated ids and truncated/blanked content must trip at least one expectation.
    assert result["failed_checks"]


def test_freshness_report_detects_stale_rows(clean_df, isolated_settings, tmp_path):
    stale = clean_df.copy()
    stale["age_days"] = isolated_settings.freshness_threshold_days + 100
    report = build_freshness_report(stale, isolated_settings, tmp_path / "freshness.json")
    assert report["stale_rows"] == len(stale)
    assert report["stale_ratio"] == 1.0
    assert report["is_fresh"] is False


def test_corruption_log_records_six_scenarios(clean_df, tmp_path):
    log_path = tmp_path / "corruption_log.json"
    corrupted = corrupt_clean_dataframe(clean_df, log_path)
    log = read_json(log_path)

    assert log["total_corruptions"] == 6
    assert log["original_rows"] == len(clean_df)
    assert len(corrupted) != len(clean_df)  # duplicates added, latest dropped

    types = {event["type"] for event in log["events"]}
    assert types == {
        "drop_latest_records",
        "blank_summary",
        "inject_noise",
        "truncate_title",
        "stale_date",
        "duplicate_rows",
    }
    for event in log["events"]:
        assert event["affected_rows"] > 0


def test_corruption_is_deterministic(clean_df, tmp_path):
    first = corrupt_clean_dataframe(clean_df, tmp_path / "a.json")
    second = corrupt_clean_dataframe(clean_df, tmp_path / "b.json")
    pd.testing.assert_frame_equal(first, second)


def test_test_set_has_four_question_types(clean_df, tmp_path):
    out = tmp_path / "test_set.json"
    test_set = build_test_set(clean_df, out)
    assert len(test_set) == 10
    assert {item["question_type"] for item in test_set} == {"summary", "authors", "date", "categories"}
    for item in test_set:
        assert item["question"]
        assert item["ground_truth"]
        assert item["ground_truth_doc_ids"]
    assert read_json(out) == test_set
    # Ground-truth doc ids must resolve against the corpus they were built from.
    corpus_ids = set(clean_df["paper_id"])
    for item in test_set:
        assert any(str(d).split("::")[0] in corpus_ids for d in item["ground_truth_doc_ids"])


def test_test_set_requires_minimum_documents():
    with pytest.raises(ValueError):
        build_test_set(pd.DataFrame({"paper_id": ["a"], "title": ["t"]}), "unused.json")


def test_test_set_skips_type_with_empty_source_column(clean_df, tmp_path):
    """A question type whose source column is empty must be dropped, not emitted blank.

    Regression: an empty categories column produced two questions with an empty
    ground truth, which scored 0.0 for a reason unrelated to data corruption.
    """
    df = clean_df.copy()
    df["categories_joined"] = ""
    out = tmp_path / "test_set.json"
    test_set = build_test_set(df, out)

    assert "categories" not in {item["question_type"] for item in test_set}
    assert len(test_set) == 10  # the freed quota moves to answerable types
    for item in test_set:
        assert str(item["ground_truth"]).strip(), f"empty ground truth in {item['id']}"


def test_test_set_rejects_corpus_with_no_answerable_type(clean_df, tmp_path):
    df = clean_df.copy()
    for field in ("summary", "authors_joined", "published", "categories_joined"):
        df[field] = ""
    with pytest.raises(ValueError):
        build_test_set(df, tmp_path / "test_set.json")


def test_stale_test_set_detected_when_corpus_drifts(clean_df):
    """A cached test set whose doc IDs are absent from the corpus must not be reused.

    Regression: a refreshed raw snapshot (different DOIs) left the old test set
    unanswerable and silently drove retrieval_hit_rate to 0.0.
    """
    from pipelines.phase1 import _test_set_matches_corpus

    matching = [{"ground_truth_doc_ids": [clean_df.iloc[0]["paper_id"]]}]
    assert _test_set_matches_corpus(matching, clean_df) is True

    drifted = [{"ground_truth_doc_ids": ["10.1145/does-not-exist"]}]
    assert _test_set_matches_corpus(drifted, clean_df) is False

    # A document id may carry a "::index" suffix; only the base DOI is compared.
    suffixed = [{"ground_truth_doc_ids": [f"{clean_df.iloc[0]['paper_id']}::0"]}]
    assert _test_set_matches_corpus(suffixed, clean_df) is True


def test_reports_are_generated(clean_df, tmp_path):
    metrics = {"retrieval_hit_rate": 0.9, "mean_token_f1": 0.8, "judge_accuracy": 0.9,
               "mean_judge_score": 4.5, "samples": 10}
    corrupted = {"retrieval_hit_rate": 0.4, "mean_token_f1": 0.3, "judge_accuracy": 0.4,
                 "mean_judge_score": 2.5, "samples": 10}
    repaired = {"retrieval_hit_rate": 0.9, "mean_token_f1": 0.8, "judge_accuracy": 0.9,
                "mean_judge_score": 4.5, "samples": 10}
    quality = {"success": True, "checks": []}
    freshness = {"is_fresh": True, "stale_rows": 0, "threshold_days": 180, "total_rows": 24,
                 "stale_ratio": 0.0, "latest_published": "2026-07-22", "oldest_published": "2026-03-28"}

    phase1 = tmp_path / "phase1.md"
    generate_phase1_report(phase1, {"source_api": "Crossref", "clean_rows": 24}, metrics, quality, freshness)
    assert "Baseline" in phase1.read_text(encoding="utf-8")

    comparison = tmp_path / "corruption.md"
    generate_corruption_report(comparison, metrics, corrupted, repaired, quality, quality, freshness, freshness)
    text = comparison.read_text(encoding="utf-8")
    assert "Baseline" in text and "Corrupted" in text and "Repaired" in text
