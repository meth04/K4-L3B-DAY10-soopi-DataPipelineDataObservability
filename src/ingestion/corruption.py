from __future__ import annotations

import random

import pandas as pd

from core.utils import write_json
from ingestion.cleaning import build_text_for_embedding

RANDOM_SEED = 42
NOISE_TOKENS = ["@@@", "###", "???", "zzz", "%%%", "!!!", "~~~", "&&&"]
NOISE_PREFIX = "lorem ipsum dolor sit amet "
STALE_DAYS = 900


def _rebuild_embedding_text(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["authors_joined"] = df["authors"].apply(lambda value: ", ".join(value) if isinstance(value, list) else value)
    df["categories_joined"] = (
        df["categories"].apply(lambda value: ", ".join(value) if isinstance(value, list) else value)
    )
    df["summary_chars"] = df["summary"].fillna("").str.len()
    df["title_chars"] = df["title"].fillna("").str.len()
    df["text_for_embedding"] = df.apply(build_text_for_embedding, axis=1)
    return df


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Inject 6 realistic data-corruption scenarios and log every mutation."""
    rng = random.Random(RANDOM_SEED)
    working = df.copy().reset_index(drop=True)
    original_rows = len(working)
    events: list[dict] = []

    # 1. Drop the newest records (simulates a failed incremental load).
    drop_count = max(1, int(round(original_rows * 0.2)))
    dropped_ids = working.head(drop_count)["paper_id"].tolist()
    working = working.iloc[drop_count:].reset_index(drop=True)
    events.append(
        {
            "type": "drop_latest_records",
            "description": f"Dropped the {drop_count} most recent records ({drop_count}/{original_rows} = 20%).",
            "affected_rows": drop_count,
            "affected_paper_ids": dropped_ids,
        }
    )

    if working.empty:
        write_json(output_log_path, {"seed": RANDOM_SEED, "original_rows": original_rows, "events": events})
        return working

    row_count = len(working)
    blank_idx = rng.sample(range(row_count), max(1, int(round(row_count * 0.25))))
    working.loc[blank_idx, "summary"] = ""
    events.append(
        {
            "type": "blank_summary",
            "description": "Replaced the abstract with an empty string on sampled rows.",
            "affected_rows": len(blank_idx),
            "affected_paper_ids": working.loc[blank_idx, "paper_id"].tolist(),
        }
    )

    remaining = [i for i in range(row_count) if i not in set(blank_idx)]
    noise_idx = rng.sample(remaining, max(1, int(round(row_count * 0.2)))) if remaining else []
    for idx in noise_idx:
        tokens = " ".join(rng.choice(NOISE_TOKENS) for _ in range(6))
        working.at[idx, "summary"] = f"{NOISE_PREFIX}{tokens} {working.at[idx, 'summary']}"
    events.append(
        {
            "type": "inject_noise",
            "description": "Prepended lorem-ipsum and junk tokens to the abstract.",
            "affected_rows": len(noise_idx),
            "affected_paper_ids": working.loc[noise_idx, "paper_id"].tolist(),
        }
    )

    truncate_idx = rng.sample(range(row_count), max(1, int(round(row_count * 0.2))))
    working.loc[truncate_idx, "title"] = working.loc[truncate_idx, "title"].str.slice(0, 7)
    events.append(
        {
            "type": "truncate_title",
            "description": "Truncated titles to 7 characters (below the 8-character minimum).",
            "affected_rows": len(truncate_idx),
            "affected_paper_ids": working.loc[truncate_idx, "paper_id"].tolist(),
        }
    )

    stale_idx = rng.sample(range(row_count), max(1, int(round(row_count * 0.3))))
    for idx in stale_idx:
        published = pd.to_datetime(working.at[idx, "published"], errors="coerce")
        if pd.isna(published):
            continue
        working.at[idx, "published"] = (published - pd.Timedelta(days=STALE_DAYS)).date().isoformat()
        working.at[idx, "age_days"] = int(working.at[idx, "age_days"]) + STALE_DAYS
    events.append(
        {
            "type": "stale_date",
            "description": f"Pushed {len(stale_idx)} publication dates {STALE_DAYS} days into the past.",
            "affected_rows": len(stale_idx),
            "affected_paper_ids": working.loc[stale_idx, "paper_id"].tolist(),
        }
    )

    duplicate_count = max(1, int(round(row_count * 0.15)))
    duplicates = working.head(duplicate_count).copy()
    working = pd.concat([working, duplicates], ignore_index=True)
    events.append(
        {
            "type": "duplicate_rows",
            "description": "Appended duplicated rows, breaking paper_id uniqueness.",
            "affected_rows": duplicate_count,
            "affected_paper_ids": duplicates["paper_id"].tolist(),
        }
    )

    working = _rebuild_embedding_text(working)
    write_json(
        output_log_path,
        {
            "seed": RANDOM_SEED,
            "original_rows": original_rows,
            "final_rows": len(working),
            "total_corruptions": len(events),
            "events": events,
        },
    )
    return working
