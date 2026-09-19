# Mastery Engine

The Mastery Engine consumes evaluated `QuestionAttempt` evidence in the same transaction that records the answer. It persists independent leaf projections for concepts and problem types and derives curriculum aggregates at read time.

## Source of truth

- `student_concept_mastery` is unique by `(student_id, concept_id)`.
- `student_problem_type_mastery` is unique by `(student_id, problem_type_id)`.
- Both tables constrain mastery and confidence to `0.0..1.0`, keep evidence counts, and record practice/update timestamps.
- Topic, Chapter, and Subject mastery are not persisted. They are equal-weight aggregates of active ProblemTypes; an unstarted active ProblemType contributes zero.

Synthetic `student_attempts` do not feed these tables. Only official evaluated `question_attempts` emit mastery evidence.

## Calculation strategy

`MasteryCalculationStrategy.calculate_from_attempt()` receives immutable previous-state, question, mapping, and attempt values. `DeterministicMasteryCalculationStrategy` is the V1 implementation and can be replaced without changing persistence, evidence processing, aggregation, or APIs.

V1 behavior:

- mapping weight scales each Concept or ProblemType update independently;
- a correct difficult question produces stronger positive evidence than a correct easy question;
- an incorrect easy question produces stronger negative evidence than an incorrect difficult question;
- hints reduce evidence and confidence gain but do not convert success into failure;
- response time is recorded but does not affect V1 mastery;
- one update is capped at a rate of `0.30`, and all results are clamped to `0.0..1.0`.

Confidence rises as evidence accumulates for both correct and incorrect answers. It represents certainty in the current estimate, not correctness.

## Derived state

- `NOT_STARTED`: no evidence.
- `LEARNING`: initial evidence that does not meet another threshold.
- `WEAK`: mastery below `0.40` with confidence at least `0.25`.
- `PRACTICING`: at least three attempts or mastery at least `0.55`.
- `MASTERED`: mastery at least `0.80` and confidence at least `0.65`.
- `REVIEW_DUE`: mastered and not practiced for at least 14 days.

State is computed on reads and is not duplicated in the database.

## API

- `GET /students/me/mastery`
- `GET /students/me/mastery/problem-types/{id}`
- `GET /students/me/mastery/concepts/{id}`
- `GET /teacher/students/{student_id}/mastery`

Teacher access requires a `TeacherClassroom` assignment and an `ACTIVE` enrollment for the requested student in the same classroom.

## Commands

```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m pytest -q tests\mastery
```

