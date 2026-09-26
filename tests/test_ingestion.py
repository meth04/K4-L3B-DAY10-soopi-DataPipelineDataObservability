"""Ingestion & cleaning tests: Crossref parsing, fallback loading and data modeling."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.config import load_settings
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records, parse_crossref_payload


@pytest.fixture
def sample_payload() -> dict:
    return {
        "status": "ok",
        "message": {
            "items": [
                {
                    "DOI": "10.1000/test.1",
                    "title": ["A Test Paper on Retrieval Augmented Generation"],
                    "abstract": "<jats:p>This abstract describes RAG systems in enough detail to pass validation.</jats:p>",
                    "author": [{"given": "An", "family": "Nguyen"}, {"given": "Binh", "family": "Tran"}],
                    "subject": ["Artificial Intelligence", "Information Retrieval"],
                    "published": {"date-parts": [[2025, 1, 15]]},
                    "created": {"date-time": "2025-01-15T10:00:00Z"},
                    "URL": "https://doi.org/10.1000/test.1",
                },
                {
                    # Invalid: no title -> must be dropped.
                    "DOI": "10.1000/test.2",
                    "title": [],
                    "abstract": "<jats:p>Short.</jats:p>",
                    "published": {"date-parts": [[2025, 2, 1]]},
                },
                {
                    # Invalid: no DOI -> must be dropped.
                    "DOI": "",
                    "title": ["Missing DOI Paper Title Here"],
                    "abstract": "<jats:p>This abstract is long enough to be embedded into the index.</jats:p>",
                    "published": {"date-parts": [[2025, 2, 1]]},
                },
            ]
        },
    }


def test_parse_crossref_payload_strips_jats_and_filters(sample_payload):
    records = parse_crossref_payload(sample_payload)
    assert len(records) == 1
    record = records[0]
    assert record.paper_id == "10.1000/test.1"
    assert "<jats:p>" not in record.summary
    assert record.summary.startswith("This abstract describes")
    assert record.authors == ["An Nguyen", "Binh Tran"]
    assert record.primary_category == "Artificial Intelligence"
    assert record.published == "2025-01-15"


def test_parse_crossref_payload_empty_message():
    assert parse_crossref_payload({}) == []
    assert parse_crossref_payload({"message": {}}) == []


def test_load_raw_records_from_snapshot(raw_records_path):
    records = load_raw_records(raw_records_path)
    assert len(records) == 24
    assert all(record.paper_id for record in records)
    assert all(record.summary for record in records)


def test_build_clean_dataframe_schema(raw_records_path):
    records = load_raw_records(raw_records_path)
    df = build_clean_dataframe(records, datetime(2026, 9, 26, tzinfo=timezone.utc))

    expected_columns = {
        "paper_id",
        "title",
        "summary",
        "authors_joined",
        "categories_joined",
        "age_days",
        "text_for_embedding",
    }
    assert expected_columns.issubset(set(df.columns))
    assert len(df) == 24
    assert df["paper_id"].is_unique
    assert (df["age_days"] >= 0).all()
    # text_for_embedding must carry all 5 structural parts.
    sample_text = df.iloc[0]["text_for_embedding"]
    for label in ("Title:", "Authors:", "Published:", "Categories:", "Abstract:"):
        assert label in sample_text


def test_build_clean_dataframe_deduplicates(raw_records_path):
    records = load_raw_records(raw_records_path)
    duplicated = records + records
    df = build_clean_dataframe(duplicated, datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert len(df) == len(records)
    assert df["paper_id"].is_unique


def test_build_clean_dataframe_empty():
    df = build_clean_dataframe([], datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert df.empty


def test_settings_paths_are_relative_to_project():
    """All artifact paths must derive from the project dir (no hardcoded absolute paths)."""
    settings = load_settings()
    project_dir = settings.paths.project_dir
    assert project_dir.is_absolute()
    for path in (settings.paths.clean_json, settings.paths.baseline_metrics, settings.paths.comparison_report):
        assert path.is_absolute()
        assert project_dir in path.parents
    assert settings.max_results == 24
