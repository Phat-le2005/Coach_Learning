# DATA-MATH12-007 — Provincial QuestionGroup academic review v0.1

This bundle is the reviewed data input for Codex integration. Codex should **not** access Google Drive or re-read the full PDF.

## Baseline
- Repo commit: `41de2ae9aaa58ac1ffbc29a9304d9216dc270efb`
- Source: `loi-giai-chi-tiet-de-thi-thu-tot-nghiep-thpt-2025-mon-toan-cua-cac-so-gddt.pdf`
- Drive file ID: `1RK3hOLaqhf2ZXDo_R1hJu2IwkYzZbvlP`
- Source PDF SHA-256: `d3f2158ee028431e01b2f30f7e446d66d75e364c27d49c53f3e09c193325b7e0`
- Raw candidate SHA-256: `b627a458e0b18c0a4e0733e18864e0bd83165f94894a7d690e4fc1313f3ed4d5`

## Review results
- Target groups: 13
- VERIFIED: 8
- HOLD: 0
- REJECTED: 5
  - duplicate solution reprints: 3
  - out of derivative-applications scope: 2
- VERIFIED child statements: 32
- Source-backed child answers: 32
- Visual asset still required: 2 groups (`0012`, `0024`)
- Production-ready/imported: 0

## Canonical source-backed answer patterns
- 0012: T F F T
- 0019: T F F T
- 0024: F T T T
- 0031: F T T F
- 0035: T F T F
- 0041: T F T T
- 0047: T T F F
- 0052: T F T T

## Rejections
- 0021 -> duplicate of 0019 (solution reprint)
- 0026 -> duplicate of 0024 (solution reprint)
- 0053 -> duplicate of 0052 (solution reprint)
- 0044 -> logarithm content, out of current derivative dataset
- 0055 -> logarithm content, out of current derivative dataset

## Important
`verified_groups.json` includes normalized source content, source-backed TRUE/FALSE answers, and child taxonomy mappings. The taxonomy mappings are explicitly `COACH_LEARNING_DERIVED`.

Do not mutate DATA-MATH12-006 artifacts or raw staging. Apply corrections as review overlays only.
