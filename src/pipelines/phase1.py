from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.config import load_settings, normalized_provider, require_llm_credentials
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


def _load_records(settings):
    if settings.refresh_source or not settings.paths.raw_records_json.exists():
        return fetch_source_records(settings)
    print(f"[phase1] Using existing raw snapshot at {settings.paths.raw_records_json}")
    return load_raw_records(settings.paths.raw_records_json)


def _test_set_matches_corpus(test_set, df: pd.DataFrame) -> bool:
    """True only if every question's ground-truth document exists in the corpus.

    A test set is only meaningful against the corpus it was built from. If the raw
    snapshot is refreshed (live Crossref fetch returns a different set of DOIs) the
    cached test set silently becomes unanswerable: retrieval_hit_rate collapses to
    0.0 with no error. Detect that drift and rebuild instead of reporting a
    meaningless score.
    """
    corpus_ids = {str(paper_id) for paper_id in df["paper_id"]}
    for item in test_set:
        doc_ids = item.get("ground_truth_doc_ids") or []
        if not any(str(doc_id).split("::")[0] in corpus_ids for doc_id in doc_ids):
            return False
    return True


def _load_or_build_test_set(settings, df: pd.DataFrame):
    path = settings.paths.eval_testset
    if settings.refresh_test_set or not path.exists():
        return build_test_set(df, path)
    existing = read_json(path)
    if not _test_set_matches_corpus(existing, df):
        print("[phase1] Cached test set does not match the current corpus; rebuilding.")
        return build_test_set(df, path)
    print(f"[phase1] Reusing existing test set at {path}")
    return existing


def _demo_agent(settings, index, test_set) -> None:
    """Run a short agent demo over sample questions (mock/offline friendly)."""
    try:
        require_llm_credentials(settings)
        from retrieval.agent import build_agent, run_agent_question

        agent = build_agent(settings, index)
        demo = []
        for item in test_set[:3]:
            answer = run_agent_question(agent, item["question"])
            demo.append({"question": item["question"], "answer": answer})
            print(f"[demo] Q: {item['question']}\n       A: {answer}")
        write_json(settings.paths.demo_answers, demo)
    except Exception as exc:
        print(f"[demo] Agent demo skipped: {type(exc).__name__}: {exc}")


def main() -> None:
    """Baseline pipeline: ingest -> clean -> index -> evaluate -> observe -> report."""
    settings = load_settings()
    run_date = now_utc()
    print(f"[phase1] Starting baseline pipeline (provider={normalized_provider(settings)})")

    # 1. Ingest raw records (live fetch or local snapshot fallback).
    records = _load_records(settings)
    print(f"[phase1] Loaded {len(records)} raw records from {settings.source_api}")

    # 2. Clean into an embedding-ready dataframe.
    df = build_clean_dataframe(records, run_date)
    if df.empty:
        raise RuntimeError("Cleaning produced an empty dataframe; aborting baseline pipeline.")
    write_csv(df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, df.to_dict(orient="records"))
    print(f"[phase1] Clean dataframe: {len(df)} rows -> {settings.paths.clean_json}")

    # 3. Build the ChromaDB vector index.
    index = LocalEmbeddingIndex.build(df, settings, settings.paths.embeddings_json)
    print(f"[phase1] Indexed {len(index.documents)} documents into '{index.collection_name}'")

    # 4. Build or reuse the evaluation set.
    test_set = _load_or_build_test_set(settings, df)
    print(f"[phase1] Test set: {len(test_set)} questions")

    # 5. Evaluate the RAG pipeline.
    bundle = evaluate_pipeline(
        settings,
        index,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    )
    print(f"[phase1] Baseline metrics: {bundle.summary}")

    # 6. Data quality gate + freshness SLA.
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = quality["freshness"]
    print(f"[phase1] Quality success={quality['success']} is_fresh={freshness['is_fresh']}")

    # 7. Write the baseline markdown report.
    source_summary = {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "raw_records": len(records),
        "clean_rows": len(df),
        "duplicates_removed": max(0, len(records) - len(df)),
        "embedding_model": settings.embedding_model,
        "collection_name": index.collection_name,
    }
    generate_phase1_report(
        settings.paths.baseline_report, source_summary, bundle.summary, quality, freshness
    )
    print(f"[phase1] Report written -> {settings.paths.baseline_report}")

    # 8. Optional agent demo.
    _demo_agent(settings, index, test_set)

    print("[phase1] Baseline pipeline complete.")


if __name__ == "__main__":
    main()
