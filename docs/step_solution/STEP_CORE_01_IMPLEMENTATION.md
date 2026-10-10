# STEP-CORE-01 — Solution lifecycle service (draft PR)

**Scope:** Persistence only, no student-facing API yet. Requires STEP-ARCH-00 / STEP-ARCH-01 PRs.

- `MathSolutionService.create` validates authenticated StudentProfile owner, APPROVED canonical question or exact authorized teacher PDF snapshot, active practice session or published classroom assignment, academic subject, enrollment and optionally APPROVED source-matched rubric.
- `add_step`, `update_step`, `reorder_steps`, `delete_step`, `restore_step`, `rollback_step`, `submit` require `expected_attempt_revision` and stable UUID `client_action_id`, with attempt-level row lock and operation journal written in same DB transaction.
- `reorder_steps` first moves to high positive indexes, flushes, then dense 1..N; does not use invalid DEFERRABLE partial indexes or negative indices.
- Revisions snapshot LaTeX/explanation and structured math artifact per step. Post-submit writes are blocked. Retrieval and revision history check ownership.
- **No EvaluationDecision, AI grading, Mastery, or LearningEvidence writes are implemented here.**
- Migration and integration tests must run against disposable PostgreSQL before merging. A successful syntax/CI check does not replace live DB checks.
- Multiple versions of the same canonical classroom question are intentionally rejected/reused. Self-practice attempts may be repeated with new idempotency keys and practice sessions.
- Future versioned API must implement rate limits, validation, server response redaction, draft retention policies and concurrent-session tests.
