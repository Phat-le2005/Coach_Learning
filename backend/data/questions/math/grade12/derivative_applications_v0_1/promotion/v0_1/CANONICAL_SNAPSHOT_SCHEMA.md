# Canonical QuestionGroup snapshot schema v0.1

This is an **internal canonical snapshot contract**, not a production DB seed.

For each `canonical_snapshot_ready=true` promotion record, Codex materializes one object:

```json
{
  "external_group_key": "M12_DERIV_GROUP_0024",
  "subject_code": "MATH12",
  "curriculum_version_code": "GDPT2018_2018",
  "group_type": "TRUE_FALSE_FOUR",
  "scoring_policy": "MOET_2025_TRUE_FALSE",
  "content": "<reviewed_group_context>",
  "source": {
    "source_code": "...",
    "effective_subsource_code": "...",
    "candidate_extraction_page": 0,
    "source_evidence_id": "...",
    "review_batch": "batch_001"
  },
  "visual_asset_id": "M12_DERIV_ASSET_0024_V1",
  "children": [
    {
      "external_question_key": "M12_DERIV_GROUP_0024:a",
      "label": "a",
      "order_index": 0,
      "question_type": "TRUE_FALSE",
      "content": "<reviewed_content>",
      "correct_answer": "TRUE",
      "problem_types": [],
      "concepts": [],
      "learning_outcomes": [],
      "taxonomy_basis": "COACH_LEARNING_DERIVED"
    }
  ],
  "production_release_eligible": false
}
```

Rules:
- Exactly four children, labels `a,b,c,d`, indexes `0..3`.
- Copy reviewed text/answers/taxonomy exactly; do not recompute.
- No HOLD or REJECTED group may appear.
- `0012` must not appear until an authentic source visual is found and reviewed.
- Do not include `difficulty`, `exam_weight`, `cognitive_level`, or `explanation` until a reviewed deterministic policy supplies them.
- Do not create DB UUIDs in this snapshot.
- Do not set existing `group_review/*/promotion_ready=true`.
