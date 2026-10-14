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


## Final hardening (2026-10-14)

- OpenAPI V2 contract regenerated and verified on previous CI-green HEAD `7b6b831`.
- HTTP ink page PUT body bounded to 384 KiB by ASGI middleware before JSON parsing, including requests without Content-Length.
- Repeated saves of identical page content create an idempotent action record but do not rewrite the compressed page or increment document revision.
- Journal retention: seven days. A bounded batch (100 expired actions) is pruned when an existing document is saved. Run `python -m app.math_ink.prune_operations` daily to cover dormant documents; each transaction deletes at most 1000, up to 100 batches per invocation.
- After retention, a stale action ID is no longer replayable. Callers must use the latest document revision; stale writes remain protected by optimistic concurrency.
- Server-side page limits remain 30 pages maximum indexed 0–29, 400 strokes, 15,000 points, and 256 KiB uncompressed per page.
- The current implementation is a backend foundation; canvas drawing, IndexedDB recovery, OCR, and page-deletion UX are separate increments.

## Outstanding acceptance gates

- Verify new hardening changes through PR CI on the latest commit.
- Add and run real PostgreSQL simultaneous-writer regression tests for Math Ink (not only the existing Math Solutions suite).
- Exercise oversized body without Content-Length, stale/no-op saves, retention and idempotency on SQLite and PostgreSQL.
- Finalize observability, retention scheduling and production deployment quotas before publishing as production-ready.
