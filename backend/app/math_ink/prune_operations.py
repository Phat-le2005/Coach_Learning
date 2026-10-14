"""Bound the autosave idempotency journal with a safe, explicit retention job.

Run `python -m app.math_ink.prune_operations` from the backend environment
daily. Expired action replay returns a revision conflict instead of silently
overwriting newer work.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.math_ink.models import MathInkOperation

INK_OPERATION_RETENTION_DAYS = 7
DEFAULT_PRUNE_BATCH_SIZE = 1000


def prune_expired_operations(
    session: Session,
    *,
    now: datetime | None = None,
    batch_size: int = DEFAULT_PRUNE_BATCH_SIZE,
    document_id=None,
) -> int:
    """Delete at most one small batch, leaving transaction control to caller."""
    if not 1 <= batch_size <= 5000:
        raise ValueError("batch_size must be between 1 and 5000")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=INK_OPERATION_RETENTION_DAYS)
    query = select(MathInkOperation.id).where(MathInkOperation.created_at < cutoff)
    if document_id is not None:
        query = query.where(MathInkOperation.document_id == document_id)
    ids = session.scalars(query.order_by(MathInkOperation.created_at, MathInkOperation.id).limit(batch_size)).all()
    if ids:
        session.execute(delete(MathInkOperation).where(MathInkOperation.id.in_(ids)))
    return len(ids)


def main() -> None:
    from app.database.session import get_session_factory

    total = 0
    # Each transaction is bounded to limit locks and WAL spikes.
    with get_session_factory()() as session:
        for _ in range(100):
            try:
                removed = prune_expired_operations(session)
                session.commit()
            except Exception:
                session.rollback()
                raise
            total += removed
            if removed < DEFAULT_PRUNE_BATCH_SIZE:
                break
    print(f"Expired Math Ink operations pruned: {total}")


if __name__ == "__main__":
    main()
