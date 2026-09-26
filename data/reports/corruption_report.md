# Corruption & Repair — 3-State Comparison Report

_Generated at 2026-09-26T04:19:14.591076+00:00_

## 1. Performance Comparison

| Metric | Baseline | Corrupted | Repaired | Delta (corruption) | Recovery |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.6000 | 1.0000 | -0.4000 | 100.0% |
| `mean_token_f1` | 1.0000 | 0.7741 | 1.0000 | -0.2259 | 100.0% |
| `judge_accuracy` | 1.0000 | 0.8000 | 1.0000 | -0.2000 | 100.0% |
| `mean_judge_score` | 5 | 4 | 5 | -1 | 100.0% |

## 2. Quality & Freshness Signals

| Signal | Baseline | Corrupted | Repaired |
| :--- | ---: | ---: | ---: |
| Quality gate success | True | False | True |
| Freshness is_fresh | True | False | True |
| Stale rows | N/A | 7 | 1 |

### Corrupted quality gate

**Overall success:** `False`

| Expectation | Success | Observed | Unexpected |
| :--- | :---: | ---: | ---: |
| `ExpectTableRowCountToBeBetween` | True | 22 | 0 |
| `ExpectColumnValuesToNotBeNull[paper_id]` | True | N/A | 0 |
| `ExpectColumnValuesToNotBeNull[title]` | True | N/A | 0 |
| `ExpectColumnValuesToBeUnique[paper_id]` | False | N/A | 6 |
| `ExpectColumnValueLengthsToBeBetween[summary]` | False | N/A | 6 |

### Repaired quality gate

**Overall success:** `True`

| Expectation | Success | Observed | Unexpected |
| :--- | :---: | ---: | ---: |
| `ExpectTableRowCountToBeBetween` | True | 24 | 0 |
| `ExpectColumnValuesToNotBeNull[paper_id]` | True | N/A | 0 |
| `ExpectColumnValuesToNotBeNull[title]` | True | N/A | 0 |
| `ExpectColumnValuesToBeUnique[paper_id]` | True | N/A | 0 |
| `ExpectColumnValueLengthsToBeBetween[summary]` | True | N/A | 0 |

## 3. Interpretation

The corrupted dataset demonstrates **silent failure**: the pipeline still runs, but retrieval and
answer quality degrade because summaries were blanked/noised, titles truncated and dates pushed stale.
The repair step rebuilds the corpus from the trusted raw snapshot (`data/raw/crossref_records.json`)
via the idempotent cleaning path, so re-running repair yields the identical clean dataset.
Quality gate and freshness signals return to their baseline state, and the agent metrics recover
to (or very near) the baseline values.
