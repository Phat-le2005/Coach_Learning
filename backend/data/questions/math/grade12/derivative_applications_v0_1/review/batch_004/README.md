# DATA-MATH12-005 — Review batch 004

Batch 004 closes the remaining non-True/False candidates for the derivative chapter.

## Result

- 18 candidates reviewed
- 0 VERIFIED
- 12 `HOLD_VISUAL_SOURCE_REVIEW`
- 6 `REJECTED_DUPLICATE`

Cumulative after batches 001–004:

- 98 / 175 reviewed
- 28 VERIFIED
- 33 HOLD
- 37 REJECTED
- 77 untouched

## Milestone

All remaining 77 untouched candidates are `TRUE_FALSE_GROUP`.

There are now:

- 0 untouched MULTIPLE_CHOICE candidates
- 0 untouched SHORT_ANSWER candidates
- 77 untouched TRUE_FALSE_GROUP candidates

Do **not** force these 77 records through the current single-question TRUE_FALSE model. The next backend data-model task should add `QuestionGroup` support for the official four-substatement True/False format, after which source review can continue.

## Visual holds

The 12 retained MCQs depend on a graph or variation table. A source answer/key alone is not enough to promote them. They remain HOLD until the source visual is extracted, attached, and validated.

## Duplicate handling

Six repeated occurrences are rejected without deleting the immutable raw extraction. `duplicate_of_candidate_id` points directly to the retained candidate.

## Promotion

No new VERIFIED candidate is created in this batch and no production import is allowed.
