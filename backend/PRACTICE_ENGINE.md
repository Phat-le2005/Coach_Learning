# Practice Engine

The Practice Engine records student-owned sessions and immutable question attempts. It uses the existing global curriculum and Question Bank; it does not create student knowledge graphs, mastery values, or recommendations.

## Persistence

- `practice_sessions` stores the student, subject, type, lifecycle status, and timestamps.
- `practice_session_problem_types` and `practice_session_concepts` persist optional selection scope.
- `question_attempts` stores the exact Question reference, answer, deterministic result, timing, hints, attempt order, and evaluation state.
- A composite foreign key requires an attempt's `student_id` to match its session owner. Unique constraints prevent a question or attempt number from appearing twice in one session.

Question versioning does not exist in the current Question Bank, so attempts reference `questions.id` directly. A version column was intentionally not introduced.

## Selection and evaluation

Selection is deterministic and restricted to `APPROVED` questions in the session subject. A selectable question must have at least one `QuestionProblemType`, `QuestionConcept`, and `QuestionLearningOutcome` mapping. When a session specifies problem types or concepts, a question must match every specified filter dimension.

`AnswerEvaluationService` evaluates:

- multiple choice by normalized option label;
- true/false by normalized `TRUE` or `FALSE`;
- short answer by Unicode NFKC, case-folded, whitespace-normalized exact comparison;
- open response as `NEEDS_EVALUATION` with no score.

The service emits `AttemptEvaluatedEvidence` through `AttemptEvidencePublisher` after an objective answer is evaluated. The publisher runs inside the same database transaction; an exception rolls back the attempt. The default publisher is a no-op extension point for a future Mastery Engine.

## API

- `POST /practice/sessions`
- `GET /practice/sessions/{id}`
- `GET /practice/sessions/{id}/next-question`
- `POST /practice/sessions/{id}/answer`

All routes require `STUDENT`. Ownership comes from the authenticated user's `StudentProfile`; request bodies cannot set `student_id`. Next-question responses omit `correct_answer` and `explanation`.

## Commands

```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m pytest -q tests\practice
```

