# Misconception Domain

## Architecture

The domain separates the global misconception taxonomy from per-student state:

- `MisconceptionDefinition` describes one stable misconception, primarily linked to a `Concept` and optionally narrowed to a `ProblemType`.
- `StudentMisconception` stores a student's confidence, occurrence count, lifecycle status, and detection timestamps for one definition.

The composite key `(student_id, misconception_definition_id)` prevents duplicate state rows. Confidence is constrained to `0.0..1.0`. Timestamp and `RESOLVED` consistency are enforced by database constraints.

`MisconceptionService` provides deterministic operations:

- `record_evidence`
- `increase_confidence`
- `confirm_if_threshold`
- `resolve`

The default policy adds `0.35` confidence per explicit evidence, requires confidence `>= 0.65`, and requires at least two occurrences. Even evidence with strength `1.0` remains `SUSPECTED` on its first occurrence. This prevents one wrong answer from becoming a persistent confirmed misconception.

The service does not classify arbitrary wrong answers. A deterministic rule or reviewed caller must first select the relevant `MisconceptionDefinition`, then call `record_evidence`. No LLM is used.

Resolved misconceptions are excluded from Digital Twin and Tutor context. Later evidence can reopen a resolved state as `SUSPECTED`; evidence dated before the resolution is rejected as stale.

## Grade 12 Mathematics taxonomy

`data/seed/misconceptions.py` contains stable taxonomy records for derivative signs, parameter inequalities, extrema, logarithms, integrals, probability, vectors, Oxyz, graph reading, and careless derivative calculations.

Every definition uses:

```python
stable_id("misconception-definition", definition.code)
```

`SeedService` validates that every referenced Concept and optional ProblemType exists. For ProblemType-specific definitions, it also validates the canonical ProblemType-to-Concept mapping. Re-running the seed reconciles mutable text and does not create duplicates.

## Migration

Revision `0024_misconception_domain` creates:

- `misconception_definitions`
- `student_misconceptions`

Run after PostgreSQL has the `pgvector` extension required by the earlier RAG migration:

```powershell
cd backend
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q tests\misconceptions
```

Coverage includes single-evidence protection, confidence thresholds, repeated evidence, bounds, resolution, stale evidence, recurrence, inactive definitions, stable seed identifiers, seed idempotency, migration downgrade/upgrade, Digital Twin projection, and Tutor context projection.
