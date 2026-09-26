from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

MIN_SUMMARY_CHARS = 40
MIN_TITLE_CHARS = 8

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "title_chars",
    "abs_url",
    "pdf_url",
    "text_for_embedding",
]


def build_text_for_embedding(row: pd.Series) -> str:
    """Compose the 5-part embedding document: title, authors, date, categories, summary."""
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined'] or 'Unknown'}",
            f"Published: {row['published'] or 'Unknown'}",
            f"Categories: {row['categories_joined'] or 'Uncategorized'}",
            f"Abstract: {row['summary']}",
        ]
    )


def _as_utc_timestamp(value: datetime) -> pd.Timestamp:
    """Coerce a datetime (naive or aware) into a UTC-aware pandas Timestamp."""
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Normalize raw Crossref records into an embedding-ready dataframe."""
    if not records:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    run_timestamp = _as_utc_timestamp(run_date)
    rows = []
    for record in records:
        title = normalize_whitespace(record.title)
        summary = normalize_whitespace(record.summary)
        if len(title) < MIN_TITLE_CHARS or len(summary) < MIN_SUMMARY_CHARS:
            # Too short to be a useful retrieval target.
            continue

        published_ts = pd.to_datetime(record.published, errors="coerce", utc=True)
        updated_ts = pd.to_datetime(record.updated or record.published, errors="coerce", utc=True)
        if pd.isna(published_ts):
            continue

        age_days = max(0, int((run_timestamp - published_ts).days))

        authors = [normalize_whitespace(a) for a in record.authors if normalize_whitespace(a)]
        categories = [normalize_whitespace(c) for c in record.categories if normalize_whitespace(c)]

        rows.append(
            {
                "paper_id": normalize_whitespace(record.paper_id),
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "primary_category": normalize_whitespace(record.primary_category)
                or (categories[0] if categories else ""),
                "published": published_ts.date().isoformat(),
                "updated": (updated_ts.date().isoformat() if not pd.isna(updated_ts) else ""),
                "age_days": age_days,
                "authors_joined": compact_join(authors),
                "categories_joined": compact_join(categories),
                "summary_chars": len(summary),
                "title_chars": len(title),
                "abs_url": record.abs_url,
                "pdf_url": record.pdf_url,
            }
        )

    df = pd.DataFrame(rows, columns=[c for c in CLEAN_COLUMNS if c != "text_for_embedding"])
    df = df.drop_duplicates(subset=["paper_id"], keep="first")
    df = df.sort_values("published", ascending=False).reset_index(drop=True)
    df["text_for_embedding"] = df.apply(build_text_for_embedding, axis=1)
    return df[CLEAN_COLUMNS]
