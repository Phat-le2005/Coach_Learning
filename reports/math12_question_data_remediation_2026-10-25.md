# Math 12 Question Bank: local remediation (25 October 2026)

Scope: the local development database at `D:\CoachLearning`. This follows the read-only audit in `math12_question_data_audit_2026-10-25.md`. It does not change curated JSON, academic answers, taxonomy, or source files.

## What was found

- 559 Question rows and 61 QuestionGroup rows were all `APPROVED`, even though source review has 27 non-VERIFIED candidate/group units.
- 293 Question rows had a PDF presentation warning; 285 contained Unicode Private Use font glyphs and 8 were flagged only by the fragmented-line heuristic. This is a presentation signal, not a judgment about the mathematics.
- 18 groups lacked at least one child answer. The previous practice selector could offer such a group, then fail to grade it.
- Four standalone short-answer questions lacked answer keys. Several rows lacked academic mappings.
- A local `SAMPLE_TEST` open-response question has no academic mappings; it is an OCR sandbox, not classified practice content.

## Changes to the local database

The default `python -m app.reconcile_question_data` is a read-only audit. On the development database, `--apply` wrote a JSON status backup first and changed 329 Question statuses and 21 QuestionGroup statuses from `APPROVED` to `REVIEW`. One `SAMPLE_TEST` OCR sandbox Question was then restored to `APPROVED` because the classified practice selectors already exclude it and 12 existing demo attempts depend on it. That exception has a separate audit record. **Net status changes: 328 Questions and 21 groups.** No rows were deleted.

The backup is `.tmp/question-data-reconciliation-2026-10-25.json`; the sandbox exception is `.tmp/question-data-reconciliation-sandbox-exception-2026-10-25.json`. These local files are intentionally ignored by Git. The status changes are reversible using the backup after an actual source review; restoring the full set now would reintroduce the same student-facing defects.

| Status after remediation | Questions | Groups |
|---|---:|---:|
| APPROVED | 231 | 40 |
| REVIEW | 328 | 21 |

All 329 Question content hashes in the backup still match the database. The remediated audit returns zero additional status changes, and zero remaining `APPROVED` questions are flagged by the PDF text detector. Existing solution attempts remain readable; attempts on quarantined questions are read-only and cannot be graded or changed. The explicit OCR sandbox remains writable for testing handwriting, but is not selected as a classified practice question.

## Remaining usable mapped questions

| Chapter | APPROVED mapped Questions | REVIEW mapped Questions | Active ProblemTypes without an APPROVED Question |
|---|---:|---:|---:|
| Derivative applications | 152 | 0 | 4 |
| Grouped data dispersion | 34 | 13 | 6 |
| Integrals | 12 | 71 | 3 |
| Oxyz | 18 | 127 | 6 |
| Conditional probability | 12 | 5 | 1 |
| Vectors and coordinates | 2 | 112 | 14 |

The additional APPROVED Question is the unmapped OCR sandbox. Curriculum nodes remain in the database; an empty practice target now means that no verified, presentable Question is currently available for that target.

## Remaining work requiring real source review

1. For the 285 Private Use and 8 fragmented-text Questions, supply faithful reviewed display text/LaTeX or a permitted full-question asset from the source. Do not reconstruct a mathematical formula from the broken extraction.
2. Resolve the source-review HOLD/REJECTED rows only through the corresponding academic review process. Rejected and out-of-scope rows should not be reapproved.
3. Supply missing child answer keys and standalone short-answer keys from trusted source evidence before returning those rows to `APPROVED`.
4. Keep question publication separate from source-review validation. The curated pipeline still reports `database_import_allowed=false`, `production_release_allowed=false`, and `rights_status=REVIEW_REQUIRED`; this local remediation does not clear those blockers.

The new reconciliation command is development/test-only and writes no academic content. It should be rerun after reviewed display corrections or new data imports; a zero-change result means that its current safety rules find no further rows to quarantine, not that all Math 12 coverage is complete.
