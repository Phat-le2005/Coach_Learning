# DATA-MATH12-004 - Real question extraction v0.1

This staging release was generated from the user's real source corpus.

## Current result

- Unique derivative candidates after exact deduplication: **175**
- ProblemTypes covered: **18/24**
- Multiple choice candidates: **77**
- True/False groups: **77**
- Short-answer candidates: **21**
- Candidates with an answer detected from the source text/solution: **54**
- Visual/table review required: **65**

## Important

This is **not an import-ready canonical question bank yet**.

Every record remains `REVIEW_REQUIRED` because:
1. mathematical symbols from PDF fonts can be distorted by text extraction;
2. graph/table questions require visual comparison with the original page;
3. official 2025 questions in the solution compilation must be cross-checked with the primary Ministry file;
4. provincial compilation questions require page-level issuer/original verification;
5. TRUE/FALSE uses a four-substatement group and the current backend Question model cannot faithfully import that format.

## ProblemType gaps

- PARAMETER_MONOTONICITY
- PARAMETER_EXTREMA_COUNT
- GLOBAL_EXTREMA_SIMPLE_DOMAIN
- COMPLETE_FUNCTION_ANALYSIS_LINEAR_FRACTION
- COMPLETE_FUNCTION_ANALYSIS_QUADRATIC_OVER_LINEAR
- REAL_WORLD_MONOTONICITY_INTERPRETATION

These gaps should drive the next source search instead of collecting random additional PDFs.

## Files

- `source_catalog.json`: source-level provenance.
- `subsource_catalog.json`: 4 MOET codes, 10 provincial exams, 40 Trương Ngọc Vỹ exams.
- `candidate_questions.json`: extracted candidate records with taxonomy mappings.
- `coverage_report.json`: coverage against all 24 derivative ProblemTypes.
- `review_queue.csv`: manual/AI-assisted visual review queue.
- `extraction_stats.json`: release statistics.

## Promotion rule

Only promote a candidate to canonical/importable data after:
- page image/formula review;
- answer verification;
- ProblemType/Concept/LearningOutcome review;
- provenance/usage review;
- QuestionGroup support for TRUE/FALSE groups when applicable.
