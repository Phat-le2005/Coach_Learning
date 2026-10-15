# Math Ink operations

## Retention policy

The Math Ink operation journal stores idempotency metadata, not handwriting strokes. Entries older than seven days may be deleted. The cleanup job does **not** delete ink documents or pages; those remain attached to the solution attempt and are removed through the existing foreign-key cascade when the attempt is deleted.

The retention query is supported by the `ix_math_ink_operations_created_at_id` index from migration `0048_math_ink_retention_index`. The CLI deletes in small transactions, up to 1,000 rows per batch and at most 100 batches (100,000 rows) per run. Run it again if a backlog remains.

## Run once

From the `backend` directory, with the project's virtual environment and database configuration available:

- Windows: `.venv\Scripts\python.exe -m app.math_ink.prune_operations`
- Linux/macOS: `.venv/bin/python -m app.math_ink.prune_operations`

The command reads the same `.env` settings as the backend. Do not put credentials in the command line or commit an environment file.

## Schedule on the deployment host

Do not run the cleanup loop inside FastAPI startup or a web worker: multiple workers could run duplicate jobs, and maintenance should have a separate lifecycle.

### Windows Task Scheduler

Create a daily task on the machine that can reach PostgreSQL:

1. **Program/script:** absolute path to `backend\.venv\Scripts\python.exe`.
2. **Add arguments:** `-m app.math_ink.prune_operations`.
3. **Start in:** absolute path to the `backend` directory.
4. Configure the task to run whether or not a user is logged in, and enable task history.
5. Confirm the task's account can read the protected backend environment and connect to PostgreSQL.

### Linux cron

Run as a dedicated service account on a host that can reach the database. Adjust paths to the deployment:

```cron
17 3 * * * cd /opt/coach-learning/backend && /opt/coach-learning/backend/.venv/bin/python -m app.math_ink.prune_operations >> /var/log/edums/math-ink-retention.log 2>&1
```

Use a database role with only the permissions needed for this task where practical: connection to the target database, schema usage, and `SELECT`/`DELETE` on `math_ink_operations`. Keep the credentials in a protected environment file or secret manager, never in source control.

## Verification checklist

- Apply migrations through `0048_math_ink_retention_index`.
- Run `pytest tests/math_solutions/test_ink_service.py tests/math_solutions/test_ink_postgres_concurrency.py -q` from `backend` with the PostgreSQL test URL set to exercise real database locking.
- Run `python -m app.math_ink.prune_operations` manually once and verify the printed row count and logs.
- Confirm the scheduled task exit code and alert on non-zero exit codes.
