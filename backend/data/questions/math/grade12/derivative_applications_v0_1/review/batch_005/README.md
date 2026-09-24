# DATA-MATH12-005 — Review batch 005

Purpose: clean question-type misclassification before implementing `QuestionGroup`.

## Batch result

- 14 reviewed
- 1 VERIFIED
- 7 HOLD
- 6 REJECTED_DUPLICATE
- 8 raw `TRUE_FALSE_GROUP` detections confirmed to actually be `MULTIPLE_CHOICE`

## Cumulative state after batches 001–005

- 29 VERIFIED
- 40 HOLD
- 43 REJECTED
- 63 untouched
- 112 reviewed total

## Type cleanup

The following raw candidates were detected as `TRUE_FALSE_GROUP` but are clearly A/B/C/D MCQ:

- 0002
- 0005
- 0011
- 0023
- 0028
- 0034
- 0037
- 0051

`0034` is text-only and can be VERIFIED after source-solution and independent mathematical checks.

The other seven remain visual/source HOLD.

## Duplicate cleanup

The following partial/truncated occurrences are duplicates:

- 0016 -> 0012
- 0029 -> 0031
- 0039 -> 0041
- 0064 -> 0062
- 0067 -> 0068
- 0142 -> 0141

Raw records are not deleted.

## Remaining 63

All 63 untouched candidates still have raw `question_type_detected=TRUE_FALSE_GROUP` and contain all four markers `a)`, `b)`, `c)`, `d)`.

This only establishes structural readiness for `QuestionGroup`; it does not mark them academically VERIFIED.

## Important backend fix

The application must distinguish raw detection from reviewed type:

`effective_question_type = reviewed_question_type ?? question_type_detected`

For HOLD records, `reviewed_question_type` lives inside `review_record`, so the resolver/helper must read that field too.

A corrected MCQ must not continue receiving `TRUE_FALSE_GROUP_UNSUPPORTED` merely because its immutable raw detector value is `TRUE_FALSE_GROUP`.

Raw staging remains unchanged.
