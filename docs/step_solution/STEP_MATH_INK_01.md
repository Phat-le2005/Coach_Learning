# STEP-MATH-INK-01 — Efficient page-scoped handwriting storage

This is a backend storage foundation (not a finished handwriting workspace or OCR service).

- Every ink document belongs to exactly one Math Solution Attempt; existing student ownership and assignment deadlines apply.
- No GET creates a database row. Empty document revision is 0; first save produces revision 1.
- The client writes one complete **page** at a time with expected_document_revision and client_action_id. Pages are capped at 30, 400 strokes, 15,000 points and 256 KiB uncompressed. zlib level 6 compresses each page; each page is separately addressable.
- The server locks the parent Attempt for writes, rejects stale revisions, and journals idempotent write actions. A retry with the same action ID and identical payload returns its original result.
- Read pages lazily. Frontend should batch pen strokes, autosave every 2–5 seconds after activity, and persist unsent work to IndexedDB; IndexedDB does **not** replace the backend.
- Do not call OCR while the pen is moving. Do not convert raw ink into SolutionStep or Mastery evidence automatically.
- Page-level full replacement is intentionally simpler than operation-based partial sync; future scale work may move compressed page blobs into object storage without changing ownership.
- Monitoring targets: payload bytes, server write frequency, page counts, WAL/TOAST growth, 409 conflicts and autosave success latency.
- Follow-up: canvas frontend, browser cache reconciliation, lossless export, OCR selection and verified step comparison.

Security: current user is derived from bearer token, not request payload; another student's attempt resolves as 404. In-progress attempts are writable; submitted/expired assignments are read only.


## Draft PR release blockers
- Regenerate \`backend/contracts/openapi-v2.json\` and \`backend/contracts/openapi-v2.sha256\` using existing deterministic exporter; update exact-route-count assertions in both v2 suites. New ink endpoints are registered but the frozen snapshot has **not** been regenerated; v2 contract CI is expected to fail.
- Run PostgreSQL Alembic upgrade/downgrade, concurrency race tests and complete backend regression. These have **not** been run in this environment.
- Validate page deletion semantics, document-wide quotas and long-term operation-journal retention before production rollout.
- Implement typed frontend canvas and offline IndexedDB reconciliation as a separate reviewed increment. This PR contains **no working browser canvas**.
