# Phase 1 — Baseline Data Pipeline Report

_Generated at 2026-09-26T04:18:39.765249+00:00_

## 1. Source & Ingestion

| Attribute | Value |
| :--- | ---: |
| Source | Crossref REST API |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-03-30,has-abstract:true` |
| Raw records | 24 |
| Clean rows | 24 |
| Duplicates removed | 0 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Collection | `papers-baseline` |

## 2. Evaluation Metrics (Baseline)

| Metric | Value |
| :--- | ---: |
| `retrieval_hit_rate` | 1.0000 |
| `mean_token_f1` | 1.0000 |
| `judge_accuracy` | 1.0000 |
| `mean_judge_score` | 5 |
| `samples` | 10 |

## 3. Data Quality Gate (Great Expectations 1.x)

**Overall success:** `True`

| Expectation | Success | Observed | Unexpected |
| :--- | :---: | ---: | ---: |
| `ExpectTableRowCountToBeBetween` | True | 24 | 0 |
| `ExpectColumnValuesToNotBeNull[paper_id]` | True | N/A | 0 |
| `ExpectColumnValuesToNotBeNull[title]` | True | N/A | 0 |
| `ExpectColumnValuesToBeUnique[paper_id]` | True | N/A | 0 |
| `ExpectColumnValueLengthsToBeBetween[summary]` | True | N/A | 0 |

## 4. Freshness SLA

| Attribute | Value |
| :--- | ---: |
| Threshold (days) | 180 |
| Total rows | 24 |
| Stale rows | 1 |
| Stale ratio | 0.0417 |
| Latest published | 2026-07-22 |
| Oldest published | 2026-03-28 |
| **is_fresh** | `True` |

## 5. Conclusion

The baseline corpus was ingested from Crossref REST API, cleaned into
24 embedding-ready rows and indexed in ChromaDB. The quality gate
reported `success=True` and the freshness SLA reported `is_fresh=True`
(stale ratio 0.0417 against a 180-day threshold).
