from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import write_json

MIN_DOCUMENTS = 4
TOTAL_QUESTIONS = 10
QUESTION_TYPES = ("summary", "authors", "date", "categories")

# Column that must be non-empty for a question type to be answerable. A question
# whose ground truth is empty is unanswerable by construction and would depress the
# score for a reason that has nothing to do with the data being corrupted.
QUESTION_FIELD = {
    "summary": "summary",
    "authors": "authors_joined",
    "date": "published",
    "categories": "categories_joined",
}


def _first_sentence(text: str) -> str:
    chunks = [chunk.strip() for chunk in str(text).split(".") if chunk.strip()]
    return chunks[0] + "." if chunks else str(text).strip()


def _build_question(question_type: str, row: pd.Series) -> tuple[str, str]:
    title = row["title"]
    if question_type == "summary":
        return f"What is the summary of the paper '{title}'?", _first_sentence(row["summary"])
    if question_type == "authors":
        return f"Who authored the paper '{title}'?", row["authors_joined"]
    if question_type == "date":
        return f"When was the paper '{title}' published?", row["published"]
    return f"What categories does the paper '{title}' belong to?", row["categories_joined"]


def _question_quota(total: int, groups: int) -> list[int]:
    """Split `total` questions as evenly as possible across `groups` types.

    10 questions over 4 types -> [3, 3, 2, 2].
    """
    base, remainder = divmod(total, groups)
    return [base + (1 if index < remainder else 0) for index in range(groups)]


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build a 10-question benchmark spanning the available business question types."""
    if len(df) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} documents to build a test set, got {len(df)}.")

    # Deterministic sampling: sort once by recency, then stride-sample within each
    # question type so the same test set is reproducible for baseline, corrupted
    # and repaired runs. A type whose source column is empty across the corpus is
    # dropped rather than emitted with an empty ground truth.
    ordered = df.sort_values("published", ascending=False).reset_index(drop=True)
    pools: dict[str, pd.DataFrame] = {}
    for question_type in QUESTION_TYPES:
        field = QUESTION_FIELD[question_type]
        pool = ordered[ordered[field].astype(str).str.strip().ne("")].reset_index(drop=True)
        if not pool.empty:
            pools[question_type] = pool
    if not pools:
        raise ValueError("No question type has a non-empty source column; cannot build a test set.")

    types = list(pools)
    quotas = dict(zip(types, _question_quota(TOTAL_QUESTIONS, len(types)), strict=True))
    # Types that cannot supply their quota release it to types that still have room,
    # so the total question count stays at TOTAL_QUESTIONS whenever the corpus allows.
    for _ in range(len(types)):
        overflow = sum(max(0, quota - len(pools[type_])) for type_, quota in quotas.items())
        if overflow == 0:
            break
        for type_ in types:
            quotas[type_] = min(quotas[type_], len(pools[type_]))
        for _ in range(overflow):
            for type_ in types:
                if quotas[type_] < len(pools[type_]):
                    quotas[type_] += 1
                    break

    test_set: list[dict[str, Any]] = []
    counter = 0
    for question_type in types:
        pool = pools[question_type]
        count = quotas[question_type]
        step = max(1, len(pool) // count)
        picked = pool.iloc[::step].head(count).reset_index(drop=True)
        if len(picked) < count:
            picked = pool.head(count).reset_index(drop=True)
        for index in range(count):
            row = picked.iloc[index]
            question, ground_truth = _build_question(question_type, row)
            if not str(ground_truth).strip():
                raise ValueError(
                    f"Question type '{question_type}' produced an empty ground truth; "
                    "this question would be unanswerable."
                )
            counter += 1
            test_set.append(
                {
                    "id": f"q{counter:02d}",
                    "question_type": question_type,
                    "question": question,
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [row["paper_id"]],
                }
            )

    write_json(output_path, test_set)
    return test_set
