# Hint System

## Architecture

`HintService` is the single application service for progressive practice hints. It validates the authenticated student, the real `PracticeSession` ownership, the active session state, and the current question before returning content.

Hints follow an enforced sequence:

1. `LEVEL_1` recalls a mapped concept or rule.
2. `LEVEL_2` suggests a solution direction.
3. `LEVEL_3` identifies an important step or check.
4. `LEVEL_4` gives a near-solution and is the first level permitted to disclose a final result.

`QuestionHint` stores author-provided hints in the Question Bank. `PracticeQuestionHint` is an immutable record of each hint actually shown in one practice session. A same-level retry returns the stored record, so it does not increment the count or call AI again.

The source order is deterministic:

1. exact predefined hint for the requested level;
2. AI Hint Generator through `AIGateway` only when that predefined level is absent.

AI receives the question, mapped ProblemTypes, Concepts, LearningOutcomes, compact mastery for only those mappings, current attempt state, prior hints, and requested level. Structured output is validated. Referenced curriculum codes must be present in the question mappings. LEVEL_1 through LEVEL_3 reject output marked as revealing the final answer and also pass through a deterministic answer-disclosure check.

Requesting a hint does not create a `QuestionAttempt` and does not update Mastery. When the answer is submitted, `PracticeService` reads the persisted hint history and puts the resulting `hint_count` on the attempt before publishing Mastery evidence.

## API

`POST /practice/questions/{question_id}/hint`

Request:

```json
{
  "practice_session_id": "uuid",
  "current_hint_level": "LEVEL_1"
}
```

`current_hint_level` is the level being requested. Requests must start at `LEVEL_1` and advance one level at a time. Repeating an already issued level is idempotent.

Response includes `hint_level`, server-calculated `hint_count`, `hint_source` (`PREDEFINED` or `AI`), content, and creation time.

Question create/patch payloads also accept up to four unique predefined hints:

```json
{
  "hints": [
    {"hint_level": "LEVEL_1", "content": "Recall the relevant rule."},
    {"hint_level": "LEVEL_2", "content": "Transform the expression first."}
  ]
}
```

## Migration

Revision `0023_hint_system` creates:

- `question_hints`;
- `practice_question_hints`;
- uniqueness, progression-count, ownership, and lookup constraints/indexes.

Run:

```powershell
cd backend
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The current migration chain includes RAG revision `0021`, which requires the PostgreSQL `pgvector` extension to be installed on the database server.

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q tests\hints
```

The suite covers predefined priority, AI fallback, curriculum whitelist validation, progressive disclosure, idempotency, real session ownership, Question Bank hint validation, Mastery isolation, server-side attempt hint counts, API behavior, and migration downgrade/upgrade.
