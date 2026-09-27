# DATA-MATH12-008 — Trương Ngọc Vỹ QuestionGroup review — batch 005

## Source
- `40-de-on-thi-tot-nghiep-thpt-2026-mon-toan-co-loi-giai-chi-tiet-truong-ngoc-vy.pdf`
- Drive file ID: `1kVuA8ZIb402-_TM_fqI_tj1WuS0CBwg1`
- PDF pages: 778
- SHA-256: `15579d487c6ad6cdd6386c96ac829c48710c3ca66104acfbd0fc9e9183b586b4`

## Scope
Tests 31–40. The current structural snapshot contains 13 target QuestionGroup candidates in this range; test 35 contributes no target group.

## Results
- VERIFIED: 8
- HOLD_SOURCE_ANSWER_CONFLICT: 1
- REJECTED: 4
  - duplicate: 2
  - out of current derivative scope: 2
- VERIFIED child statements / trusted answers: 32
- visual asset required: 3
- promotion ready: 0

### VERIFIED answer patterns
- 0143 = F F T T
- 0147 = T T F F
- 0150 = T F F F
- 0154 = F T F T — visual required
- 0163 = T T F F — visual required
- 0165 = F T T F
- 0170 = T T F F — visual required
- 0174 = F F T T

### Source-answer conflict
- 0159 (test 36, question 1), item a: the source table marks TRUE, but its detailed solution gives the derivative only on `(-∞,1) ∪ (4,+∞)`, while the statement includes endpoints `1` and `4`, where the displayed derivative denominator is zero. Keep HOLD; do not assign a trusted answer to item a.

### Rejected from the current derivative dataset
- 0144: spatial-geometry sphere problem; preserve for geometry/broader exam routing.
- 0145: solution-section reprint of 0144; also keep OUT_OF_SCOPE because the current validator forbids a duplicate target that is itself rejected.
- 0155 -> duplicate of 0154.
- 0175 -> duplicate of 0174.

### Special provenance case
- 0163 was structurally extracted from solution page 708. The canonical question is on PDF pages 700–701 and the explicit solution is on pages 708–709. There is no separate structural candidate for the original occurrence, so 0163 is the canonical reviewed group for this snapshot.

Codex must integrate this reviewed bundle only. It must not access Drive/PDF or recompute answers.
