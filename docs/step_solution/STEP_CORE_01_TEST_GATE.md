## STEP-CORE-01 — Remaining required integration verification

These tests do **not** substitute for a running PostgreSQL database.

Mandatory before merge:
1. Alembic upgrade and downgrade 0046 in disposable PostgreSQL, checking metadata and all 10 tables.
2. Real user/student/teacher fixtures: IDOR cross-student and cross-classroom, active enrollment, teacher material snapshot matching, and canonical assigned question matching.
3. Add/update/rollback/delete/restore/reorder/submit with revision histories and immutable artifact snapshots.
4. Transaction concurrency (two tabs) with row locks, stale attempt revision 409, repeated client action UUID, and same UUID with different content 409.
5. Failed mutating operations must rollback both the operation journal and steps.
6. After submit, all mutating operations reject; no LearningEvidenceEvent/Mastery rows are created.
7. API-V1-FREEZE checks unchanged. API v2 not yet exposed.

Do not merge PRs #3/#4 or this PR solely on static smoke tests.
