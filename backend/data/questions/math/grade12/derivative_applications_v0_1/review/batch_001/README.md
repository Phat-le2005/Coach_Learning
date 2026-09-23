# DATA-MATH12-005 - Verified question review, batch 001

Scope: Grade 12 Mathematics - `Ứng dụng đạo hàm để khảo sát và vẽ đồ thị của hàm số`.

This batch performs human/source review over selected candidates from DATA-MATH12-004.

## Result

- 16 candidates reviewed
- 12 VERIFIED
- 2 HOLD
- 2 REJECTED_OUT_OF_SCOPE
- 159 candidates remain unreviewed

`VERIFIED` in this review layer means:
- source page checked;
- answer checked against the source solution where available;
- answer independently sanity-checked mathematically;
- ProblemType/Concept/LearningOutcome mapping accepted for this batch;
- cleaned question content prepared.

It does **not** mean the record may enter production automatically. Explicit promotion is still blocked while the curriculum taxonomy remains staging and before a promotion workflow exists.

## Important findings

1. `M12_DERIV_CAND_0038` was incorrectly detected as `SHORT_ANSWER`; the source is a 4-option multiple-choice question. Corrected to `MULTIPLE_CHOICE`.
2. `M12_DERIV_CAND_0121` is held because the source answer says a reducible rational function has no oblique asymptote, while the usual limit-based definition gives the line `y=x-2` as an asymptote. Do not promote until the project adopts an explicit convention.
3. `M12_DERIV_CAND_0152` is an integral/area application and is rejected from the derivative chapter.
4. `M12_DERIV_CAND_0172` is an exponential/logarithmic monotonicity question and is rejected from the derivative chapter.

## Files

- `verified_candidates.json`: clean reviewed records.
- `hold_candidates.json`: questions needing expert/convention review.
- `rejected_candidates.json`: false-positive chapter classifications.
- `candidate_patch.json`: deterministic patch instructions for DATA-MATH12-004 candidates.
- `review_stats.json`: batch summary.

Do not delete the original raw candidate text. The review layer is additive and auditable.
