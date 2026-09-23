Implement DATA-MATH12-004 staging support in Phat-le2005/Coach_Learning.

Use the attached staging data. Do not invent or modify question content.

Tasks:
1. Add the staging directory under:
   backend/data/questions/math/grade12/derivative_applications_v0_1/staging/
2. Add a non-production validation/report command for candidate_questions.json.
3. Validate ProblemType, Concept and LearningOutcome codes against the canonical/staging curriculum taxonomy.
4. Reject promotion/import when status != VERIFIED.
5. Reject TRUE_FALSE_GROUP promotion until a proper QuestionGroup model exists.
6. Produce coverage report by ProblemType and question type.
7. Add exact-fingerprint duplicate reporting.
8. Preserve source_code, subsource_code, page and question_number as provenance metadata.
9. Do not create migrations in this task.
10. Do not mark any candidate VERIFIED.
11. Do not change mastery, recommendation or digital-twin logic.
12. Add tests.

Acceptance:
- Staging validation passes.
- Existing backend tests remain green.
- No unreviewed question can enter the production QuestionImportService path.
- The command reports the six current coverage gaps.
