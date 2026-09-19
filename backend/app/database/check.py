"""Run `python -m app.database.check` to verify the configured local database."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import configure_logging
from app.database.session import dispose_engine, get_engine

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    try:
        with get_engine().connect() as connection:
            if connection.execute(text("SELECT 1")).scalar_one() != 1:
                logger.error("PostgreSQL connectivity check returned an unexpected result")
                return 1
        logger.info("PostgreSQL connection successful")
        return 0
    except SQLAlchemyError as exc:
        logger.error(
            "PostgreSQL connection failed (%s). Check the local service and backend/.env.",
            type(exc).__name__,
        )
        return 1
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
