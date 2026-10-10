# STEP-ARCH-00 — Final Schema & Evidence Safety Gate
**Status:** Design approved in principle, **NOT APPROVED for production migration** until real PostgreSQL/integration checks pass. Baseline `afa40f5`.

## 1. PostgreSQL
`CREATE UNIQUE INDEX uq_math_solution_step_active_index ON math_solution_steps(attempt_id,step_index) WHERE is_deleted=FALSE;` uses immediate uniqueness; partial unique index cannot be DEFERRABLE. Keep `CHECK(step_index>=1)`. For reorder, lock attempt `FOR UPDATE`, check authorized actor + expected revision **under lock**, validate full active-set permutation, update all rows to unique temporary **positive** indices beyond existing maximum, flush, then update to final 1..N, flush, append immutable step revisions + idempotency journal and increment attempt revision in same transaction. Rollback all on error. Soft-delete excludes row from unique index; restore reassigns free index. Test using [SQL probe](sql/partial_index_reorder_probe.sql).

## 2. Mutation idempotency — 10 tables
Original eight tables + `math_evaluation_overrides` + new `math_solution_operations` = **10**. Operation journal: id UUID PK, attempt_id UUID FK, actor_user_id UUID FK, client_action_id UUID, operation_type, request_hash CHAR(64), response_snapshot JSONB, result_attempt_revision, created_at, unique(attempt_id,client_action_id). Every mutation after attempt creation records journal atomically. Same key and identical payload returns saved response without mutation; same key and different hash returns 409. Attempt creation uses unique per-student key.

## 3. Canonical / teacher-PDF source ownership
Canonical self-practice uses approved Question. Canonical classroom source links `assignment_student_question_id` to exact Question and `student_assignment_id`. PDF source links `student_assignment_material_item_id` to immutable AssignmentMaterialItem snapshot; verify parent Assignment and student/classroom. All read and write paths enforce authenticated student/teacher access server-side; do not trust client foreign keys. Freeze rubric ID/version on assignment/attempt and keep correct answers/rubrics hidden when required. Composite FK where useful, service validation in same transaction.

## 4. Correction must not add a learning attempt
A completed actual SolutionAttempt produces at most one LearningEvidenceEvent, no events for drafts/autosaves. Real verification, adaptive-repair and review attempts are separate. Teacher grade correction appends `math_evaluation_overrides` only; **never** publish a second LearningEvidenceEvent for the same learning attempt. Latest authorized override defines *effective* score and correctness of original event. Under student lock, deterministically replay/rebuild whole effective student event history (or provable snapshot) in stable order with original weights/difficulty/hints and unchanged event cardinality, then reconcile ReviewSchedule. Fail closed (PENDING correction) until projection and schedule reconciliation safe. Test 0.40 → 1.00 → 0.70, retry idempotency, attempt_count remains 1; one independent attempt adds exactly one. SQLAlchemy ORM immutability hooks are not a PostgreSQL trigger; review DB write privileges / trigger.

## 5. API v2 & immutable v1
Mount FastAPI sub-app at `/api/v2`, child endpoints use relative paths. Keep root OpenAPI derived from actual `create_app(settings)`; neither edit v1 schema file nor checksum. **Shared schema/enum changes** (e.g. `MATH_SOLUTION_EVALUATION`) can still alter v1 schema despite mount; run exact v1 contract check and isolate v2/internal DTO if drift. Test auth, CORS, root/v2 OpenAPI independence, no rubric/answer leakage.

## 6. Data and review gates
Derivative staging remains rights-blocked. 18–20 in-house questions are targeted, not confirmed approved inventory; authorship, licensing, independent academic review and signoff need real records. Do not claim ownership of a nonexistent/unverified company. Candidate misconception `SIGN_TABLE_QUADRATIC_RULE_INVERTED` stays out of seeds until domain review; `DERIVATIVE_ARITHMETIC_SLIP` is not a label for wrong calculus rules.

## Status / proof
The bundled SQL probe has NOT been run on a real PostgreSQL instance in this environment. SQLAlchemy PostgreSQL dialect can compile the non-deferrable partial unique index, which is **not** a substitute for transactional Postgres tests. No runtime service/migration/API changes are included. STEP-ARCH-01 may proceed only in test databases after Postgres probe, concurrency, ownership, evidence correction and v1 contract checks pass.
