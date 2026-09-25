# DATA-MATH12-006 — QuestionGroup structural staging

This directory is generated deterministically from the effective reviewed question
staging view. It is an auditable structural split only and is not production seed data.

- Parent ProblemType, Concept, and LearningOutcome mappings are retained only as source
  provenance. Child taxonomy remains `REVIEW_REQUIRED`.
- Child TRUE/FALSE answers are deliberately unset and remain `UNREVIEWED`.
- Structural holds require source-page review and are not emitted as valid groups.
- No record in this directory is production-promotable without a separate academic
  review and promotion workflow.
