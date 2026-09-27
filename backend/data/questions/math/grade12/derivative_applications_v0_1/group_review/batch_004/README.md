# DATA-MATH12-008 — Trương Ngọc Vỹ QuestionGroup review — batch 004

## Source
- `40-de-on-thi-tot-nghiep-thpt-2026-mon-toan-co-loi-giai-chi-tiet-truong-ngoc-vy.pdf`
- Drive file ID: `1kVuA8ZIb402-_TM_fqI_tj1WuS0CBwg1`
- PDF pages: 778
- SHA-256: `15579d487c6ad6cdd6386c96ac829c48710c3ca66104acfbd0fc9e9183b586b4`

## Scope
Tests 21–30. The current structural snapshot contains 13 target QuestionGroup candidates in this range; test 25 contributes no target group.

## Results
- VERIFIED: 8
- HOLD_SOURCE_ANSWER_CONFLICT: 1
- REJECTED: 4
  - duplicate: 3
  - out of current derivative scope: 1
- VERIFIED child statements / trusted answers: 32
- visual asset required: 0
- promotion ready: 0

### VERIFIED answer patterns
- 0116 = T T F F
- 0120 = T T F T
- 0124 = T T F F
- 0126 = T F T F
- 0131 = F T T F
- 0134 = F F T T
- 0136 = T T T F
- 0141 = F T F T

### Source-answer conflict
- 0138 (test 29, question 1): source table = `F F T F`, but the detailed solution implies `c=F` and `d=T`. Keep this group as `HOLD_SOURCE_ANSWER_CONFLICT`; do not silently correct or assign trusted answers to the conflicting children.

### Rejected from the current derivative dataset
- 0118 -> duplicate of 0116 (solution reprint)
- 0122 -> duplicate of 0120 (solution reprint)
- 0127 -> duplicate of 0126 (solution reprint)
- 0139 -> spatial-geometry sphere problem; preserve for broader exam/geometry routing

Codex must integrate this reviewed bundle only. It must not access Drive/PDF or recompute the answers.
