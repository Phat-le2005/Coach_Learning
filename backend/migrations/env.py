from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.base import Base
from app.database import models as _models  # noqa: F401

# Import future module models here so their tables enter Base.metadata.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        get_settings().database_url,
        poolclass=pool.NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


configure_logging()
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
