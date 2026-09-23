# DATA-MATH12-002 — Derivative applications taxonomy

Scope: `Ứng dụng đạo hàm để khảo sát và vẽ đồ thị của hàm số`.

This directory is a **staging/review candidate**, not the canonical imported dataset yet.

## Provenance boundary

- `official_learning_outcomes.json`: normalized from the official Grade 12 Mathematics curriculum.
- `learning_outcomes.json`: import-compatible representation of the same source-backed outcomes.
- `topics.json`, `problem_types.json`, `concepts.json`, `concept_relations.json`,
  `problem_type_concepts.json`: Coach Learning derived taxonomy.
- `default_difficulty` and concept `weight` values are initial expert estimates, not Ministry data
  and not empirical student statistics.

## Official area covered

1. Tính đơn điệu của hàm số.
2. Cực trị as required within the monotonicity/graph outcomes.
3. Giá trị lớn nhất, giá trị nhỏ nhất.
4. Tiệm cận, khảo sát và vẽ đồ thị.
5. Ứng dụng đạo hàm vào vấn đề thực tiễn.

## Review gate before canonical merge

A math teacher/domain reviewer should review:

- ProblemType boundaries.
- Concept granularity.
- Prerequisite direction.
- Concept weights.
- Initial difficulty.
- Mapping from ProblemTypes to official learning outcomes.

Do not set the main curriculum `verified_at` merely because the JSON validates.
