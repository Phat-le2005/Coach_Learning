# OCR → Evaluation: Integration readiness (2026-11-01)

## Verified baseline

- PR3-A/B/C and E2E remediation #28 are merged in main. Review produces human-approved `SolutionStep` and sequential idempotent ADD_STEP mutations.
- Frontend `handleSubmitSolution` sends a separate `submitMathAttempt`, whose backend `MathSolutionService.submit` only transitions the attempt to `SUBMITTED`; it does **not** call `MathEvaluatorService.evaluate_attempt`.
- The existing UI then optionally starts AI Review for `OPEN_RESPONSE`. AI Review is advisory; it is **not** an equivalent substitute for deterministic rubric grading.
- `MathEvaluatorService.evaluate_attempt` exists, but requires a pinned approved rubric, a verified one-variable polynomial target, supported step content, and refuses final scores when any step is `UNDETERMINED` or `NEEDS_REVIEW`. Successful evaluation can publish learning evidence and update mastery atomically.

## Safety fix in this branch

Before creating any SUBMIT mutation, the frontend reads the IndexedDB OCR batch journal **inside the same Web Lock used for batch mutations**. PREPARED/PAUSED, corrupted or inaccessible journals and unavailable Web Locks fail closed. COMPLETE/ABANDONED or absent journals are allowed, subject to the existing backend revision check. React UI state alone is insufficient, particularly just after F5 or in another tab.

No new endpoint, evaluator change, rubric mutation, or auto-scoring side effect is introduced in this change.

## Integration decision for Phát + Tri

Do not automatically run deterministic scoring on every OCR submission. First agree on:

1. **Activation:** explicit teacher-controlled/approved rubric or an eligibility/readiness endpoint? `SUBMIT` is not equivalent to `EVALUATE`.
2. **Ownership and permissions:** who can request a score, for which attempt and when? Keep submitted attempts immutable; verify student/teacher authorization on the server.
3. **Outcome contract:** persist and expose `EVALUATED`, `GRADING_REVIEW_REQUIRED`, `GRADING_TARGET_UNSUPPORTED`, `GRADING_RUBRIC_REQUIRED`, and retry/in-progress states without treating unknown as incorrect.
4. **Idempotency and side effects:** a repeated evaluation must not double-publish LearningEvidence or double-update mastery; all score/evidence mutations remain in one backend transaction.
5. **Human oversight:** separate OCR transcription approval (is the recognized formula correct?) from mathematical validity (does the transformed step follow?). Do not use an OCR confidence score as CAS confidence.

## Required acceptance matrix (isolated PostgreSQL)

| Case | Expected outcome |
| --- | --- |
| Correct 3–5 step polynomial solution with approved rubric | Stable persisted steps, deterministic result, exactly one evaluation decision and one evidence event |
| Intentionally incorrect derivative or root | `INVALID` or rubric-supported incorrect outcome, not silent acceptance |
| Out-of-scope transcendental/non-polynomial target | `GRADING_TARGET_UNSUPPORTED`; no score or evidence |
| A step unsupported by deterministic rules | `GRADING_REVIEW_REQUIRED`; no fabricated score/evidence |
| Missing/unapproved rubric | Explicit rubric error; no mutation |
| Network timeout and repeat evaluation request | Existing decision reused, no double evidence |
| Two tabs attempting submit while OCR batch PAUSED | Submission blocked, batch replay remains recoverable |
| Unauthorized student/teacher | Appropriate 401/403; no cross-student data disclosure |

Collect real ink plus ground-truth transcripts for 30 independent solutions (5–10 writers) and compare OCR-assisted versus manual entry: segmentation F1, LaTeX edit distance, StepKind coverage/accuracy, correction time, end-to-end exact step match and p95 latency. These are proposed sample sizes and metrics, not measured accuracy.

**Next PR after this safety gate:** a contract/integration test for one polynomial exercise through `SolutionStep` → `MathEvaluatorService` → teacher/human feedback, authored with the backend owner. No scoring endpoint should be exposed to students before authorization and side-effect semantics are agreed.
