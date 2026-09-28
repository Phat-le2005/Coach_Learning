# DATA-MATH12-016 - Vector question materialization v0.1

Base commit: `1bbd044497b873df78fa5cfdcb388ca8ecff9035`

This bundle materializes real Vector/Coordinate structural candidates from the three SHA-locked PDFs already registered in DATA-MATH12-015. No question is fabricated.

## Result

- raw included source occurrences: **132**
- deduplicated unique candidates: **72**
- standalone candidates: **58**
- TRUE_FALSE_FOUR groups: **14**
- structural holds: **0**
- MCQ: **54**
- TRUE_FALSE_GROUP: **14**
- short answer: **4**
- visual-required preflight: **53**
- detected source-solution answers: **47** (not academically verified)
- mixed-scope TRUE_FALSE_FOUR: **12**
- ProblemTypes with candidates: **9 / 15**

Coverage gaps are intentionally reported instead of filling them with fake questions.

## Source integrity

All three local PDF binaries were SHA-256 checked and exactly match the DATA-MATH12-015 locks. PDFs themselves are not included in this bundle/repo.

## Important boundaries

`answer_detected` is only extraction evidence, never an approved answer. TRUE_FALSE child correct answers remain null. All candidates remain `STRUCTURAL_CANDIDATE` / `NOT_REVIEWED`.

OXYZ-primary standalone tasks are excluded. A mixed TRUE_FALSE_FOUR is retained atomically only when vector-scope children share context with OXYZ children; it is marked `mixed_scope=true` for academic review.
