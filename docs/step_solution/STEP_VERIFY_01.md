# STEP-VERIFY-01 — Verification PR

Goal: run existing frozen-v1 checker and STEP migration/lifecycle tests in isolated CI PostgreSQL.

### Constraints and honest status
- Local container lacks PostgreSQL binaries and a reachable database, so **no local PostgreSQL execution** is asserted.
- GitHub Actions workflow runs a disposable pgvector PostgreSQL 16 instance; credentials are CI-only test strings.
- SQLite tests use the existing test schema fixture and no production data.
- Full suite pass and concurrency race tests are **not yet demonstrated**. Keep PR in draft until CI and migration roundtrip are green.
- Concurrent writers, source ownership cross-classroom and full downgrade tests are required before release. The PostgreSQL fixture creates isolated schema but does not itself run a downgrade; expand a separate disposable run for downgrade coverage.
